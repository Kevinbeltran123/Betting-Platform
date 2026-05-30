"""Build the referee tendency table from StatsBomb match metadata (offline).

Output: data/cache/tsp/referee_tendencies.json + demo of the board×referee cross.
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
from bip.evaluation.tournaments.team_style_profiler.referee_tendencies import (
    apply_referee_to_board,
    build_referee_tendencies,
    parse_match_discipline,
)
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    build_match_index,
)

PROJECT = Path(__file__).resolve().parents[3]
MATCHES_DIR = PROJECT / "data" / "cache" / "statsbomb" / "matches"
EVENTS_DIR = PROJECT / "data" / "cache" / "statsbomb" / "events"
OUT = PROJECT / "data" / "cache" / "tsp" / "referee_tendencies.json"


def main() -> int:
    match_index, _ = build_match_index(MATCHES_DIR)
    per_ref: dict[str, tuple[str, list]] = {}
    grouped: dict[str, list] = defaultdict(list)
    ref_country: dict[str, str] = {}

    argentina_match_events = None
    for f in sorted(EVENTS_DIR.glob("*.json")):
        mid = int(f.stem)
        meta = match_index.get(mid)
        if not meta:
            continue
        ref = (meta.get("referee") or {}).get("name")
        if not ref:
            continue
        events = json.loads(f.read_text())
        grouped[ref].append(parse_match_discipline(events))
        ref_country[ref] = (meta.get("referee") or {}).get("country", {}).get("name", "")

    per_ref = {r: (ref_country[r], ms) for r, ms in grouped.items()}
    table = build_referee_tendencies(per_ref)

    OUT.write_text(json.dumps({
        name: {
            "country": t.country, "n_matches": t.n_matches,
            "confidence": t.confidence, "strictness": t.strictness,
            "cards_per_match": round(t.cards_per_match.mean, 2),
            "yellows_per_match": round(t.yellows_per_match.mean, 2),
            "reds_per_match": round(t.reds_per_match.mean, 3),
            "fouls_per_match": round(t.fouls_per_match.mean, 1),
            "penalties_per_match": round(t.penalties_per_match.mean, 3),
        }
        for name, t in sorted(table.items())
    }, indent=2, ensure_ascii=False))

    reliable = [t for t in table.values() if t.confidence in ("green", "yellow")]
    print(f"\n=== Referee tendencies: {len(table)} refs ({len(reliable)} with n>=4) ===\n")
    print(f"{'STRICT?':9}{'cards':>6}{'fouls':>6}{'pens':>6}{'n':>4}  REFEREE")
    for t in sorted(reliable, key=lambda x: -x.cards_per_match.mean):
        print(f"{t.strictness:9}{t.cards_per_match.mean:6.1f}{t.fouls_per_match.mean:6.0f}"
              f"{t.penalties_per_match.mean:6.2f}{t.n_matches:4}  {t.referee_name}")

    # --- Demo: Argentina prop board under a STRICT vs LENIENT referee ---
    per_match = []
    recent = {"FIFA World Cup 2022", "African Cup of Nations 2023",
              "Copa America 2024", "UEFA Euro 2024"}
    for f in sorted(EVENTS_DIR.glob("*.json")):
        meta = match_index.get(int(f.stem))
        if not meta or f'{meta["competition"]["competition_name"]} {meta["season"]["season_name"]}' not in recent:
            continue
        evs = json.loads(f.read_text())
        per_match.append((*_parse(evs),))
    profiles = [p for p in build_player_profiles(per_match) if p.team == "Argentina"]
    board = prop_board(profiles)
    strict = max(reliable, key=lambda x: x.cards_per_match.mean)
    lenient = min(reliable, key=lambda x: x.cards_per_match.mean)
    print(f"\n--- Argentina soft props under STRICT ref ({strict.referee_name}) ---")
    for c in apply_referee_to_board(board, strict):
        if c.softness == 1:
            print(f"  {c.market:22} {c.player_name:22} {c.stat}")
    print(f"\n--- ...under LENIENT ref ({lenient.referee_name}) ---")
    for c in apply_referee_to_board(board, lenient):
        if c.softness == 1:
            print(f"  {c.market:22} {c.player_name:22} {c.stat}")
    return 0


def _parse(events):
    counts, meta = parse_player_counts(events)
    return counts, meta, parse_player_minutes(events)


if __name__ == "__main__":
    sys.exit(main())
