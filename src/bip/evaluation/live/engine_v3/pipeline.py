"""End-to-end V3 shadow pipeline.

Wires together the components defined in this package:

    LiveMatchState + priors + market_snapshot
        ↓ GSVBuilder
    GameStateVector
        ↓ generate_theses (rule layer)
    List[Thesis]
        ↓ select_markets (MES + family routing) + conditional predictor
    List[MarketCandidate]
        ↓ run_gate (8 no-bet rules)
    List[GateResult]   (allowed + denied; reasons logged)
        ↓ ShadowPick synthesizer
    List[ShadowPick]   (audit-only, never sent to Telegram in Phase 1)

This is **shadow-mode** (sec 7.5 + Phase 2 of sec 10): the output goes
to a log / parquet sink, not to the operator. The whole point is to
let the v3 run alongside the current system for 2-4 weeks and compare
ROIs cohort-against-cohort without risk.

The pipeline is a single class so callers can wire dependencies once
and call ``run(...)`` per fixture-frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from bip.evaluation.live.engine_v3.archetypes import generate_theses
from bip.evaluation.live.engine_v3.conditional_predictor import (
    ConditionalPredictor,
    make_fair_prob_provider,
)
from bip.evaluation.live.engine_v3.pattern_layer import (
    PatternLayer,
    generate_theses_hybrid,
)
from bip.evaluation.live.engine_v3.gsv import (
    CriticalEvent,
    GameStateVector,
    MarketSnapshot,
    PreMatchPriors,
)
from bip.evaluation.live.engine_v3.gsv_builder import GSVBuilder
from bip.evaluation.live.engine_v3.market_selector import (
    MarketCandidate,
    select_markets,
)
from bip.evaluation.live.engine_v3.mispricing_window import (
    MispricingWindowConfig,
    WindowResult,
    classify_gsv,
)
from bip.evaluation.live.engine_v3.no_bet_gate import GateResult, run_gate
from bip.evaluation.live.engine_v3.ood_detector import OODDetector
from bip.evaluation.live.engine_v3.thesis import Thesis
from bip.evaluation.live.match_state import LiveMatchState

# Phase-3 surfaces. Imported lazily-as-types to keep Phase-1/2 callers
# (which never wire a promoter) free of any phase3 import overhead.
try:  # pragma: no cover — type-only import path
    from bip.evaluation.live.engine_v3.phase3.tier_promoter import (
        PromotedPick,
        TierDPromoter,
    )
except ImportError:  # pragma: no cover
    PromotedPick = None  # type: ignore[assignment]
    TierDPromoter = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from bip.evaluation.live.engine_v3.drift_monitor import (
        CalibrationDriftMonitor,
    )


@dataclass(frozen=True)
class ShadowPick:
    """The minimal audit-trail entry per allowed candidate.

    Phase 2 will extend this with the predictor's fair_prob CI, the
    operator's Kelly fraction, and the calibrated isotonic bucket."""

    fixture_id: int
    timestamp_utc: datetime
    candidate: MarketCandidate
    full_thesis: Thesis = field(repr=False)


@dataclass(frozen=True)
class PipelineOutput:
    """All outputs of one frame, for audit + telemetry.

    Sec 7.2 requires that **every** rejected candidate be logged with
    its rule number. ``gate_results`` carries that.

    ``promoted_picks`` is populated only when a Phase-3 ``TierDPromoter``
    is wired to the pipeline. Otherwise it stays empty — Phase 1/2
    callers see no behaviour change.
    """

    gsv: GameStateVector
    theses: list[Thesis]
    candidates: list[MarketCandidate]
    gate_results: list[GateResult]
    allowed_picks: list[ShadowPick]
    promoted_picks: list = field(default_factory=list)
    mispricing_window: WindowResult | None = None


