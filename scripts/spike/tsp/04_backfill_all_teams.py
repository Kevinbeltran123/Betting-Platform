"""Backfill TSV for all 47 WC2026-relevant national teams.

Reads team_ids.json + coach_history. For each team:
  1. Pull /fixtures looped over seasons since DT start (or 2023-01-01).
  2. Filter to FT/AET matches.
  3. Per match: pull /statistics + /events.
  4. Compute TSV via tsv_calculator.
  5. Save individual JSON to data/cache/tsp/profiles/{team}.json.
  6. Emit per-team summary line + final diagnostic.

Error handling: per-team try/except — one team failure doesn't abort
the whole run. Failed teams listed at the end.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    EventsResponse,
    FixturesResponse,
    StatsResponse,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    CURRENT_COACHES,
    get_current_coach,
    get_effective_filter_date,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_calculator import (
    compute_tsv,
    extract_match_features,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import CoachInfo


ROOT = Path(__file__).resolve().parents[4]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles"


def _conf_lookup_factory(team_ids_by_id: dict[int, str], coach_map: dict[str, str]):
    """Build a closure that maps API-Football team_id -> confederation."""
    def lookup(team_id: int) -> str:
        team_name = team_ids_by_id.get(team_id)
        if team_name is None:
            return "UNK"
        coach_record = coach_map.get(team_name)
        if coach_record is None:
            return "UNK"
        return coach_record  # already the confederation string

    return lookup


async def profile_one_team(
    client: httpx.AsyncClient,
    team_name: str,
    team_id: int,
    confederation: str,
    coach_info: CoachInfo,
    filter_date: date,
    today: date,
    conf_lookup,
) -> tuple[str, int, str, float]:
    """Returns (team_name, n_matches, flag, elapsed_seconds)."""
    t0 = time.time()
    api_calls = 0

    # Pull fixtures across seasons since filter_date.
    seasons = list(range(filter_date.year, today.year + 1))
    all_fixtures = []
    for season in seasons:
        r = await client.get(
            "/fixtures", params={"team": team_id, "season": season}
        )
        r.raise_for_status()
        all_fixtures.extend(FixturesResponse.model_validate(r.json()).response)
        api_calls += 1

    finished = [
        f for f in all_fixtures
        if f.is_finished and f.fixture.date.date() >= filter_date
    ]

    # Per-fixture stats + events
    match_features = []
    for fix in finished:
        fid = fix.fixture_id
        r_stats = await client.get("/fixtures/statistics", params={"fixture": fid})
        r_stats.raise_for_status()
        stats_resp = StatsResponse.model_validate(r_stats.json())
        team_stats = stats_resp.for_team(team_id)
        opp_id = (
            fix.teams.away.id if team_id == fix.teams.home.id
            else fix.teams.home.id
        )
        opp_stats = stats_resp.for_team(opp_id)

        r_events = await client.get("/fixtures/events", params={"fixture": fid})
        r_events.raise_for_status()
        events_resp = EventsResponse.model_validate(r_events.json())

        api_calls += 2

        mf = extract_match_features(
            fixture=fix,
            team_id=team_id,
            team_stats=team_stats,
            opponent_stats=opp_stats,
            events=events_resp.response,
            opponent_confederation_lookup=conf_lookup,
        )
        match_features.append(mf)

    # Compute TSV
    tsv = compute_tsv(
        team_name=team_name,
        api_football_team_id=team_id,
        confederation=confederation,
        coach=coach_info,
        matches=match_features,
        last_updated=datetime.now(),
    )

    # Save
    out_path = OUT_DIR / f"{team_name.replace(' ', '_').replace(chr(39), '').lower()}_tsv.json"
    out_path.write_text(tsv.model_dump_json(indent=2))

    elapsed = time.time() - t0
    return (team_name, tsv.n_matches, tsv.flag, elapsed)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API key")
        return 1

    if not TEAM_IDS_PATH.exists():
        print(f"ERROR: {TEAM_IDS_PATH} not found. Run 02_discover_team_ids.py first.")
        return 1
    team_ids: dict[str, dict] = json.loads(TEAM_IDS_PATH.read_text())

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Inverse map for opponent confederation lookup
    team_ids_by_id: dict[int, str] = {
        rec["id"]: name for name, rec in team_ids.items() if rec.get("id")
    }
    coach_map = {name: rec.confederation for name, rec in CURRENT_COACHES.items()}
    conf_lookup = _conf_lookup_factory(team_ids_by_id, coach_map)

    today = date.today()
    succeeded: list[tuple[str, int, str, float]] = []
    failed: list[tuple[str, str]] = []

    # Order: prioritize WC2026 likely participants. We pull all 47 anyway.
    teams_in_order = sorted(team_ids.keys())

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        print(f"\n=== TSV Backfill — {len(teams_in_order)} teams ===\n")
        t0 = time.time()
        total_api_calls = 0

        for i, team_name in enumerate(teams_in_order, 1):
            team_id = team_ids[team_name]["id"]
            coach_rec = get_current_coach(team_name)
            if coach_rec is None:
                print(f"  [{i:2}/{len(teams_in_order)}] {team_name:20} → "
                      f"SKIP (not in coach_history)")
                failed.append((team_name, "not in coach_history"))
                continue

            filter_date = get_effective_filter_date(team_name)
            assert filter_date is not None

            try:
                result = await profile_one_team(
                    client=client,
                    team_name=team_name,
                    team_id=team_id,
                    confederation=coach_rec.confederation,
                    coach_info=CoachInfo(
                        coach_name=coach_rec.coach_name,
                        start_date=coach_rec.coach_start_date,
                    ),
                    filter_date=filter_date,
                    today=today,
                    conf_lookup=conf_lookup,
                )
                succeeded.append(result)
                _, n, flag, elapsed = result
                flag_glyph = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(flag, "?")
                print(f"  [{i:2}/{len(teams_in_order)}] {team_name:20} → "
                      f"n={n:3} {flag_glyph} {flag:6} ({elapsed:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                failed.append((team_name, msg))
                print(f"  [{i:2}/{len(teams_in_order)}] {team_name:20} → "
                      f"FAIL ({msg})")

        total_elapsed = time.time() - t0
        print(f"\n=== Backfill complete in {total_elapsed:.1f}s ===\n")

    # Summary
    by_flag: dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
    by_conf: dict[str, dict[str, int]] = {}
    for name, n, flag, _ in succeeded:
        by_flag[flag] = by_flag.get(flag, 0) + 1
        coach_rec = get_current_coach(name)
        if coach_rec:
            conf = coach_rec.confederation
            by_conf.setdefault(conf, {"green": 0, "yellow": 0, "red": 0})
            by_conf[conf][flag] += 1

    print("Summary by flag:")
    for flag, cnt in by_flag.items():
        print(f"  {flag}: {cnt}")

    print("\nSummary by confederation:")
    for conf in sorted(by_conf.keys()):
        c = by_conf[conf]
        print(f"  {conf:10}: green={c['green']:2}, yellow={c['yellow']:2}, red={c['red']:2}")

    if failed:
        print(f"\nFailed teams ({len(failed)}):")
        for name, err in failed:
            print(f"  {name}: {err}")

    # Write diagnostic
    diag_path = OUT_DIR / "backfill_diagnostic.json"
    diag_path.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "total_attempted": len(teams_in_order),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "by_flag": by_flag,
        "by_confederation": by_conf,
        "succeeded_detail": [
            {"team": n, "n_matches": m, "flag": f, "elapsed_s": round(e, 2)}
            for n, m, f, e in succeeded
        ],
        "failed_detail": [{"team": n, "error": e} for n, e in failed],
        "total_elapsed_s": round(total_elapsed, 2),
    }, indent=2))
    print(f"\nDiagnostic saved: {diag_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
