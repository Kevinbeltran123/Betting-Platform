"""Demo: generate match dossiers for hypothetical WC2026 fixtures.

Showcases 4 fixture types:
  1. Argentina vs USA — CONMEBOL vs CONCACAF host, defensive matchup
  2. Brazil vs Germany — CONMEBOL vs UEFA, both attacking
  3. Morocco vs Senegal — CAF vs CAF, team-transfer signals
  4. Mexico vs France — CONCACAF host vs UEFA top
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.dossier_renderer import (
    render_json,
    render_markdown,
)
from bip.evaluation.tournaments.team_style_profiler.match_dossier import (
    DossierContext,
    generate_dossier,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import (
    TeamStyleVector,
)


ROOT = Path(__file__).resolve().parents[3]
PROFILES = ROOT / "data" / "cache" / "tsp" / "profiles"
DEMOS_DIR = ROOT / "data" / "cache" / "tsp" / "dossier_demos"


def _load(name: str) -> TeamStyleVector | None:
    safe = name.replace(" ", "_").replace("'", "").replace("ô", "o").lower()
    p = PROFILES / f"{safe}_tsv.json"
    if not p.exists():
        return None
    return TeamStyleVector.model_validate_json(p.read_text())


FIXTURES = [
    ("Argentina", "USA", "world_cup_2026", date(2026, 6, 14)),
    ("Brazil", "Germany", "world_cup_2026", date(2026, 6, 18)),
    ("Morocco", "Senegal", "world_cup_2026", date(2026, 6, 22)),
    ("Mexico", "France", "world_cup_2026", date(2026, 6, 14)),
    ("Spain", "Portugal", "world_cup_2026", date(2026, 7, 1)),
    ("Japan", "Argentina", "world_cup_2026", date(2026, 6, 25)),
]


def main() -> int:
    DEMOS_DIR.mkdir(parents=True, exist_ok=True)
    for home, away, tournament, fdate in FIXTURES:
        h = _load(home)
        a = _load(away)
        ctx = DossierContext(
            home_team=home, away_team=away,
            home_tsv=h, away_tsv=a,
            tournament_slug=tournament,
            fixture_date=fdate,
        )
        dossier = generate_dossier(ctx)
        md = render_markdown(dossier)
        js = render_json(dossier)
        slug = f"{home}_vs_{away}".replace(" ", "_").replace("'", "").lower()
        (DEMOS_DIR / f"{slug}.md").write_text(md)
        (DEMOS_DIR / f"{slug}.json").write_text(js)

        # Print top-line summary
        print(f"\n{'=' * 70}")
        print(f"{home} vs {away}  ({tournament}, {fdate})")
        print(f"{'=' * 70}")
        if not dossier.picks:
            print("  No picks generated.")
            continue
        for i, pick in enumerate(dossier.picks[:5], 1):
            cat = pick.category
            print(f"  [{i}] {cat:11} {pick.market:55} score={pick.score:.2f}")

        print(f"  → Markdown: {DEMOS_DIR / f'{slug}.md'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
