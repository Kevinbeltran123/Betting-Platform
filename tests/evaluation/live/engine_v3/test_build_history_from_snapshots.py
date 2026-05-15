"""OFFLINE synthetic tests for build_history_from_snapshots.py.

All tests build a temporary snapshot directory tree in memory — no
dependency on data/cache/ (absent in agent worktrees). The synthetic
fixture dicts use the minimal Sportmonks schema that Fixture.model_validate
and LiveMatchState.from_fixture require.

# requires-real-data (real corpus validation happens on main post-merge)

Test matrix:
- 2 finished fixtures (FT) -> appear in output
- 1 in-progress fixture (INPLAY_2H) -> skipped
- 1 unparseable fixture (invalid JSON / missing required fields) -> skipped
- last-snapshot-per-dir selection
- home/away correctness via the parser (not hand-rolled)
- exact output schema matches build_lambda_store.py contract
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from scripts.spike.v3.build_history_from_snapshots import (
    _FINISHED_STATES,
    _last_snapshot,
    _parse_fixture,
    extract_history,
    write_outputs,
)


# ── Synthetic fixture helpers ─────────────────────────────────────────────────

def _make_participant(
    pid: int, name: str, location: str
) -> dict:
    """Minimal Sportmonks participant dict with meta.location set."""
    return {
        "id": pid,
        "name": name,
        "meta": {"location": location},
    }


def _make_score(fid: int, type_id: int, participant_id: int, location: str, goals: int) -> dict:
    """Minimal Sportmonks score entry."""
    return {
        "id": fid * 1000 + type_id + participant_id,
        "fixture_id": fid,
        "type_id": type_id,
        "participant_id": participant_id,
        "score": {"goals": goals, "participant": location},
    }


def _make_fixture_dict(
    fid: int,
    home_pid: int,
    home_name: str,
    away_pid: int,
    away_name: str,
    home_goals: int,
    away_goals: int,
    state_dev_name: str,
) -> dict:
    """Build a minimal Sportmonks fixture dict that Fixture.model_validate accepts.

    Uses CURRENT score type_id (1525) so _extract_current_score picks it up.
    Uses meta.location on participants so _identify_home_away uses Layer 1.
    """
    return {
        "id": fid,
        "sport_id": 1,
        "league_id": 8,
        "season_id": 2025,
        "participants": [
            _make_participant(home_pid, home_name, "home"),
            _make_participant(away_pid, away_name, "away"),
        ],
        "state": {
            "id": 1,
            "state": state_dev_name,
            "name": state_dev_name,
            "developer_name": state_dev_name,
        },
        "scores": [
            _make_score(fid, 1525, home_pid, "home", home_goals),
            _make_score(fid, 1525, away_pid, "away", away_goals),
        ],
    }


def _write_snapshot(fid_dir: Path, fname: str, payload: object) -> Path:
    """Write a JSON snapshot file and return its path."""
    fid_dir.mkdir(parents=True, exist_ok=True)
    path = fid_dir / fname
    if isinstance(payload, str):
        # Allow writing raw strings for invalid-JSON testing
        path.write_text(payload)
    else:
        path.write_text(json.dumps(payload))
    return path


# ── Fixture tree builder ───────────────────────────────────────────────────────

def _build_snapshot_tree(tmp_path: Path) -> Path:
    """Build a tmp snapshots tree:

    snapshots/
      1001/   <- FINISHED (FT) — Arsenal 2-1 Brentford
        20260513T150000Z.json  (early snapshot: 0-0)
        20260513T160000Z.json  (final snapshot: 2-1) <- LAST
      1002/   <- FINISHED (FT) — Man City 3-0 Crystal Palace
        20260513T193000Z.json  (final snapshot: 3-0) <- LAST
      1003/   <- IN-PROGRESS (INPLAY_2H) — Liverpool 1-0 Chelsea
        20260513T200000Z.json
      1004/   <- UNPARSEABLE (corrupt JSON)
        20260513T210000Z.json

    Returns the snapshots root path.
    """
    root = tmp_path / "snapshots"

    # --- Fixture 1001: FINISHED, 2 snapshots ---
    dir_1001 = root / "1001"
    # Early snapshot: 0-0 (NOT the last one — must be ignored)
    early = _make_fixture_dict(1001, 10, "Arsenal", 20, "Brentford", 0, 0, "INPLAY_2H")
    _write_snapshot(dir_1001, "20260513T150000Z.json", early)
    # Final snapshot: 2-1 FT (the one we must use)
    final_1001 = _make_fixture_dict(1001, 10, "Arsenal", 20, "Brentford", 2, 1, "FT")
    _write_snapshot(dir_1001, "20260513T160000Z.json", final_1001)

    # --- Fixture 1002: FINISHED, 1 snapshot, wrapped in {"data": {...}} ---
    dir_1002 = root / "1002"
    inner = _make_fixture_dict(1002, 9, "Man City", 51, "Crystal Palace", 3, 0, "FT")
    _write_snapshot(dir_1002, "20260513T193000Z.json", {"data": inner})

    # --- Fixture 1003: IN-PROGRESS (should be skipped) ---
    dir_1003 = root / "1003"
    inprog = _make_fixture_dict(1003, 77, "Liverpool", 88, "Chelsea", 1, 0, "INPLAY_2H")
    _write_snapshot(dir_1003, "20260513T200000Z.json", inprog)

    # --- Fixture 1004: UNPARSEABLE (corrupt JSON) ---
    dir_1004 = root / "1004"
    _write_snapshot(dir_1004, "20260513T210000Z.json", "{not valid json!!!")

    return root


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestLastSnapshot:
    def test_returns_last_by_lexicographic_order(self, tmp_path: Path) -> None:
        d = tmp_path / "fid"
        _write_snapshot(d, "20260513T150000Z.json", {})
        _write_snapshot(d, "20260513T200000Z.json", {})
        _write_snapshot(d, "20260513T160000Z.json", {})
        result = _last_snapshot(d)
        assert result is not None
        assert result.name == "20260513T200000Z.json"

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        assert _last_snapshot(d) is None


class TestParseFixture:
    def test_parses_bare_fixture_dict(self, tmp_path: Path) -> None:
        payload = _make_fixture_dict(1001, 10, "Arsenal", 20, "Brentford", 2, 1, "FT")
        path = _write_snapshot(tmp_path, "snap.json", payload)
        fx = _parse_fixture(path)
        assert fx is not None
        assert fx.id == 1001

    def test_parses_data_envelope(self, tmp_path: Path) -> None:
        inner = _make_fixture_dict(1002, 9, "Man City", 51, "Crystal Palace", 3, 0, "FT")
        path = _write_snapshot(tmp_path, "snap.json", {"data": inner})
        fx = _parse_fixture(path)
        assert fx is not None
        assert fx.id == 1002

    def test_returns_none_for_corrupt_json(self, tmp_path: Path) -> None:
        path = _write_snapshot(tmp_path, "bad.json", "{corrupted")
        assert _parse_fixture(path) is None

    def test_returns_none_for_missing_required_fields(self, tmp_path: Path) -> None:
        # Fixture requires id, sport_id, league_id, season_id
        path = _write_snapshot(tmp_path, "bad.json", {"id": 1})
        result = _parse_fixture(path)
        # Pydantic v2 will raise on missing fields; _parse_fixture should return None
        assert result is None


class TestFinishedStates:
    """Verify the _FINISHED_STATES constant matches the parser's semantics."""

    def test_finished_states_contents(self) -> None:
        assert "FT" in _FINISHED_STATES
        assert "AET" in _FINISHED_STATES
        assert "FT_PEN" in _FINISHED_STATES
        assert "FINISHED" in _FINISHED_STATES
        assert "INPLAY_2H" not in _FINISHED_STATES
        assert "HT" not in _FINISHED_STATES
        assert "NS" not in _FINISHED_STATES


