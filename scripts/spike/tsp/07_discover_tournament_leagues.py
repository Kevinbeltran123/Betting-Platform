"""Discover league IDs for AFCON 2023, Copa America 2024, Euro 2024.

API-Football /leagues?search={name} returns matching leagues with their
IDs. We need the canonical IDs to pull tournament fixtures.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = ROOT / "data" / "cache" / "tsp" / "tournament_leagues.json"


SEARCHES = [
    ("AFCON_2023", "Africa Cup of Nations", 2023),
    ("Copa_2024", "Copa America", 2024),
    ("Euro_2024", "Euro Championship", 2024),
]


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1

    discovered: dict[str, dict] = {}

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        for key, name, season in SEARCHES:
            r = await client.get("/leagues", params={"search": name})
            r.raise_for_status()
            response = r.json().get("response", [])
            print(f"\n{name} ({season}):")
            for item in response[:5]:
                league = item.get("league", {})
                country = item.get("country", {})
                seasons = [s.get("year") for s in item.get("seasons", [])]
                print(
                    f"  id={league.get('id'):4} name={league.get('name'):40} "
                    f"country={country.get('name'):20} type={league.get('type')} "
                    f"seasons={seasons[-5:] if len(seasons) > 5 else seasons}"
                )
            # Heuristic: pick the one whose name closely matches + has the requested season
            best = None
            for item in response:
                league = item.get("league", {})
                lname = league.get("name", "").lower()
                seasons_years = [s.get("year") for s in item.get("seasons", [])]
                if name.lower() in lname and season in seasons_years:
                    best = {
                        "id": league.get("id"),
                        "name": league.get("name"),
                        "type": league.get("type"),
                        "country": item.get("country", {}).get("name"),
                        "season": season,
                    }
                    break
            if best:
                discovered[key] = best
                print(f"  → PICKED: id={best['id']} {best['name']}")
            else:
                print(f"  → NO MATCH FOUND")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(discovered, indent=2))
    print(f"\nSaved: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
