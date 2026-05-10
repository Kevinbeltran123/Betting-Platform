"""Layer-1 tests for the Top-N filter cascade and scoring.

Uses synthetic Polars DataFrames mimicking the picks_graded schema. Real-data
validation lives in ``analyze_jornada.py`` reruns against picks.db.

Test plan covers each F1-F5 filter behavior, the Bayesian shrinkage helper,
the non-monotonic logical kernel, and the Top-N selection's per-fixture
+ per-window quotas.
"""

from __future__ import annotations

import polars as pl
import pytest

from scripts.spike.sportmonks.topn_filter import (
    DROP_LEAGUE_IDS,
    EDGE_FLOOR_PCT,
    GLOBAL_PRIOR_ROI,
    KEEP_COND,
    KEEP_UNCOND,
    ODD_CEIL,
    ODD_FLOOR,
    apply_cascade,
    calibrated_edge,
    f1_market_whitelist,
    f2_placement_window,
    f3_edge_floor,
    f4_odd_band,
    f5_league_filter,
    logical_kernel,
    odd_kernel,
    score,
    shrunk_roi,
    time_kernel,
    top_n,
)


def _make_pick(
    *,
    pick_id: int = 1,
    fixture_id: int = 100,
    market: str = "ou_3_5",
    selection: str = "over",
    minute: int = 30,
    bookmaker_odd: float = 1.80,
    edge_pct: float = 20.0,
    logical_score: float = 0.65,
    league_id: int | None = 8,
    status: str = "won",
    profit_units: float = 0.80,
) -> dict:
    """Build a synthetic pick row matching picks_graded.parquet schema."""
    return {
        "id": pick_id,
        "fixture_id": fixture_id,
        "market": market,
        "selection": selection,
        "minute": minute,
        "bookmaker_odd": bookmaker_odd,
        "our_probability": 1.0 / bookmaker_odd * (1 + edge_pct / 100),
        "edge_pct": edge_pct,
        "logical_score": logical_score,
        "league_id": league_id,
        "status": status,
        "profit_units": profit_units,
        "home_team": "Home",
        "away_team": "Away",
    }


def _df(*picks: dict) -> pl.DataFrame:
    return pl.from_dicts(list(picks), infer_schema_length=None)


# ── F1 — market whitelist ──────────────────────────────────────────────


class TestF1MarketWhitelist:

    def test_keeps_unconditional_market_regardless_of_edge(self):
        # ou_3_5 is in KEEP_UNCOND with low edge — must survive
        df = _df(_make_pick(market="ou_3_5", edge_pct=12.5))
        out = f1_market_whitelist(df)
        assert out.height == 1

    def test_drops_unlisted_markets(self):
        # btts is on the implicit drop list (not in KEEP_UNCOND or KEEP_COND)
        df = _df(_make_pick(market="btts", edge_pct=50.0))
        assert f1_market_whitelist(df).height == 0

    def test_drops_away_ou_1_5(self):
        # away_ou_1_5: -9.58% Day-1, dropped entirely
        df = _df(_make_pick(market="away_ou_1_5", edge_pct=30.0))
        assert f1_market_whitelist(df).height == 0

    @pytest.mark.parametrize("market,floor", list(KEEP_COND.items()))
    def test_conditional_market_requires_edge_floor(self, market, floor):
        # Below floor → drop; at or above floor → keep
        below = _df(_make_pick(market=market, edge_pct=floor - 0.1))
        at_floor = _df(_make_pick(market=market, edge_pct=floor))
        assert f1_market_whitelist(below).height == 0, f"{market} below floor"
        assert f1_market_whitelist(at_floor).height == 1, f"{market} at floor"

    def test_unconditional_set_actually_kept(self):
        rows = [_make_pick(pick_id=i, market=m, edge_pct=15.0)
                for i, m in enumerate(KEEP_UNCOND)]
        df = _df(*rows)
        assert f1_market_whitelist(df).height == len(KEEP_UNCOND)


# ── F2 — placement window ──────────────────────────────────────────────


