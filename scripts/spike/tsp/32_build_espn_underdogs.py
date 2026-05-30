"""Ingest ESPN qualifier player stats for the 8 StatsBomb-less WC2026 teams.

ESPN public API (works without Cloudflare). Builds PlayerPropProfile(source=espn)
+ prop boards for the underdogs. Output: data/cache/tsp/player_props/{team}.json
(same schema as script 30, with source=espn).
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import requests

from bip.evaluation.tournaments.team_style_profiler.espn_ingest import match_player_counts
from bip.evaluation.tournaments.team_style_profiler.player_props import (
    build_player_profiles,
    prop_board,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "player_props"
S = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# WC2026 teams absent from StatsBomb → their WC-qualifying competition.
UNDERDOGS = {
    "Bosnia and Herzegovina": "fifa.worldq.uefa",
    "Norway": "fifa.worldq.uefa",
    "Curacao": "fifa.worldq.concacaf",
    "Haiti": "fifa.worldq.concacaf",
    "Iraq": "fifa.worldq.afc",
    "Jordan": "fifa.worldq.afc",
    "Uzbekistan": "fifa.worldq.afc",
    "New Zealand": "fifa.worldq.ofc",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("-", " ")
    # drop the connector word so "Bosnia and Herzegovina" == "Bosnia-Herzegovina"
    tokens = [t for t in s.split() if t != "and"]
    return " ".join(tokens)


def _slug(name: str) -> str:
    return _norm(name).replace(" ", "_")


def _get(url: str) -> dict:
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    time.sleep(0.25)  # be polite
    return r.json()


def resolve_team_id(league: str, name: str) -> tuple[str, str] | None:
    data = _get(f"{S}/{league}/teams")
    target = _norm(name)
    for sport in data.get("sports", []):
        for lg in sport.get("leagues", []):
            for t in lg.get("teams", []):
                team = t.get("team", {})
                if target in _norm(team.get("displayName", "")) or _norm(team.get("displayName", "")) in target:
                    return team["id"], team.get("displayName", name)
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, league in UNDERDOGS.items():
        try:
            resolved = resolve_team_id(league, name)
        except Exception as e:
            print(f"  ✗ {name}: teams endpoint error {type(e).__name__}")
            continue
        if not resolved:
            print(f"  ✗ {name}: not found in {league}")
            continue
        team_id, disp = resolved
        try:
            sched = _get(f"{S}/{league}/teams/{team_id}/schedule")
        except Exception as e:
            print(f"  ✗ {name}: schedule error {type(e).__name__}")
            continue
        completed = [
            e["id"] for e in sched.get("events", [])
            if e.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("completed")
        ]
        per_match = []
        for eid in completed:
            try:
                summ = _get(f"{S}/{league}/summary?event={eid}")
            except Exception:
                continue
            cm = match_player_counts(summ, team_id)
            if cm[0]:
                per_match.append(cm)
        profiles = build_player_profiles(per_match, source="espn")
        profiles.sort(key=lambda p: -p.n_matches)
        board = prop_board(profiles)

        out = {
            "team": name, "espn_name": disp, "source": "espn", "league": league,
            "n_matches_ingested": len(per_match), "n_players": len(profiles),
            "players": [{
                "name": p.player_name, "position": p.position, "n_matches": p.n_matches,
                "confidence": p.confidence,
                "shots_per90": round(p.shots_per90.mean, 2),
                "sot_per90": round(p.shots_on_target_per90.mean, 2),
                "goals_per90": round(p.goals_per90.mean, 3),
                "fouls_per90": round(p.fouls_committed_per90.mean, 2),
                "yellows_per90": round(p.yellow_cards_per90.mean, 3),
                "assists_per90": round(p.assists_per90.mean, 3),
                "p_anytime_scorer": round(p.p_anytime_scorer, 3),
            } for p in profiles],
            "prop_board": [{
                "market": c.market, "player": c.player_name, "position": c.position,
                "stat": c.stat, "softness": c.softness, "confidence": c.confidence,
            } for c in board],
        }
        (OUT_DIR / f"{_slug(name)}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"  ✓ {name:24} ({disp}) — {len(per_match)} matches, {len(profiles)} players")
        for c in board[:4]:
            print(f"        [{c.softness}] {c.market:24} {c.player_name:22} {c.stat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
