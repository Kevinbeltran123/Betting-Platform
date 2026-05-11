"""Conditional Predictor — section 3 of LIVE_ENGINE_V3_DESIGN.md.

For each ``(thesis, market, GSV)`` we want ``P(outcome | GSV, horizon)``.

Sec 3 architectural rule: one predictor PER MARKET FAMILY, not a
monolith. Goals/BTTS uses a time-decay hazard model conditioned on
state. Corners uses a Poisson rate model. Cards likewise. Next-X uses
a hazard-point model. Props use shrinkage from pre-match priors.

This Phase-1 scaffold ships **two families**: corners and goals-2H.
Both implement a common protocol so the Market Selector can call them
uniformly. The implementations are **deliberately simple** — Phase 2
swaps them for the real calibrated estimators per sec 5 (state
bucketing + hierarchical pooling + isotonic per minute-bucket).

The protocol is what unblocks the architecture: get the **types**
right now and the predictor implementations can swap in without
touching the selector or the gate.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bip.evaluation.live.engine_v3.gsv import GameStateVector
from bip.evaluation.live.engine_v3.thesis import MarketFamily, Thesis


@dataclass(frozen=True)
class PredictionPoint:
    """Predicted probability + uncertainty band.

    ``ci_low`` / ``ci_high`` reflect the predictor's own confidence; the
    No-Bet gate rule #8 reads these to abort overly-uncertain calls."""

    p: float
    ci_low: float
    ci_high: float
    family: MarketFamily


class FamilyPredictor(Protocol):
    """Each market-family predictor implements this single method."""

    family: MarketFamily

    def predict(
        self, thesis: Thesis, market_id: str, gsv: GameStateVector
    ) -> PredictionPoint | None:
        ...


# ──────────────────────────────────────────────────────────────────────
# Corners family
# ──────────────────────────────────────────────────────────────────────


def _poisson_ge(lam: float, k: int) -> float:
    """P(X >= k) for Poisson(λ). Uses CDF complement."""
    if lam <= 0:
        return 0.0
    s = 0.0
    pmf = math.exp(-lam)
    for i in range(0, k):
        s += pmf
        pmf *= lam / (i + 1)
    return max(0.0, 1.0 - s)


def _parse_line(market_id: str) -> float | None:
    """Best-effort: pull the Over/Under line value from a market id like
    ``match_corners_over_10.5``. Returns None when ambiguous."""
    parts = market_id.replace("_", " ").split()
    for p in reversed(parts):
        try:
            v = float(p)
            return v
        except ValueError:
            continue
    return None


class CornersPredictor:
    """Poisson rate model for corners markets.

    The live rate is built from:
    - Pre-match expected corners (``priors.expected_corners_total``)
    - The observed live rate (``corners_to_minute / minute × 90``)
    - A blending weight from ``minute / (minute + 18)`` — taken from
      the operator's existing predictor's `CORNERS_PRIOR_WEIGHT_MINUTES`

    Then scaled forward over the remaining horizon and combined with
    the **thesis adjustment**: if a relevant archetype is active, the
    rate is nudged by the thesis ``magnitude_pp`` (interpreted as a
    fractional rate change since corners are continuous, not bounded).
    """

    family = MarketFamily.CORNERS

    def __init__(self, prior_blend_minutes: float = 18.0) -> None:
        self.prior_blend_minutes = prior_blend_minutes

    def _expected_total(self, gsv: GameStateVector) -> float:
        prior = gsv.priors.expected_corners_total
        observed = gsv.corners.corners_home + gsv.corners.corners_away
        minute = max(1, gsv.time.minute)
        rate_observed = observed / minute * 90.0
        w_minute = minute / (minute + self.prior_blend_minutes)
        return w_minute * rate_observed + (1.0 - w_minute) * prior

    def predict(
        self, thesis: Thesis, market_id: str, gsv: GameStateVector
    ) -> PredictionPoint | None:
        if thesis.prediction.family not in (MarketFamily.CORNERS, MarketFamily.NEXT_CORNER):
            return None
        line = _parse_line(market_id)
        if line is None:
            return None
        expected_total = self._expected_total(gsv)
        # Thesis adjustment: a corners-over thesis ups the rate by magnitude_pp,
        # a corners-under thesis lowers it.
        sign = 1.0 if thesis.prediction.direction == "over" else -1.0
        adjusted = expected_total * (1.0 + sign * thesis.prediction.magnitude_pp)
        # Remaining-time portion: corners we still expect to see.
        remaining = max(0, gsv.time.time_remaining_match)
        already = gsv.corners.corners_home + gsv.corners.corners_away
        future_lam = adjusted * remaining / 90.0
        # Over line means total corners >= ceil(line) + 1 if half-line.
        target = int(math.ceil(line)) if line != int(line) else int(line) + 1
        need = max(0, target - already)
        p_over = _poisson_ge(future_lam, need)
        # Crude CI: ± √λ as fraction.
        sigma = math.sqrt(future_lam) / max(1.0, target)
        return PredictionPoint(
            p=p_over if thesis.prediction.direction == "over" else max(0.0, 1.0 - p_over),
            ci_low=max(0.0, p_over - sigma),
            ci_high=min(1.0, p_over + sigma),
            family=MarketFamily.CORNERS,
        )