class TestF2PlacementWindow:

    def test_full_match_kept_at_minute_75(self):
        # Boundary: minute 75 must survive (inclusive)
        df = _df(_make_pick(market="ou_3_5", minute=75))
        assert f2_placement_window(df).height == 1

    def test_full_match_dropped_at_minute_76(self):
        df = _df(_make_pick(market="ou_3_5", minute=76))
        assert f2_placement_window(df).height == 0

    def test_first_half_dropped_at_minute_31(self):
        df = _df(_make_pick(market="first_half_ou_0_5", minute=31))
        assert f2_placement_window(df).height == 0

    def test_first_half_kept_at_minute_30(self):
        df = _df(_make_pick(market="first_half_ou_0_5", minute=30))
        assert f2_placement_window(df).height == 1

    def test_btts_first_half_uses_first_half_window(self):
        df = _df(
            _make_pick(market="btts_first_half", minute=25, pick_id=1),
            _make_pick(market="btts_first_half", minute=44, pick_id=2),
        )
        out = f2_placement_window(df)
        assert out.height == 1
        assert out.row(0, named=True)["minute"] == 25

    def test_btts_second_half_requires_minute_45_to_70(self):
        df = _df(
            _make_pick(market="btts_second_half", minute=44, pick_id=1),  # too early
            _make_pick(market="btts_second_half", minute=45, pick_id=2),  # boundary
            _make_pick(market="btts_second_half", minute=60, pick_id=3),  # mid
            _make_pick(market="btts_second_half", minute=70, pick_id=4),  # boundary
            _make_pick(market="btts_second_half", minute=71, pick_id=5),  # too late
        )
        out = f2_placement_window(df)
        kept = sorted(r["minute"] for r in out.iter_rows(named=True))
        assert kept == [45, 60, 70]


# ── F3 — edge floor ────────────────────────────────────────────────────


class TestF3EdgeFloor:

    @pytest.mark.parametrize("edge,kept", [
        (EDGE_FLOOR_PCT - 0.1, False),
        (EDGE_FLOOR_PCT, True),
        (EDGE_FLOOR_PCT + 0.1, True),
        (50.0, True),
    ])
    def test_boundary_at_floor(self, edge, kept):
        df = _df(_make_pick(edge_pct=edge))
        assert (f3_edge_floor(df).height == 1) == kept


# ── F4 — odd band ──────────────────────────────────────────────────────


class TestF4OddBand:

    @pytest.mark.parametrize("odd,kept", [
        (ODD_FLOOR - 0.01, False),
        (ODD_FLOOR, True),
        (1.80, True),
        (ODD_CEIL, True),
        (ODD_CEIL + 0.01, False),
    ])
    def test_boundaries(self, odd, kept):
        df = _df(_make_pick(bookmaker_odd=odd))
        assert (f4_odd_band(df).height == 1) == kept

    def test_btts_2h_low_odds_survive(self):
        # btts_2h winners had ~1.35 odds with 86.5% win rate — must not be killed
        df = _df(_make_pick(market="btts_second_half", bookmaker_odd=1.35))
        assert f4_odd_band(df).height == 1


# ── F5 — league filter ─────────────────────────────────────────────────


class TestF5LeagueFilter:

    def test_drops_serie_a(self):
        df = _df(_make_pick(league_id=384))
        assert f5_league_filter(df).height == 0

    def test_keeps_other_leagues(self):
        df = _df(
            _make_pick(pick_id=1, league_id=301),  # Ligue 1
            _make_pick(pick_id=2, league_id=8),    # EPL
            _make_pick(pick_id=3, league_id=82),   # Bundesliga
        )
        assert f5_league_filter(df).height == 3

    def test_keeps_unknown_league(self):
        # Lower-tier league not in DROP set → keep
        df = _df(_make_pick(league_id=999))
        assert f5_league_filter(df).height == 1

    def test_keeps_null_league_id(self):
        # Picks without league enrichment are not gated by F5
        df = _df(_make_pick(league_id=None))
        assert f5_league_filter(df).height == 1

    def test_noop_when_column_missing(self):
        # Without league_id column, F5 is a no-op
        rows = [_make_pick()]
        for r in rows:
            r.pop("league_id", None)
        df = pl.from_dicts(rows, infer_schema_length=None)
        out = f5_league_filter(df)
        assert out.height == 1

    def test_drop_set_matches_constants(self):
        assert 384 in DROP_LEAGUE_IDS


# ── Cascade composition ───────────────────────────────────────────────


