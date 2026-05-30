"""Resolve the 4 team_ids that script 18 failed to find.

API-Football quirks:
  - Turkey rebranded to "Türkiye" officially in 2022
  - Cape Verde appears as "Cabo Verde"
  - DR Congo as "Congo DR"
  - Bosnia and Herzegovina as "Bosnia and Herzegovina" or "Bosnia"

Strategy: try each alternative; if still NOT FOUND, fall back to /teams
with country search.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


CANDIDATES: dict[str, list[str]] = {
    "Bosnia and Herzegovina": ["Bosnia", "Bosnia and Herzegovina", "Bosnia-Herzegovina"],
    "Cape Verde": ["Cabo Verde", "Cape Verde Islands", "Cabo"],
    "DR Congo": ["Congo DR", "DR Congo", "Democratic Republic of Congo", "Congo"],
    "Turkey": ["Türkiye", "Turkiye", "Turkey"],
}


async def search_team(client: httpx.AsyncClient, name: str) -> dict | None:
    """Search /teams?name=X and return the first national-team match."""
    r = await client.get("/teams", params={"name": name})
    r.raise_for_status()
    response = r.json().get("response", [])
    for item in response:
        team = item.get("team", {})
        if team.get("national") is True:
            return team
    if response:
        return response[0].get("team")
    return None


async def search_by_country(client: httpx.AsyncClient, country: str) -> dict | None:
    """Fallback: /teams?country=X filtered to national teams."""
    r = await client.get("/teams", params={"country": country})
    r.raise_for_status()
    response = r.json().get("response", [])
    for item in response:
        team = item.get("team", {})
        if team.get("national") is True:
            return team
    return None


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    discovered: dict[str, dict] = {}

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        for canonical, alts in CANDIDATES.items():
            print(f"\n--- {canonical} ---")
            found = None
            for alt in alts:
                team = await search_team(client, alt)
                if team:
                    found = team
                    print(f"  ✓ '{alt}' -> id={team.get('id')} ({team.get('name')}, "
                          f"country={team.get('country')}, national={team.get('national')})")
                    break
                else:
                    print(f"  ✗ '{alt}' -> not found")

            if not found:
                # Last resort: country-based search
                for country in alts:
                    team = await search_by_country(client, country)
                    if team:
                        found = team
                        print(f"  ✓ (country={country}) -> id={team.get('id')} ({team.get('name')})")
                        break

            if found:
                discovered[canonical] = {
                    "id": found.get("id"),
                    "name": found.get("name"),
                    "code": found.get("code"),
                    "country": found.get("country"),
                    "national": found.get("national"),
                }
            else:
                print(f"  !!! STILL NOT FOUND — manual lookup needed.")

    # Merge into team_ids.json (using the path the rest of TSP code uses)
    out_path = Path(__file__).resolve().parents[4] / "data" / "cache" / "tsp" / "team_ids.json"
    existing = json.loads(out_path.read_text()) if out_path.exists() else {}
    before = len(existing)
    existing.update(discovered)
    out_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"\n\nMerged into {out_path}: {before} -> {len(existing)}.")
    print(f"Resolved: {sorted(discovered.keys())}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
