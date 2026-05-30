"""Backfill TSV for the 10 WC2026 teams missing from the original 47-team profile run.

These were added to coach_history.CURRENT_COACHES + team_ids.json on 2026-05-28
after their WC2026 playoff qualification locked in.

Teams: Bosnia and Herzegovina, Cape Verde, Curaçao, Czech Republic, DR Congo,
Haiti, Iraq, Qatar, Sweden, Turkey.

Reuses the same flow as 04_backfill_all_teams.py. Per-team try/except so any
one team's failure doesn't abort the run.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
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


MISSING_10 = [
    "Bosnia and Herzegovina",
    "Cape Verde",
    "Curaçao",
    "Czech Republic",
    "DR Congo",
    "Haiti",
    "Iraq",
    "Qatar",
    "Sweden",
    "Turkey",
]


def _conf_lookup_factory(team_ids_by_id: dict[int, str], coach_map: dict[str, str]):
    def lookup(team_id: int) -> str:
        team_name = team_ids_by_id.get(team_id)
        if team_name is None:
            return "UNK"
        return coach_map.get(team_name, "UNK")
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
    t0 = time.time()

    seasons = list(range(filter_date.year, today.year + 1))
    all_fixtures = []
    for season in seasons:
        r = await client.get("/fixtures", params={"team": team_id, "season": season})
        r.raise_for_status()
        all_fixtures.extend(FixturesResponse.model_validate(r.json()).response)

    finished = [
        f for f in all_fixtures
        if f.is_finished and f.fixture.date.date() >= filter_date
    ]

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

        mf = extract_match_features(
            fixture=fix,
            team_id=team_id,
            team_stats=team_stats,
            opponent_stats=opp_stats,
            events=events_resp.response,
            opponent_confederation_lookup=conf_lookup,
        )
        match_features.append(mf)

    tsv = compute_tsv(
        team_name=team_name,
        api_football_team_id=team_id,
        confederation=confederation,
        coach=coach_info,
        matches=match_features,
        last_updated=datetime.now(),
    )

    out_path = OUT_DIR / f"{team_name.replace(' ', '_').replace(chr(39), '').lower()}_tsv.json"
    out_path.write_text(tsv.model_dump_json(indent=2))

    elapsed = time.time() - t0
    return (team_name, tsv.n_matches, tsv.flag, elapsed)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}
    coach_map = {name: rec.confederation for name, rec in CURRENT_COACHES.items()}
    conf_lookup = _conf_lookup_factory(team_ids_by_id, coach_map)

    today = date.today()
    succeeded = []
    failed = []

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        print(f"\n=== TSV backfill — {len(MISSING_10)} missing teams ===\n")
        t0 = time.time()

        for i, team_name in enumerate(MISSING_10, 1):
            entry = team_ids.get(team_name)
            if not entry:
                failed.append((team_name, "missing from team_ids.json"))
                print(f"  [{i:2}/{len(MISSING_10)}] {team_name:30} -> SKIP (no team_id)")
                continue
            team_id = entry["id"]

            coach_rec = get_current_coach(team_name)
            if coach_rec is None:
                failed.append((team_name, "not in CURRENT_COACHES"))
                print(f"  [{i:2}/{len(MISSING_10)}] {team_name:30} -> SKIP (no coach)")
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
                glyph = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(flag, "?")
                print(f"  [{i:2}/{len(MISSING_10)}] {team_name:30} -> "
                      f"n={n:3} {glyph} {flag:6} ({elapsed:.1f}s)")
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                failed.append((team_name, msg))
                print(f"  [{i:2}/{len(MISSING_10)}] {team_name:30} -> FAIL ({msg})")

        total_elapsed = time.time() - t0
        print(f"\n=== Done in {total_elapsed:.1f}s ===\n")

    by_flag = {"green": 0, "yellow": 0, "red": 0}
    for _, _, flag, _ in succeeded:
        by_flag[flag] = by_flag.get(flag, 0) + 1
    print("By flag:")
    for f, c in by_flag.items():
        print(f"  {f}: {c}")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for n, e in failed:
            print(f"  {n}: {e}")

    diag_path = OUT_DIR / "backfill_diagnostic_wc2026_missing.json"
    diag_path.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "total_attempted": len(MISSING_10),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "by_flag": by_flag,
        "succeeded_detail": [
            {"team": n, "n_matches": m, "flag": f, "elapsed_s": round(e, 2)}
            for n, m, f, e in succeeded
        ],
        "failed_detail": [{"team": n, "error": e} for n, e in failed],
        "total_elapsed_s": round(total_elapsed, 2),
    }, indent=2, ensure_ascii=False))
    print(f"\nDiagnostic saved: {diag_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
