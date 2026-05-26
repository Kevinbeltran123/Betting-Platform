"""Analyze the LAST friendly each WC22 participant played before WC22 kick-off.

The hypothesis (operator 2026-05-24): the very last pre-WC friendly
reveals the team's "mode" entering the tournament:
  - "Warming up" mode: team plays to score, intense, looking for goals
  - "Reserving" mode: team protects starters, low-intensity, low-action

By aggregating WC22 last-friendlies we learn the BASE distribution:
  - What % were high-scoring?
  - What % were BTTS Yes?
  - Average total goals?
  - Possession patterns?
  - Card counts?

This baseline informs how to bet pre-WC2026 friendlies on the same
"last-friendly" window.

Output:
  data/cache/tsp/wc22_analysis/last_friendlies.json — detail per team
  data/cache/tsp/wc22_analysis/last_friendlies_baseline.json — aggregates
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
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
WC22_FIXTURES_PATH = OUT_DIR / "wc22_fixtures.json"
DETAIL_PATH = OUT_DIR / "last_friendlies.json"
BASELINE_PATH = OUT_DIR / "last_friendlies_baseline.json"

WC22_START = date(2022, 11, 20)
FRIENDLIES_LEAGUE_ID = 10


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    if not WC22_FIXTURES_PATH.exists():
        print(f"ERROR: {WC22_FIXTURES_PATH} not found. Run 15_*.py first.")
        return 1

    # Build WC22 participants list
    wc22_fixtures = json.loads(WC22_FIXTURES_PATH.read_text())
    participants: dict[int, str] = {}
    for f in wc22_fixtures:
        participants[f["home_id"]] = f["home_name"]
        participants[f["away_id"]] = f["away_name"]
    print(f"WC22 participants: {len(participants)}")

    last_friendlies = []
    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        for i, (team_id, team_name) in enumerate(sorted(participants.items()), 1):
            # Pull 2022 fixtures
            r = await client.get("/fixtures", params={"team": team_id, "season": 2022})
            r.raise_for_status()
            parsed = FixturesResponse.model_validate(r.json()).response
            # Filter to friendlies BEFORE WC22 start
            friendlies = [
                f for f in parsed
                if f.is_finished
                and f.league.id == FRIENDLIES_LEAGUE_ID
                and f.fixture.date.date() < WC22_START
            ]
            if not friendlies:
                print(f"  [{i:2}/{len(participants)}] {team_name:22} → no pre-WC friendly found")
                continue
            # Pick the LAST one
            last = max(friendlies, key=lambda f: f.fixture.date)
            # Pull stats + events
            r_stats = await client.get(
                "/fixtures/statistics", params={"fixture": last.fixture_id}
            )
            r_stats.raise_for_status()
            stats_resp = StatsResponse.model_validate(r_stats.json())
            r_events = await client.get(
                "/fixtures/events", params={"fixture": last.fixture_id}
            )
            r_events.raise_for_status()
            events_resp = EventsResponse.model_validate(r_events.json())

            home_id = last.teams.home.id
            away_id = last.teams.away.id
            team_is_home = team_id == home_id
            opp_id = away_id if team_is_home else home_id
            opp_name = last.teams.away.name if team_is_home else last.teams.home.name

            hg = last.goals.home or 0
            ag = last.goals.away or 0
            team_gf = hg if team_is_home else ag
            team_ga = ag if team_is_home else hg
            total_goals = hg + ag
            btts = (hg > 0) and (ag > 0)
            over25 = total_goals > 2
            ht_hg = last.score.halftime.home or 0
            ht_ag = last.score.halftime.away or 0
            days_before_wc = (WC22_START - last.fixture.date.date()).days

            # Team stats
            team_stats_block = stats_resp.for_team(team_id)
            def _get(stat: str) -> float | None:
                if team_stats_block is None:
                    return None
                v = team_stats_block.get(stat)
                return float(v) if v is not None else None

            yc = sum(
                1 for e in events_resp.response
                if e.is_yellow_card and e.team.id == team_id
            )
            opp_yc = sum(
                1 for e in events_resp.response
                if e.is_yellow_card and e.team.id == opp_id
            )

            entry = {
                "team_id": team_id,
                "team_name": team_name,
                "opponent_name": opp_name,
                "opponent_id": opp_id,
                "team_is_home": team_is_home,
                "fixture_id": last.fixture_id,
                "date": last.fixture.date.isoformat(),
                "days_before_wc": days_before_wc,
                "score": f"{hg}-{ag}",
                "team_gf": team_gf,
                "team_ga": team_ga,
                "total_goals": total_goals,
                "ht_score": f"{ht_hg}-{ht_ag}",
                "btts": btts,
                "over_25": over25,
                "team_shots": _get("Total Shots"),
                "team_sot": _get("Shots on Goal"),
                "team_corners": _get("Corner Kicks"),
                "team_fouls": _get("Fouls"),
                "team_possession": _get("Ball Possession"),
                "team_yellow_cards": yc,
                "opp_yellow_cards": opp_yc,
            }
            last_friendlies.append(entry)
            print(
                f"  [{i:2}/{len(participants)}] {team_name:22} → vs {opp_name:20} "
                f"{entry['score']:7} (d-{days_before_wc:2}) "
                f"shots={entry['team_shots'] or 0:.0f} "
                f"yc={yc}+{opp_yc}"
            )

    # Save detail
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_PATH.write_text(json.dumps(last_friendlies, indent=2))
    print(f"\nSaved detail: {DETAIL_PATH} ({len(last_friendlies)} matches)")

    # Aggregate baseline
    def _arr(field: str) -> np.ndarray:
        vals = [e[field] for e in last_friendlies if e.get(field) is not None]
        return np.asarray(vals, dtype=float)

    total_goals_arr = _arr("total_goals")
    btts_arr = np.asarray([1 if e["btts"] else 0 for e in last_friendlies], dtype=float)
    over25_arr = np.asarray([1 if e["over_25"] else 0 for e in last_friendlies], dtype=float)
    gf_arr = _arr("team_gf")
    ga_arr = _arr("team_ga")
    shots_arr = _arr("team_shots")
    yc_total_arr = np.asarray(
        [e["team_yellow_cards"] + e["opp_yellow_cards"] for e in last_friendlies],
        dtype=float,
    )

    baseline = {
        "n_matches": len(last_friendlies),
        "mean_total_goals": float(total_goals_arr.mean()),
        "median_total_goals": float(np.median(total_goals_arr)),
        "btts_rate": float(btts_arr.mean()),
        "over_25_rate": float(over25_arr.mean()),
        "mean_team_gf": float(gf_arr.mean()),
        "mean_team_ga": float(ga_arr.mean()),
        "mean_team_shots": float(shots_arr.mean()) if len(shots_arr) > 0 else None,
        "mean_total_yellow_cards": float(yc_total_arr.mean()),
        "goal_distribution": {
            "0_goals": int((total_goals_arr == 0).sum()),
            "1_goals": int((total_goals_arr == 1).sum()),
            "2_goals": int((total_goals_arr == 2).sum()),
            "3_goals": int((total_goals_arr == 3).sum()),
            "4_goals": int((total_goals_arr == 4).sum()),
            "5plus_goals": int((total_goals_arr >= 5).sum()),
        },
        "score_distribution_summary": {
            "blowouts_3plus_diff": sum(
                1 for e in last_friendlies if abs(e["team_gf"] - e["team_ga"]) >= 3
            ),
            "draws": sum(
                1 for e in last_friendlies if e["team_gf"] == e["team_ga"]
            ),
            "close_1goal_diff": sum(
                1 for e in last_friendlies if abs(e["team_gf"] - e["team_ga"]) == 1
            ),
        },
        "days_before_wc_distribution": {
            "1_to_5_days": sum(1 for e in last_friendlies if e["days_before_wc"] <= 5),
            "6_to_10_days": sum(1 for e in last_friendlies if 5 < e["days_before_wc"] <= 10),
            "11_to_20_days": sum(1 for e in last_friendlies if 10 < e["days_before_wc"] <= 20),
            "21plus_days": sum(1 for e in last_friendlies if e["days_before_wc"] > 20),
        },
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2))
    print(f"\nSaved baseline: {BASELINE_PATH}")

    # Report
    print(f"\n{'=' * 70}")
    print(f"Last-friendly pre-WC22 baseline ({len(last_friendlies)} matches)")
    print(f"{'=' * 70}")
    print(f"  Mean total goals/match:  {baseline['mean_total_goals']:.2f}")
    print(f"  Median total goals:      {baseline['median_total_goals']:.1f}")
    print(f"  BTTS rate:               {baseline['btts_rate']*100:.1f}%")
    print(f"  Over 2.5 rate:           {baseline['over_25_rate']*100:.1f}%")
    print(f"  Mean shots/team:         {baseline.get('mean_team_shots', 0):.1f}")
    print(f"  Mean yellow cards total: {baseline['mean_total_yellow_cards']:.2f}")
    print(f"\nGoal distribution:")
    for k, v in baseline["goal_distribution"].items():
        print(f"  {k}: {v}")
    print(f"\nScore patterns:")
    for k, v in baseline["score_distribution_summary"].items():
        print(f"  {k}: {v}")
    print(f"\nDays before WC22 distribution:")
    for k, v in baseline["days_before_wc_distribution"].items():
        print(f"  {k}: {v}")

    # Per-team summary table
    print(f"\n{'=' * 110}")
    print(f"{'Team':<22} {'vs':<22} {'Score':<7} {'d-wc':>5} {'shots':>6} {'YC tot':>7} {'Mode hint'}")
    print(f"{'=' * 110}")
    for e in sorted(last_friendlies, key=lambda x: -x["total_goals"]):
        total_yc = e["team_yellow_cards"] + e["opp_yellow_cards"]
        mode = ""
        if e["total_goals"] >= 4:
            mode = "WARMING UP (high goals)"
        elif e["total_goals"] == 0:
            mode = "RESERVING (no goals)"
        elif e["total_goals"] <= 1 and total_yc <= 2:
            mode = "low intensity"
        elif total_yc >= 5:
            mode = "competitive"
        print(
            f"{e['team_name']:<22} {e['opponent_name']:<22} {e['score']:<7} "
            f"{e['days_before_wc']:>5} "
            f"{(e.get('team_shots') or 0):>6.0f} {total_yc:>7} {mode}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
