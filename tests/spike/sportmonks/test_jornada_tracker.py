"""Tests for jornada_tracker CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "sportmonks"))
import jornada_tracker as jt  # type: ignore  # noqa: E402


def _make_picks(tmp_path: Path) -> Path:
    df = pl.DataFrame({
        "id": list(range(1, 13)),
        "fixture_id": [100, 100, 101, 101, 200, 200, 201, 201, 300, 300, 301, 301],
        "home_team": ["A"]*12,
        "away_team": ["B"]*12,
        "market": ["ou_3_5"]*12,
        "selection": ["under"]*12,
        "bookmaker_id": [2]*12,
        "minute": [30]*12,
        "minute_bucket": ["30-44"]*12,
        "bookmaker_odd": [1.85]*12,
        "our_probability": [0.7]*12,
        "fair_odd": [1.43]*12,
        "edge_pct": [10.0]*12,
        "kelly_fraction_full": [0.2]*12,
        "suggested_stake_pct": [1.0]*12,
        "market_description": [None]*12,
        "snapshot_kind": ["live"]*12,
        "emitted_at": [
            "2026-05-10T13:00:00Z", "2026-05-10T13:30:00Z",
            "2026-05-10T14:00:00Z", "2026-05-10T14:30:00Z",
            "2026-05-13T13:00:00Z", "2026-05-13T13:30:00Z",
            "2026-05-13T14:00:00Z", "2026-05-13T14:30:00Z",
            "2026-05-14T13:00:00Z", "2026-05-14T13:30:00Z",
            "2026-05-14T14:00:00Z", "2026-05-14T14:30:00Z",
        ],
        "flagged_reason": [None]*12,
        "logical_score": [0.8]*12,
        "logical_components_json": [None]*12,
        "confidence_half_width": [0.05]*12,
        # 4 picks per jornada: 3 wins, 1 loss → 75% wr
        # profit per pick: win = (1.85-1)*1.0 = 0.85; loss = -1.0
        # per-jornada profit: 3*0.85 + 1*(-1.0) = 2.55 - 1.0 = 1.55
        # ROI: 1.55 / 4.0 = 38.75%
        "status": ["won","won","won","lost",
                   "won","won","won","lost",
                   "won","won","won","lost"],
        "settled_at": ["2026-05-10T15:00:00Z"]*4 +
                      ["2026-05-13T15:00:00Z"]*4 +
                      ["2026-05-14T15:00:00Z"]*4,
        "profit_units": [0.85, 0.85, 0.85, -1.0]*3,
        "placed_at_betano": [None]*12,
        "betano_odd": [None]*12,
        "actual_stake_units": [None]*12,
        "notes": [None]*12,
    })
    path = tmp_path / "picks_graded.parquet"
    df.write_parquet(path)
    return path


class TestGroupByJornada:
    def test_groups_by_date(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        df = pl.read_parquet(path)
        summaries = jt._group_by_jornada(df)
        assert len(summaries) == 3
        # 3 unique dates
        dates = [s.date for s in summaries]
        assert dates == sorted(dates)
        assert "2026-05-10" in dates
        assert "2026-05-13" in dates
        assert "2026-05-14" in dates

    def test_per_jornada_aggregation(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        df = pl.read_parquet(path)
        summaries = jt._group_by_jornada(df)
        # Each jornada: 4 picks, 3 won, 1 lost
        for s in summaries:
            assert s.n_emit == 4
            assert s.n_settled == 4
            assert s.n_won == 3
            assert s.win_rate == pytest.approx(75.0)
            assert s.profit_units == pytest.approx(1.55)
            assert s.stake_pct_total == pytest.approx(4.0)
            assert s.roi_pct == pytest.approx(38.75)

    def test_empty_picks(self, tmp_path: Path):
        # Empty df returns no summaries — must use schema overrides for str cols
        empty_path = tmp_path / "empty.parquet"
        pl.DataFrame(
            schema={
                "emitted_at": pl.String,
                "status": pl.String,
                "profit_units": pl.Float64,
                "suggested_stake_pct": pl.Float64,
            }
        ).write_parquet(empty_path)
        df = pl.read_parquet(empty_path)
        summaries = jt._group_by_jornada(df)
        assert summaries == []


class TestCumulative:
    def test_cumulative_roi(self):
        from jornada_tracker import JornadaSummary
        # Three jornadas with identical stats → cum ROI = per-jornada ROI
        summaries = [
            JornadaSummary("d1", 4, 4, 3, 75.0, 1.55, 4.0, 38.75),
            JornadaSummary("d2", 4, 4, 3, 75.0, 1.55, 4.0, 38.75),
            JornadaSummary("d3", 4, 4, 3, 75.0, 1.55, 4.0, 38.75),
        ]
        cum = jt._cumulative(summaries)
        for c in cum:
            assert c == pytest.approx(38.75)


class TestVsExpected:
    def test_within_band(self):
        out = jt._vs_expected(roi=50.0, mean=50.0, std=10.0)
        assert "within band" in out

    def test_below_1sigma(self):
        out = jt._vs_expected(roi=35.0, mean=50.0, std=10.0)
        assert "below 1σ band" in out or "below mean" in out

    def test_above_2sigma(self):
        out = jt._vs_expected(roi=75.0, mean=50.0, std=10.0)
        assert "above mean" in out


class TestReport:
    def test_report_has_per_jornada_table(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        df = pl.read_parquet(path)
        summaries = jt._group_by_jornada(df)
        out = jt.render_report(summaries)
        assert "JORNADA ROI TRACKER" in out
        assert "Per-jornada breakdown" in out
        assert "2026-05-10" in out
        assert "Cumulative" in out

    def test_report_with_expected_band(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        df = pl.read_parquet(path)
        summaries = jt._group_by_jornada(df)
        out = jt.render_report(
            summaries, expected_roi_mean=50.6, expected_roi_std=15.07,
        )
        assert "Expected ROI band" in out
        assert "vs expected" in out

    def test_variance_check_kicks_in_at_3_jornadas(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        df = pl.read_parquet(path)
        summaries = jt._group_by_jornada(df)
        out = jt.render_report(
            summaries, expected_roi_mean=50.6, expected_roi_std=15.07,
        )
        # 3 jornadas → variance check should appear
        assert "Variance check" in out

    def test_no_settled_picks_message(self, tmp_path: Path):
        out = jt.render_report([])
        assert "No settled picks" in out


class TestMain:
    def test_main_runs(self, tmp_path: Path, capsys):
        path = _make_picks(tmp_path)
        rc = jt.main(["--picks", str(path)])
        assert rc == 0
        assert "JORNADA ROI TRACKER" in capsys.readouterr().out

    def test_main_with_profile(self, tmp_path: Path, capsys):
        path = _make_picks(tmp_path)
        rc = jt.main(["--picks", str(path), "--profile", "aggressive"])
        assert rc == 0
        assert "aggressive" in capsys.readouterr().out

    def test_main_unknown_profile_error(self, tmp_path: Path, capsys):
        path = _make_picks(tmp_path)
        rc = jt.main(["--picks", str(path), "--profile", "nonexistent"])
        assert rc == 2

    def test_main_writes_json_sidecar(self, tmp_path: Path):
        path = _make_picks(tmp_path)
        out_path = tmp_path / "out.json"
        rc = jt.main([
            "--picks", str(path), "--json-out", str(out_path),
            "--profile", "balanced",
        ])
        assert rc == 0
        assert out_path.exists()
        payload = json.loads(out_path.read_text())
        assert payload["profile"] == "balanced"
        assert len(payload["jornadas"]) == 3

    def test_main_missing_picks_error(self, tmp_path: Path):
        rc = jt.main(["--picks", str(tmp_path / "missing.parquet")])
        assert rc == 1
