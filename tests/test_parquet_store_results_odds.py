"""D-04 + Pitfall 4 — results/ and odds/ Parquet stores with 3-level partitioning.

Pitfall 1 regression guards: fixture_id dtype must be pl.Int64 everywhere.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def store(tmp_path: Path):
    from bip.core.storage.parquet_store import ParquetStore
    return ParquetStore(base_path=tmp_path)


@pytest.fixture
def sample_results() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fixture_id": [1001, 1002, 1003],
            "sport": ["football"] * 3,
            "league": ["premier_league", "premier_league", "la_liga"],
            "season": ["2024-2025"] * 3,
            "home_goals": [2, 1, 0],
            "away_goals": [1, 1, 3],
            "status": ["finished", "finished", "finished"],
        },
        schema_overrides={"fixture_id": pl.Int64},
    )


@pytest.fixture
def sample_odds() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fixture_id": [1001, 1002, 1003],
            "sport": ["football"] * 3,
            "league": ["premier_league", "premier_league", "la_liga"],
            "season": ["2024-2025"] * 3,
            "bookmaker": ["Betano"] * 3,
            "opening_home": [2.10, 2.50, 1.80],
            "opening_draw": [3.40, 3.30, 3.60],
            "opening_away": [3.20, 2.70, 4.20],
            "closing_home": [2.05, 2.45, 1.82],
            "closing_draw": [3.45, 3.35, 3.55],
            "closing_away": [3.25, 2.75, 4.15],
            "pinnacle_close_home": [None, None, None],
            "pinnacle_close_draw": [None, None, None],
            "pinnacle_close_away": [None, None, None],
        },
        schema_overrides={
            "fixture_id": pl.Int64,
            "pinnacle_close_home": pl.Float64,
            "pinnacle_close_draw": pl.Float64,
            "pinnacle_close_away": pl.Float64,
        },
    )


class TestResultsStore:
    def test_round_trip_results(self, store, sample_results):
        store.write_results(sample_results)
        result = store.read_results(sport="football", league="premier_league")
        assert len(result) == 2
        assert "home_goals" in result.columns
        assert "away_goals" in result.columns
        assert "status" in result.columns

    def test_results_is_3_level_not_4_level(self, store, sample_results):
        """Pitfall 4: no matchday=... directory under results/."""
        store.write_results(sample_results)
        results_dir = store.base_path / "results"
        assert results_dir.exists()
        assert not any("matchday=" in str(p) for p in results_dir.rglob("*"))

    def test_fixture_id_is_int64_in_results(self, store, sample_results):
        """Pitfall 1 regression guard."""
        store.write_results(sample_results)
        result = store.read_results(sport="football", league="premier_league")
        assert result.schema["fixture_id"] == pl.Int64


class TestOddsStore:
    def test_round_trip_odds(self, store, sample_odds):
        store.write_odds(sample_odds)
        result = store.read_odds(sport="football", league="premier_league")
        assert len(result) == 2
        assert "opening_home" in result.columns
        assert "closing_home" in result.columns
        # nullable pinnacle_* columns survive serialization
        assert "pinnacle_close_home" in result.columns
        assert result["pinnacle_close_home"].null_count() == 2

    def test_odds_is_3_level_not_4_level(self, store, sample_odds):
        store.write_odds(sample_odds)
        odds_dir = store.base_path / "odds"
        assert odds_dir.exists()
        assert not any("matchday=" in str(p) for p in odds_dir.rglob("*"))

    def test_fixture_id_is_int64_in_odds(self, store, sample_odds):
        store.write_odds(sample_odds)
        result = store.read_odds(sport="football", league="premier_league")
        assert result.schema["fixture_id"] == pl.Int64


class TestFeaturesUnchanged:
    """Regression guard: write_features still 4-level (Phase 1 compat)."""

    def test_features_still_4_level(self, store):
        df = pl.DataFrame(
            {
                "fixture_id": [1001, 1002],
                "sport": ["football"] * 2,
                "league": ["premier_league"] * 2,
                "season": ["2024-2025"] * 2,
                "matchday": [1, 2],
                "computed_at": ["2024-08-01T00:00:00+00:00"] * 2,
                "feat_a": [0.5, 0.6],
            },
            schema_overrides={"fixture_id": pl.Int64, "matchday": pl.Int64},
        )
        store.write_features(df)
        features_dir = store.base_path / "features"
        assert features_dir.exists()
        # At least one directory must be matchday=... (4-level preserved)
        matchday_dirs = list(features_dir.rglob("matchday=*"))
        assert len(matchday_dirs) >= 1
