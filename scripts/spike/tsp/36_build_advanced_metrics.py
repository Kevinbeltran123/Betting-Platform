"""Build advanced team metrics (field tilt, GK shot-stopping, game-state xG)
from cached StatsBomb events. 100% offline — deeper mine of data we already have.

Output: data/cache/tsp/advanced_metrics/{team}.json + analyst highlights.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.advanced_metrics import (
    build_profiles,
    extract_match,
)
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    build_match_index,
)

PROJECT = Path(__file__).resolve().parents[3]
MATCHES_DIR = PROJECT / "data" / "cache" / "statsbomb" / "matches"
EVENTS_DIR = PROJECT / "data" / "cache" / "statsbomb" / "events"
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "advanced_metrics"


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").lower()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    match_index, _ = build_match_index(MATCHES_DIR)
    per_match = []
    for f in sorted(EVENTS_DIR.glob("*.json")):
        meta = match_index.get(int(f.stem))
        if not meta:
            continue
        home = meta["home_team"]["home_team_name"]
        away = meta["away_team"]["away_team_name"]
        per_match.append(extract_match(json.loads(f.read_text()), home, away))

    profiles = build_profiles(per_match)
    for p in profiles.values():
        (OUT_DIR / f"{_slug(p.team)}.json").write_text(json.dumps({
            "team": p.team, "n_matches": p.n_matches,
            "field_tilt": round(p.field_tilt.mean, 3),
            "gk_goals_prevented_per_match": round(p.gk_goals_prevented_per_match.mean, 3),
            "line_height": round(p.line_height.mean, 1),
            "directness": round(p.directness.mean, 3),
            "xg_share_leading": round(p.xg_share_leading, 3),
            "xg_share_level": round(p.xg_share_level, 3),
            "xg_share_trailing": round(p.xg_share_trailing, 3),
        }, indent=2, ensure_ascii=False))

    rel = [p for p in profiles.values() if p.n_matches >= 6]
    print(f"\n=== Advanced metrics: {len(profiles)} teams ({len(rel)} with n>=6) ===")
    print("\n-- Most territorial (field tilt) --")
    for p in sorted(rel, key=lambda x: -x.field_tilt.mean)[:6]:
        print(f"  {p.team:16} tilt {p.field_tilt.mean:.0%}  (n={p.n_matches})")
    print("\n-- Best keeper shot-stopping (xG faced − goals, per match) --")
    for p in sorted(rel, key=lambda x: -x.gk_goals_prevented_per_match.mean)[:6]:
        print(f"  {p.team:16} {p.gk_goals_prevented_per_match.mean:+.2f}/match")
    print("\n-- Chasers (highest xG share while TRAILING) --")
    for p in sorted(rel, key=lambda x: -x.xg_share_trailing)[:6]:
        print(f"  {p.team:16} trailing {p.xg_share_trailing:.0%} | level {p.xg_share_level:.0%} | leading {p.xg_share_leading:.0%}")
    print("\n-- Front-runners (highest xG share while LEADING) --")
    for p in sorted(rel, key=lambda x: -x.xg_share_leading)[:5]:
        print(f"  {p.team:16} leading {p.xg_share_leading:.0%} | level {p.xg_share_level:.0%} | trailing {p.xg_share_trailing:.0%}")
    print("\n-- Highest defensive line (press high) vs deepest block --")
    byline = sorted(rel, key=lambda x: -x.line_height.mean)
    for p in byline[:3] + byline[-3:]:
        print(f"  {p.team:16} line x={p.line_height.mean:.1f}  directness {p.directness.mean:.0%} long")
    return 0


if __name__ == "__main__":
    sys.exit(main())
