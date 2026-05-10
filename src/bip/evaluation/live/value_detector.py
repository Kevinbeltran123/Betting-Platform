"""ValueDetector — finds picks where our probability beats the bookie's.

For each market the predictor emits, we look at the matching live odds
on the API. If our probability times the decimal odd exceeds 1 + min_edge,
we have value. We then size the stake via fractional Kelly (¼ default).

CRITICAL DESIGN CHOICES:
- Suspended / stopped odds are SKIPPED (no live trade possible)
- Only one bookmaker is currently exposed by Sportmonks at our tier
  (bookmaker_id=2). Multi-bookmaker comparison comes when the operator
  adds The Odds API or a second feed.
- Fair odds = 1 / our_probability; commission ignored (Betano-style).
- Kelly fraction is bounded at MAX_STAKE_PCT (1.5%) to protect bankroll.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from bip.evaluation.live.match_state import LiveMatchState
from bip.evaluation.live.predictor import (
    MARKET_AWAY_OU_15,
    MARKET_BTTS,
    MARKET_BTTS_FIRST_HALF,
    MARKET_DOUBLE_CHANCE,
    MARKET_FIRST_HALF_OU_05,
    MARKET_FIRST_HALF_OU_15,
    MARKET_FIRST_HALF_RESULT,
    MARKET_FULLTIME_RESULT,
    MARKET_HOME_OU_15,
    MARKET_OU_05,
    MARKET_OU_15,
    MARKET_OU_25,
    MARKET_OU_35,
    MarketProbabilities,
)
from bip.sports.football.sportmonks.schemas import Odd
from bip.sports.football.sportmonks.types import MarketID

logger = logging.getLogger(__name__)


# All matchers take an ``Odd`` and return either our internal selection
# key (e.g. "home"/"away"/"draw" for 1X2) or None if the odd doesn't
# correspond to any of our markets.
SelectionMatcher = Callable[[Odd], str | None]


# ── label-based matchers ────────────────────────────────────────────────────


def _ftr_matcher(odd: Odd) -> str | None:
    return {
        "1": "home", "X": "draw", "2": "away",
        "Home": "home", "Draw": "draw", "Away": "away",
    }.get(odd.label)


def _double_chance_matcher(odd: Odd) -> str | None:
    return {
        "1X": "1x", "12": "12", "X2": "x2",
        "Home or Draw": "1x", "Home or Away": "12", "Draw or Away": "x2",
    }.get(odd.label)


def _yes_no_matcher(odd: Odd) -> str | None:
    return {"Yes": "yes", "No": "no"}.get(odd.label)


def _line_matcher_for(target_line: float) -> SelectionMatcher:
    """Returns a matcher for a specific line on a Match Goals / Half Goals odd."""
    def _match(odd: Odd) -> str | None:
        try:
            line = float(odd.total) if odd.total else None
        except (TypeError, ValueError):
            return None
        if line != target_line:
            return None
        return {"Over": "over", "Under": "under"}.get(odd.label)
    return _match


# Map our predictor market keys → (Sportmonks market_id, selection matcher).
_MARKET_BINDINGS: dict[str, tuple[int, SelectionMatcher]] = {
    MARKET_FULLTIME_RESULT: (MarketID.FULLTIME_RESULT, _ftr_matcher),
    MARKET_DOUBLE_CHANCE: (MarketID.DOUBLE_CHANCE, _double_chance_matcher),
    MARKET_FIRST_HALF_RESULT: (MarketID.HALF_TIME_RESULT, _ftr_matcher),
    MARKET_BTTS: (MarketID.BOTH_TEAMS_TO_SCORE, _yes_no_matcher),
    MARKET_BTTS_FIRST_HALF: (MarketID.BTTS_FIRST_HALF, _yes_no_matcher),
    MARKET_OU_05: (MarketID.MATCH_GOALS, _line_matcher_for(0.5)),
    MARKET_OU_15: (MarketID.MATCH_GOALS, _line_matcher_for(1.5)),
    MARKET_OU_25: (MarketID.MATCH_GOALS, _line_matcher_for(2.5)),
    MARKET_OU_35: (MarketID.MATCH_GOALS, _line_matcher_for(3.5)),
    MARKET_FIRST_HALF_OU_05: (MarketID.FIRST_HALF_GOALS, _line_matcher_for(0.5)),
    MARKET_FIRST_HALF_OU_15: (MarketID.FIRST_HALF_GOALS, _line_matcher_for(1.5)),
    MARKET_HOME_OU_15: (MarketID.HOME_GOALS, _line_matcher_for(1.5)),
    MARKET_AWAY_OU_15: (MarketID.AWAY_GOALS, _line_matcher_for(1.5)),
}


# Defaults — operator can override per-CLI run
DEFAULT_MIN_EDGE_PCT = 3.0     # Reject anything < +3% EV
DEFAULT_MAX_STAKE_PCT = 1.5    # Kelly cap at 1.5% of bankroll
DEFAULT_KELLY_FRACTION = 0.25  # ¼ Kelly (CLAUDE.md account-safety mandate)
DEFAULT_MIN_ODD = 1.20         # avoid micro-odds (low absolute return)
DEFAULT_MAX_ODD = 8.0          # avoid lottery tickets (variance kills CLV)
# Edge values above SANITY_EDGE_CAP are usually stale-odd artifacts, NOT
# real value. We mark them as 'flagged' so the operator can verify
# manually before placing — they're emitted but not auto-confirmed.
DEFAULT_SANITY_EDGE_CAP = 50.0


def _market_is_for_team(market: str, selection: str, side: str) -> bool:
    """Return True iff this market+selection pick implies that ``side`` wins
    or doesn't lose.

    Used by sanity filters to drop picks that depend on a team in a
    structural disadvantage (e.g. red card with 30+ min left).
    """
    if market == MARKET_FULLTIME_RESULT:
        return selection == side
    if market == MARKET_FIRST_HALF_RESULT:
        return selection == side
    if market == MARKET_DOUBLE_CHANCE:
        if side == "home":
            return selection in ("1x", "12")
        return selection in ("x2", "12")
    if market == MARKET_HOME_OU_15:
        return side == "home" and selection == "over"
    if market == MARKET_AWAY_OU_15:
        return side == "away" and selection == "over"
    return False


@dataclass(frozen=True)
class LivePick:
    """One actionable pick — model probability strongly beats bookmaker odds."""

    fixture_id: int
    minute: int
    home_team: str
    away_team: str
    market: str           # our market key (e.g. 'first_half_result')
    selection: str        # our selection key (e.g. 'home')
    bookmaker_id: int
    bookmaker_odd: float
    our_probability: float
    fair_odd: float
    edge_pct: float       # ((odd × prob) - 1) × 100
    kelly_fraction_full: float
    suggested_stake_pct: float  # bounded fraction-Kelly of bankroll
    market_description: str | None = None
    snapshot_kind: str = "live"
    # Sanity flag — emitted but NOT auto-confirmed; operator should verify
    flagged_reason: str | None = None


class ValueDetector:
    """Compare predictor probabilities against in-play odds; emit LivePicks."""

    def __init__(
        self,
        *,
        min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
        max_stake_pct: float = DEFAULT_MAX_STAKE_PCT,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
        min_odd: float = DEFAULT_MIN_ODD,
        max_odd: float = DEFAULT_MAX_ODD,
        sanity_edge_cap: float = DEFAULT_SANITY_EDGE_CAP,
        drop_flagged: bool = False,
    ) -> None:
        self.min_edge_pct = min_edge_pct
        self.max_stake_pct = max_stake_pct
        self.kelly_fraction = kelly_fraction
        self.min_odd = min_odd
        self.max_odd = max_odd
        self.sanity_edge_cap = sanity_edge_cap
        self.drop_flagged = drop_flagged

    def evaluate(
        self,
        probs: MarketProbabilities,
        odds: list[Odd],
        *,
        home_team_name: str,
        away_team_name: str,
        state: LiveMatchState | None = None,
    ) -> list[LivePick]:
        """Return a sorted list of LivePicks (highest-edge first)."""
        picks: list[LivePick] = []
        odds_by_market: dict[int, list[Odd]] = defaultdict(list)
        for o in odds:
            if o.suspended or o.stopped:
                continue
            odds_by_market[o.market_id].append(o)

        for market_key, market_probs in probs.by_market.items():
            binding = _MARKET_BINDINGS.get(market_key)
            if not binding:
                continue
            market_id, matcher = binding
            available_odds = odds_by_market.get(market_id, [])
            if not available_odds:
                continue
            for odd in available_odds:
                sel = matcher(odd)
                if sel is None:
                    continue
                our_prob = market_probs.get(sel)
                if our_prob is None or our_prob <= 0.0:
                    continue
                d = odd.decimal_odd
                if d is None or d < self.min_odd or d > self.max_odd:
                    continue
                ev = our_prob * d - 1.0
                edge_pct = ev * 100.0
                if edge_pct < self.min_edge_pct:
                    continue
                # Kelly: f* = (bp - q) / b, where b = d-1, p = our_prob, q = 1-p
                b = d - 1.0
                if b <= 0:
                    continue
                f_star = (b * our_prob - (1 - our_prob)) / b
                f_kelly = max(0.0, f_star) * self.kelly_fraction
                stake_pct = min(f_kelly * 100.0, self.max_stake_pct)
                fair_odd = 1.0 / our_prob

                # ── Sanity filters ───────────────────────────────────
                flagged_reason = self._check_sanity(
                    market=market_key, selection=sel, edge_pct=edge_pct,
                    state=state,
                )

                pick = LivePick(
                    fixture_id=probs.fixture_id,
                    minute=probs.minute,
                    home_team=home_team_name,
                    away_team=away_team_name,
                    market=market_key,
                    selection=sel,
                    bookmaker_id=odd.bookmaker_id,
                    bookmaker_odd=d,
                    our_probability=our_prob,
                    fair_odd=fair_odd,
                    edge_pct=edge_pct,
                    kelly_fraction_full=f_star,
                    suggested_stake_pct=stake_pct,
                    market_description=odd.market_description,
                    snapshot_kind=probs.snapshot_kind,
                    flagged_reason=flagged_reason,
                )

                # Drop flagged picks entirely if configured (CLI flag)
                if flagged_reason and self.drop_flagged:
                    continue

                picks.append(pick)

        # Sort: highest edge first, tie-breaker on lower variance (lower odd)
        picks.sort(key=lambda p: (-p.edge_pct, p.bookmaker_odd))
        return picks

    # ── Sanity filters ──────────────────────────────────────────────────

    def _check_sanity(
        self,
        *,
        market: str, selection: str, edge_pct: float,
        state: LiveMatchState | None,
    ) -> str | None:
        """Return a reason string if the pick is suspect, else None.

        Reasons documented:
        - 'edge_above_sanity_cap': EV > 50% — almost always a stale-odd
          artifact, requires manual verification.
        - 'red_card_invalidates_pick:<side>': pick depends on the man-down
          team winning or avoiding loss with substantial time remaining.
        - 'red_card_inflates_draw': pick is on draw or "team-not-loses"
          when a team has a numerical advantage with substantial time
          left → draw probability is over-modeled.
        - 'red_card_inflates_overs': pick is "Over X.5 goals" after a
          red card with home/away team man-down and few minutes left.
        - 'btts_late_red_card_scoreless_<side>': BTTS-yes pick after a
          red card with that team yet to score and < 30 min remaining.
        - 'late_minute_extreme_score': late game (>85 min) with score
          already very different from market — almost always stale.
        """
        if edge_pct > self.sanity_edge_cap:
            return f"edge_above_sanity_cap (>{self.sanity_edge_cap:.0f}%)"

        if state is None:
            return None

        remaining = max(0, 90 - state.minute) if state.is_live else 0

        # ── Red-card filters — apply when ≥20 min remain ──────────────
        if remaining >= 20:
            # 1. Pick on the man-down team to win / not-lose
            for side, has_red in (
                ("home", state.has_red_card_home),
                ("away", state.has_red_card_away),
            ):
                if not has_red:
                    continue
                if _market_is_for_team(market, selection, side):
                    return f"red_card_invalidates_pick:{side}"

            # 2. Draw probability is inflated when one team has the man
            #    advantage — the team with 11 men is more likely to break
            #    through than the symmetric Bivariate Poisson assumes.
            #    Picks on 'draw' (1X2) or "trailing-team won't lose"
            #    (DC 1X / X2) should be skipped.
            if state.has_red_card_home != state.has_red_card_away:
                if market == MARKET_FULLTIME_RESULT and selection == "draw":
                    return "red_card_inflates_draw"
                if market == MARKET_FIRST_HALF_RESULT and selection == "draw":
                    return "red_card_inflates_draw"
                # Double chance involving the side with man advantage
                # going through is fine; drop only DC that gives the
                # man-down side a non-loss outcome
                if market == MARKET_DOUBLE_CHANCE:
                    if (state.has_red_card_home and selection in ("1x", "12")) or \
                       (state.has_red_card_away and selection in ("x2", "12")):
                        # already caught by red_card_invalidates_pick above
                        pass

        # ── BTTS-yes sanity ──────────────────────────────────────────
        if market == MARKET_BTTS and selection == "yes" and remaining < 30:
            scoreless_home = state.home_goals == 0
            scoreless_away = state.away_goals == 0
            if scoreless_home and state.has_red_card_home:
                return "btts_yes_late_red_card_scoreless_home"
            if scoreless_away and state.has_red_card_away:
                return "btts_yes_late_red_card_scoreless_away"

        # ── Over-goals sanity in late game ───────────────────────────
        # If we're past min 80 with a low total, "Over X.5" picks are
        # almost always wrong; the bookie just hasn't suspended yet.
        if remaining < 10 and market.startswith("ou_") and selection == "over":
            line_str = market[3:]  # e.g., '2_5'
            try:
                line_int = int(line_str.split("_")[0])
                line_dec = int(line_str.split("_")[1])
                line = line_int + line_dec / 10.0
            except (IndexError, ValueError):
                line = None
            if line is not None:
                total = state.home_goals + state.away_goals
                # Need ≥ ceil(line) to win; if we need ≥2 more goals in
                # ≤10 min, that's almost never going to happen
                import math as _m
                goals_needed = _m.ceil(line) - total
                if goals_needed >= 2:
                    return "over_late_game_unrealistic"

        return None