class TestApplyCascade:

    def test_pristine_pick_passes_all_filters(self):
        df = _df(_make_pick(
            market="ou_3_5", minute=30, bookmaker_odd=2.00,
            edge_pct=20.0, league_id=301,
        ))
        assert apply_cascade(df).height == 1

    def test_late_pick_dropped(self):
        df = _df(_make_pick(market="ou_3_5", minute=85, league_id=301))
        assert apply_cascade(df).height == 0

    def test_low_edge_dropped(self):
        df = _df(_make_pick(market="ou_3_5", edge_pct=10.0, league_id=301))
        assert apply_cascade(df).height == 0

    def test_serie_a_dropped(self):
        df = _df(_make_pick(market="ou_3_5", league_id=384))
        assert apply_cascade(df).height == 0

    def test_long_shot_dropped(self):
        df = _df(_make_pick(market="ou_3_5", bookmaker_odd=5.00, league_id=301))
        assert apply_cascade(df).height == 0


# ── Bayesian shrinkage ────────────────────────────────────────────────


class TestShrunkRoi:

    def test_pulls_small_n_toward_prior(self):
        # n=5 with extreme observation gets pulled hard toward prior
        observed_far = -0.50
        result = shrunk_roi(observed_far, n=5, prior_roi=0.10, k=30)
        # With k=30 vs n=5: weight is 30/(30+5) = 0.857 toward prior
        # → 5*(-0.50)/35 + 30*0.10/35 = -0.0714 + 0.0857 = 0.0143
        assert -0.05 < result < 0.05

    def test_large_n_dominates_prior(self):
        # n=300 dominates k=30 — shrinkage is mild
        observed = 0.50
        result = shrunk_roi(observed, n=300, prior_roi=0.10, k=30)
        # 300*0.50/330 + 30*0.10/330 = 0.4545 + 0.0091 = 0.4636
        assert 0.45 < result < 0.47

    def test_n_zero_returns_prior(self):
        assert shrunk_roi(0.99, n=0) == GLOBAL_PRIOR_ROI

    def test_negative_observation_pulled_up(self):
        # btts with -77% on n=38 should be pulled up but stay negative
        result = shrunk_roi(-0.7724, n=38, prior_roi=0.10, k=30)
        assert -0.50 < result < -0.30


# ── Logical kernel (non-monotonic) ─────────────────────────────────────


class TestLogicalKernel:

    @pytest.mark.parametrize("score,expected", [
        (None, 0.0),
        (0.30, 0.0),
        (0.45, 0.7),  # bucket 0.40-0.50 — second-best
        (0.55, 0.3),  # bucket 0.50-0.60 — penalized weak tier
        (0.65, 1.0),  # bucket 0.60-0.70 — workhorse
        (0.78, 0.4),  # bucket 0.70-0.85 — clean-but-weak
        (0.90, 0.9),  # bucket 0.85+ — high-conf
    ])
    def test_buckets(self, score, expected):
        assert logical_kernel(score) == expected

    def test_non_monotonic(self):
        # Verify the dip at 0.50-0.60 is real
        assert logical_kernel(0.45) > logical_kernel(0.55)
        assert logical_kernel(0.65) > logical_kernel(0.55)
        assert logical_kernel(0.78) < logical_kernel(0.65)


# ── Odd kernel ────────────────────────────────────────────────────────


class TestOddKernel:

    def test_zero_outside_band(self):
        assert odd_kernel(1.20) == 0.0
        assert odd_kernel(5.00) == 0.0

    def test_peak_in_mid_range(self):
        assert odd_kernel(2.00) == 1.0
        assert odd_kernel(2.50) == 1.0

    def test_floor_value_at_band_edge(self):
        assert odd_kernel(1.30) == pytest.approx(0.6)


# ── Time kernel ───────────────────────────────────────────────────────


class TestTimeKernel:

    def test_full_match_decays_after_minute_25(self):
        assert time_kernel(20, "ou_3_5") == 1.0
        assert time_kernel(25, "ou_3_5") == 1.0
        assert time_kernel(50, "ou_3_5") == pytest.approx(0.5)
        assert time_kernel(75, "ou_3_5") == 0.0

    def test_first_half_decays_from_zero(self):
        assert time_kernel(0, "first_half_ou_0_5") == 1.0
        assert time_kernel(15, "first_half_ou_0_5") == pytest.approx(0.5)
        assert time_kernel(30, "first_half_ou_0_5") == 0.0

    def test_second_half_zero_before_45(self):
        assert time_kernel(40, "btts_second_half") == 0.0

    def test_second_half_peak_45_to_60(self):
        assert time_kernel(45, "btts_second_half") == 1.0
        assert time_kernel(60, "btts_second_half") == 1.0

    def test_second_half_decay_after_60(self):
        assert time_kernel(65, "btts_second_half") == pytest.approx(0.5)
        assert time_kernel(70, "btts_second_half") == 0.0


