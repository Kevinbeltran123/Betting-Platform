"""Discover real API-Football team IDs for WC2026-relevant national teams.

The coach_history.py hardcoded IDs were guesses — most are wrong.
Real IDs are pulled via /teams?name=X. Output is a JSON mapping
team_name -> {id, code, country}.
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

# Same list as coach_history.CURRENT_COACHES
TEAMS_TO_DISCOVER = [
    # UEFA
    "France", "Germany", "England", "Spain", "Italy", "Portugal",
    "Netherlands", "Belgium", "Croatia", "Switzerland", "Denmark",
    "Poland", "Austria", "Turkey", "Norway", "Serbia", "Scotland",
    # CONMEBOL
    "Argentina", "Brazil", "Uruguay", "Colombia", "Ecuador", "Paraguay",
    # CAF
    "Morocco", "Senegal", "Egypt", "Algeria", "Tunisia", "Ghana",
    "Nigeria", "Ivory Coast", "Cameroon", "South Africa", "Mali",
    "Cape Verde",
    # AFC
    "Japan", "South Korea", "Australia", "Iran", "Saudi Arabia",
    "Uzbekistan", "Jordan",
    # CONCACAF
    "USA", "Mexico", "Canada", "Costa Rica", "Panama", "Jamaica",
    # OFC
    "New Zealand",
]


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API key")
        return 1

    discovered: dict[str, dict] = {}
    not_found: list[str] = []

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        t0 = time.time()
        print(f"Searching {len(TEAMS_TO_DISCOVER)} teams...\n")

        for i, name in enumerate(TEAMS_TO_DISCOVER, 1):
            # API-Football /teams supports ?name=X but for national teams we
            # also need to filter to NATIONAL teams (country=World) — they
            # appear in the "World" country.
            r = await client.get("/teams", params={"name": name})
            r.raise_for_status()
            payload = r.json()
            response = payload.get("response", [])

            # National teams have country=name (Argentina is in country
            # "Argentina") OR are tagged national=true. Filter accordingly.
            national_match = None
            for item in response:
                team = item.get("team", {})
                if team.get("national") is True:
                    national_match = team
                    break

            if national_match is None and response:
                # Fallback: pick first result anyway
                national_match = response[0].get("team")

            if national_match:
                discovered[name] = {
                    "id": national_match.get("id"),
                    "name": national_match.get("name"),
                    "code": national_match.get("code"),
                    "country": national_match.get("country"),
                    "national": national_match.get("national"),
                }
                print(f"  [{i:2}/{len(TEAMS_TO_DISCOVER)}] {name:20} → "
                      f"id={discovered[name]['id']:6} "
                      f"({discovered[name]['name']}, "
                      f"national={discovered[name]['national']})")
            else:
                not_found.append(name)
                print(f"  [{i:2}/{len(TEAMS_TO_DISCOVER)}] {name:20} → NOT FOUND")

        elapsed = time.time() - t0
        print(f"\nTotal: {len(discovered)} found, {len(not_found)} missing "
              f"({elapsed:.1f}s, {len(TEAMS_TO_DISCOVER) / max(elapsed/60, 1/60):.0f} req/min)")

    # Save discovered IDs
    out_path = Path(__file__).resolve().parents[4] / "data" / "cache" / "tsp" / "team_ids.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(discovered, indent=2))
    print(f"\nSaved: {out_path}")

    if not_found:
        print(f"\nNOT FOUND: {not_found}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
