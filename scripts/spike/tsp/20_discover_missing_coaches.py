"""Discover current coach for the 8 WC2026 teams not yet in CURRENT_COACHES.

Uses API-Football /coachs?team=X. Picks the active coach (no end date) with
the latest start date. Outputs proposed CoachRecord(...) literals to paste
into coach_history.CURRENT_COACHES.

Confederations are hard-coded from FIFA assignment.
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


# Confederation lookup (FIFA)
CONFEDERATION_OF: dict[str, str] = {
    "Bosnia and Herzegovina": "UEFA",
    "Curaçao": "CONCACAF",
    "Czech Republic": "UEFA",
    "DR Congo": "CAF",
    "Haiti": "CONCACAF",
    "Iraq": "AFC",
    "Qatar": "AFC",
    "Sweden": "UEFA",
}


async def get_active_coach(client: httpx.AsyncClient, team_id: int) -> dict | None:
    """Return the active head coach (latest career entry with no end date)."""
    r = await client.get("/coachs", params={"team": team_id})
    r.raise_for_status()
    response = r.json().get("response", [])
    if not response:
        return None

    # The /coachs response can contain multiple coaches (current + past). The
    # current coach has career[].end == None for the team in question.
    candidates = []
    for coach in response:
        career = coach.get("career", []) or []
        for entry in career:
            t = entry.get("team", {}) or {}
            if t.get("id") == team_id and entry.get("end") is None:
                start = entry.get("start")
                candidates.append((start, coach, entry))

    if not candidates:
        # Fallback: pick the most recent career entry overall
        for coach in response:
            career = coach.get("career", []) or []
            for entry in career:
                t = entry.get("team", {}) or {}
                if t.get("id") == team_id:
                    candidates.append((entry.get("start"), coach, entry))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0] or "", reverse=True)
    _, coach, entry = candidates[0]
    return {
        "coach_id": coach.get("id"),
        "coach_name": coach.get("name"),
        "start": entry.get("start"),
        "end": entry.get("end"),
    }


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    team_ids_path = Path(__file__).resolve().parents[4] / "data" / "cache" / "tsp" / "team_ids.json"
    team_ids = json.loads(team_ids_path.read_text())

    results: dict[str, dict] = {}

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        for name, conf in CONFEDERATION_OF.items():
            entry = team_ids.get(name)
            if not entry:
                print(f"!!! {name}: missing from team_ids.json")
                continue
            team_id = entry["id"]
            coach = await get_active_coach(client, team_id)
            if coach is None:
                print(f"  {name:30} (id={team_id}): NO COACH FOUND")
                continue
            results[name] = {
                "team_id": team_id,
                "confederation": conf,
                **coach,
            }
            print(f"  {name:30} (id={team_id}, conf={conf}): "
                  f"{coach['coach_name']} since {coach['start']} (end={coach['end']})")

    print("\n\n=== Proposed CURRENT_COACHES entries (paste into coach_history.py) ===\n")
    for name, info in results.items():
        start_str = info["start"] or "2020-01-01"
        try:
            d = datetime.strptime(start_str, "%Y-%m-%d").date()
            year, month, day = d.year, d.month, d.day
        except Exception:
            year, month, day = 2020, 1, 1
        py_name = name.replace("'", "\\'")
        coach_name = info["coach_name"].replace("'", "\\'") if info["coach_name"] else "Unknown"
        print(f'    "{py_name}": CoachRecord("{py_name}", {info["team_id"]}, '
              f'"{coach_name}", date({year}, {month}, {day}), "{info["confederation"]}"),')

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
