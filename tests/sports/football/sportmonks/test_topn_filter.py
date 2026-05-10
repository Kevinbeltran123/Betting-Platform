"""Layer-1 tests for the Top-N filter cascade and scoring.

Uses synthetic Polars DataFrames mimicking the picks_graded schema. Real-data
validation lives in ``analyze_jornada.py`` reruns against picks.db.

Test plan covers each F1-F5 filter behavior, the Bayesian shrinkage helper,
the non-monotonic logical kernel, the Top-N selection's per-fixture +
per-window quotas, dedup, dynamic priors recomputation, and signal
enrichment.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import polars as pl
import pytest

from scripts.spike.sportmonks.topn_filter import (
    DROP_LEAGUE_IDS,
    EDGE_BUCKETS,
    EDGE_FLOOR_PCT,
    GLOBAL_PRIOR_ROI,
    KEEP_COND,
    KEEP_UNCOND,
    LOGICAL_COMPONENT_KEYS,
    ODD_CEIL,
    ODD_FLOOR,
    SIGNAL_COLUMNS,
    WINDOW_FIRST_HALF,
    WINDOW_FULL_MATCH,
    WINDOW_SECOND_HALF,
    apply_cascade,
    cache_priors,
    calibrated_edge,
    compute_edge_buckets_from_db,
    compute_market_priors_from_db,
    dedup_picks,
    enrich_with_signals,
    explode_logical_components,
    f1_market_whitelist,
    f2_placement_window,
    f3_edge_floor,
    f4_odd_band,
    f5_league_filter,
    load_cached_priors,
    load_league_market_policy,
    load_market_windows,
    logical_kernel,
    make_edge_calibrator,
    market_window,
    odd_kernel,
    parse_logical_components,
    placement_schedule,
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
        # 5 distinct (market, selection) bets on same fixture; cap=3 must bind.
        # Use distinct markets so dedup doesn't collapse them.
        markets = ["ou_3_5", "cards_total_4_5", "ou_2_5",
                   "first_half_ou_0_5", "team_to_score_first"]
        rows = [_make_pick(pick_id=i, fixture_id=999, market=markets[i],
                           selection="under" if i < 4 else "home",
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


# ── Smart dedup ────────────────────────────────────────────────────────


class TestDedupPicks:

    def test_duplicate_collapsed_to_highest_score(self):
        # Same (fixture, market, selection) emitted at min 62 and 72.
        # Day-1 case: Athletic-Valencia ttsf/home losers — highest scoring
        # one wins, the other dropped.
        rows = [
            _make_pick(pick_id=1, fixture_id=999, market="team_to_score_first",
                       selection="home", minute=62, edge_pct=27.0),
            _make_pick(pick_id=2, fixture_id=999, market="team_to_score_first",
                       selection="home", minute=72, edge_pct=31.0),
        ]
        df = score(_df(*rows))
        out = dedup_picks(df)
        assert out.height == 1

    def test_different_selections_preserved(self):
        # ftr/home vs ftr/away on same fixture are DIFFERENT bets
        rows = [
            _make_pick(pick_id=1, fixture_id=999, market="fulltime_result",
                       selection="home", edge_pct=20.0),
            _make_pick(pick_id=2, fixture_id=999, market="fulltime_result",
                       selection="away", edge_pct=22.0),
        ]
        df = score(_df(*rows))
        assert dedup_picks(df).height == 2

    def test_different_markets_preserved(self):
        rows = [
            _make_pick(pick_id=1, fixture_id=999, market="ou_3_5",
                       selection="under", edge_pct=20.0),
            _make_pick(pick_id=2, fixture_id=999, market="ou_2_5",
                       selection="under", edge_pct=22.0),
        ]
        df = score(_df(*rows))
        assert dedup_picks(df).height == 2

    def test_top_n_dedup_default_on(self):
        # 5 duplicate emissions of same bet → only 1 selected
        rows = [
            _make_pick(pick_id=i, fixture_id=999,
                       market="ou_3_5", selection="under",
                       minute=20 + i, edge_pct=25.0)
            for i in range(5)
        ]
        df = score(_df(*rows))
        out = top_n(df, n=10, dedup=True)
        assert out.height == 1

    def test_top_n_dedup_off_keeps_dupes(self):
        rows = [
            _make_pick(pick_id=i, fixture_id=999,
                       market="ou_3_5", selection="under",
                       minute=20 + i, edge_pct=25.0)
            for i in range(5)
        ]
        df = score(_df(*rows))
        # max_per_fixture=3 still binds even without dedup
        out = top_n(df, n=10, dedup=False)
        assert out.height == 3

    def test_dedup_empty_dataframe(self):
        assert dedup_picks(pl.DataFrame()).is_empty()

    def test_dedup_works_pre_score(self):
        # No 'score' column → falls back to edge_pct sort
        rows = [
            _make_pick(pick_id=1, fixture_id=999, market="ou_3_5",
                       selection="under", edge_pct=20.0),
            _make_pick(pick_id=2, fixture_id=999, market="ou_3_5",
                       selection="under", edge_pct=30.0),
        ]
        df = _df(*rows)
        out = dedup_picks(df)
        assert out.height == 1
        assert out.row(0, named=True)["edge_pct"] == 30.0


# ── Dynamic priors from DB ─────────────────────────────────────────────


@pytest.fixture
def synthetic_picks_db(tmp_path: Path) -> Path:
    """Build a temp picks.db with known per-market ROI for testing priors."""
    db = tmp_path / "picks.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE picks (
                id INTEGER PRIMARY KEY,
                fixture_id INTEGER,
                home_team TEXT,
                away_team TEXT,
                market TEXT,
                selection TEXT,
                minute INTEGER,
                bookmaker_odd REAL,
                our_probability REAL,
                edge_pct REAL,
                logical_score REAL,
                status TEXT,
                profit_units REAL,
                emitted_at TEXT
            )
        """)
        # ou_3_5: 10 won @ +0.80, 0 lost → ROI = +0.80
        # btts: 1 won @ +1.00, 9 lost @ -1.00 → ROI = -0.80
        # rare_market: only 3 graded (below PRIORS_MIN_N=5) → excluded
        rows = []
        for i in range(10):
            rows.append((100 + i, 1, "H", "A", "ou_3_5", "under", 30, 1.80,
                         0.70, 25.0, 0.65, "won", 0.80,
                         "2026-05-10T13:00:00Z"))
        rows.append((200, 2, "H", "A", "btts", "yes", 30, 2.00, 0.65, 30.0,
                     0.55, "won", 1.00, "2026-05-10T13:00:00Z"))
        for i in range(9):
            rows.append((201 + i, 2, "H", "A", "btts", "yes", 30, 2.00, 0.65,
                         30.0, 0.55, "lost", -1.00, "2026-05-10T13:00:00Z"))
        for i in range(3):
            rows.append((300 + i, 3, "H", "A", "rare_market", "x", 30, 1.50,
                         0.74, 15.0, 0.60, "won", 0.50,
                         "2026-05-10T13:00:00Z"))
        conn.executemany(
            "INSERT INTO picks (id, fixture_id, home_team, away_team, market, "
            "selection, minute, bookmaker_odd, our_probability, edge_pct, "
            "logical_score, status, profit_units, emitted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return db


class TestComputePriors:

    def test_recomputes_per_market_roi(self, synthetic_picks_db: Path):
        priors = compute_market_priors_from_db(synthetic_picks_db)
        assert "ou_3_5" in priors
        roi, n = priors["ou_3_5"]
        assert n == 10
        assert roi == pytest.approx(0.80)

    def test_negative_roi_correctly_computed(self, synthetic_picks_db: Path):
        priors = compute_market_priors_from_db(synthetic_picks_db)
        assert "btts" in priors
        roi, n = priors["btts"]
        assert n == 10
        # 1×(+1.00) + 9×(-1.00) = -8.00 across 10 = -0.80
        assert roi == pytest.approx(-0.80)

    def test_below_min_n_dropped(self, synthetic_picks_db: Path):
        priors = compute_market_priors_from_db(synthetic_picks_db)
        # rare_market has only 3 picks (< PRIORS_MIN_N=5) → excluded
        assert "rare_market" not in priors


# ── Priors cache (parquet roundtrip) ───────────────────────────────────


class TestPriorsCache:

    def test_roundtrip(self, tmp_path: Path):
        market_in = {"ou_3_5": (0.50, 30), "btts": (-0.30, 20)}
        league_in = {301: (0.25, 100), 8: (0.20, 80)}
        cache_path = tmp_path / "priors.parquet"
        cache_priors(market_in, league_in, cache_path)
        loaded = load_cached_priors(cache_path)
        assert loaded is not None
        market_out, league_out = loaded
        assert market_out["ou_3_5"][0] == pytest.approx(0.50)
        assert market_out["ou_3_5"][1] == 30
        assert league_out[301][0] == pytest.approx(0.25)

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_cached_priors(tmp_path / "missing.parquet") is None

    def test_append_preserves_history(self, tmp_path: Path):
        cache_path = tmp_path / "priors.parquet"
        cache_priors({"ou_3_5": (0.50, 10)}, {}, cache_path)
        cache_priors({"ou_3_5": (0.55, 20)}, {}, cache_path)
        # Both snapshots in the cache; load returns latest
        full = pl.read_parquet(cache_path)
        assert full.height == 2  # 2 market entries (1 per snapshot)
        loaded = load_cached_priors(cache_path)
        assert loaded is not None
        market_out, _ = loaded
        # Latest is 0.55
        assert market_out["ou_3_5"][0] == pytest.approx(0.55)


# ── Signal enrichment ─────────────────────────────────────────────────


@pytest.fixture
def synthetic_snapshots(tmp_path: Path) -> Path:
    """Build a synthetic snapshots_derived.parquet for enrichment tests."""
    rows = [
        # fixture 100: 3 snapshots at minute 25, 30, 35 (timestamps approx)
        {"fixture_id": 100, "snapshot_taken_at": "2026-05-10T13:25:00+00:00",
         "informational_density": 0.10, "home_momentum": 0.50,
         "away_momentum": 0.50, "home_shot_acceleration": 0.0,
         "away_shot_acceleration": 0.0, "home_set_piece_intensity": 0.5,
         "away_set_piece_intensity": 0.5, "home_killing_clock": False,
         "away_killing_clock": False},
        {"fixture_id": 100, "snapshot_taken_at": "2026-05-10T13:30:00+00:00",
         "informational_density": 0.20, "home_momentum": 0.80,
         "away_momentum": 0.20, "home_shot_acceleration": 0.5,
         "away_shot_acceleration": 0.0, "home_set_piece_intensity": 0.8,
         "away_set_piece_intensity": 0.5, "home_killing_clock": False,
         "away_killing_clock": False},
        {"fixture_id": 100, "snapshot_taken_at": "2026-05-10T13:35:00+00:00",
         "informational_density": 0.30, "home_momentum": 0.70,
         "away_momentum": 0.30, "home_shot_acceleration": 0.3,
         "away_shot_acceleration": 0.1, "home_set_piece_intensity": 0.6,
         "away_set_piece_intensity": 0.5, "home_killing_clock": True,
         "away_killing_clock": False},
    ]
    path = tmp_path / "snapshots_derived.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


class TestSignalEnrichment:

    def test_attaches_signal_columns(self, synthetic_snapshots: Path):
        pick = _make_pick(pick_id=1, fixture_id=100, minute=30)
        pick["emitted_at"] = "2026-05-10T13:30:01+00:00"
        df = _df(pick)
        out = enrich_with_signals(df, synthetic_snapshots)
        for col in SIGNAL_COLUMNS:
            assert col in out.columns, f"missing {col}"

    def test_picks_nearest_snapshot(self, synthetic_snapshots: Path):
        # Pick at 13:30:01 should match the 13:30:00 snapshot
        pick = _make_pick(pick_id=1, fixture_id=100, minute=30)
        pick["emitted_at"] = "2026-05-10T13:30:01+00:00"
        df = _df(pick)
        out = enrich_with_signals(df, synthetic_snapshots)
        assert out.row(0, named=True)["informational_density"] == pytest.approx(0.20)
        assert out.row(0, named=True)["home_momentum"] == pytest.approx(0.80)

    def test_killing_clock_preserved_as_bool(self, synthetic_snapshots: Path):
        pick = _make_pick(pick_id=1, fixture_id=100, minute=35)
        pick["emitted_at"] = "2026-05-10T13:35:00+00:00"
        df = _df(pick)
        out = enrich_with_signals(df, synthetic_snapshots)
        assert out.row(0, named=True)["home_killing_clock"] is True

    def test_missing_parquet_no_op(self, tmp_path: Path):
        pick = _make_pick(pick_id=1, fixture_id=100)
        pick["emitted_at"] = "2026-05-10T13:30:00+00:00"
        df = _df(pick)
        out = enrich_with_signals(df, tmp_path / "nope.parquet")
        # No signal cols added
        assert "informational_density" not in out.columns

    def test_missing_emitted_at_no_op(self, synthetic_snapshots: Path):
        pick = _make_pick(pick_id=1, fixture_id=100)
        # Drop emitted_at
        pick.pop("emitted_at", None)
        df = _df(pick)
        out = enrich_with_signals(df, synthetic_snapshots)
        assert "informational_density" not in out.columns


# ── A/B comparison harness (smoke test) ───────────────────────────────


class TestComparison:

    def test_compare_smoke(self, synthetic_picks_db: Path, tmp_path: Path,
                            monkeypatch):
        """End-to-end compare two configs; verify it returns sane shape."""
        from scripts.spike.sportmonks.compare_topn import (
            FilterConfig, compare,
        )
        # Stub league enrichment (synthetic db has no snapshots)
        from scripts.spike.sportmonks import topn_filter as tf

        def _no_league(df, *_a, **_k):
            return df.with_columns(pl.lit(None).cast(pl.Int64).alias("league_id"))

        monkeypatch.setattr(tf, "enrich_with_league", _no_league)
        monkeypatch.setattr(
            "scripts.spike.sportmonks.compare_topn.enrich_with_league",
            _no_league,
        )

        cfg_a = FilterConfig(name="baseline", top_n=5)
        cfg_b = FilterConfig(name="strict", top_n=3)

        result = compare(cfg_a, cfg_b, db_path=synthetic_picks_db)
        assert "verdict" in result
        assert "a" in result and "b" in result
        assert result["a"]["name"] == "baseline"
        assert result["b"]["name"] == "strict"
        # B has tighter cap so should have ≤ A
        assert result["b"]["n"] <= result["a"]["n"]


# ── Logical components decomposition (Lote A.2) ───────────────────────


class TestLogicalComponents:

    def test_parse_happy_path(self):
        s = ('{"consilience": 0.65, "informational_content": 1.0, '
             '"liquidity": 1.0, "odds_credibility": 0.63, '
             '"size_consistency": 0.5}')
        out = parse_logical_components(s)
        assert out["consilience"] == 0.65
        assert out["informational_content"] == 1.0
        assert out["odds_credibility"] == pytest.approx(0.63)
        assert out["size_consistency"] == 0.5

    def test_parse_none_returns_all_none(self):
        out = parse_logical_components(None)
        assert all(v is None for v in out.values())
        assert set(out.keys()) == set(LOGICAL_COMPONENT_KEYS)

    def test_parse_invalid_json_returns_all_none(self):
        out = parse_logical_components("not json")
        assert all(v is None for v in out.values())

    def test_parse_missing_keys_default_to_none(self):
        # Older snapshot might lack size_consistency
        s = '{"consilience": 0.5, "informational_content": 0.9}'
        out = parse_logical_components(s)
        assert out["consilience"] == 0.5
        assert out["informational_content"] == 0.9
        assert out["liquidity"] is None
        assert out["odds_credibility"] is None
        assert out["size_consistency"] is None

    def test_explode_adds_lc_columns(self):
        rows = [
            _make_pick(pick_id=1) | {"logical_components_json":
                '{"consilience": 0.65, "informational_content": 1.0, '
                '"liquidity": 1.0, "odds_credibility": 0.63, '
                '"size_consistency": 0.5}'},
        ]
        df = pl.from_dicts(rows, infer_schema_length=None)
        out = explode_logical_components(df)
        for k in LOGICAL_COMPONENT_KEYS:
            assert f"lc_{k}" in out.columns
        assert out.row(0, named=True)["lc_consilience"] == 0.65

    def test_explode_no_op_when_column_missing(self):
        df = _df(_make_pick())
        # _make_pick doesn't add logical_components_json
        out = explode_logical_components(df)
        # Same shape (no new cols)
        assert "lc_consilience" not in out.columns


# ── Placement schedule (Lote A.3) ─────────────────────────────────────


class TestPlacementSchedule:

    def _pick_at(self, ts: str, **kw) -> dict:
        p = _make_pick(**kw)
        p["emitted_at"] = ts
        return p

    def test_groups_by_15min_window(self):
        picks = [
            self._pick_at("2026-05-10T13:00:00+00:00", pick_id=1),
            self._pick_at("2026-05-10T13:14:30+00:00", pick_id=2),  # same window
            self._pick_at("2026-05-10T13:15:00+00:00", pick_id=3),  # new window
            self._pick_at("2026-05-10T13:45:00+00:00", pick_id=4),  # third window
        ]
        df = _df(*picks)
        sched = placement_schedule(df, window_minutes=15)
        assert len(sched) == 3
        assert sched[0]["n_picks"] == 2
        assert sched[1]["n_picks"] == 1
        assert sched[2]["n_picks"] == 1

    def test_picks_carry_blurb_fields(self):
        picks = [self._pick_at("2026-05-10T13:00:00+00:00",
                                pick_id=1, market="ou_3_5",
                                selection="under", bookmaker_odd=1.80)]
        df = _df(*picks)
        sched = placement_schedule(df, window_minutes=15)
        first = sched[0]["picks"][0]
        assert first["market"] == "ou_3_5"
        assert first["selection"] == "under"
        assert first["odd"] == 1.80
        assert "fixture" in first

    def test_empty_or_missing_emitted_at(self):
        # Without emitted_at column → empty schedule
        rows = [_make_pick()]
        for r in rows:
            r.pop("emitted_at", None)
        df = pl.from_dicts(rows, infer_schema_length=None)
        assert placement_schedule(df) == []

    def test_chronological_order(self):
        picks = [
            self._pick_at("2026-05-10T15:00:00+00:00", pick_id=1),  # latest
            self._pick_at("2026-05-10T13:00:00+00:00", pick_id=2),  # earliest
            self._pick_at("2026-05-10T14:00:00+00:00", pick_id=3),  # middle
        ]
        df = _df(*picks)
        sched = placement_schedule(df, window_minutes=15)
        starts = [w["window_start"] for w in sched]
        assert starts == sorted(starts)


# ── Dynamic edge calibration (Lote B) ─────────────────────────────────


@pytest.fixture
def edge_calibration_db(tmp_path: Path) -> Path:
    """Synthetic DB with controlled per-bucket realizations.

    Designed so each bucket lands on a known factor:
      (8, 12):  10 picks, edge=10%, all lost (-1.0 each) → realized=-1.0
                avg_nominal=0.10 → factor=-10 → clipped to 0.0
      (12, 15): 10 picks, edge=13%, all won @ +0.50 each → realized=+0.50
                avg_nominal=0.13 → factor=3.85 → clipped to 1.0
      (15, 20): 10 picks, edge=17%, half won (+1.0), half lost (-1.0) → 0
                avg_nominal=0.17 → factor=0 → 0.0
      (20, 30): 10 picks, edge=25%, all won @ +0.20 each → realized=0.20
                avg_nominal=0.25 → factor=0.80
      (30+):    only 3 picks (below MIN_N) → factor=1.0
    """
    db = tmp_path / "edge.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE picks (
                id INTEGER PRIMARY KEY, fixture_id INTEGER,
                market TEXT, selection TEXT, minute INTEGER,
                bookmaker_odd REAL, our_probability REAL,
                edge_pct REAL, logical_score REAL,
                status TEXT, profit_units REAL,
                emitted_at TEXT
            )
        """)
        rows = []
        pid = 1
        # Bucket (8, 12): 10 lost @ -1.0, edge=10%
        for _ in range(10):
            rows.append((pid, 1, "ou_3_5", "u", 30, 1.5, 0.7, 10.0, 0.6,
                         "lost", -1.0, "2026-05-10T13:00:00Z"))
            pid += 1
        # Bucket (12, 15): 10 won @ +0.50, edge=13%
        for _ in range(10):
            rows.append((pid, 2, "ou_3_5", "u", 30, 1.5, 0.7, 13.0, 0.6,
                         "won", 0.50, "2026-05-10T13:00:00Z"))
            pid += 1
        # Bucket (15, 20): 5 won + 5 lost, edge=17%
        for k in range(10):
            status = "won" if k < 5 else "lost"
            pl_units = 1.0 if status == "won" else -1.0
            rows.append((pid, 3, "ou_3_5", "u", 30, 2.0, 0.7, 17.0, 0.6,
                         status, pl_units, "2026-05-10T13:00:00Z"))
            pid += 1
        # Bucket (20, 30): 10 won @ +0.20, edge=25%
        for _ in range(10):
            rows.append((pid, 4, "ou_3_5", "u", 30, 1.2, 0.85, 25.0, 0.6,
                         "won", 0.20, "2026-05-10T13:00:00Z"))
            pid += 1
        # Bucket (30+): only 3 picks → below threshold
        for _ in range(3):
            rows.append((pid, 5, "ou_3_5", "u", 30, 1.5, 0.7, 35.0, 0.6,
                         "won", 0.50, "2026-05-10T13:00:00Z"))
            pid += 1
        conn.executemany(
            "INSERT INTO picks (id, fixture_id, market, selection, minute, "
            "bookmaker_odd, our_probability, edge_pct, logical_score, "
            "status, profit_units, emitted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows,
        )
    return db


class TestEdgeCalibration:

    def test_compute_buckets_returns_one_factor_per_bucket(self,
                                                            edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        assert set(factors.keys()) == set(EDGE_BUCKETS)

    def test_anti_edge_bucket_clipped_to_zero(self, edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        # (8, 12): 10 picks all lost @ -1.0 → factor would be -10, clipped 0
        assert factors[(8.0, 12.0)] == 0.0

    def test_over_realizing_bucket_clipped_to_one(self, edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        # (12, 15): realized 0.50 / nominal 0.13 = 3.85 → clipped to 1.0
        assert factors[(12.0, 15.0)] == 1.0

    def test_break_even_bucket_zero_factor(self, edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        # (15, 20): 5W+5L → realized=0 → factor=0
        assert factors[(15.0, 20.0)] == 0.0

    def test_partial_realization_bucket(self, edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        # (20, 30): realized=0.20, nominal=0.25 → factor=0.80
        assert factors[(20.0, 30.0)] == pytest.approx(0.80, abs=0.01)

    def test_below_min_n_defaults_to_one(self, edge_calibration_db):
        factors = compute_edge_buckets_from_db(edge_calibration_db)
        # (30+): only 3 picks, below MIN_N=5 → factor=1.0
        assert factors[(30.0, 1000.0)] == 1.0

    def test_make_calibrator_none_returns_legacy(self):
        cal = make_edge_calibrator(None)
        # Legacy: 10% edge → 50% haircut → 0.05
        assert cal(10.0) == pytest.approx(0.05)

    def test_make_calibrator_applies_per_bucket_factor(self):
        factors = {
            (0.0, 8.0): 1.0,
            (8.0, 12.0): 0.0,
            (12.0, 15.0): 0.5,
            (15.0, 20.0): 0.75,
            (20.0, 30.0): 0.58,
            (30.0, 1000.0): 0.39,
        }
        cal = make_edge_calibrator(factors)
        # 10% edge in (8, 12) bucket → 0.0
        assert cal(10.0) == 0.0
        # 13.5% edge in (12, 15) → 0.135 * 0.5 = 0.0675
        assert cal(13.5) == pytest.approx(0.0675)
        # 25% edge in (20, 30) → 0.25 * 0.58 = 0.145
        assert cal(25.0) == pytest.approx(0.145)
        # 40% edge in (30+) → 0.40 * 0.39 = 0.156
        assert cal(40.0) == pytest.approx(0.156)

    def test_score_uses_passed_calibrator(self):
        # Two identical picks except edge_pct. Custom calibrator zeros out
        # the 10% pick (factor 0) and passes the 40% pick through (factor 1).
        # 40% edge → cal=0.40, hits the score cap → contributes the full
        # 0.20 weight. 10% pick contributes 0. Delta = 0.20.
        rows = [
            _make_pick(pick_id=1, edge_pct=10.0, market="ou_3_5",
                       league_id=301),
            _make_pick(pick_id=2, edge_pct=40.0, market="ou_3_5",
                       league_id=301),
        ]
        df = _df(*rows)
        factors = {(0.0, 12.0): 0.0, (12.0, 100.0): 1.0}
        cal = make_edge_calibrator(factors)
        out = score(df, edge_calibrator=cal)
        s1, s2 = out.sort("id").get_column("score").to_list()
        assert s2 - s1 == pytest.approx(0.20, abs=0.01)


# ── Drift report (Lote C) ─────────────────────────────────────────────


class TestDriftReport:

    def test_empty_cache_returns_error(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        result = compute_drift(cache_path=tmp_path / "missing.parquet")
        assert result["error"] is not None
        assert result["n_snapshots"] == 0

    def test_single_snapshot_returns_error(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        cache_path = tmp_path / "priors.parquet"
        cache_priors({"ou_3_5": (0.50, 30)}, {}, cache_path)
        result = compute_drift(cache_path=cache_path)
        assert result["n_snapshots"] == 1
        assert "need at least 2" in result["error"]

    def test_two_snapshots_compute_drift(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        cache_path = tmp_path / "priors.parquet"
        cache_priors({"ou_3_5": (0.50, 30), "btts": (-0.30, 20)}, {},
                     cache_path)
        # Force timestamp difference for second snapshot
        import time as _t
        _t.sleep(0.01)
        # Use values that avoid float precision issues at threshold boundaries
        cache_priors({"ou_3_5": (0.43, 50), "btts": (-0.15, 40)}, {},
                     cache_path)
        result = compute_drift(cache_path=cache_path)
        assert result["error"] is None
        assert result["n_snapshots"] == 2
        # ou_3_5: 0.50 → 0.43 = -7pp (drifting)
        ou = next(r for r in result["rows"] if r["key"] == "ou_3_5")
        assert ou["delta_roi_pp"] == pytest.approx(-7.0, abs=0.1)
        assert ou["delta_n"] == 20
        assert ou["status"] == "drifting"
        # btts: -0.30 → -0.15 = +15pp (alert)
        btts = next(r for r in result["rows"] if r["key"] == "btts")
        assert btts["delta_roi_pp"] == pytest.approx(15.0, abs=0.1)
        assert btts["status"] == "alert"

    def test_status_thresholds(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        cache_path = tmp_path / "priors.parquet"
        cache_priors({
            "stable_market":   (0.10, 20),
            "drifting_market": (0.10, 20),
            "alert_market":    (0.10, 20),
        }, {}, cache_path)
        import time as _t
        _t.sleep(0.01)
        cache_priors({
            "stable_market":   (0.12, 30),  # +2pp → stable
            "drifting_market": (0.17, 30),  # +7pp → drifting
            "alert_market":    (0.25, 30),  # +15pp → alert
        }, {}, cache_path)
        result = compute_drift(cache_path=cache_path)
        by_key = {r["key"]: r for r in result["rows"]}
        assert by_key["stable_market"]["status"] == "stable"
        assert by_key["drifting_market"]["status"] == "drifting"
        assert by_key["alert_market"]["status"] == "alert"

    def test_new_and_dropped_keys(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        cache_path = tmp_path / "priors.parquet"
        cache_priors({"old_market": (0.20, 15)}, {}, cache_path)
        import time as _t
        _t.sleep(0.01)
        cache_priors({"new_market": (0.30, 10)}, {}, cache_path)
        result = compute_drift(cache_path=cache_path)
        statuses = {r["key"]: r["status"] for r in result["rows"]}
        assert statuses["old_market"] == "dropped"
        assert statuses["new_market"] == "new"

    def test_kind_filter(self, tmp_path: Path):
        from scripts.spike.sportmonks.drift_report import compute_drift
        cache_path = tmp_path / "priors.parquet"
        cache_priors({"m1": (0.10, 20)}, {1: (0.20, 30)}, cache_path)
        import time as _t
        _t.sleep(0.01)
        cache_priors({"m1": (0.15, 30)}, {1: (0.25, 40)}, cache_path)
        result = compute_drift(cache_path=cache_path, kind_filter="market")
        assert all(r["kind"] == "market" for r in result["rows"])


# ── Empirical windows + (league, market) policy ───────────────────────


class TestMarketWindow:

    def test_class_default_full_match(self):
        # No empirical → return class default
        assert market_window("ou_3_5") == WINDOW_FULL_MATCH
        assert market_window("ou_3_5", empirical={}) == WINDOW_FULL_MATCH

    def test_class_default_first_half(self):
        assert market_window("first_half_ou_0_5") == WINDOW_FIRST_HALF
        assert market_window("btts_first_half") == WINDOW_FIRST_HALF

    def test_class_default_second_half(self):
        assert market_window("btts_second_half") == WINDOW_SECOND_HALF

    def test_empirical_narrows(self):
        # Empirical [10, 49] inside class [0, 75] → tightened to [10, 49]
        emp = {"ou_3_5": (10, 49)}
        assert market_window("ou_3_5", emp) == (10, 49)

    def test_empirical_cannot_widen_below_class_floor(self):
        # btts_2h class [45, 70]; empirical wider [20, 89] → INTERSECT [45, 70]
        emp = {"btts_second_half": (20, 89)}
        assert market_window("btts_second_half", emp) == (45, 70)

    def test_empirical_intersect_partial(self):
        # Class [0, 75], empirical [50, 90] → [50, 75]
        emp = {"team_to_score_first": (50, 90)}
        assert market_window("team_to_score_first", emp) == (50, 75)

    def test_market_not_in_empirical(self):
        # Empirical defined for some markets but not this one → class default
        emp = {"ou_3_5": (10, 49)}
        assert market_window("draw_no_bet", emp) == WINDOW_FULL_MATCH


class TestF2WithEmpiricalWindows:

    def test_f2_uses_empirical_when_provided(self):
        # ou_3_5 picks at minute 50, 60, 70 — class allows all (≤75)
        # Empirical [10, 49] should drop all three
        rows = [_make_pick(pick_id=i, market="ou_3_5", minute=m)
                for i, m in enumerate([50, 60, 70])]
        df = _df(*rows)
        empirical = {"ou_3_5": (10, 49)}
        out = f2_placement_window(df, empirical_windows=empirical)
        assert out.height == 0

    def test_f2_intersect_with_class_default(self):
        # btts_2h: class is [45, 70]; empirical [20, 89] should NOT widen
        rows = [
            _make_pick(pick_id=1, market="btts_second_half", minute=30),  # below class
            _make_pick(pick_id=2, market="btts_second_half", minute=50),  # in class
            _make_pick(pick_id=3, market="btts_second_half", minute=80),  # above class
        ]
        df = _df(*rows)
        empirical = {"btts_second_half": (20, 89)}
        out = f2_placement_window(df, empirical_windows=empirical)
        kept = sorted(r["minute"] for r in out.iter_rows(named=True))
        assert kept == [50]

    def test_f2_no_empirical_uses_class(self):
        # Backwards-compat: no empirical → class defaults applied
        rows = [_make_pick(pick_id=1, market="ou_3_5", minute=80)]
        df = _df(*rows)
        # Class default [0, 75] — minute 80 dropped
        assert f2_placement_window(df).height == 0


class TestF5WithPolicyBlocks:

    def test_f5_drops_policy_block_cell(self):
        # Pick in (league=999, market=foo) with explicit block in policy
        rows = [
            _make_pick(pick_id=1, fixture_id=1, market="ou_3_5", league_id=999),
            _make_pick(pick_id=2, fixture_id=2, market="ou_3_5", league_id=8),
        ]
        df = _df(*rows)
        blocks = {(999, "ou_3_5")}
        out = f5_league_filter(df, policy_blocks=blocks)
        assert out.height == 1
        assert out.row(0, named=True)["league_id"] == 8

    def test_f5_drop_league_id_still_applies(self):
        # Whole-league drop list still fires regardless of policy
        rows = [_make_pick(pick_id=1, league_id=384, market="ou_3_5")]
        df = _df(*rows)
        out = f5_league_filter(df, policy_blocks=None)
        assert out.height == 0

    def test_f5_no_blocks_passes_through(self):
        rows = [_make_pick(pick_id=1, league_id=8, market="ou_3_5")]
        df = _df(*rows)
        out = f5_league_filter(df, policy_blocks=set())
        assert out.height == 1


class TestScoreWithBonuses:

    def test_score_applies_bonus_multiplier(self):
        rows = [
            _make_pick(pick_id=1, league_id=301, market="ou_3_5"),
            _make_pick(pick_id=2, league_id=8, market="ou_3_5"),
        ]
        df = _df(*rows)
        bonuses = {(301, "ou_3_5"): 1.20}
        out = score(df, policy_bonuses=bonuses).sort("id")
        s1, s2 = out.get_column("score").to_list()
        # s1 (league 301) should be ~20% higher than s2 (league 8)
        assert s1 > s2
        # Approximate the ratio (will be exactly 1.20 only if both base scores equal,
        # but priors differ so check direction)
        assert s1 / s2 > 1.05

    def test_score_no_bonuses_unchanged(self):
        rows = [_make_pick(pick_id=1, league_id=301, market="ou_3_5")]
        df = _df(*rows)
        s_no_bonus = score(df).get_column("score").to_list()[0]
        s_empty_bonus = score(df, policy_bonuses={}).get_column("score").to_list()[0]
        assert s_no_bonus == s_empty_bonus


class TestYamlLoaders:

    def test_load_market_windows_missing_file(self, tmp_path: Path):
        assert load_market_windows(tmp_path / "missing.yaml") == {}

    def test_load_market_windows_parses_correctly(self, tmp_path: Path):
        import yaml
        path = tmp_path / "windows.yaml"
        path.write_text(yaml.safe_dump({
            "markets": {
                "ou_3_5": {"window": [10, 49], "n_total": 42},
                "draw_no_bet": {"window": [20, 59], "n_total": 109},
                "cards_total_5_5": {"window": None, "n_total": 16},
            }
        }))
        out = load_market_windows(path)
        assert out["ou_3_5"] == (10, 49)
        assert out["draw_no_bet"] == (20, 59)
        assert "cards_total_5_5" not in out

    def test_load_policy_missing_file(self, tmp_path: Path):
        blocks, bonuses = load_league_market_policy(tmp_path / "missing.yaml")
        assert blocks == set()
        assert bonuses == {}

    def test_load_policy_parses_correctly(self, tmp_path: Path):
        import yaml
        path = tmp_path / "policy.yaml"
        path.write_text(yaml.safe_dump({
            "blocks": [
                {"league_id": 208, "market": "btts", "n": 12,
                 "shrunk_roi": -0.5},
            ],
            "bonuses": [
                {"league_id": 301, "market": "ou_3_5", "n": 10,
                 "multiplier": 1.20},
            ],
        }))
        blocks, bonuses = load_league_market_policy(path)
        assert (208, "btts") in blocks
        assert bonuses[(301, "ou_3_5")] == 1.20


class TestDiscoverPolicies:

    def test_discover_market_windows_finds_positive_window(self,
                                                            tmp_path: Path):
        from scripts.spike.sportmonks.discover_policies import (
            discover_market_windows,
        )
        # Synthetic market with strong signal: positive in min 20-49,
        # negative in min 60-89
        rows = []
        for _ in range(15):  # min 20-29: all win
            rows.append(_make_pick(market="m1", minute=25,
                                    status="won", profit_units=1.0))
        for _ in range(15):  # min 30-39: all win
            rows.append(_make_pick(market="m1", minute=35,
                                    status="won", profit_units=1.0))
        for _ in range(10):  # min 60-69: all lose
            rows.append(_make_pick(market="m1", minute=65,
                                    status="lost", profit_units=-1.0))
        df = _df(*rows)
        out = discover_market_windows(df, min_n=30)
        m1 = out["m1"]
        assert m1["window"] is not None
        # Window should include positive buckets (20-39), exclude negative (60-69)
        lo, hi = m1["window"]
        assert lo <= 20
        assert hi <= 49  # cuts off before the negative bucket

    def test_discover_falls_back_when_n_below_threshold(self):
        from scripts.spike.sportmonks.discover_policies import (
            discover_market_windows,
        )
        rows = [_make_pick(market="rare", status="won", profit_units=1.0)
                for _ in range(5)]
        df = _df(*rows)
        out = discover_market_windows(df, min_n=30)
        assert out["rare"]["window"] is None

    def test_discover_policy_blocks_negative_cells(self, tmp_path: Path):
        from scripts.spike.sportmonks.discover_policies import (
            discover_league_market_policy,
        )
        # Synthetic: league 999 + market "loser" all lost (n=12)
        rows = [
            _make_pick(pick_id=i, fixture_id=1, market="loser",
                       league_id=999, status="lost", profit_units=-1.0)
            for i in range(12)
        ]
        # Add a baseline market for shrinkage anchoring
        rows.extend([
            _make_pick(pick_id=100 + i, fixture_id=2, market="winner",
                       league_id=999, status="won", profit_units=1.0)
            for i in range(15)
        ])
        df = _df(*rows)
        out = discover_league_market_policy(df, min_cell_n=10,
                                             block_threshold=-0.10)
        block_keys = {(b["league_id"], b["market"]) for b in out["blocks"]}
        assert (999, "loser") in block_keys
