"""Tests for analyze_decisions CLI."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import polars as pl
import pytest

# Import the script as a module
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "sportmonks"))
import analyze_decisions as ad  # type: ignore  # noqa: E402


def _make_decisions(tmp_path: Path) -> Path:
    df = pl.DataFrame({
        "id": list(range(1, 11)),
        "fixture_id": [100, 100, 101, 101, 102, 102, 103, 103, 104, 104],
        "minute": [10, 15, 20, 25, 30, 35, 40, 45, 50, 55],
        "market": ["ou_3_5", "btts", "ou_3_5", "ou_3_5",
                   "btts", "draw_no_bet", "ou_3_5", "btts",
                   "ou_3_5", "draw_no_bet"],
        "selection": ["under", "yes", "under", "over",
                      "yes", "home", "under", "no",
                      "under", "draw"],
        "bookmaker_id": [2]*10,
        "bookmaker_odd": [1.85]*10,
        "our_probability": [0.7]*10,
        "edge_pct": [10.0]*10,
        "decision": ["emit", "drop", "emit", "drop",
                     "drop", "flag", "emit", "drop",
                     "emit", "flag"],
        "drop_reason": [None, "below_min_edge", None, "below_min_edge",
                        "market_blacklist", None, None, "positive_side_binary_ban",
                        None, None],
        "sm_marginal": [None]*10,
        "valuebet_agrees": [None]*10,
        "informational_density": [0.5]*10,
        "logical_score": [0.8]*10,
        "logical_components_json": [None]*10,
        "confidence_half_width": [0.05]*10,
        "pick_id": [None]*10,
        "snapshot_taken_at": [
            "2026-05-13T10:00:00Z", "2026-05-13T10:01:00Z",
            "2026-05-13T11:00:00Z", "2026-05-13T11:01:00Z",
            "2026-05-14T10:00:00Z", "2026-05-14T10:01:00Z",
            "2026-05-14T11:00:00Z", "2026-05-14T11:01:00Z",
            "2026-05-14T12:00:00Z", "2026-05-14T12:01:00Z",
        ],
        "audited_at": ["2026-05-13T10:00:00Z"]*10,
    })
    path = tmp_path / "decisions.parquet"
    df.write_parquet(path)
    return path


class TestLoad:
    def test_load_unfiltered(self, tmp_path: Path):
        path = _make_decisions(tmp_path)
        df = ad._load(path, None, None)
        assert len(df) == 10

    def test_load_since_filter(self, tmp_path: Path):
        path = _make_decisions(tmp_path)
        df = ad._load(path, "2026-05-14", None)
        # 6 rows on 2026-05-14
        assert len(df) == 6

    def test_load_until_filter(self, tmp_path: Path):
        path = _make_decisions(tmp_path)
        df = ad._load(path, None, "2026-05-14")
        # 4 rows on 2026-05-13
        assert len(df) == 4

    def test_load_missing_file_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            ad._load(tmp_path / "nonexistent.parquet", None, None)


class TestSummary:
    def test_summary_outputs_decision_distribution(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        df = ad._load(path, None, None)
        ad.cmd_summary(df)
        out = capsys.readouterr().out
        assert "DECISIONS SUMMARY" in out
        assert "drop" in out
        assert "emit" in out
        assert "flag" in out

    def test_summary_empty_window(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        empty_df = ad._load(path, "2030-01-01", "2030-01-02")
        ad.cmd_summary(empty_df)
        out = capsys.readouterr().out
        assert "No decisions" in out


class TestGates:
    def test_gates_shows_cumulative(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        df = ad._load(path, None, None)
        ad.cmd_gates(df)
        out = capsys.readouterr().out
        assert "GATE BREAKDOWN" in out
        # Should reference drop_reasons present in fixture
        assert "below_min_edge" in out or "market_blacklist" in out
        assert "cumulative" in out


class TestMarkets:
    def test_markets_output_includes_market_names(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        df = ad._load(path, None, None)
        ad.cmd_markets(df)
        out = capsys.readouterr().out
        assert "ou_3_5" in out
        assert "btts" in out


class TestRangeParse:
    def test_valid_range(self):
        a, b = ad._parse_range("2026-05-10:2026-05-11")
        assert a == "2026-05-10"
        assert b == "2026-05-11"

    def test_invalid_format_raises(self):
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            ad._parse_range("invalid-no-colon")


class TestCompare:
    def test_compare_runs_without_error(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        ad.cmd_compare(
            path,
            range_a=("2026-05-13", "2026-05-14"),
            range_b=("2026-05-14", "2026-05-15"),
        )
        out = capsys.readouterr().out
        assert "COMPARE" in out
        assert "Δ" in out


class TestMain:
    def test_main_summary(self, tmp_path: Path, monkeypatch, capsys):
        path = _make_decisions(tmp_path)
        rc = ad.main(["summary", "--path", str(path)])
        assert rc == 0
        assert "DECISIONS SUMMARY" in capsys.readouterr().out

    def test_main_compare_missing_ranges(self, tmp_path: Path, capsys):
        path = _make_decisions(tmp_path)
        rc = ad.main(["compare", "--path", str(path)])
        assert rc == 2
        err = capsys.readouterr().err
        assert "range-a" in err