# ── Calibrated edge ───────────────────────────────────────────────────


class TestCalibratedEdge:

    def test_haircut_below_15(self):
        # Day-1 said 8-15% bucket overconfident → 50% haircut
        assert calibrated_edge(10.0) == pytest.approx(0.05)
        assert calibrated_edge(14.9) == pytest.approx(0.0745)

    def test_no_haircut_above_15(self):
        assert calibrated_edge(15.0) == pytest.approx(0.15)
        assert calibrated_edge(30.0) == pytest.approx(0.30)


# ── Scoring ───────────────────────────────────────────────────────────


class TestScore:

    def test_adds_score_column(self):
        df = _df(_make_pick())
        out = score(df)
        assert "score" in out.columns

    def test_score_in_unit_range(self):
        df = _df(
            _make_pick(pick_id=1, market="ou_3_5", edge_pct=30.0,
                       logical_score=0.65, bookmaker_odd=2.00,
                       minute=20, league_id=301),
            _make_pick(pick_id=2, market="draw_no_bet", edge_pct=12.5,
                       logical_score=0.55, bookmaker_odd=1.80,
                       minute=70, league_id=8),
        )
        out = score(df)
        scores = out.select("score").to_series().to_list()
        assert all(-1.0 < s < 1.5 for s in scores)

    def test_better_market_scores_higher_ceteris_paribus(self):
        # ou_3_5 (+73% Day-1) should beat draw_no_bet (+8.82%) holding all else
        df = _df(
            _make_pick(pick_id=1, market="ou_3_5",
                       edge_pct=20.0, logical_score=0.65, league_id=301,
                       bookmaker_odd=2.00, minute=30),
            _make_pick(pick_id=2, market="draw_no_bet",
                       edge_pct=20.0, logical_score=0.65, league_id=301,
                       bookmaker_odd=2.00, minute=30),
        )
        out = score(df).sort("score", descending=True)
        assert out.row(0, named=True)["market"] == "ou_3_5"


# ── Top-N selection ───────────────────────────────────────────────────


class TestTopN:

    def test_returns_at_most_n(self):
        # Spread across windows + fixtures so quotas don't bind below n=10
        rows = [_make_pick(pick_id=i, fixture_id=i,
                           minute=10 + (i * 5) % 60)
                for i in range(50)]
        df = score(_df(*rows))
        assert top_n(df, n=10, max_per_window=10).height == 10

    def test_max_per_fixture_enforced(self):
        # 5 picks on same fixture → only 3 should survive with cap=3
        rows = [_make_pick(pick_id=i, fixture_id=999,
                           minute=20 + i, edge_pct=30.0 - i)
                for i in range(5)]
        df = score(_df(*rows))
        out = top_n(df, n=10, max_per_fixture=3)
        assert out.height == 3
        assert all(r["fixture_id"] == 999 for r in out.iter_rows(named=True))

    def test_max_per_window_enforced(self):
        # 7 picks all in window 30-44 (window_15 == 2) → cap of 5
        rows = [_make_pick(
            pick_id=i, fixture_id=i,  # different fixtures so per-fixture cap doesn't bind
            minute=30 + i, edge_pct=30.0,
        ) for i in range(7)]
        df = score(_df(*rows))
        out = top_n(df, n=10, max_per_window=5)
        # All these picks fall in window=2 (minute//15=2)
        windows = [r["minute"] // 15 for r in out.iter_rows(named=True)]
        assert windows.count(2) == 5

    def test_higher_score_picked_first(self):
        # Lower-edge pick on weaker market should rank below
        rows = [
            _make_pick(pick_id=1, fixture_id=1, market="ou_3_5",
                       edge_pct=30.0, logical_score=0.65, league_id=301,
                       bookmaker_odd=2.00, minute=20),
            _make_pick(pick_id=2, fixture_id=2, market="cards_total_5_5",
                       edge_pct=12.0, logical_score=0.55, league_id=999,
                       bookmaker_odd=1.40, minute=70),
        ]
        df = score(_df(*rows))
        out = top_n(df, n=1)
        assert out.row(0, named=True)["id"] == 1

    def test_empty_input_returns_empty(self):
        df = pl.DataFrame()
        assert top_n(df, n=25).is_empty()
