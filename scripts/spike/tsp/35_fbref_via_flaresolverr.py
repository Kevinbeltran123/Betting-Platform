"""Demo: pull FBref player shooting stats (with xG) via FlareSolverr.

Requires a FlareSolverr instance (docker run -d -p 8191:8191
ghcr.io/flaresolverr/flaresolverr). Proves the FBref unlock end-to-end:
season URL -> FlareSolverr -> comment-strip -> per-player xG.
Output: data/cache/tsp/fbref/{slug}_shooting.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.fbref_scrape import (
    fetch,
    parse_player_table,
    season_stats_url,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "fbref"

FIELDS = ["player", "team", "minutes_90s", "shots", "shots_on_target",
          "goals", "xg", "npxg", "shots_per90", "shots_on_target_per90"]


def _f(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    url = season_stats_url(1, "2022", "World-Cup", "shooting")
    print(f"Fetching {url}")
    rows = parse_player_table(fetch(url), "stats_shooting", FIELDS)
    print(f"parsed {len(rows)} player rows")

    players = [{
        "player": r["player"], "team": r["team"],
        "nineties": _f(r["minutes_90s"]), "shots": _f(r["shots"]),
        "sot": _f(r["shots_on_target"]), "goals": _f(r["goals"]),
        "xg": _f(r["xg"]), "npxg": _f(r["npxg"]),
        "xg_per90": (_f(r["xg"]) / _f(r["minutes_90s"])) if _f(r["minutes_90s"]) else 0.0,
    } for r in rows]
    (OUT_DIR / "wc2022_shooting.json").write_text(json.dumps(players, indent=2, ensure_ascii=False))

    top = sorted([p for p in players if p["nineties"] >= 2], key=lambda p: -p["xg_per90"])[:10]
    print("\nTop xG/90 (>=2 full matches) — REAL xG, unavailable from ESPN:")
    for p in top:
        print(f"  {p['player']:24} {p['team']:14} xG/90 {p['xg_per90']:.2f}  "
              f"(xG {p['xg']:.1f}, {p['shots']:.0f} shots, {p['goals']:.0f} G)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
