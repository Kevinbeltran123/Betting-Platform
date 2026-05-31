"""Build the press-resistance table from cached StatsBomb events (offline).

Press-resistance = pass completion under opponent pressure (the build-up side,
complementing PPDA's pressing side). Output: data/cache/tsp/press_resistance.json
keyed by team name, consumed by intel_io.load_press_resistance.
"""
from __future__ import annotations

import json
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.press_resistance import (
    build_press_resistance,
    extract_match_press,
)

PROJECT = Path(__file__).resolve().parents[3]
EVENTS_DIR = PROJECT / "data" / "cache" / "statsbomb" / "events"
OUT = PROJECT / "data" / "cache" / "tsp" / "press_resistance.json"


def main() -> None:
    per_match = [extract_match_press(json.loads(f.read_text()))
                 for f in sorted(EVENTS_DIR.glob("*.json"))]
    table = build_press_resistance(per_match)

    OUT.write_text(json.dumps({
        t.team: {
            "n_matches": t.n_matches,
            "confidence": t.confidence,
            "passes_up_per_match": round(t.passes_under_pressure_per_match.mean, 1),
            "completion_under_pressure": round(t.completion_under_pressure.mean, 3),
            "resistance": t.resistance,
        } for t in table.values()
    }, indent=2, ensure_ascii=False))

    reliable = [t for t in table.values() if t.confidence in ("green", "yellow")]
    print(f"{len(table)} teams ({len(reliable)} reliable) -> {OUT}")
    print(f"{'team':22}{'compl%':>8}{'n':>4}  resistance")
    for t in sorted(reliable, key=lambda x: x.completion_under_pressure.mean):
        print(f"{t.team:22}{t.completion_under_pressure.mean:8.0%}{t.n_matches:4}  {t.resistance}")


if __name__ == "__main__":
    main()
