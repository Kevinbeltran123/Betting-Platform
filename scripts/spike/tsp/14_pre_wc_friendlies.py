"""Pull pre-WC2026 fixtures (friendlies + last qualifiers).

Window: today → 2026-06-11 (WC start).
For each profiled team, pull season=2026 fixtures, filter to NS/upcoming
inside window, dedupe by fixture_id, sort by date.

Output:
  - data/cache/tsp/pre_wc_fixtures.json — full list
  - Console table with: date, time, home vs away, league, status
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    FixturesResponse,
)

ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
OUT_PATH = ROOT / "data" / "cache" / "tsp" / "pre_wc_fixtures.json"

WC_START = date(2026, 6, 11)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    today = date.today()
    print(f"\nPulling fixtures for {len(team_ids)} teams")
    print(f"Window: {today} → {WC_START} (exclusive)\n")

    all_fixtures: dict[int, dict] = {}  # dedupe by fixture_id
    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        t0 = time.time()
        for i, (team_name, info) in enumerate(sorted(team_ids.items()), 1):
            team_id = info["id"]
            try:
                r = await client.get(
                    "/fixtures", params={"team": team_id, "season": 2026}
                )
                r.raise_for_status()
                parsed = FixturesResponse.model_validate(r.json())
                # Filter to NS (not started) within window
                upcoming = [
                    f for f in parsed.response
                    if today <= f.fixture.date.date() < WC_START
                    and f.fixture.status.short in ("NS", "TBD")
                ]
                for f in upcoming:
                    all_fixtures[f.fixture_id] = {
                        "fixture_id": f.fixture_id,
                        "date": f.fixture.date.isoformat(),
                        "league_id": f.league.id,
                        "league_name": f.league.name,
                        "league_country": f.league.country,
                        "home_team_id": f.teams.home.id,
                        "home_team_name": f.teams.home.name,
                        "away_team_id": f.teams.away.id,
                        "away_team_name": f.teams.away.name,
                        "status": f.fixture.status.short,
                    }
                print(f"  [{i:2}/{len(team_ids)}] {team_name:22} → {len(upcoming)} upcoming")
            except Exception as exc:
                print(f"  [{i:2}/{len(team_ids)}] {team_name:22} → FAIL ({exc})")

        elapsed = time.time() - t0
        print(f"\nElapsed: {elapsed:.1f}s")

    # Sort by date
    fixtures = sorted(all_fixtures.values(), key=lambda f: f["date"])

    # Save
    OUT_PATH.write_text(json.dumps(fixtures, indent=2))
    print(f"\nSaved: {OUT_PATH} ({len(fixtures)} unique fixtures)")

    # Console table
    profiled_names = {team_ids[n]["id"]: n for n in team_ids}
    print(f"\n{'=' * 110}")
    print(f"{'Date':<11} {'Time':<6} {'Home':<22} {'vs':<3} {'Away':<22} {'League':<35}")
    print(f"{'=' * 110}")
    for f in fixtures:
        dt = datetime.fromisoformat(f["date"].replace("Z", "+00:00"))
        h_profiled = "★" if f["home_team_id"] in profiled_names else " "
        a_profiled = "★" if f["away_team_id"] in profiled_names else " "
        both = "★★" if (h_profiled == "★" and a_profiled == "★") else f"{h_profiled}{a_profiled}"
        league_short = (f["league_name"] or "")[:32]
        print(
            f"{dt.date()} {dt.strftime('%H:%M')}  "
            f"{f['home_team_name']:<22} vs  {f['away_team_name']:<22} "
            f"{league_short:<35} {both}"
        )

    # Summary by league
    by_league: dict[str, int] = {}
    for f in fixtures:
        by_league[f["league_name"]] = by_league.get(f["league_name"], 0) + 1
    print(f"\n{'=' * 60}")
    print("By league:")
    for league, count in sorted(by_league.items(), key=lambda x: -x[1]):
        print(f"  {count:3} × {league}")

    # Both-profiled matches (★★)
    both_profiled = [
        f for f in fixtures
        if f["home_team_id"] in profiled_names and f["away_team_id"] in profiled_names
    ]
    print(f"\n★★ Both teams profiled: {len(both_profiled)}/{len(fixtures)}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
