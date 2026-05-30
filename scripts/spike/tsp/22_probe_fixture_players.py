"""Probe API-Football /fixtures/players to see what advanced stats are available
for international matches.

Output: print the schema of one player block for both teams of a recent
Argentina match, so we can design the team-level aggregation properly.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        # Step 1: find a recent Argentina friendly (Mar 2025 window)
        r = await client.get("/fixtures", params={"team": 26, "season": 2025})
        r.raise_for_status()
        fixtures = r.json().get("response", [])
        finished = [f for f in fixtures if f["fixture"]["status"]["short"] == "FT"]
        if not finished:
            print("No finished fixtures found")
            return 1
        # Pick the most recent
        finished.sort(key=lambda f: f["fixture"]["date"], reverse=True)
        sample = finished[0]
        fid = sample["fixture"]["id"]
        home = sample["teams"]["home"]["name"]
        away = sample["teams"]["away"]["name"]
        score = sample["score"]["fulltime"]
        print(f"\n--- Probing fixture {fid}: {home} {score['home']} - {score['away']} {away} ---\n")

        # Step 2: get players
        r2 = await client.get("/fixtures/players", params={"fixture": fid})
        r2.raise_for_status()
        payload = r2.json()
        teams = payload.get("response", [])
        if not teams:
            print("Empty /fixtures/players response")
            return 1

        # Show one player block per team
        for team_block in teams:
            tname = team_block.get("team", {}).get("name", "?")
            tid = team_block.get("team", {}).get("id", "?")
            players = team_block.get("players", [])
            print(f"\n=== Team: {tname} (id={tid}), n_players={len(players)} ===")
            if players:
                # Pick the starter with most minutes — most likely to have full stats
                top = max(players, key=lambda p: (p.get("statistics", [{}])[0].get("games", {}).get("minutes") or 0))
                print(f"Sample player: {top.get('player', {}).get('name', '?')}")
                print(json.dumps(top.get("statistics", [{}])[0], indent=2, default=str, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
