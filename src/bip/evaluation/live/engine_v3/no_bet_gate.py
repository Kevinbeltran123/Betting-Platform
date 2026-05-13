"""No-Bet Policy Gate — the 8 hard rules from section 6.

Each rule is a pure ``(candidate, gsv) → NoBetVerdict`` function. The
gate runs them in order; the first failure aborts the candidate with a
reason string. Reasons are persisted to the audit log per sec 7.2.

The most load-bearing rule is **#2 — the Napoli rule**. It is the one
that codifies the structural insight from the design doc: a
``dominant_losing=True`` state is INCOMPATIBLE with Under-direction
theses except via explicit allow-list (``cruise_mode``). This is the
asymmetric guard the current system lacks.

Rules are AND-composed — any failure → no pick. Each failure is logged
with the rule number, the reason, and the (thesis, market) it killed.
"""
from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING

from bip.evaluation.live.engine_v3.gsv import GameStateVector
from bip.evaluation.live.engine_v3.market_selector import MarketCandidate
from bip.evaluation.live.engine_v3.mispricing_window import (
    MispricingWindowConfig,
    WindowResult,
    classify_gsv,
)
from bip.evaluation.live.engine_v3.ood_detector import OODDetector
from bip.evaluation.live.engine_v3.thesis import (
    Thesis,
    UNDER_DIRECTION_ALLOWED_ARCHETYPES,
)

if TYPE_CHECKING:
    from bip.evaluation.live.engine_v3.drift_monitor import (
        CalibrationDriftMonitor,
    )

UNDER_DIRECTIONS = frozenset({"under", "no"})


@dataclass(frozen=True)
class NoBetVerdict:
    """Result of the gate. ``allowed=False`` means the candidate is killed."""

    allowed: bool
    rule_number: int | None = None
    reason: str = ""

    @classmethod
    def ok(cls) -> NoBetVerdict:
        return cls(allowed=True)

    @classmethod
    def deny(cls, rule_number: int, reason: str) -> NoBetVerdict:
        return cls(allowed=False, rule_number=rule_number, reason=reason)


# ──────────────────────────────────────────────────────────────────────
# Rule implementations
# ──────────────────────────────────────────────────────────────────────


def rule_1_thesis_present(theses: list[Thesis]) -> NoBetVerdict:
    """#1 — No-thesis-no-pick: if the rule layer (and pattern/commentary
    layers) produced zero theses, abort. The EV is not evaluated."""
    if not theses:
        return NoBetVerdict.deny(1, "no thesis activated by hypothesis generator")
    return NoBetVerdict.ok()


def rule_2_score_state_inversion(candidate: MarketCandidate, gsv: GameStateVector) -> NoBetVerdict:
    """#2 — Score-state inversion rule (the Napoli rule).

    If ``dominant_losing=True`` AND the candidate direction is in
    ``{under, no}``, abort UNLESS the thesis archetype is in the
    allow-list (cruise_mode, late_collapse_underdog).
    """
    if not gsv.score.dominant_losing:
        return NoBetVerdict.ok()
    if candidate.thesis.prediction.direction not in UNDER_DIRECTIONS:
        return NoBetVerdict.ok()
    if candidate.thesis.archetype in UNDER_DIRECTION_ALLOWED_ARCHETYPES:
        return NoBetVerdict.ok()
    return NoBetVerdict.deny(
        2,
        f"dominant_losing=True + under-direction thesis "
        f"{candidate.thesis.archetype.value} not in allow-list",
    )


def rule_3_critical_event_freshness(gsv: GameStateVector) -> NoBetVerdict:
    """#3 — If the last critical event was <90s ago, abort. State has
    not yet stabilized."""
    age = gsv.last_critical_event_age_sec
    if age is None:
        return NoBetVerdict.ok()
    if age < 90.0:
        return NoBetVerdict.deny(3, f"last critical event {age:.0f}s ago < 90s")
    return NoBetVerdict.ok()


def rule_4_line_freshness(candidate: MarketCandidate, gsv: GameStateVector,
                          max_age_sec: float = 60.0) -> NoBetVerdict:
    """#4 — If the line in question hasn't moved in >60s, abort.

    The (timestamp, side_a, side_b) tuple is read from the line's
    ``last_update_utc`` against the GSV timestamp.
    """
    line = gsv.markets.lines.get(candidate.market_id)
    if line is None or line.last_update_utc is None:
        return NoBetVerdict.deny(4, "no line snapshot")
    age = (gsv.timestamp_utc - line.last_update_utc).total_seconds()
    if age > max_age_sec:
        return NoBetVerdict.deny(4, f"line stale ({age:.0f}s > {max_age_sec:.0f}s)")
    return NoBetVerdict.ok()


