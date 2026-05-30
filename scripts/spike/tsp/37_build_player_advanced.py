"""Build per-player advanced metrics (progression/creation/defence) from cached
StatsBomb events. Offline. Output: data/cache/tsp/player_advanced/{team}.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.player_advanced import (
    build_advanced_profiles,
    extract_match_advanced,
    weak_links,
)
from bip.evaluation.tournaments.team_style_profiler.player_props import parse_player_minutes
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import build_match_index

PROJECT = Path(__file__).resolve().parents[3]
MATCHES_DIR = PROJECT / "data" / "cache" / "statsbomb" / "matches"
EVENTS_DIR = PROJECT / "data" / "cache" / "statsbomb" / "events"
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "player_advanced"
RECENT = {"FIFA World Cup 2022", "African Cup of Nations 2023",
          "Copa America 2024", "UEFA Euro 2024"}
DEMO = ["Spain", "Argentina", "Morocco", "England"]


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").lower()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    idx, _ = build_match_index(MATCHES_DIR)
    per_match = []
    for f in sorted(EVENTS_DIR.glob("*.json")):
        meta = idx.get(int(f.stem))
        if not meta or f'{meta["competition"]["competition_name"]} {meta["season"]["season_name"]}' not in RECENT:
            continue
        events = json.loads(f.read_text())
        counts, pmeta = extract_match_advanced(events)
        per_match.append((counts, pmeta, parse_player_minutes(events)))

    profiles = build_advanced_profiles(per_match)
    by_team = defaultdict(list)
    for p in profiles:
        by_team[p.team].append(p)

    for team, plist in by_team.items():
        (OUT_DIR / f"{_slug(team)}.json").write_text(json.dumps({
            "team": team, "n_players": len(plist),
            "players": [{"name": p.player_name, "position": p.position, "n_matches": p.n_matches,
                         "confidence": p.confidence,
                         "prog_passes_per90": round(p.prog_passes_per90.mean, 1),
                         "prog_carries_per90": round(p.prog_carries_per90.mean, 1),
                         "sca_per90": round(p.sca_per90.mean, 2), "gca_per90": round(p.gca_per90.mean, 3),
                         "tackles_per90": round(p.tackles_per90.mean, 2),
                         "interceptions_per90": round(p.interceptions_per90.mean, 2),
                         "dribbled_past_per90": round(p.dribbled_past_per90.mean, 2),
                         "aerial_won_per90": round(p.aerial_won_per90.mean, 2),
                         "aerial_win_rate": round(p.aerial_win_rate, 2)} for p in plist],
            "weak_links": weak_links(plist),
        }, indent=2, ensure_ascii=False))

    print(f"\n=== Player advanced: {len(profiles)} players, {len(by_team)} teams ===")
    for team in DEMO:
        plist = by_team.get(team)
        if not plist:
            continue
        creators = sorted([p for p in plist if p.confidence in ("green", "yellow")],
                          key=lambda x: -x.sca_per90.mean)[:3]
        print(f"\n-- {team} top creators (SCA/90) --")
        for p in creators:
            print(f"   {p.player_name:24} SCA {p.sca_per90.mean:.1f}  prog_pass {p.prog_passes_per90.mean:.0f}  ({p.position[:14]})")
        wl = weak_links(plist)
        if wl:
            print(f"   weak-links: " + "; ".join(f"{w['player']} ({w['reason']})" for w in wl[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
