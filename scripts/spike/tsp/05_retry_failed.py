"""Retry teams that failed in backfill — Côte d'Ivoire (name fix), Jordan (timeout)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
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

ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles"

RETRIES = ["Côte d'Ivoire", "Jordan"]


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}
    coach_map = {n: r.confederation for n, r in CURRENT_COACHES.items()}

    def conf_lookup(tid: int) -> str:
        name = team_ids_by_id.get(tid)
        return coach_map.get(name, "UNK") if name else "UNK"

    today = date.today()

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(120.0),
    ) as client:
        for team_name in RETRIES:
            if team_name not in team_ids:
                print(f"  {team_name}: not in team_ids.json")
                continue
            team_id = team_ids[team_name]["id"]
            coach_rec = get_current_coach(team_name)
            if coach_rec is None:
                print(f"  {team_name}: not in coach_history — skip")
                continue
            filter_date = get_effective_filter_date(team_name) or date(2023, 1, 1)
            print(f"\nRetrying {team_name} (id={team_id}, {filter_date} → {today})...")

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
            print(f"  {len(finished)} finished fixtures since {filter_date}")

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
                    fixture=fix, team_id=team_id,
                    team_stats=team_stats, opponent_stats=opp_stats,
                    events=events_resp.response,
                    opponent_confederation_lookup=conf_lookup,
                )
                match_features.append(mf)

            tsv = compute_tsv(
                team_name=team_name,
                api_football_team_id=team_id,
                confederation=coach_rec.confederation,
                coach=CoachInfo(
                    coach_name=coach_rec.coach_name,
                    start_date=coach_rec.coach_start_date,
                ),
                matches=match_features,
                last_updated=datetime.now(),
            )
            safe_name = (
                team_name.replace(" ", "_").replace("'", "")
                .replace("Ô", "o").replace("ô", "o").lower()
            )
            out_path = OUT_DIR / f"{safe_name}_tsv.json"
            out_path.write_text(tsv.model_dump_json(indent=2))
            print(f"  ✓ n={tsv.n_matches} flag={tsv.flag} → {out_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
