"""Build tactical identities (planteamiento) for WC2026 teams from StatsBomb
advanced profiles, and demo cross-matchup reads.

Offline. Reads data/cache/tsp/profiles_statsbomb/*_sb.json (built by script 25).
Output: data/cache/tsp/tactical_identities/{team}_tid.json + a report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    TeamStatsBombProfile,
)
from bip.evaluation.tournaments.team_style_profiler.tactical_identity import (
    derive_tactical_identity,
    read_matchup,
)

PROJECT = Path(__file__).resolve().parents[3]
PROFILES_DIR = PROJECT / "data" / "cache" / "tsp" / "profiles_statsbomb"
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "tactical_identities"

# A few illustrative WC2026-relevant matchups to demo the read.
DEMO_MATCHUPS = [
    ("Spain", "Morocco"),
    ("Brazil", "Iran"),
    ("France", "Croatia"),
    ("Argentina", "Mexico"),
    ("Qatar", "Saudi Arabia"),
]


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").lower()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = {}
    for f in sorted(PROFILES_DIR.glob("*_sb.json")):
        if f.stem.startswith("_"):
            continue
        profile = TeamStatsBombProfile.model_validate_json(f.read_text())
        tid = derive_tactical_identity(profile)
        ids[tid.team_name] = tid
        (OUT_DIR / f"{_slug(tid.team_name)}_tid.json").write_text(
            json.dumps(
                {
                    "team_name": tid.team_name,
                    "n_matches": tid.n_matches,
                    "confidence": tid.confidence,
                    "press_intensity": tid.press_intensity,
                    "set_piece_reliance": tid.set_piece_reliance,
                    "finishing_profile": tid.finishing_profile,
                    "ppda": round(tid.ppda, 2),
                    "set_piece_xg_share": round(tid.set_piece_xg_share, 3),
                    "conversion_rate": round(tid.conversion_rate, 3),
                    "archetype": tid.archetype,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

    print(f"\n=== Tactical identities ({len(ids)} teams) ===\n")
    print(f"{'TEAM':18}{'conf':7}{'ARCHETYPE':30}{'ppda':>6}{'sp%':>6}{'conv':>6}")
    for name in sorted(ids, key=lambda n: ids[n].archetype):
        t = ids[name]
        print(f"{name:18}{t.confidence:7}{t.archetype:30}{t.ppda:6.1f}{t.set_piece_xg_share*100:5.0f}%{t.conversion_rate:6.2f}")

    print("\n\n=== Demo matchup reads ===")
    for h, a in DEMO_MATCHUPS:
        if h not in ids or a not in ids:
            continue
        r = read_matchup(ids[h], ids[a])
        print(f"\n--- {h} ({ids[h].archetype}) vs {a} ({ids[a].archetype}) ---")
        print(f"  Tempo:  {r.tempo}")
        print(f"  Forma:  {r.game_shape}")
        for lean in r.market_leans:
            print(f"   • {lean}")
        for c in r.caveats:
            print(f"   ⚠ {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
