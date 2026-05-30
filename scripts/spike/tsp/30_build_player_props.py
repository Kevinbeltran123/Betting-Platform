"""Build player-prop profiles from cached StatsBomb events (offline).

Parses all 314 cached matches → per-player per-90 rates + prop boards.
Output: data/cache/tsp/player_props/{team}.json + demo boards printed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.player_props import (
    build_player_profiles,
    parse_player_counts,
    parse_player_minutes,
    prop_board,
)
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    build_match_index,
)

PROJECT = Path(__file__).resolve().parents[3]
MATCHES_DIR = PROJECT / "data" / "cache" / "statsbomb" / "matches"
EVENTS_DIR = PROJECT / "data" / "cache" / "statsbomb" / "events"
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "player_props"

# Current-squad relevance window: WC2022 onward. Drops WC2018 + Euro2020 (retired
# players like Mascherano/Diego Costa). Keeps WC2022 — the only StatsBomb data
# for AFC teams (no Asian Cup in open data) and still-current players.
RECENT_COMPETITIONS = {
    "FIFA World Cup 2022",
    "African Cup of Nations 2023",
    "Copa America 2024",
    "UEFA Euro 2024",
}

DEMO_TEAMS = ["Spain", "Argentina", "England", "Croatia"]


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").lower()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    match_index, _ = build_match_index(MATCHES_DIR)
    per_match = []
    n_files = 0
    n_skipped_era = 0
    for f in sorted(EVENTS_DIR.glob("*.json")):
        mid = int(f.stem)
        meta_m = match_index.get(mid)
        if meta_m is not None:
            label = f'{meta_m["competition"]["competition_name"]} {meta_m["season"]["season_name"]}'
            if label not in RECENT_COMPETITIONS:
                n_skipped_era += 1
                continue
        events = json.loads(f.read_text())
        counts, meta = parse_player_counts(events)
        minutes = parse_player_minutes(events)
        per_match.append((counts, meta, minutes))
        n_files += 1
    print(f"(era filter: kept {n_files} recent matches, skipped {n_skipped_era} old)")

    profiles = build_player_profiles(per_match)
    by_team: dict[str, list] = defaultdict(list)
    for p in profiles:
        by_team[p.team].append(p)

    print(f"\n=== Player-prop profiles from {n_files} matches: "
          f"{len(profiles)} players across {len(by_team)} teams ===\n")

    for team, plist in sorted(by_team.items()):
        plist.sort(key=lambda x: -x.minutes_total)
        board = prop_board(plist)
        out = {
            "team": team,
            "n_players": len(plist),
            "players": [{
                "name": p.player_name, "position": p.position,
                "n_matches": p.n_matches, "minutes": round(p.minutes_total),
                "confidence": p.confidence,
                "shots_per90": round(p.shots_per90.mean, 2),
                "sot_per90": round(p.shots_on_target_per90.mean, 2),
                "xg_per90": round(p.xg_per90.mean, 3),
                "goals_per90": round(p.goals_per90.mean, 3),
                "fouls_per90": round(p.fouls_committed_per90.mean, 2),
                "yellows_per90": round(p.yellow_cards_per90.mean, 3),
                "p_anytime_scorer": round(p.p_anytime_scorer, 3),
                "penalties_taken": p.penalties_taken,
            } for p in plist],
            "prop_board": [{
                "market": c.market, "player": c.player_name, "position": c.position,
                "stat": c.stat, "softness": c.softness, "confidence": c.confidence,
            } for c in board],
        }
        (OUT_DIR / f"{_slug(team)}.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False))

    for team in DEMO_TEAMS:
        plist = by_team.get(team)
        if not plist:
            continue
        print(f"--- {team} prop board (softest-first) ---")
        for c in prop_board(plist):
            soft = {1: "SOFT", 2: "med", 3: "hard"}[c.softness]
            print(f"  [{soft}] {c.market:24} {c.player_name:22} ({c.position[:12]:12}) {c.stat}  <{c.confidence}>")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
