"""Backfill StatsBomb-derived advanced stats for WC2026 teams.

Reads cached events from data/cache/statsbomb/events. NO external API calls.
Output: data/cache/tsp/profiles_statsbomb/{team}_sb.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.coach_history import CURRENT_COACHES
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    SB_NAME_OF,
    SBMatchAggregate,
    aggregate_match_for_team,
    aggregate_team_profile,
    build_match_index,
)


ROOT = Path(__file__).resolve().parents[4]
MATCHES_DIR = ROOT / "betting-intelligence-platform" / "data" / "cache" / "statsbomb" / "matches"
EVENTS_DIR = ROOT / "betting-intelligence-platform" / "data" / "cache" / "statsbomb" / "events"
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_statsbomb"


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Building StatsBomb advanced profiles for WC2026 teams ===\n")
    t0 = time.time()

    match_index, team_to_matches = build_match_index(MATCHES_DIR)
    print(f"Cached: {len(match_index)} matches across competitions")

    coach_key_for = {"Ivory Coast": "Côte d'Ivoire"}

    profiled = []
    skipped = []

    for tsv_name in WC2026_TEAMS:
        sb_name = SB_NAME_OF.get(tsv_name, tsv_name)
        if sb_name not in team_to_matches:
            skipped.append(tsv_name)
            continue
        match_ids = team_to_matches[sb_name]

        coach_lookup = coach_key_for.get(tsv_name, tsv_name)
        coach_rec = CURRENT_COACHES.get(coach_lookup)
        confederation = coach_rec.confederation if coach_rec else "UNK"

        agg_matches: list[SBMatchAggregate] = []
        for mid in match_ids:
            events_path = EVENTS_DIR / f"{mid}.json"
            if not events_path.exists():
                continue
            events = json.loads(events_path.read_text())
            meta = match_index[mid]
            agg = aggregate_match_for_team(events, sb_name, meta)
            if agg is not None:
                agg_matches.append(agg)

        if not agg_matches:
            skipped.append(tsv_name)
            continue

        profile = aggregate_team_profile(
            team_name=tsv_name,
            confederation=confederation,
            matches=agg_matches,
            last_updated=datetime.now(),
        )

        out_path = OUT_DIR / f"{tsv_name.replace(' ', '_').replace(chr(39), '').lower()}_sb.json"
        out_path.write_text(profile.model_dump_json(indent=2))
        profiled.append((tsv_name, len(agg_matches), profile.xg_for_per_match.mean, profile.xg_against_per_match.mean))
        print(f"  ✓ {tsv_name:25} n={len(agg_matches):2}  xG={profile.xg_for_per_match.mean:.2f}  xGA={profile.xg_against_per_match.mean:.2f}")

    elapsed = time.time() - t0
    print(f"\n=== Done in {elapsed:.1f}s ===")
    print(f"Profiled: {len(profiled)}/48")
    print(f"Skipped (not in StatsBomb cache): {len(skipped)}")
    for s in skipped:
        print(f"  - {s}")

    diag = {
        "timestamp": datetime.now().isoformat(),
        "profiled": [{"team": t, "n": n, "xg_for": x, "xg_against": xa}
                     for t, n, x, xa in profiled],
        "skipped": skipped,
        "elapsed_s": round(elapsed, 1),
    }
    (OUT_DIR / "_diagnostic.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
