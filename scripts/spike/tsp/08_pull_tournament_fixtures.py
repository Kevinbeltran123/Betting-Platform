"""Pull fixtures + outcomes for AFCON23 / Copa24 / Euro24.

For each tournament:
  1. Pull /fixtures?league=X&season=Y  (1 call)
  2. Save fixtures with parsed home/away + scores + dates
  3. Build unique participant list

Outputs:
  data/cache/tsp/tournaments/{key}_fixtures.json — list of fixture dicts
  data/cache/tsp/tournaments/{key}_participants.json — team IDs in tournament
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    FixturesResponse,
)

ROOT = Path(__file__).resolve().parents[3]
LEAGUES_PATH = ROOT / "data" / "cache" / "tsp" / "tournament_leagues.json"
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "tournaments"


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    leagues = json.loads(LEAGUES_PATH.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        for key, info in leagues.items():
            league_id = info["id"]
            season = info["season"]
            print(f"\n{key}: league={league_id}, season={season}")
            r = await client.get("/fixtures", params={"league": league_id, "season": season})
            r.raise_for_status()
            payload = r.json()
            parsed = FixturesResponse.model_validate(payload)
            finished = [f for f in parsed.response if f.is_finished]
            print(f"  {len(parsed.response)} total, {len(finished)} finished")

            # Compact storage
            fixtures_compact = []
            participants: set[int] = set()
            tournament_start = min(f.fixture.date for f in parsed.response).date()
            for f in parsed.response:
                home_id = f.teams.home.id
                away_id = f.teams.away.id
                participants.add(home_id)
                participants.add(away_id)
                fixtures_compact.append({
                    "fixture_id": f.fixture_id,
                    "date": f.fixture.date.isoformat(),
                    "home_team_id": home_id,
                    "home_team_name": f.teams.home.name,
                    "away_team_id": away_id,
                    "away_team_name": f.teams.away.name,
                    "home_goals": f.goals.home,
                    "away_goals": f.goals.away,
                    "ht_home": f.score.halftime.home,
                    "ht_away": f.score.halftime.away,
                    "status": f.fixture.status.short,
                    "is_finished": f.is_finished,
                })

            # Save
            fixtures_path = OUT_DIR / f"{key}_fixtures.json"
            fixtures_path.write_text(json.dumps(fixtures_compact, indent=2))
            participants_path = OUT_DIR / f"{key}_participants.json"
            participants_path.write_text(json.dumps({
                "tournament_start": tournament_start.isoformat(),
                "participant_team_ids": sorted(participants),
                "n_participants": len(participants),
                "n_fixtures": len(parsed.response),
                "n_finished": len(finished),
            }, indent=2))
            print(f"  Tournament start: {tournament_start}")
            print(f"  Participants: {len(participants)}")
            print(f"  Saved: {fixtures_path.name}, {participants_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