def rule_5_thesis_market_mismatch(candidate: MarketCandidate,
                                  threshold: float = 0.6) -> NoBetVerdict:
    """#5 — If MES < threshold, abort. Means valid thesis + no market
    expresses it well. Default to no-bet, NOT to the 3 safe markets."""
    if candidate.mes.score < threshold:
        return NoBetVerdict.deny(
            5, f"MES {candidate.mes.score:.3f} < {threshold:.2f}"
        )
    return NoBetVerdict.ok()


def rule_6_commentary_lag(candidate: MarketCandidate, gsv: GameStateVector,
                          commentary_required: bool = False) -> NoBetVerdict:
    """#6 — If the candidate is derived from a commentary-layer thesis
    AND the commentary parse hasn't completed for the triggering event,
    abort.

    For rule-layer theses, this trivially passes. For Phase 1 the
    commentary layer is not yet wired in production, so ``commentary_required``
    defaults to False.
    """
    if candidate.thesis.source.layer != "commentary":
        return NoBetVerdict.ok()
    if commentary_required and gsv.last_critical_event is None:
        return NoBetVerdict.deny(6, "commentary-derived thesis lacks event anchor")
    return NoBetVerdict.ok()


def rule_7_liquidity_gate(candidate: MarketCandidate) -> NoBetVerdict:
    """#7 — If liquidity_score = 0 (stake cap < 50% of target), abort.

    Hard floor (not multiplicative) so a small-stake market never gets
    routing — they signal stale lines or flagged accounts."""
    if candidate.mes.liquidity_score <= 0.0:
        return NoBetVerdict.deny(7, "liquidity_score=0 — stake cap below half target")
    return NoBetVerdict.ok()


def rule_8_predictive_uncertainty(candidate: MarketCandidate,
                                  uncertainty_band: float = 0.08) -> NoBetVerdict:
    """#8 — If the conditional predictor reports a confidence interval
    wider than book_implied ± 8%, abort.

    The width is currently embedded in the ``mes.conditional_variance``
    factor. We compare against a normalised threshold: a variance
    larger than ``uncertainty_band * 10`` is considered too wide. This
    is a structural placeholder; Phase 2 wires the real CI from the
    predictor."""
    if candidate.mes.conditional_variance > uncertainty_band * 10:
        return NoBetVerdict.deny(
            8,
            f"predictive variance {candidate.mes.conditional_variance:.2f} "
            f"exceeds band {uncertainty_band * 10:.2f}",
        )
    return NoBetVerdict.ok()


def rule_10_mispricing_window(
    candidate: MarketCandidate,
    window: WindowResult,
    cfg: MispricingWindowConfig,
) -> NoBetVerdict:
    """#10 — Mispricing window enforcement (principle #3 of the design doc).

    When the window is COLD (>600s since last critical event) AND the
    base edge is below ``cfg.cold_edge_threshold``, abort. The book has
    had ample time to adjust; persistent small edge in this window is
    model noise, not real mispricing.

    HOT, OPTIMAL, WARM, INDEFINITE windows pass — only COLD with weak
    edge dies here.
    """
    if not window.is_cold:
        return NoBetVerdict.ok()
    edge = candidate.mes.base_edge
    if edge < cfg.cold_edge_threshold:
        return NoBetVerdict.deny(
            10,
            f"COLD window (age {window.age_sec:.0f}s) + edge "
            f"{edge:.3f} < cold-threshold {cfg.cold_edge_threshold:.3f}",
        )
    return NoBetVerdict.ok()


def rule_11_calibration_drift(
    candidate: MarketCandidate,
    gsv: GameStateVector,
    monitor: "CalibrationDriftMonitor | None",
) -> NoBetVerdict:
    """#11 — Calibration drift gate.

    When the ``CalibrationDriftMonitor`` reports the candidate's
    ``(market_family, minute_bucket)`` cell as drifted (KS-test p < α),
    abort the candidate. The motivation comes from the Day-1 → Day-2
    contrafactual analysis (Papers/V3_DAY3_DIAGNOSIS) where calibration
    fitted on Day-1 catastrophically failed on Day-2's cards cohort
    (predicted 0.70 vs actual 0.11). Better to skip drifted cells than
    bet on a model the world is no longer agreeing with.

    Fail-safe:
    - ``monitor=None`` → pass (Phase-1 deployments without the monitor
      unchanged).
    - monitor present but cell not warm (n < min_observations) → pass
      with a structlog note. The cell needs more observations before
      drift can be diagnosed; until then, defer to the other rules.
    - cell warm and drifted → deny.
    """
    if monitor is None:
        return NoBetVerdict.ok()
    family = candidate.family
    status = monitor.status(family, gsv.time.minute)
    if not status.is_warm:
        return NoBetVerdict.ok()
    if status.is_drifted:
        return NoBetVerdict.deny(
            11,
            f"calibration drifted for {status.family}@{status.minute_bucket}: "
            f"expected_wr={status.expected_win_rate:.2f} vs empirical_wr="
            f"{status.empirical_win_rate:.2f} (ks_p={status.ks_p_value:.4f}, "
            f"n={status.n})",
        )
    return NoBetVerdict.ok()