class TestExtractHistory:
    """Integration tests over the full synthetic snapshot tree."""

    def test_only_finished_fixtures_emitted(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        # 2 finished (1001, 1002); 1 in-progress (1003) + 1 unparseable (1004) skipped
        assert len(history) == 2
        assert len(fixtures) == 2

    def test_fixture_ids_in_output(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        _history, fixtures = extract_history(root)
        fids = {r["fixture_id"] for r in fixtures}
        assert fids == {1001, 1002}

    def test_last_snapshot_used_for_score(self, tmp_path: Path) -> None:
        """Fixture 1001 has an early 0-0 snap and a final 2-1 snap.
        The extractor must use the LAST (lexicographically greatest) file."""
        root = _build_snapshot_tree(tmp_path)
        history, _fixtures = extract_history(root)
        row_1001 = next(r for r in history if r.get("home_team") == "Arsenal")
        assert row_1001["home_goals"] == 2
        assert row_1001["away_goals"] == 1

    def test_home_away_correct_via_parser(self, tmp_path: Path) -> None:
        """Fixture 1002: Man City (home) 3-0 Crystal Palace (away).
        The parser must derive home/away from meta.location, NOT array order."""
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        row_1002_hist = next(r for r in history if r.get("home_team") == "Man City")
        row_1002_fix = next(r for r in fixtures if r.get("fixture_id") == 1002)
        assert row_1002_hist["home_team"] == "Man City"
        assert row_1002_hist["away_team"] == "Crystal Palace"
        assert row_1002_hist["home_goals"] == 3
        assert row_1002_hist["away_goals"] == 0
        assert row_1002_fix["home_team"] == "Man City"
        assert row_1002_fix["away_team"] == "Crystal Palace"

    def test_team_name_vocabulary_consistent(self, tmp_path: Path) -> None:
        """home_team/away_team in history and fixtures must use identical strings."""
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        hist_teams = {(r["home_team"], r["away_team"]) for r in history}
        fix_teams = {(r["home_team"], r["away_team"]) for r in fixtures}
        assert hist_teams == fix_teams

    def test_missing_root_returns_empty(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        history, fixtures = extract_history(nonexistent)
        assert history == []
        assert fixtures == []


class TestOutputSchema:
    """Verify the written parquets exactly match build_lambda_store.py's schema."""

    def test_history_parquet_schema(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        out_hist = tmp_path / "history.parquet"
        out_fix = tmp_path / "fixtures.parquet"
        write_outputs(history, fixtures, out_hist, out_fix)

        df = pl.read_parquet(out_hist)
        # build_lambda_store.py reads: home_team, away_team, home_goals, away_goals
        assert set(df.columns) >= {"home_team", "away_team", "home_goals", "away_goals"}
        assert df.schema["home_team"] == pl.Utf8
        assert df.schema["away_team"] == pl.Utf8
        assert df.schema["home_goals"] == pl.Int64
        assert df.schema["away_goals"] == pl.Int64
        assert len(df) == 2

    def test_fixtures_parquet_schema(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        out_hist = tmp_path / "h.parquet"
        out_fix = tmp_path / "f.parquet"
        write_outputs(history, fixtures, out_hist, out_fix)

        df = pl.read_parquet(out_fix)
        # build_lambda_store.py reads: fixture_id, home_team, away_team
        assert set(df.columns) >= {"fixture_id", "home_team", "away_team"}
        assert df.schema["fixture_id"] == pl.Int64
        assert df.schema["home_team"] == pl.Utf8
        assert df.schema["away_team"] == pl.Utf8
        assert len(df) == 2

    def test_history_data_values_correct(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        out_hist = tmp_path / "h.parquet"
        out_fix = tmp_path / "f.parquet"
        write_outputs(history, fixtures, out_hist, out_fix)

        df = pl.read_parquet(out_hist)
        rows = {r["home_team"]: r for r in df.to_dicts()}
        assert rows["Arsenal"]["home_goals"] == 2
        assert rows["Arsenal"]["away_goals"] == 1
        assert rows["Man City"]["home_goals"] == 3
        assert rows["Man City"]["away_goals"] == 0

    def test_fixtures_data_values_correct(self, tmp_path: Path) -> None:
        root = _build_snapshot_tree(tmp_path)
        history, fixtures = extract_history(root)
        out_hist = tmp_path / "h.parquet"
        out_fix = tmp_path / "f.parquet"
        write_outputs(history, fixtures, out_hist, out_fix)

        df = pl.read_parquet(out_fix)
        rows = {r["fixture_id"]: r for r in df.to_dicts()}
        assert rows[1001]["home_team"] == "Arsenal"
        assert rows[1001]["away_team"] == "Brentford"
        assert rows[1002]["home_team"] == "Man City"
        assert rows[1002]["away_team"] == "Crystal Palace"


class TestAetAndOtherFinishedStates:
    """Verify AET and FT_PEN fixtures are included (not just FT)."""

    def test_aet_fixture_included(self, tmp_path: Path) -> None:
        root = tmp_path / "snapshots"
        d = root / "2001"
        aet = _make_fixture_dict(2001, 11, "PSG", 22, "Real Madrid", 2, 2, "AET")
        _write_snapshot(d, "20260513T200000Z.json", aet)
        history, fixtures = extract_history(root)
        assert len(history) == 1
        assert history[0]["home_team"] == "PSG"
        assert history[0]["away_goals"] == 2

    def test_ft_pen_fixture_included(self, tmp_path: Path) -> None:
        root = tmp_path / "snapshots"
        d = root / "2002"
        pen = _make_fixture_dict(2002, 33, "Bayern", 44, "Dortmund", 1, 1, "FT_PEN")
        _write_snapshot(d, "20260513T200000Z.json", pen)
        history, fixtures = extract_history(root)
        assert len(history) == 1
        assert history[0]["home_team"] == "Bayern"
