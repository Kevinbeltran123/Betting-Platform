"""WC22 experiment: did pre-tournament friendlies predict WC22 performance?

Workflow:
  1. Pull WC22 fixtures (league=1, season=2022) → identify 32 participants.
  2. WC22 started 2022-11-20. Pre-tournament window: 2022-09-01 to 2022-11-19.
  3. For each participant, pull their 2022 fixtures.
     - Friendlies (league=10) in [2022-09-01, 2022-11-19] = pre-WC22 amistosos.
     - WC22 fixtures (league=1) = tournament performance.
  4. For each fixture: pull /statistics + /events.
  5. Compute per-team stats: friendlies aggregates vs WC22 aggregates.
  6. Correlation analysis: does friendly GF predict WC GF? etc.

Output: data/cache/tsp/wc22_friendlies_analysis.json + console report.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    EventsResponse,
    FixturesResponse,
    StatsResponse,
)

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "wc22_analysis"
OUT_PATH = OUT_DIR / "summary.json"

WC22_LEAGUE_ID = 1   # FIFA World Cup (will verify)
FRIENDLIES_LEAGUE_ID = 10
WC22_START = date(2022, 11, 20)
WC22_FINAL = date(2022, 12, 18)
PRE_WC22_FROM = date(2022, 9, 1)
PRE_WC22_TO = date(2022, 11, 19)


def _league_name(league_id: int) -> str:
    return {1: "World Cup", 10: "Friendlies"}.get(league_id, str(league_id))


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        # Step 1: Pull WC22 fixtures
        print("[1/4] Pulling WC22 fixtures (league=1, season=2022)...")
        r = await client.get("/fixtures", params={"league": 1, "season": 2022})
        r.raise_for_status()
        wc22_fixtures = FixturesResponse.model_validate(r.json()).response
        print(f"  {len(wc22_fixtures)} fixtures")
        # Save
        (OUT_DIR / "wc22_fixtures.json").write_text(json.dumps(
            [{
                "fixture_id": f.fixture_id, "date": f.fixture.date.isoformat(),
                "home_id": f.teams.home.id, "home_name": f.teams.home.name,
                "away_id": f.teams.away.id, "away_name": f.teams.away.name,
                "home_goals": f.goals.home, "away_goals": f.goals.away,
            } for f in wc22_fixtures], indent=2,
        ))
        # Identify participants
        participants: dict[int, str] = {}
        for f in wc22_fixtures:
            participants[f.teams.home.id] = f.teams.home.name
            participants[f.teams.away.id] = f.teams.away.name
        print(f"  {len(participants)} participants: {sorted(participants.values())}")

        # Step 2: Per participant, pull 2022 fixtures
        print("\n[2/4] Pulling 2022 fixtures per participant...")
        per_team_fixtures: dict[int, list] = {}
        for team_id, name in sorted(participants.items()):
            r = await client.get("/fixtures", params={"team": team_id, "season": 2022})
            r.raise_for_status()
            parsed = FixturesResponse.model_validate(r.json()).response
            per_team_fixtures[team_id] = parsed
            # Filter
            friendlies_pre = [
                f for f in parsed
                if PRE_WC22_FROM <= f.fixture.date.date() <= PRE_WC22_TO
                and f.is_finished
                and f.league.id == FRIENDLIES_LEAGUE_ID
            ]
            wc_matches = [
                f for f in parsed
                if WC22_START <= f.fixture.date.date() <= WC22_FINAL
                and f.is_finished
                and f.league.id == WC22_LEAGUE_ID
            ]
            print(f"  {name:22} → friendlies={len(friendlies_pre):2}, wc={len(wc_matches):2}")

        # Step 3: Pull stats + events for friendlies + WC22 matches
        print("\n[3/4] Pulling stats + events for each match...")
        # Build unique match list (friendlies pre-WC + WC22 matches)
        unique_matches: dict[int, dict] = {}
        for team_id, name in participants.items():
            for f in per_team_fixtures[team_id]:
                if not f.is_finished:
                    continue
                in_friendly = (
                    PRE_WC22_FROM <= f.fixture.date.date() <= PRE_WC22_TO
                    and f.league.id == FRIENDLIES_LEAGUE_ID
                )
                in_wc = (
                    WC22_START <= f.fixture.date.date() <= WC22_FINAL
                    and f.league.id == WC22_LEAGUE_ID
                )
                if not (in_friendly or in_wc):
                    continue
                unique_matches[f.fixture_id] = {
                    "fixture": f,
                    "category": "friendly" if in_friendly else "wc",
                    "home_id": f.teams.home.id,
                    "away_id": f.teams.away.id,
                    "home_goals": f.goals.home or 0,
                    "away_goals": f.goals.away or 0,
                }
        print(f"  Unique matches to pull stats+events for: {len(unique_matches)}")

        match_stats: dict[int, dict] = {}
        for i, (fid, info) in enumerate(unique_matches.items(), 1):
            r_stats = await client.get("/fixtures/statistics", params={"fixture": fid})
            r_stats.raise_for_status()
            stats_resp = StatsResponse.model_validate(r_stats.json())
            r_events = await client.get("/fixtures/events", params={"fixture": fid})
            r_events.raise_for_status()
            events_resp = EventsResponse.model_validate(r_events.json())
            match_stats[fid] = {
                "stats": {b.team.id: b for b in stats_resp.response},
                "events": events_resp.response,
                "info": info,
            }
            if i % 25 == 0:
                print(f"    [{i}/{len(unique_matches)}] processed")

        # Step 4: Compute per-team aggregates per category
        print("\n[4/4] Computing per-team aggregates...")
        per_team: dict[int, dict] = {
            tid: {
                "name": name, "friendly": [], "wc": [],
            }
            for tid, name in participants.items()
        }

        for fid, m in match_stats.items():
            info = m["info"]
            cat = info["category"]
            home_id = info["home_id"]
            away_id = info["away_id"]
            hg = info["home_goals"]
            ag = info["away_goals"]

            # For each side that's a participant, add their match data
            for team_id, gf, ga in [(home_id, hg, ag), (away_id, ag, hg)]:
                if team_id not in per_team:
                    continue
                stats_block = m["stats"].get(team_id)
                shots = sot = corners = fouls = yellow = possession = None
                if stats_block:
                    shots = stats_block.get("Total Shots")
                    sot = stats_block.get("Shots on Goal")
                    corners = stats_block.get("Corner Kicks")
                    fouls = stats_block.get("Fouls")
                    possession = stats_block.get("Ball Possession")
                # Count cards for this team
                yc = sum(
                    1 for e in m["events"]
                    if e.is_yellow_card and e.team.id == team_id
                )
                per_team[team_id][cat].append({
                    "fixture_id": fid, "goals_for": gf, "goals_against": ga,
                    "shots": shots, "sot": sot, "corners": corners,
                    "fouls": fouls, "yellow_cards": yc, "possession": possession,
                })

        # Aggregate
        def _mean(vals: list[float | None]) -> float | None:
            v = [x for x in vals if x is not None]
            return float(np.mean(v)) if v else None

        analysis: dict[str, dict] = {}
        for team_id, data in per_team.items():
            if not data["friendly"] or not data["wc"]:
                continue
            friendly = data["friendly"]
            wc = data["wc"]
            analysis[data["name"]] = {
                "team_id": team_id,
                "n_friendly": len(friendly),
                "n_wc": len(wc),
                "friendly": {
                    "gf_per_match": _mean([m["goals_for"] for m in friendly]),
                    "ga_per_match": _mean([m["goals_against"] for m in friendly]),
                    "btts_rate": float(np.mean([1 if (m["goals_for"] > 0 and m["goals_against"] > 0) else 0 for m in friendly])),
                    "over_25_rate": float(np.mean([1 if (m["goals_for"] + m["goals_against"]) > 2 else 0 for m in friendly])),
                    "shots": _mean([m["shots"] for m in friendly]),
                    "sot": _mean([m["sot"] for m in friendly]),
                    "corners": _mean([m["corners"] for m in friendly]),
                    "yellow_cards": _mean([m["yellow_cards"] for m in friendly]),
                    "possession": _mean([m["possession"] for m in friendly]),
                },
                "wc": {
                    "gf_per_match": _mean([m["goals_for"] for m in wc]),
                    "ga_per_match": _mean([m["goals_against"] for m in wc]),
                    "btts_rate": float(np.mean([1 if (m["goals_for"] > 0 and m["goals_against"] > 0) else 0 for m in wc])),
                    "over_25_rate": float(np.mean([1 if (m["goals_for"] + m["goals_against"]) > 2 else 0 for m in wc])),
                    "shots": _mean([m["shots"] for m in wc]),
                    "sot": _mean([m["sot"] for m in wc]),
                    "corners": _mean([m["corners"] for m in wc]),
                    "yellow_cards": _mean([m["yellow_cards"] for m in wc]),
                    "possession": _mean([m["possession"] for m in wc]),
                },
            }

        OUT_PATH.write_text(json.dumps(analysis, indent=2))
        print(f"\nSaved: {OUT_PATH} ({len(analysis)} teams)")

        # Correlation analysis
        print(f"\n{'=' * 80}")
        print("Per-team comparison: Friendlies vs WC22")
        print(f"{'=' * 80}")
        print(f"{'Team':<22} {'n_f':>4} {'n_wc':>4} | {'GF_f':>5} {'GF_w':>5} Δ "
              f"| {'GA_f':>5} {'GA_w':>5} Δ | {'O25_f':>5} {'O25_w':>5}")
        print(f"{'-' * 100}")
        for name in sorted(analysis.keys()):
            a = analysis[name]
            f, w = a["friendly"], a["wc"]
            print(
                f"{name:<22} {a['n_friendly']:>4} {a['n_wc']:>4} | "
                f"{f['gf_per_match']:>5.2f} {w['gf_per_match']:>5.2f} "
                f"{w['gf_per_match'] - f['gf_per_match']:+5.2f} | "
                f"{f['ga_per_match']:>5.2f} {w['ga_per_match']:>5.2f} "
                f"{w['ga_per_match'] - f['ga_per_match']:+5.2f} | "
                f"{f['over_25_rate']*100:>4.0f}% {w['over_25_rate']*100:>4.0f}%"
            )

        # Correlations
        print(f"\n{'=' * 80}")
        print("Correlations (Friendlies → WC22)")
        print(f"{'=' * 80}")
        for stat_name in ["gf_per_match", "ga_per_match", "btts_rate", "over_25_rate",
                          "shots", "sot", "corners", "yellow_cards", "possession"]:
            xs = []
            ys = []
            for name, a in analysis.items():
                xv = a["friendly"].get(stat_name)
                yv = a["wc"].get(stat_name)
                if xv is not None and yv is not None:
                    xs.append(xv)
                    ys.append(yv)
            if len(xs) >= 5:
                corr = float(np.corrcoef(xs, ys)[0, 1])
                print(f"  {stat_name:20}: r = {corr:+.3f}  (n={len(xs)})")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
