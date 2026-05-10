"""Layer-1 tests for ValueDetector."""

from __future__ import annotations

import pytest

from bip.evaluation.live.predictor import (
    MARKET_BTTS,
    MARKET_FULLTIME_RESULT,
    MARKET_OU_25,
    MarketProbabilities,
)
from bip.evaluation.live.value_detector import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_PCT,
    LivePick,
    ValueDetector,
)
from bip.sports.football.sportmonks.schemas import Odd
from bip.sports.football.sportmonks.types import MarketID


def _odd(
    *,
    market_id: int,
    label: str,
    value: str,
    suspended: bool = False,
    stopped: bool = False,
    total: str | None = None,
    bookmaker_id: int = 2,
    fixture_id: int = 1,
    market_description: str | None = None,
) -> Odd:
    return Odd.model_validate({
        "id": id(label),
        "fixture_id": fixture_id,
        "market_id": market_id,
        "bookmaker_id": bookmaker_id,
        "label": label,
        "value": value,
        "suspended": suspended,
        "stopped": stopped,
        "total": total,
        "market_description": market_description,
    })


def _probs(
    *,
    fixture_id: int = 1,
    minute: int = 30,
    snapshot_kind: str = "live",
    market_probs: dict[str, dict[str, float]],
) -> MarketProbabilities:
    return MarketProbabilities(
        fixture_id=fixture_id,
        minute=minute,
        snapshot_kind=snapshot_kind,
        by_market=market_probs,
        sources={k: "test" for k in market_probs},
    )


# ── Edge calculation ────────────────────────────────────────────────────────


class TestEdgeDetection:
    def test_value_pick_above_threshold(self):
        # Our prob = 0.55 on home; bookie pays 2.0 (implied 0.50) → +10% EV
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.55, "draw": 0.25, "away": 0.20},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00"),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].market == MARKET_FULLTIME_RESULT
        assert picks[0].selection == "home"
        assert picks[0].edge_pct == pytest.approx(10.0, abs=0.01)

    def test_no_pick_below_threshold(self):
        # Our prob = 0.51 on home; bookie pays 2.0 (implied 0.50) → +2% EV (below threshold)
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.51, "draw": 0.25, "away": 0.24},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00"),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 0


class TestSuspendedFiltering:
    def test_suspended_odds_skipped(self):
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.60, "draw": 0.20, "away": 0.20},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00",
                 suspended=True),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_stopped_odds_skipped(self):
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.60, "draw": 0.20, "away": 0.20},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00",
                 stopped=True),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []


class TestOddRangeFiltering:
    def test_micro_odd_rejected(self):
        # Odd 1.10 is too low to be a useful pick
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.95, "draw": 0.03, "away": 0.02},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="1.10"),
        ]
        det = ValueDetector(min_edge_pct=3.0, min_odd=1.20)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_lottery_odd_rejected(self):
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.13, "draw": 0.10, "away": 0.77},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="10.00"),
        ]
        det = ValueDetector(min_edge_pct=3.0, max_odd=8.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []


# ── Kelly sizing ────────────────────────────────────────────────────────────


class TestKellySizing:
    def test_kelly_quarter_default(self):
        # Our prob 0.55, odd 2.00 → b=1, p=0.55, q=0.45
        # Full Kelly = (1×0.55 - 0.45) / 1 = 0.10
        # Quarter Kelly = 0.025 → 2.5% → CAP applies (1.5%)
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.55, "draw": 0.25, "away": 0.20},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert picks[0].kelly_fraction_full == pytest.approx(0.10, abs=1e-6)
        # Stake: min(0.10 × 0.25 × 100, 1.5%) = min(2.5, 1.5) = 1.5
        assert picks[0].suggested_stake_pct == pytest.approx(DEFAULT_MAX_STAKE_PCT, abs=1e-6)

    def test_kelly_below_cap_uses_quarter(self):
        # Smaller edge → kelly stays under cap
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.42, "draw": 0.30, "away": 0.28},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.50")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        # Full Kelly: (1.5 × 0.42 - 0.58) / 1.5 = 0.0333
        assert picks[0].kelly_fraction_full == pytest.approx(0.0333, abs=1e-3)
        # Quarter = 0.00833 → ~0.83% < 1.5% cap
        assert picks[0].suggested_stake_pct < DEFAULT_MAX_STAKE_PCT


# ── Sorting ────────────────────────────────────────────────────────────────


class TestSorting:
    def test_picks_sorted_by_edge_desc(self):
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.50, "draw": 0.25, "away": 0.25},
            MARKET_BTTS: {"yes": 0.65, "no": 0.35},
        })
        odds = [
            _odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.20"),  # +10% EV
            _odd(market_id=MarketID.BOTH_TEAMS_TO_SCORE, label="Yes", value="1.80"),  # +17% EV
        ]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 2
        # BTTS edge larger → first
        assert picks[0].market == MARKET_BTTS
        assert picks[1].market == MARKET_FULLTIME_RESULT


# ── Line market matching ────────────────────────────────────────────────────


class TestLineMatching:
    def test_ou_25_matches_correct_line(self):
        probs = _probs(market_probs={
            MARKET_OU_25: {"over": 0.60, "under": 0.40},
        })
        odds = [
            # Wrong line — should be ignored
            _odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.50",
                 total="1.5"),
            # Right line — match
            _odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85",
                 total="2.5"),
            # Wrong line again
            _odd(market_id=MarketID.MATCH_GOALS, label="Over", value="3.00",
                 total="3.5"),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        # Only the line=2.5 odd should match
        assert all(p.bookmaker_odd == 1.85 for p in picks)
        assert len(picks) == 1