def rule_9_ood_detector(
    gsv: GameStateVector,
    detector: OODDetector | None,
    *,
    threshold: float | None = None,
) -> NoBetVerdict:
    """#9 — Out-of-distribution game state (Risk #2 mitigation).

    When ``detector`` is unfitted or ``None`` the rule passes (fail-safe);
    when fitted and the GSV's Mahalanobis distance from the training
    centroid exceeds the threshold, the candidate is denied with the
    score embedded in the reason so the audit log captures it.
    """
    if detector is None or not detector.is_fitted:
        return NoBetVerdict.ok()
    score = detector.score(gsv)
    cutoff = detector.threshold if threshold is None else threshold
    if score > cutoff:
        return NoBetVerdict.deny(
            9,
            f"OOD game state — Mahalanobis {score:.2f} > threshold {cutoff:.2f} "
            f"(trained on n={detector.n_train})",
        )
    return NoBetVerdict.ok()


# ──────────────────────────────────────────────────────────────────────
# Compose
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateResult:
    candidate: MarketCandidate
    verdict: NoBetVerdict


def run_gate(
    theses: list[Thesis],
    candidates: list[MarketCandidate],
    gsv: GameStateVector,
    *,
    mes_threshold: float = 0.6,
    line_max_age_sec: float = 60.0,
    commentary_required: bool = False,
    uncertainty_band: float = 0.08,
    ood_detector: OODDetector | None = None,
    mispricing_window_cfg: MispricingWindowConfig | None = None,
    drift_monitor: "CalibrationDriftMonitor | None" = None,
) -> list[GateResult]:
    """Run the 10 rules against each candidate.

    Returns one ``GateResult`` per candidate; callers filter by
    ``r.verdict.allowed``. Even denied results are returned (with their
    rule number + reason) so the audit log can capture them — sec 7.2
    requires that "every rejected pick is logged with reason".

    Rule 9 (OOD) is global to the GSV — it would emit the same verdict
    for every candidate at this state — so we short-circuit on it first
    when the detector is fitted and the state is OOD.

    Rule 10 (mispricing window) is per-candidate (it inspects the
    candidate's base_edge against a window-dependent threshold) but
    the window classification itself is GSV-level, computed once.
    """
    # Rule 1 is global (applies once). If no theses, every candidate is denied
    # against rule 1; we short-circuit to one verdict per candidate.
    if not theses:
        return [
            GateResult(candidate=c, verdict=NoBetVerdict.deny(1, "no theses"))
            for c in candidates
        ]
    # Rule 9 is also state-global. If the GSV is OOD, every candidate dies
    # against rule 9 — short-circuit so the audit log shows the real reason.
    ood_verdict = rule_9_ood_detector(gsv, ood_detector)
    if not ood_verdict.allowed:
        return [GateResult(candidate=c, verdict=ood_verdict) for c in candidates]
    win_cfg = mispricing_window_cfg or MispricingWindowConfig()
    window = classify_gsv(gsv, win_cfg)
    out: list[GateResult] = []
    for c in candidates:
        for verdict in (
            rule_2_score_state_inversion(c, gsv),
            rule_3_critical_event_freshness(gsv),
            rule_4_line_freshness(c, gsv, line_max_age_sec),
            rule_5_thesis_market_mismatch(c, mes_threshold),
            rule_6_commentary_lag(c, gsv, commentary_required),
            rule_7_liquidity_gate(c),
            rule_8_predictive_uncertainty(c, uncertainty_band),
            rule_10_mispricing_window(c, window, win_cfg),
            rule_11_calibration_drift(c, gsv, drift_monitor),
        ):
            if not verdict.allowed:
                out.append(GateResult(candidate=c, verdict=verdict))
                break
        else:
            out.append(GateResult(candidate=c, verdict=NoBetVerdict.ok()))
    return out


def allowed_candidates(results: list[GateResult]) -> list[MarketCandidate]:
    return [r.candidate for r in results if r.verdict.allowed]


__all__ = [
    "GateResult",
    "NoBetVerdict",
    "allowed_candidates",
    "rule_1_thesis_present",
    "rule_2_score_state_inversion",
    "rule_3_critical_event_freshness",
    "rule_4_line_freshness",
    "rule_5_thesis_market_mismatch",
    "rule_6_commentary_lag",
    "rule_7_liquidity_gate",
    "rule_8_predictive_uncertainty",
    "rule_9_ood_detector",
    "rule_10_mispricing_window",
    "rule_11_calibration_drift",
    "run_gate",
]
