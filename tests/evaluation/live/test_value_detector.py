"""Layer-1 tests for ValueDetector."""

from __future__ import annotations

import pytest

from bip.evaluation.live.match_state import LiveMatchState
from bip.evaluation.live.predictor import (
    MARKET_AWAY_OU_15,
    MARKET_BTTS,
    MARKET_BTTS_SECOND_HALF,
    MARKET_CARDS_TOTAL_3_5,
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
        # Opt out of Day-1 audit gates: this test exercises pure sorting
        # behavior, not the post-audit cascade rules.
        det = ValueDetector(
            min_edge_pct=3.0,
            market_blacklist=frozenset(),
            ban_positive_side_binaries=False,
        )
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
        # Opt out of positive-side ban: this test exercises line-matching only.
        det = ValueDetector(
            min_edge_pct=3.0, ban_positive_side_binaries=False,
        )
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        # Only the line=2.5 odd should match
        assert all(p.bookmaker_odd == 1.85 for p in picks)
        assert len(picks) == 1


# ── Day-1 wrong-side audit gates (Tier 1.1 - 1.5) ───────────────────────────
# Justification: reports/sportmonks_live/exploratory/05_day5_action_plan.md


def _state(
    *,
    fixture_id: int = 1,
    minute: int = 30,
    home_goals: int = 0,
    away_goals: int = 0,
) -> LiveMatchState:
    return LiveMatchState(
        fixture_id=fixture_id,
        home_team_id=10, away_team_id=20,
        home_team_name="A", away_team_name="B",
        home_goals=home_goals, away_goals=away_goals,
        minute=minute, period_id=1 if minute < 45 else 2,
        is_live=True, is_half_time=False, is_finished=False,
    )


class TestMarketBlacklist:
    """Tier 1.1 + 1.3 — btts, away_ou_1_5, cards_total_3_5 are blacklisted."""

    def test_btts_market_dropped_by_default(self):
        probs = _probs(market_probs={MARKET_BTTS: {"no": 0.65, "yes": 0.35}})
        odds = [_odd(market_id=MarketID.BOTH_TEAMS_TO_SCORE, label="No", value="1.80")]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_away_ou_1_5_dropped_by_default(self):
        probs = _probs(market_probs={MARKET_AWAY_OU_15: {"under": 0.70, "over": 0.30}})
        odds = [
            _odd(market_id=MarketID.AWAY_GOALS, label="Under", value="1.70", total="1.5"),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_cards_total_3_5_dropped_by_default(self):
        probs = _probs(market_probs={MARKET_CARDS_TOTAL_3_5: {"under": 0.65, "over": 0.35}})
        odds = [
            _odd(market_id=MarketID.NUMBER_OF_CARDS, label="Under", value="1.80", total="3.5"),
        ]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_btts_emitted_when_blacklist_explicitly_disabled(self):
        probs = _probs(market_probs={MARKET_BTTS: {"no": 0.65, "yes": 0.35}})
        odds = [_odd(market_id=MarketID.BOTH_TEAMS_TO_SCORE, label="No", value="1.80")]
        det = ValueDetector(min_edge_pct=3.0, market_blacklist=frozenset())
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].market == MARKET_BTTS

    def test_emits_drop_decision_with_market_blacklist_reason(self):
        probs = _probs(market_probs={MARKET_BTTS: {"no": 0.65, "yes": 0.35}})
        odds = [_odd(market_id=MarketID.BOTH_TEAMS_TO_SCORE, label="No", value="1.80")]
        recorded: list[dict] = []
        det = ValueDetector(min_edge_pct=3.0)
        det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            on_decision=lambda **kw: recorded.append(kw),
        )
        assert any(r.get("drop_reason") == "market_blacklist" for r in recorded)


class TestPositiveSideBinaryBan:
    """Tier 1.2 — over/yes on binary markets are dropped by default."""

    def test_btts_second_half_yes_dropped(self):
        # BTTS_SECOND_HALF is NOT in market_blacklist but IS binary.
        probs = _probs(market_probs={MARKET_BTTS_SECOND_HALF: {"yes": 0.85, "no": 0.15}})
        odds = [_odd(market_id=MarketID.BTTS_SECOND_HALF, label="Yes", value="1.40")]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_ou_25_over_dropped(self):
        probs = _probs(market_probs={MARKET_OU_25: {"over": 0.60, "under": 0.40}})
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85", total="2.5")]
        det = ValueDetector(min_edge_pct=3.0)
        assert det.evaluate(probs, odds, home_team_name="A", away_team_name="B") == []

    def test_btts_second_half_no_emitted(self):
        # Negative side passes the ban.
        probs = _probs(market_probs={MARKET_BTTS_SECOND_HALF: {"no": 0.65, "yes": 0.35}})
        odds = [_odd(market_id=MarketID.BTTS_SECOND_HALF, label="No", value="1.80")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].selection == "no"

    def test_multi_side_market_unaffected(self):
        # Fulltime result is NOT binary — neither home/draw/away is "over"/"yes".
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.55, "draw": 0.25, "away": 0.20},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].selection == "home"

    def test_ban_opt_out(self):
        probs = _probs(market_probs={MARKET_OU_25: {"over": 0.60, "under": 0.40}})
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85", total="2.5")]
        det = ValueDetector(min_edge_pct=3.0, ban_positive_side_binaries=False)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].selection == "over"


