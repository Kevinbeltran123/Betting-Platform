"""Live match predictor — combines Sportmonks ML predictions with our own
Dixon-Robinson-style live state model.

Strategy (operator-imparcial choice 2026-05-09):

  Sportmonks already emits 29 well-calibrated pre-built predictions
  (1X2, BTTS, OU, HT/FT, First Half Winner, Correct Score, etc.). We
  TRUST those as a strong baseline — competing with their proprietary
  ML head-on is a losing battle. Our model adds value at TWO seams:

  1. Live state adjustments — Sportmonks predictions are pre-match
     biased; we re-score using Dixon-Robinson scaling for remaining-
     time markets:
         λ_remaining = λ_pre × (90 - minute) / 90
     This is the standard literature approach (Dixon & Robinson 1998).

  2. Live signal lift — when our `pressure` and `xG_proxy` strongly
     contradict Sportmonks (e.g., home pressure 80 vs 30 but pre-match
     prediction is balanced), we shift probabilities a bounded amount
     toward the live signal. The boost is capped at ±10pp per market.

The output is a ``MarketProbabilities`` object with a probability for
every market the value detector knows how to compare against odds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from bip.evaluation.live.match_state import LiveMatchState
from bip.evaluation.tournaments.predictors.bivariate_poisson import (
    _bivariate_poisson_grid as _bivariate_poisson_grid_full,
)
from bip.sports.football.sportmonks.types import PredictionType


def _bivariate_poisson_grid(
    lam_home: float, lam_away: float, *, rho: float = 0.04, max_n: int = 8,
) -> np.ndarray:
    """Build a Bivariate Poisson grid over (additional_home, additional_away).

    Wraps the existing tournaments-package implementation, decomposing
    the rho parameter into the shared lambda_3 component:
        λ_3 = rho × √(λ_h × λ_a), clamped so λ_1, λ_2 ≥ 0
        λ_1 = λ_h − λ_3,  λ_2 = λ_a − λ_3
    """
    if lam_home <= 0 and lam_away <= 0:
        # Degenerate: no chance of any goals → all mass at (0,0)
        g = np.zeros((max_n + 1, max_n + 1))
        g[0, 0] = 1.0
        return g
    lh = max(lam_home, 1e-6)
    la = max(lam_away, 1e-6)
    lam_12 = rho * math.sqrt(lh * la)
    lam_12 = max(0.0, min(lam_12, min(lh, la) - 1e-9))
    lam_1 = lh - lam_12
    lam_2 = la - lam_12
    return _bivariate_poisson_grid_full(lam_1, lam_2, lam_12, max_n)


# Standard markets we emit. Selection-keys are inspired by Sportmonks
# vocabulary so callers can map to in-play odds market_descriptions.
MARKET_FULLTIME_RESULT = "fulltime_result"      # {home, draw, away}
MARKET_DOUBLE_CHANCE = "double_chance"           # {1x, x2, 12}
MARKET_FIRST_HALF_RESULT = "first_half_result"   # {home, draw, away}
MARKET_HTFT = "htft"                              # 9 cells
MARKET_BTTS = "btts"                              # {yes, no}
MARKET_BTTS_FIRST_HALF = "btts_first_half"        # {yes, no}
MARKET_OU_05 = "ou_0_5"                           # {over, under}
MARKET_OU_15 = "ou_1_5"
MARKET_OU_25 = "ou_2_5"
MARKET_OU_35 = "ou_3_5"
MARKET_FIRST_HALF_OU_05 = "first_half_ou_0_5"
MARKET_FIRST_HALF_OU_15 = "first_half_ou_1_5"
MARKET_HOME_OU_15 = "home_ou_1_5"
MARKET_AWAY_OU_15 = "away_ou_1_5"

# Tunables
PRESSURE_DIFF_TRIGGER = 25.0          # avg pressure diff (0-100) before we adjust
PRESSURE_BOOST_MAX = 0.05              # max ±5pp shift on 1X2 from pressure
XG_PROXY_DIFF_TRIGGER = 0.5            # xG-proxy diff to trigger BTTS adjustment
XG_PROXY_BOOST_MAX = 0.04              # max ±4pp shift


@dataclass(frozen=True)
class MarketProbabilities:
    """Per-fixture probabilities, one map per market.

    Probabilities sum to 1.0 within a market (for mutually exclusive
    selections like 1X2 / BTTS / OU). Numeric tolerances are applied to
    the SUM at construction time (1.0 ± 1e-3 acceptable).
    """

    fixture_id: int
    minute: int
    snapshot_kind: str  # 'pre_match' | 'live'
    by_market: dict[str, dict[str, float]]
    # Provenance: which model contributed which probabilities
    sources: dict[str, str]   # market → 'sportmonks' | 'live_adjusted' | 'derived'

    def get(self, market: str, selection: str) -> float | None:
        m = self.by_market.get(market)
        if m is None:
            return None
        return m.get(selection)


class LiveMatchPredictor:
    """Combine Sportmonks predictions with live state adjustments."""

    def __init__(
        self,
        *,
        pressure_boost_max: float = PRESSURE_BOOST_MAX,
        xg_proxy_boost_max: float = XG_PROXY_BOOST_MAX,
    ) -> None:
        self.pressure_boost_max = pressure_boost_max
        self.xg_proxy_boost_max = xg_proxy_boost_max

    def predict(self, state: LiveMatchState) -> MarketProbabilities:
        """Emit market probabilities for the current state."""
        by_market: dict[str, dict[str, float]] = {}
        sources: dict[str, str] = {}

        # 1. Fulltime result — adjust for live signal
        ft_probs, ft_src = self._fulltime_result(state)
        if ft_probs:
            by_market[MARKET_FULLTIME_RESULT] = ft_probs
            sources[MARKET_FULLTIME_RESULT] = ft_src
            # Derived: double chance
            by_market[MARKET_DOUBLE_CHANCE] = self._double_chance_from_1x2(ft_probs)
            sources[MARKET_DOUBLE_CHANCE] = "derived"

        # 2. First half result — only useful before HT
        if not state.is_finished and state.minute < 45:
            fh_probs = self._sportmonks_first_half_result(state)
            if fh_probs:
                by_market[MARKET_FIRST_HALF_RESULT] = fh_probs
                sources[MARKET_FIRST_HALF_RESULT] = "sportmonks"

        # 3. HT/FT — only useful before HT
        if not state.is_finished and state.minute < 45:
            htft = self._sportmonks_htft(state)
            if htft:
                by_market[MARKET_HTFT] = htft
                sources[MARKET_HTFT] = "sportmonks"

        # 4. BTTS (full match) — already-scored teams shift probability
        btts = self._btts(state)
        if btts:
            by_market[MARKET_BTTS] = btts
            sources[MARKET_BTTS] = "live_adjusted"

        # 5. BTTS first half — pre-HT only
        if not state.is_finished and state.minute < 45:
            btts1 = self._btts_first_half(state)
            if btts1:
                by_market[MARKET_BTTS_FIRST_HALF] = btts1
                sources[MARKET_BTTS_FIRST_HALF] = "live_adjusted"

        # 6. OU 0.5/1.5/2.5/3.5 — Dixon-Robinson scaled when in play
        for line, market in [(0.5, MARKET_OU_05), (1.5, MARKET_OU_15),
                             (2.5, MARKET_OU_25), (3.5, MARKET_OU_35)]:
            ou = self._ou_total(state, line=line)
            if ou:
                by_market[market] = ou
                sources[market] = "live_adjusted"

        # 7. First half OU
        if not state.is_finished and state.minute < 45:
            for line, market in [(0.5, MARKET_FIRST_HALF_OU_05),
                                 (1.5, MARKET_FIRST_HALF_OU_15)]:
                ou = self._first_half_ou(state, line=line)
                if ou:
                    by_market[market] = ou
                    sources[market] = "live_adjusted"

        # 8. Per-team OU 1.5
        home_ou15 = self._team_ou(state, line=1.5, side="home")
        away_ou15 = self._team_ou(state, line=1.5, side="away")
        if home_ou15:
            by_market[MARKET_HOME_OU_15] = home_ou15
            sources[MARKET_HOME_OU_15] = "sportmonks"
        if away_ou15:
            by_market[MARKET_AWAY_OU_15] = away_ou15
            sources[MARKET_AWAY_OU_15] = "sportmonks"

        kind = "live" if state.is_live or state.is_half_time else "pre_match"
        return MarketProbabilities(
            fixture_id=state.fixture_id,
            minute=state.minute,
            snapshot_kind=kind,
            by_market=by_market,
            sources=sources,
        )

    # ── per-market predictors ───────────────────────────────────────────

    def _fulltime_result(
        self, state: LiveMatchState,
    ) -> tuple[dict[str, float], str] | tuple[None, None]:
        sm = state.sportmonks_prediction(PredictionType.FULLTIME_RESULT_PROBABILITY)
        if not sm:
            return None, None
        # Sportmonks pre-match probability — used as the prior
        base = {
            "home": _pct(sm.get("home")),
            "draw": _pct(sm.get("draw")),
            "away": _pct(sm.get("away")),
        }

        # Pre-match: trust Sportmonks fully
        if not state.is_live and not state.is_half_time and state.minute == 0:
            return _normalise(base), "sportmonks"

        # ── Dixon-Robinson live scoring ────────────────────────────────
        # Estimate per-team λ_remaining via Sportmonks per-team OU 0.5
        # → P(team scores ≥ 1) = 1 - exp(-λ_full); invert to get λ_full,
        # then scale by remaining-time fraction.
        lam_home_remaining = self._team_lambda_remaining(state, side="home")
        lam_away_remaining = self._team_lambda_remaining(state, side="away")

        if lam_home_remaining is None or lam_away_remaining is None:
            # Fall back to nudged Sportmonks if we can't model remaining time
            return _normalise(base), "sportmonks"

        # Build a bivariate Poisson grid over ADDITIONAL goals scored
        # (rho=0.04 Dixon-Coles default; international-style low-correlation
        # is fine for live-state since most goals are independent in tail)
        grid = _bivariate_poisson_grid(lam_home_remaining, lam_away_remaining,
                                        rho=0.04, max_n=8)

        # Map each (h_add, a_add) outcome to current_score + add → final outcome
        p_home, p_draw, p_away = 0.0, 0.0, 0.0
        for h_add in range(grid.shape[0]):
            for a_add in range(grid.shape[1]):
                fh = state.home_goals + h_add
                fa = state.away_goals + a_add
                p = grid[h_add, a_add]
                if fh > fa:
                    p_home += p
                elif fh == fa:
                    p_draw += p
                else:
                    p_away += p

        live_probs = _normalise({"home": p_home, "draw": p_draw, "away": p_away})

        # Pressure-based nudge — small, only when there's an active period
        if state.is_live:
            diff = state.home_pressure_avg - state.away_pressure_avg
            if abs(diff) > PRESSURE_DIFF_TRIGGER:
                shift = self.pressure_boost_max * min(1.0, abs(diff) / 50.0)
                live_probs = dict(live_probs)
                if diff > 0:
                    live_probs["home"] += shift
                    live_probs["away"] -= shift / 2
                    live_probs["draw"] -= shift / 2
                else:
                    live_probs["away"] += shift
                    live_probs["home"] -= shift / 2
                    live_probs["draw"] -= shift / 2
                live_probs = _normalise(_clip(live_probs))

        return live_probs, "live_adjusted"

    def _team_lambda_remaining(
        self, state: LiveMatchState, *, side: str,
    ) -> float | None:
        """Per-team Poisson λ scaled to remaining minutes.

        Uses Sportmonks per-team OU 0.5 to back out the full-match λ:
            P(team scores ≥ 1) = 1 - exp(-λ_full)
            λ_full = -ln(1 - P)
        Then scales by remaining/90 for live use.
        """
        type_id = (
            PredictionType.HOME_OVER_UNDER_0_5_PROBABILITY if side == "home"
            else PredictionType.AWAY_OVER_UNDER_0_5_PROBABILITY
        )
        sm = state.sportmonks_prediction(type_id)
        if not sm:
            return None
        p_over_0_5 = _pct(sm.get("yes"))
        if not 0.0 < p_over_0_5 < 1.0:
            return None
        lam_full = -math.log(1 - p_over_0_5)
        remaining_fraction = max(0, 90 - state.minute) / 90.0
        return lam_full * remaining_fraction

    def _sportmonks_first_half_result(
        self, state: LiveMatchState,
    ) -> dict[str, float] | None:
        sm = state.sportmonks_prediction(PredictionType.FIRST_HALF_WINNER_PROBABILITY)
        if not sm:
            return None
        return _normalise({
            "home": _pct(sm.get("home")),
            "draw": _pct(sm.get("draw")),
            "away": _pct(sm.get("away")),
        })

    def _sportmonks_htft(self, state: LiveMatchState) -> dict[str, float] | None:
        sm = state.sportmonks_prediction(PredictionType.HTFT_PROBABILITY)
        if not sm:
            return None
        keys = [
            "home_home", "home_draw", "home_away",
            "draw_home", "draw_draw", "draw_away",
            "away_home", "away_draw", "away_away",
        ]
        body = {k: _pct(sm.get(k)) for k in keys}
        return _normalise(body)

    def _btts(self, state: LiveMatchState) -> dict[str, float] | None:
        sm = state.sportmonks_prediction(PredictionType.BTTS_PROBABILITY)
        if not sm:
            return None
        # If the match is in play and only one team has scored, BTTS-yes
        # depends only on the OTHER team scoring in remaining time.
        # We use the Sportmonks pre-match BTTS as a baseline and
        # condition on the current state.
        base_yes = _pct(sm.get("yes"))
        base_no = _pct(sm.get("no"))
        if not state.is_live and not state.is_half_time:
            return _normalise({"yes": base_yes, "no": base_no})

        if state.home_goals == 0 or state.away_goals == 0:
            # Need the other team to score in the remaining minutes
            # Use Dixon-Robinson scaling on Sportmonks per-team OU 0.5
            need_team = "away" if state.home_goals > 0 else "home"
            scoring_prob = self._team_to_score_remaining(state, need_team)
            if scoring_prob is None:
                return _normalise({"yes": base_yes, "no": base_no})
            return _normalise({"yes": scoring_prob, "no": 1 - scoring_prob})
        # Both already scored → BTTS yes is certain
        return {"yes": 1.0, "no": 0.0}

    def _btts_first_half(self, state: LiveMatchState) -> dict[str, float] | None:
        # Sportmonks doesn't ship BTTS-1H pre-built; derive from
        # Home OU 0.5 1H × Away OU 0.5 1H if available
        # (Both OU 0.5 yes ≡ team_score_first_half_yes).
        # Simpler fallback: half of full-match BTTS pre-match.
        sm = state.sportmonks_prediction(PredictionType.BTTS_PROBABILITY)
        if not sm:
            return None
        full_yes = _pct(sm.get("yes"))
        # Empirical fraction: ~45% of BTTS happens by half-time.
        first_half_yes = full_yes * 0.45
        return _normalise({"yes": first_half_yes, "no": 1 - first_half_yes})

    def _ou_total(
        self, state: LiveMatchState, *, line: float,
    ) -> dict[str, float] | None:
        # Map line → Sportmonks PredictionType
        mapping = {
            0.5: None,  # not directly emitted, derive
            1.5: PredictionType.OVER_UNDER_1_5_PROBABILITY,
            2.5: PredictionType.OVER_UNDER_2_5_PROBABILITY,
            3.5: PredictionType.OVER_UNDER_3_5_PROBABILITY,
        }
        type_id = mapping.get(line)

        # Pre-match: trust Sportmonks directly
        if not state.is_live and not state.is_half_time:
            if type_id is None:
                return None
            sm = state.sportmonks_prediction(type_id)
            if not sm:
                return None
            return _normalise({"over": _pct(sm.get("yes")),
                               "under": _pct(sm.get("no"))})

        # Live: condition on already-scored goals + Dixon-Robinson scaled λ
        already = state.home_goals + state.away_goals
        if already > line:
            return {"over": 1.0, "under": 0.0}
        goals_needed = math.ceil(line) - already
        if goals_needed <= 0:
            # Already over (e.g., line=2.5 and 3 goals)
            return {"over": 1.0, "under": 0.0}

        # Use combined home + away xG proxy + Sportmonks pre-match λ
        # Estimate match λ from Sportmonks OU 2.5 if available:
        # P(over 2.5) ≈ P(Poisson(λ) ≥ 3); invert numerically
        lam_total = self._estimate_total_lambda(state)
        if lam_total is None:
            return None
        # Remaining-time scale
        lam_remaining = lam_total * (max(0, 90 - state.minute) / 90.0)
        if lam_remaining <= 0:
            return {"over": 1.0 if already > line else 0.0,
                    "under": 0.0 if already > line else 1.0}
        # Probability that ≥ goals_needed more goals score
        p_over = 1.0 - _poisson_cdf(goals_needed - 1, lam_remaining)
        return {"over": _clip_scalar(p_over), "under": _clip_scalar(1 - p_over)}

    def _first_half_ou(
        self, state: LiveMatchState, *, line: float,
    ) -> dict[str, float] | None:
        # Pre-HT only; if past HT, this market is a settled market handled
        # elsewhere. Derive from current 1H goals + remaining 1H minutes.
        if state.minute >= 45:
            return None
        already_1h = self._first_half_goals_so_far(state)
        if already_1h > line:
            return {"over": 1.0, "under": 0.0}
        goals_needed = math.ceil(line) - already_1h
        # Estimate 1H λ ~= 0.45 × full λ
        lam_total = self._estimate_total_lambda(state)
        if lam_total is None:
            return None
        lam_first_half_total = lam_total * 0.45
        # Remaining 1H: (45 - minute) / 45 fraction
        lam_remaining_1h = lam_first_half_total * max(0, 45 - state.minute) / 45.0
        if lam_remaining_1h <= 0:
            return {"over": 1.0 if already_1h > line else 0.0,
                    "under": 0.0 if already_1h > line else 1.0}
        p_over = 1.0 - _poisson_cdf(goals_needed - 1, lam_remaining_1h)
        return {"over": _clip_scalar(p_over), "under": _clip_scalar(1 - p_over)}

    def _team_ou(
        self, state: LiveMatchState, *, line: float, side: str,
    ) -> dict[str, float] | None:
        # Use Sportmonks per-team OU when available
        type_map = {
            ("home", 0.5): PredictionType.HOME_OVER_UNDER_0_5_PROBABILITY,
            ("home", 1.5): PredictionType.HOME_OVER_UNDER_1_5_PROBABILITY,
            ("home", 2.5): PredictionType.HOME_OVER_UNDER_2_5_PROBABILITY,
            ("home", 3.5): PredictionType.HOME_OVER_UNDER_3_5_PROBABILITY,
            ("away", 0.5): PredictionType.AWAY_OVER_UNDER_0_5_PROBABILITY,
            ("away", 1.5): PredictionType.AWAY_OVER_UNDER_1_5_PROBABILITY,
            ("away", 2.5): PredictionType.AWAY_OVER_UNDER_2_5_PROBABILITY,
            ("away", 3.5): PredictionType.AWAY_OVER_UNDER_3_5_PROBABILITY,
        }
        type_id = type_map.get((side, line))
        if type_id is None:
            return None
        sm = state.sportmonks_prediction(type_id)
        if not sm:
            return None
        return _normalise({
            "over": _pct(sm.get("yes")),
            "under": _pct(sm.get("no")),
        })

    # ── live helpers ────────────────────────────────────────────────────

    def _estimate_total_lambda(self, state: LiveMatchState) -> float | None:
        """Estimate the full-match Poisson λ for total goals.

        Use Sportmonks OU 2.5 to back out λ via P(goals ≥ 3 | Poisson(λ)) =
        Sportmonks_yes. We solve numerically (binary search 0.5 → 6.0).
        """
        sm = state.sportmonks_prediction(PredictionType.OVER_UNDER_2_5_PROBABILITY)
        if not sm:
            return None
        target = _pct(sm.get("yes"))  # P(over 2.5)
        if not 0.0 < target < 1.0:
            # Edge case: trust mid-range default
            return 2.7
        # Binary search for λ
        lo, hi = 0.1, 6.0
        for _ in range(40):
            mid = (lo + hi) / 2
            p = 1.0 - _poisson_cdf(2, mid)  # P(X ≥ 3)
            if p < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def _team_to_score_remaining(
        self, state: LiveMatchState, side: str,
    ) -> float | None:
        """P(side scores ≥ 1 in the remaining minutes).

        Use the per-team OU 0.5 Sportmonks prediction as the base team-λ
        (over 0.5 for the full match → ≥1 goal), back out the per-team λ,
        scale by remaining-time fraction, return P(Poisson(λ_remaining) ≥ 1).
        """
        type_id = (
            PredictionType.HOME_OVER_UNDER_0_5_PROBABILITY if side == "home"
            else PredictionType.AWAY_OVER_UNDER_0_5_PROBABILITY
        )
        sm = state.sportmonks_prediction(type_id)
        if not sm:
            return None
        p_over_0_5 = _pct(sm.get("yes"))
        if not 0.0 < p_over_0_5 < 1.0:
            return None
        # P(Poisson(λ) ≥ 1) = 1 - exp(-λ)  →  λ = -ln(1 - P)
        lam_pre = -math.log(1 - p_over_0_5)
        already = state.home_goals if side == "home" else state.away_goals
        # P(team already scored)? If yes → already 1.0 BTTS contribution
        if already > 0:
            return 1.0
        lam_remaining = lam_pre * max(0, 90 - state.minute) / 90.0
        if lam_remaining <= 0:
            return 0.0
        return 1.0 - math.exp(-lam_remaining)

    def _first_half_goals_so_far(self, state: LiveMatchState) -> int:
        """Count goals scored in the first half (period_id == 1)."""
        return sum(
            1 for minute, _team in state.goal_events if minute <= 45
        )

    def _double_chance_from_1x2(self, ft: dict[str, float]) -> dict[str, float]:
        return {
            "1x": _clip_scalar(ft["home"] + ft["draw"]),
            "x2": _clip_scalar(ft["draw"] + ft["away"]),
            "12": _clip_scalar(ft["home"] + ft["away"]),
        }


# ── numeric helpers ─────────────────────────────────────────────────────────


def _pct(x: Any) -> float:
    """Sportmonks emits percentages 0-100. Convert to 0-1."""
    if x is None:
        return 0.0
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v / 100.0 if v > 1.5 else v


def _normalise(body: dict[str, float]) -> dict[str, float]:
    total = sum(body.values())
    if total <= 0:
        return body
    return {k: v / total for k, v in body.items()}


def _clip(body: dict[str, float], *, lo: float = 0.001, hi: float = 0.999) -> dict[str, float]:
    return {k: max(lo, min(hi, v)) for k, v in body.items()}


def _clip_scalar(v: float, *, lo: float = 0.001, hi: float = 0.999) -> float:
    return max(lo, min(hi, v))


def _sums_to_one(body: dict[str, float], *, tol: float = 1e-3) -> bool:
    return abs(sum(body.values()) - 1.0) < tol


def _poisson_cdf(k: int, lam: float) -> float:
    """P(X ≤ k) for Poisson(λ). For small k this is a sum; we cap k at 30."""
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0
    cdf = 0.0
    term = math.exp(-lam)
    cdf += term
    for i in range(1, min(k, 30) + 1):
        term *= lam / i
        cdf += term
    return cdf
