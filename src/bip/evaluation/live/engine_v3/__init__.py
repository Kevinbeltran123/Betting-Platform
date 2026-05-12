"""Live Engine v3 — causal-reasoning pipeline.

See ``Papers/LIVE_ENGINE_V3_DESIGN.md`` for the architectural blueprint.

End-to-end surface: GSV primitives, hypothesis layer (12 archetypes),
MES routing, family-specific conditional predictors, 8-rule No-Bet
Gate, line recorder, shadow logger, and the composing ``V3Pipeline``.

Usage::

    from bip.evaluation.live.engine_v3 import V3Pipeline, PreMatchPriors

    pipeline = V3Pipeline()
    out = pipeline.run(live_state, priors=priors, markets=markets)
    for pick in out.allowed_picks:
        log.info("v3 shadow pick: %s", pick)
"""
from bip.evaluation.live.engine_v3.archetypes import generate_theses
from bip.evaluation.live.engine_v3.conditional_predictor import (
    ConditionalPredictor,
    CornersPredictor,
    Goals2HPredictor,
    PredictionPoint,
)
from bip.evaluation.live.engine_v3.gsv import (
    CardsState,
    CornerState,
    CriticalEvent,
    FlowState,
    GameStateVector,
    MarketLine,
    MarketSnapshot,
    NumericalState,
    PreMatchPriors,
    RosterState,
    ScoreState,
    TacticalState,
    TimeState,
    XGState,
)
from bip.evaluation.live.engine_v3.gsv_builder import GSVBuilder
from bip.evaluation.live.engine_v3.line_recorder import LineRecorder
from bip.evaluation.live.engine_v3.market_selector import (
    MarketCandidate,
    family_for_market_id,
    select_markets,
)
from bip.evaluation.live.engine_v3.mes import MESResult, compute_mes
from bip.evaluation.live.engine_v3.no_bet_gate import (
    GateResult,
    NoBetVerdict,
    allowed_candidates,
    run_gate,
)
from bip.evaluation.live.engine_v3.ood_detector import OODDetector, vectorize_gsv
from bip.evaluation.live.engine_v3.pipeline import (
    PipelineOutput,
    ShadowPick,
    V3Pipeline,
)
from bip.evaluation.live.engine_v3.shadow_logger import ShadowLogger
from bip.evaluation.live.engine_v3.thesis import (
    CausalChain,
    CausalStep,
    ConditionalShift,
    GSVPredicate,
    InvalidationTrigger,
    MarketFamily,
    Thesis,
    ThesisArchetype,
    ThesisSource,
    TimeWindow,
)

__all__ = [
    "CardsState",
    "CausalChain",
    "CausalStep",
    "ConditionalPredictor",
    "ConditionalShift",
    "CornerState",
    "CornersPredictor",
    "CriticalEvent",
    "FlowState",
    "GSVBuilder",
    "GSVPredicate",
    "GameStateVector",
    "GateResult",
    "Goals2HPredictor",
    "InvalidationTrigger",
    "LineRecorder",
    "MESResult",
    "MarketCandidate",
    "MarketFamily",
    "MarketLine",
    "MarketSnapshot",
    "NoBetVerdict",
    "NumericalState",
    "OODDetector",
    "PipelineOutput",
    "PreMatchPriors",
    "PredictionPoint",
    "RosterState",
    "ScoreState",
    "ShadowLogger",
    "ShadowPick",
    "TacticalState",
    "Thesis",
    "ThesisArchetype",
    "ThesisSource",
    "TimeState",
    "TimeWindow",
    "V3Pipeline",
    "XGState",
    "allowed_candidates",
    "compute_mes",
    "family_for_market_id",
    "generate_theses",
    "run_gate",
    "select_markets",
    "vectorize_gsv",
]