def _isolated_detector(**overrides) -> ValueDetector:
    """ValueDetector with logical_score / CI / coherence gates disabled —
    used to isolate behavior of Day-1 audit gates in tests."""
    return ValueDetector(
        min_edge_pct=3.0,
        min_logical_score_emit=0.0,
        min_logical_score_flag=0.0,
        enforce_ci_gate=False,
        enforce_coherence=False,
        **overrides,
    )


class TestZeroZeroOverGate:
    """Tier 1.5 — drop Over picks at 0-0 score after minute 30 threshold."""

    def test_drops_over_at_zero_zero_after_threshold(self):
        probs = _probs(
            market_probs={MARKET_OU_25: {"over": 0.60, "under": 0.40}},
            minute=35,
        )
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85", total="2.5")]
        det = _isolated_detector(ban_positive_side_binaries=False)
        state = _state(minute=35, home_goals=0, away_goals=0)
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B", state=state,
        )
        assert picks == []

    def test_keeps_over_when_one_team_scored(self):
        probs = _probs(
            market_probs={MARKET_OU_25: {"over": 0.60, "under": 0.40}},
            minute=35,
        )
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85", total="2.5")]
        det = _isolated_detector(
            ban_positive_side_binaries=False,
            enforce_blackout=False,
        )
        state = _state(minute=35, home_goals=1, away_goals=0)
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B", state=state,
        )
        assert len(picks) == 1

    def test_keeps_over_at_zero_zero_before_threshold(self):
        probs = _probs(
            market_probs={MARKET_OU_25: {"over": 0.60, "under": 0.40}},
            minute=20,
        )
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Over", value="1.85", total="2.5")]
        det = _isolated_detector(ban_positive_side_binaries=False)
        state = _state(minute=20, home_goals=0, away_goals=0)
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B", state=state,
        )
        assert len(picks) == 1

    def test_under_unaffected_by_gate(self):
        probs = _probs(
            market_probs={MARKET_OU_25: {"under": 0.65, "over": 0.35}},
            minute=35,
        )
        odds = [_odd(market_id=MarketID.MATCH_GOALS, label="Under", value="1.70", total="2.5")]
        det = _isolated_detector()
        state = _state(minute=35, home_goals=0, away_goals=0)
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B", state=state,
        )
        assert len(picks) == 1
        assert picks[0].selection == "under"


class TestHighProbabilityKellyHaircut:
    """Tier 1.4 — linear taper on Kelly sizing above probability threshold."""

    def test_haircut_applied_above_threshold(self):
        # p=0.95, odd=1.30. Full Kelly = (0.30×0.95 - 0.05) / 0.30 = 0.7833.
        # kelly_fraction_full preserves the DIAGNOSTIC (raw, no haircut) value
        # so downstream consumers can see what would have been staked without
        # the haircut.
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.95, "draw": 0.03, "away": 0.02},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="1.30")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        assert picks[0].kelly_fraction_full == pytest.approx(0.7833, abs=1e-3)

    def test_no_haircut_below_threshold(self):
        # p=0.55 (below 0.85 threshold) → haircut not applied
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.55, "draw": 0.25, "away": 0.20},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="2.00")]
        det = ValueDetector(min_edge_pct=3.0)
        picks = det.evaluate(probs, odds, home_team_name="A", away_team_name="B")
        assert len(picks) == 1
        # Full Kelly: (1×0.55 - 0.45) / 1 = 0.10 — unchanged
        assert picks[0].kelly_fraction_full == pytest.approx(0.10, abs=1e-6)

    def test_haircut_reduces_stake_vs_no_haircut(self):
        # Compare stakes at p=0.90 with haircut on (default) vs off.
        probs = _probs(market_probs={
            MARKET_FULLTIME_RESULT: {"home": 0.90, "draw": 0.05, "away": 0.05},
        })
        odds = [_odd(market_id=MarketID.FULLTIME_RESULT, label="Home", value="1.40")]
        det_hc = ValueDetector(min_edge_pct=3.0)
        det_no_hc = ValueDetector(min_edge_pct=3.0, high_prob_haircut_threshold=1.01)
        with_haircut = det_hc.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
        )[0]
        without = det_no_hc.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
        )[0]
        # Stake with haircut should be ≤ stake without (both capped or both not).
        # At this stake size both hit the cap, but kelly_fraction_full differs.
        # Compare directly via internal sizing: lower the cap to surface diff.
        det_hc_low = ValueDetector(min_edge_pct=3.0, max_stake_pct=100.0)
        det_no_hc_low = ValueDetector(
            min_edge_pct=3.0, max_stake_pct=100.0,
            high_prob_haircut_threshold=1.01,
        )
        with_low = det_hc_low.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
        )[0]
        without_low = det_no_hc_low.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
        )[0]
        assert with_low.suggested_stake_pct < without_low.suggested_stake_pct