# ──────────────────────────────────────────────────────────────────────
# Goals-2H family
# ──────────────────────────────────────────────────────────────────────


class Goals2HPredictor:
    """Goals predictor scoped to the second-half horizon.

    Uses a Poisson model on a state-conditional λ:
    - Base λ_2H ≈ (home λ + away λ) × time_remaining / 90
    - Conditioned on ``tactical.game_phase``:
        * cagey_closed → ×0.55
        * cruise → ×0.55
        * cagey_open → ×0.80
        * open_attacking → ×1.00
        * desperate → ×1.30
    - Then nudged by the thesis magnitude_pp (in the over/under direction)
    """

    family = MarketFamily.GOALS

    _PHASE_MULT: dict[str, float] = {
        "cagey_closed": 0.55,
        "cruise": 0.55,
        "cagey_open": 0.80,
        "open_attacking": 1.00,
        "desperate": 1.30,
    }

    def _lambda_remaining(self, gsv: GameStateVector) -> float:
        prior_lam = gsv.priors.lambda_home_prematch + gsv.priors.lambda_away_prematch
        remaining = max(0, gsv.time.time_remaining_match)
        base = prior_lam * remaining / 90.0
        return base * self._PHASE_MULT.get(gsv.tactical.game_phase, 1.0)

    def predict(
        self, thesis: Thesis, market_id: str, gsv: GameStateVector
    ) -> PredictionPoint | None:
        if thesis.prediction.family not in (MarketFamily.GOALS, MarketFamily.BTTS,
                                            MarketFamily.NEXT_GOAL):
            return None
        line = _parse_line(market_id)
        already = gsv.score.home_goals + gsv.score.away_goals
        lam = self._lambda_remaining(gsv)
        sign = 1.0 if thesis.prediction.direction == "over" else -1.0
        lam *= (1.0 + sign * thesis.prediction.magnitude_pp)
        # For "next_goal" markets, line is meaningless; we report P(any future goal).
        if thesis.prediction.family == MarketFamily.NEXT_GOAL:
            p = 1.0 - math.exp(-max(0.0, lam))
        elif line is None:
            return None
        else:
            target = int(math.ceil(line)) if line != int(line) else int(line) + 1
            need = max(0, target - already)
            p_over = _poisson_ge(lam, need)
            p = p_over if thesis.prediction.direction == "over" else max(0.0, 1.0 - p_over)
        sigma = math.sqrt(max(0.01, lam)) / 4.0
        return PredictionPoint(
            p=p, ci_low=max(0.0, p - sigma), ci_high=min(1.0, p + sigma),
            family=MarketFamily.GOALS,
        )


# ──────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────


class ConditionalPredictor:
    """Composite predictor that dispatches by family.

    Designed to grow: register additional family predictors with
    ``register(predictor)``. Phase 2 will add cards, next-goal hazard,
    props with shrinkage."""

    def __init__(self) -> None:
        self._predictors: dict[MarketFamily, FamilyPredictor] = {}

    def register(self, predictor: FamilyPredictor) -> None:
        self._predictors[predictor.family] = predictor

    @classmethod
    def default(cls) -> ConditionalPredictor:
        p = cls()
        p.register(CornersPredictor())
        p.register(Goals2HPredictor())
        return p

    def predict(
        self, thesis: Thesis, market_id: str, gsv: GameStateVector
    ) -> PredictionPoint | None:
        """Dispatch using the thesis's predicted family, then fall back
        to BTTS/next_goal routing into goals."""
        family = thesis.prediction.family
        # Route NEXT_CORNER + CORNERS to the corners predictor.
        if family in (MarketFamily.CORNERS, MarketFamily.NEXT_CORNER):
            return self._predictors[MarketFamily.CORNERS].predict(thesis, market_id, gsv)
        # Route NEXT_GOAL/BTTS/GOALS to the goals predictor.
        if family in (MarketFamily.GOALS, MarketFamily.BTTS, MarketFamily.NEXT_GOAL):
            return self._predictors[MarketFamily.GOALS].predict(thesis, market_id, gsv)
        return None


# ──────────────────────────────────────────────────────────────────────
# Fair-prob provider — bridge from predictor to selector
# ──────────────────────────────────────────────────────────────────────


def make_fair_prob_provider(predictor: ConditionalPredictor) -> Callable[
    [Thesis, str, GameStateVector], float | None
]:
    def provider(thesis: Thesis, market_id: str, gsv: GameStateVector) -> float | None:
        result = predictor.predict(thesis, market_id, gsv)
        if result is None:
            return None
        return result.p

    return provider


__all__ = [
    "ConditionalPredictor",
    "CornersPredictor",
    "FamilyPredictor",
    "Goals2HPredictor",
    "PredictionPoint",
    "make_fair_prob_provider",
]
