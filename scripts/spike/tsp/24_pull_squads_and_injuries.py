"""Snapshot current squad + active injuries for all 48 WC2026 teams.

Two endpoints, two passes:
  - /players/squads?team=X    -> active roster with positions, ages, jersey #
  - /injuries?team=X&season=Y -> active injuries (current season)

Output:
  data/cache/tsp/squads/{team}_squad.json
  data/cache/tsp/injuries/{team}_injuries.json

Cost: ~96 calls (48 teams × 2 endpoints).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[4]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
SQUADS_DIR = ROOT / "data" / "cache" / "tsp" / "squads"
INJURIES_DIR = ROOT / "data" / "cache" / "tsp" / "injuries"


WC2026_TEAMS = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde",
    "Colombia", "Croatia", "Curaçao", "Czech Republic", "DR Congo",
    "Ecuador", "Egypt", "England", "France", "Germany", "Ghana", "Haiti",
    "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco",
    "Netherlands", "New Zealand", "Norway", "Panama", "Paraguay",
    "Portugal", "Qatar", "Saudi Arabia", "Scotland", "Senegal",
    "South Africa", "South Korea", "Spain", "Sweden", "Switzerland",
    "Tunisia", "Turkey", "USA", "Uruguay", "Uzbekistan",
]


async def pull_squad(client: httpx.AsyncClient, team_id: int) -> dict:
    r = await client.get("/players/squads", params={"team": team_id})
    r.raise_for_status()
    payload = r.json()
    return payload.get("response", [{}])[0] if payload.get("response") else {}


async def pull_injuries(client: httpx.AsyncClient, team_id: int, season: int) -> list[dict]:
    r = await client.get("/injuries", params={"team": team_id, "season": season})
    r.raise_for_status()
    return r.json().get("response", [])


def summarize_squad(squad: dict) -> dict:
    """Compute aggregate stats over the squad roster."""
    players = squad.get("players", []) or []
    ages = [p.get("age") for p in players if p.get("age")]
    by_position = {}
    for p in players:
        pos = p.get("position") or "Unknown"
        by_position[pos] = by_position.get(pos, 0) + 1
    return {
        "n_players": len(players),
        "mean_age": round(mean(ages), 1) if ages else None,
        "median_age": median(ages) if ages else None,
        "min_age": min(ages) if ages else None,
        "max_age": max(ages) if ages else None,
        "by_position": by_position,
    }


def summarize_injuries(injuries: list[dict]) -> dict:
    """Group active injuries by player + type."""
    active = []
    for inj in injuries:
        pl = inj.get("player") or {}
        team = inj.get("team") or {}
        fix = inj.get("fixture") or {}
        active.append({
            "name": pl.get("name"),
            "position": pl.get("position"),
            "type": pl.get("type"),
            "reason": pl.get("reason"),
            "fixture_id": fix.get("id"),
            "league": (inj.get("league") or {}).get("name"),
            "date": (inj.get("fixture") or {}).get("date"),
        })
    return {"n": len(active), "active": active}


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    SQUADS_DIR.mkdir(parents=True, exist_ok=True)
    INJURIES_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    current_season = today.year if today.month >= 7 else today.year - 1

    succeeded: list[tuple[str, dict, dict]] = []
    failed: list[tuple[str, str]] = []

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        print(f"\n=== Squad + injuries snapshot — {len(WC2026_TEAMS)} teams (season {current_season}) ===\n")
        t0 = time.time()

        for i, name in enumerate(WC2026_TEAMS, 1):
            entry = team_ids.get(name)
            if not entry:
                failed.append((name, "no team_id"))
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {name:30} -> SKIP (no team_id)")
                continue
            team_id = entry["id"]

            try:
                squad = await pull_squad(client, team_id)
                injuries = await pull_injuries(client, team_id, current_season)

                squad_path = SQUADS_DIR / f"{name.replace(' ', '_').replace(chr(39), '').lower()}.json"
                squad_path.write_text(json.dumps({
                    "team_name": name,
                    "team_id": team_id,
                    "season": current_season,
                    "snapshot_at": datetime.now().isoformat(),
                    "summary": summarize_squad(squad),
                    "raw": squad,
                }, indent=2, ensure_ascii=False))

                inj_path = INJURIES_DIR / f"{name.replace(' ', '_').replace(chr(39), '').lower()}.json"
                inj_path.write_text(json.dumps({
                    "team_name": name,
                    "team_id": team_id,
                    "season": current_season,
                    "snapshot_at": datetime.now().isoformat(),
                    "summary": summarize_injuries(injuries),
                }, indent=2, ensure_ascii=False))

                ss = summarize_squad(squad)
                isum = summarize_injuries(injuries)
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {name:30} -> "
                      f"squad={ss['n_players']:2} (mean_age={ss['mean_age']}), "
                      f"injuries={isum['n']}")
                succeeded.append((name, ss, isum))
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                failed.append((name, msg))
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {name:30} -> FAIL ({msg})")

        elapsed = time.time() - t0

    print(f"\n=== Done in {elapsed:.1f}s. Profiled: {len(succeeded)}/{len(WC2026_TEAMS)} ===")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for n, e in failed:
            print(f"  {n}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
