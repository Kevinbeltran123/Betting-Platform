"""Extract FINISHED fixture history from raw Sportmonks snapshots.

BOOTSTRAP / LOW-CONFIDENCE WARNING
===================================
This script is a structure-first bootstrap that turns the ~176 already-
collected Sportmonks club-fixture snapshots into the input format that
``build_lambda_store.py`` expects. With ~176 matches across many leagues
the resulting Dixon-Coles model is THIN and should NOT be used as a
production prior. It validates the full wiring (snapshot -> history ->
lambda store -> derive_priors_from_fixture -> ML-lambda tier) without
spending API quota. Real per-league seasonal corpus is a separate
follow-up.

# requires-real-data

Usage
-----
    uv run python scripts/spike/v3/build_history_from_snapshots.py \\
        --snapshots-root data/cache/sportmonks/snapshots \\
        --out-history    data/cache/lambda_history.parquet \\
        --out-fixtures   data/cache/lambda_fixtures.parquet

Input layout
------------
    <snapshots-root>/<fixture_id>/<timestamp>.json

Each JSON file is either a raw Sportmonks fixture dict or wrapped in a
``{"data": {...}}`` envelope (same as the cache format used by the live
watcher). The LAST snapshot per fixture directory (lexicographic max)
is used for the final score, exactly as in regrade_day4_from_raw.py.

Output schema (matches build_lambda_store.py contract)
------------------------------------------------------
history.parquet
    home_team  str   — home team name (parser-derived)
    away_team  str   — away team name (parser-derived)
    home_goals int   — final home goals
    away_goals int   — final away goals

fixtures.parquet
    fixture_id int   — Sportmonks fixture ID
    home_team  str   — home team name (same vocabulary as history)
    away_team  str   — away team name (same vocabulary as history)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.match_state import LiveMatchState  # noqa: E402
from bip.sports.football.sportmonks.schemas import Fixture  # noqa: E402

log = logging.getLogger("v3.build_history")

# Sportmonks developer_name values that indicate a fixture is truly finished.
_FINISHED_STATES: frozenset[str] = frozenset({"FT", "AET", "FT_PEN", "FINISHED"})

# Bootstrap marker embedded in log output so downstream consumers can see
# this data was produced from thin corpus, not a full seasonal dataset.
_BOOTSTRAP_BANNER = (
    "\n"
    "=" * 72 + "\n"
    "  BOOTSTRAP / LOW-CONFIDENCE DATA\n"
    "  Source: ~176 Sportmonks snapshots (multi-league, thin corpus)\n"
    "  DO NOT use the resulting lambda store as a production prior.\n"
    "  Validates wiring ONLY. Real seasonal corpus is a separate task.\n"
    "=" * 72
)


def _last_snapshot(fid_dir: Path) -> Path | None:
    """Return the lexicographically last .json file in ``fid_dir``.

    Snapshot filenames are ISO-sorted timestamps (e.g. 20260513T193000Z.json),
    so the lexicographic maximum is also the chronological last.
    """
    jsons = sorted(fid_dir.glob("*.json"))
    return jsons[-1] if jsons else None


def _parse_fixture(path: Path) -> Fixture | None:
    """Parse a snapshot JSON file into a Fixture model.

    Mirrors the pattern used in regrade_day4_from_raw.py:
      raw  = json.load(path)
      data = raw.get("data", raw)   # handle envelope OR bare dict
      fx   = Fixture.model_validate(data)

    Returns None on any parse failure (invalid JSON, schema mismatch, etc.).
    """
    try:
        raw = json.loads(path.read_text())
    except Exception as exc:
        log.debug("json_load_error path=%s err=%s", path, exc)
        return None
    fx_data = raw.get("data", raw) if isinstance(raw, dict) else raw
    try:
        return Fixture.model_validate(fx_data)
    except Exception as exc:
        log.debug("fixture_validate_error path=%s err=%s", path, exc)
        return None


def extract_history(
    snapshots_root: Path,
) -> tuple[list[dict], list[dict]]:
    """Walk ``snapshots_root/<fid>/`` dirs and return (history_rows, fixture_rows).

    Each ``fid`` directory is assumed to contain one or more timestamped
    JSON snapshots. Only the LAST snapshot per directory is parsed. Only
    FINISHED fixtures (state.developer_name in _FINISHED_STATES) are
    included in the output.

    Returns
    -------
    history_rows
        Dicts with keys: home_team, away_team, home_goals, away_goals.
    fixture_rows
        Dicts with keys: fixture_id, home_team, away_team.
        (The same parser-derived team-name vocabulary is used in both,
        so build_lambda_store.py can cross-reference them correctly.)
    """
    history_rows: list[dict] = []
    fixture_rows: list[dict] = []
    skip_reasons: Counter[str] = Counter()

    if not snapshots_root.exists():
        log.error("snapshots_root not found: %s", snapshots_root)
        return [], []

    fid_dirs = sorted(
        (d for d in snapshots_root.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    n_dirs = len(fid_dirs)
    log.info("Scanning %d fixture dirs under %s", n_dirs, snapshots_root)

    for fid_dir in fid_dirs:
        fid = int(fid_dir.name)

        # Pick the last (most complete) snapshot in the directory.
        snap_path = _last_snapshot(fid_dir)
        if snap_path is None:
            skip_reasons["no_json_files"] += 1
            log.debug("skip fid=%d reason=no_json_files", fid)
            continue

        # Parse via the EXISTING fixed parser — NOT hand-rolled JSON extraction.
        # This is critical: the home/away bug (abb4a16) lived in hand-rolled
        # score extraction, not in LiveMatchState.from_fixture.
        fx = _parse_fixture(snap_path)
        if fx is None:
            skip_reasons["parse_error"] += 1
            log.warning("skip fid=%d snap=%s reason=parse_error", fid, snap_path.name)
            continue

        try:
            state = LiveMatchState.from_fixture(fx)
        except Exception as exc:
            skip_reasons["from_fixture_error"] += 1
            log.warning(
                "skip fid=%d snap=%s reason=from_fixture_error err=%s",
                fid, snap_path.name, exc,
            )
            continue

        # State check: only FINISHED fixtures contribute to history.
        dev_name = fx.state.developer_name if fx.state else ""
        if dev_name not in _FINISHED_STATES:
            skip_reasons[f"not_finished:{dev_name}"] += 1
            log.debug(
                "skip fid=%d dev_name=%r reason=not_finished", fid, dev_name
            )
            continue

        home_team = state.home_team_name
        away_team = state.away_team_name
        home_goals = state.home_goals
        away_goals = state.away_goals

        history_rows.append({
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": home_goals,
            "away_goals": away_goals,
        })
        fixture_rows.append({
            "fixture_id": fid,
            "home_team": home_team,
            "away_team": away_team,
        })
        log.debug(
            "ok fid=%d %s %d-%d %s state=%s",
            fid, home_team, home_goals, away_goals, away_team, dev_name,
        )

    n_finished = len(history_rows)
    n_skipped = sum(skip_reasons.values())
    log.info(
        "Summary: dirs=%d finished=%d skipped=%d reasons=%s",
        n_dirs, n_finished, n_skipped, dict(skip_reasons),
    )
    return history_rows, fixture_rows


def write_outputs(
    history_rows: list[dict],
    fixture_rows: list[dict],
    out_history: Path,
    out_fixtures: Path,
) -> None:
    """Write history and fixtures parquets in build_lambda_store.py schema."""
    out_history.parent.mkdir(parents=True, exist_ok=True)
    out_fixtures.parent.mkdir(parents=True, exist_ok=True)

    hist_df = pl.DataFrame({
        "home_team": [r["home_team"] for r in history_rows],
        "away_team": [r["away_team"] for r in history_rows],
        "home_goals": [r["home_goals"] for r in history_rows],
        "away_goals": [r["away_goals"] for r in history_rows],
    }).with_columns([
        pl.col("home_team").cast(pl.Utf8),
        pl.col("away_team").cast(pl.Utf8),
        pl.col("home_goals").cast(pl.Int64),
        pl.col("away_goals").cast(pl.Int64),
    ])
    hist_df.write_parquet(out_history)
    log.info("Wrote history.parquet: %d rows -> %s", len(history_rows), out_history)

    fix_df = pl.DataFrame({
        "fixture_id": [r["fixture_id"] for r in fixture_rows],
        "home_team": [r["home_team"] for r in fixture_rows],
        "away_team": [r["away_team"] for r in fixture_rows],
    }).with_columns([
        pl.col("fixture_id").cast(pl.Int64),
        pl.col("home_team").cast(pl.Utf8),
        pl.col("away_team").cast(pl.Utf8),
    ])
    fix_df.write_parquet(out_fixtures)
    log.info("Wrote fixtures.parquet: %d rows -> %s", len(fixture_rows), out_fixtures)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Extract FINISHED fixture history from raw Sportmonks snapshots "
            "and write history+fixtures parquets for build_lambda_store.py. "
            "BOOTSTRAP / low-confidence — thin corpus. See module docstring."
        )
    )
    parser.add_argument(
        "--snapshots-root",
        type=Path,
        default=Path("data/cache/sportmonks/snapshots"),
        help="Root directory containing <fixture_id>/*.json dirs",
    )
    parser.add_argument(
        "--out-history",
        type=Path,
        default=Path("data/cache/lambda_history.parquet"),
        help="Output path for history parquet (home_team, away_team, home_goals, away_goals)",
    )
    parser.add_argument(
        "--out-fixtures",
        type=Path,
        default=Path("data/cache/lambda_fixtures.parquet"),
        help="Output path for fixtures parquet (fixture_id, home_team, away_team)",
    )
    args = parser.parse_args(argv)

    print(_BOOTSTRAP_BANNER)

    history_rows, fixture_rows = extract_history(args.snapshots_root)

    if not history_rows:
        log.error("No FINISHED fixtures found — nothing to write.")
        return 1

    write_outputs(history_rows, fixture_rows, args.out_history, args.out_fixtures)

    print(_BOOTSTRAP_BANNER)
    print(
        f"  Finished fixtures extracted: {len(history_rows)}\n"
        f"  history  -> {args.out_history}\n"
        f"  fixtures -> {args.out_fixtures}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
