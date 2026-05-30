"""Demo: full match dossier WITH tactical identity (planteamiento) layer.

Loads TSV (for the pick rules) + StatsBomb-derived tactical identity (for the
game-plan read) for marquee WC2026 matchups, generates the complete dossier,
renders Markdown. Offline.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.dossier_renderer import (
    render_markdown,
)
from bip.evaluation.tournaments.team_style_profiler.match_dossier import (
    DossierContext,
    generate_dossier,
)
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    TeamStatsBombProfile,
)
from bip.evaluation.tournaments.team_style_profiler.tactical_identity import (
    TacticalIdentity,
    derive_tactical_identity,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import TeamStyleVector

PROJECT = Path(__file__).resolve().parents[3]
TSV_DIR = PROJECT / "data" / "cache" / "tsp" / "profiles"
SB_DIR = PROJECT / "data" / "cache" / "tsp" / "profiles_statsbomb"
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "dossier_demos"

MATCHUPS = [
    ("Spain", "Morocco", date(2026, 7, 1)),
    ("Argentina", "Mexico", date(2026, 6, 14)),
    ("France", "Croatia", date(2026, 6, 25)),
]


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


def _load_tsv(name: str) -> TeamStyleVector | None:
    p = TSV_DIR / f"{_slug(name)}_tsv.json"
    return TeamStyleVector.model_validate_json(p.read_text()) if p.exists() else None


def _load_tid(name: str) -> TacticalIdentity | None:
    p = SB_DIR / f"{_slug(name)}_sb.json"
    if not p.exists():
        return None
    return derive_tactical_identity(TeamStatsBombProfile.model_validate_json(p.read_text()))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for home, away, fdate in MATCHUPS:
        ctx = DossierContext(
            home_team=home,
            away_team=away,
            home_tsv=_load_tsv(home),
            away_tsv=_load_tsv(away),
            tournament_slug="world_cup_2026",
            fixture_date=fdate,
            home_tid=_load_tid(home),
            away_tid=_load_tid(away),
        )
        dossier = generate_dossier(ctx)
        md = render_markdown(dossier)
        out = OUT_DIR / f"{_slug(home)}_vs_{_slug(away)}_tactical.md"
        out.write_text(md)
        print(f"  ✓ {home} vs {away} → {out.relative_to(PROJECT)}")
    print(f"\nFirst dossier preview:\n{'='*70}")
    h, a, fd = MATCHUPS[0]
    ctx = DossierContext(
        home_team=h, away_team=a,
        home_tsv=_load_tsv(h), away_tsv=_load_tsv(a),
        tournament_slug="world_cup_2026", fixture_date=fd,
        home_tid=_load_tid(h), away_tid=_load_tid(a),
    )
    print(render_markdown(generate_dossier(ctx)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