class V3Pipeline:
    """One pipeline instance per process. Holds a stateful GSVBuilder
    (for ``state_version``) and reusable components."""

    def __init__(
        self,
        *,
        gsv_builder: GSVBuilder | None = None,
        conditional_predictor: ConditionalPredictor | None = None,
        tier_promoter: "TierDPromoter | None" = None,
        ood_detector: OODDetector | None = None,
        pattern_layer: PatternLayer | None = None,
        mispricing_window_cfg: MispricingWindowConfig | None = None,
        drift_monitor: "CalibrationDriftMonitor | None" = None,
        mes_threshold: float = 0.6,
        target_stake: float = 100.0,
        line_max_age_sec: float = 300.0,
        commentary_required: bool = False,
        uncertainty_band: float = 0.08,
        top_k_per_thesis: int = 3,
    ) -> None:
        self.gsv_builder = gsv_builder or GSVBuilder()
        self.predictor = conditional_predictor or ConditionalPredictor.default()
        self.tier_promoter = tier_promoter
        self.ood_detector = ood_detector
        self.pattern_layer = pattern_layer
        self.mispricing_window_cfg = mispricing_window_cfg or MispricingWindowConfig()
        self.drift_monitor = drift_monitor
        self.mes_threshold = mes_threshold
        self.target_stake = target_stake
        self.line_max_age_sec = line_max_age_sec
        self.commentary_required = commentary_required
        self.uncertainty_band = uncertainty_band
        self.top_k_per_thesis = top_k_per_thesis

    def run(
        self,
        state: LiveMatchState,
        *,
        priors: PreMatchPriors,
        markets: MarketSnapshot,
        dominant_team_id: int | None = None,
        ref_card_rate_prior: float = 0.0,
        last_critical_event: CriticalEvent | None = None,
        last_critical_event_age_sec: float | None = None,
        now_utc: datetime | None = None,
    ) -> PipelineOutput:
        """Run one frame end-to-end."""
        gsv = self.gsv_builder.build(
            state,
            priors=priors,
            markets=markets,
            dominant_team_id=dominant_team_id,
            ref_card_rate_prior=ref_card_rate_prior,
            last_critical_event=last_critical_event,
            last_critical_event_age_sec=last_critical_event_age_sec,
            now_utc=now_utc,
        )
        if self.pattern_layer is not None and self.pattern_layer.is_fitted:
            theses = generate_theses_hybrid(
                gsv,
                pattern_layer=self.pattern_layer,
                ood_detector=self.ood_detector,
            )
        else:
            theses = generate_theses(gsv)
        provider = make_fair_prob_provider(self.predictor)
        candidates = select_markets(
            theses, gsv, provider,
            top_k=self.top_k_per_thesis,
            target_stake=self.target_stake,
            mes_threshold=self.mes_threshold,
        )
        gate_results = run_gate(
            theses, candidates, gsv,
            mes_threshold=self.mes_threshold,
            line_max_age_sec=self.line_max_age_sec,
            commentary_required=self.commentary_required,
            uncertainty_band=self.uncertainty_band,
            ood_detector=self.ood_detector,
            mispricing_window_cfg=self.mispricing_window_cfg,
            drift_monitor=self.drift_monitor,
        )
        window = classify_gsv(gsv, self.mispricing_window_cfg)
        allowed = [
            ShadowPick(
                fixture_id=gsv.fixture_id,
                timestamp_utc=gsv.timestamp_utc,
                candidate=r.candidate,
                full_thesis=r.candidate.thesis,
            )
            for r in gate_results
            if r.verdict.allowed
        ]
        promoted: list = []
        if self.tier_promoter is not None:
            for r in gate_results:
                if not r.verdict.allowed:
                    continue
                promoted.append(self.tier_promoter.promote(r.candidate, gsv))
        return PipelineOutput(
            gsv=gsv,
            theses=theses,
            candidates=candidates,
            gate_results=gate_results,
            allowed_picks=allowed,
            promoted_picks=promoted,
            mispricing_window=window,
        )


__all__ = ["PipelineOutput", "ShadowPick", "V3Pipeline"]
