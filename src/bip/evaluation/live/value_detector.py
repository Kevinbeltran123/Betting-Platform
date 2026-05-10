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
    ) -> None:
        self.min_edge_pct = min_edge_pct
        self.max_stake_pct = max_stake_pct
        self.kelly_fraction = kelly_fraction
        self.min_odd = min_odd
        self.max_odd = max_odd

    def evaluate(
        self,
        probs: MarketProbabilities,
        odds: list[Odd],
        *,
        home_team_name: str,
        away_team_name: str,
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
                picks.append(LivePick(
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
                ))

        # Sort: highest edge first, tie-breaker on lower variance (lower odd)
        picks.sort(key=lambda p: (-p.edge_pct, p.bookmaker_odd))
        return picks
