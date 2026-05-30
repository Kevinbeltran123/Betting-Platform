"""Discover API-Football team IDs for the 10 WC2026 teams missing from team_ids.json.

The original discovery (02) ran 2026-05-24, before WC2026 playoff results
locked these 10 teams. We need their real API-Football IDs to backfill TSV.

Output: merges new IDs into data/cache/tsp/team_ids.json (keyed by canonical
English name used in coach_history.CURRENT_COACHES).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv


MISSING_TEAMS = [
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


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY in environment")
        return 1

    discovered: dict[str, dict] = {}
    not_found: list[str] = []

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        t0 = time.time()
        print(f"Searching {len(MISSING_TEAMS)} missing teams...\n")

        for i, name in enumerate(MISSING_TEAMS, 1):
            r = await client.get("/teams", params={"name": name})
            r.raise_for_status()
            payload = r.json()
            response = payload.get("response", [])

            national_match = None
            for item in response:
                team = item.get("team", {})
                if team.get("national") is True:
                    national_match = team
                    break

            if national_match is None and response:
                national_match = response[0].get("team")

            if national_match:
                discovered[name] = {
                    "id": national_match.get("id"),
                    "name": national_match.get("name"),
                    "code": national_match.get("code"),
                    "country": national_match.get("country"),
                    "national": national_match.get("national"),
                }
                print(f"  [{i:2}/{len(MISSING_TEAMS)}] {name:30} -> "
                      f"id={discovered[name]['id']:6} "
                      f"({discovered[name]['name']}, national={discovered[name]['national']})")
            else:
                not_found.append(name)
                print(f"  [{i:2}/{len(MISSING_TEAMS)}] {name:30} -> NOT FOUND")

        elapsed = time.time() - t0
        print(f"\nFound: {len(discovered)}, missing: {len(not_found)}, elapsed: {elapsed:.1f}s")

    out_path = Path(__file__).resolve().parents[4] / "data" / "cache" / "tsp" / "team_ids.json"
    if out_path.exists():
        existing = json.loads(out_path.read_text())
    else:
        existing = {}

    before = len(existing)
    existing.update(discovered)
    out_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"\nMerged into {out_path}: {before} -> {len(existing)} entries.")

    if not_found:
        print(f"\nSTILL NOT FOUND: {not_found}")
        print("Action: search /teams/countries to find correct keyword.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
