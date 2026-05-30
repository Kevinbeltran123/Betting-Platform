"""One-command match analysis.

    uv run python -m scripts.spike.tsp.39_analyze "Spain" "Morocco"
    uv run python -m scripts.spike.tsp.39_analyze "Spain" "Morocco" --referee="Mateu Lahoz"
    uv run python -m scripts.spike.tsp.39_analyze "Spain" "Morocco" --no-injuries

Pulls fresh injuries (Transfermarkt), looks up the referee if given, loads every
cached layer + ESPN current form, assembles the Match Intel and writes/prints it.
Read §0 (Investigar tú) first — it is a briefing, not a verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.intel import render_intel_markdown
from bip.evaluation.tournaments.team_style_profiler.intel_io import build_match_intel

OUT = Path(__file__).resolve().parents[3] / "data" / "cache" / "tsp" / "dossier_demos"


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = [a for a in argv if a.startswith("--")]
    if len(args) < 2:
        print('Uso: 39_analyze "Home" "Away" [--referee="Name"] [--no-injuries]')
        return 1
    home, away = args[0], args[1]
    referee = None
    if "--referee" in flags or any(a.startswith("--referee=") for a in flags):
        # accept --referee=Name or --referee then next positional was consumed; simplest: --referee=Name
        for a in flags:
            if a.startswith("--referee="):
                referee = a.split("=", 1)[1]

    print(f"Analizando {home} vs {away}"
          + (f" (árbitro: {referee})" if referee else "")
          + ("  [sin pull de lesiones]" if "--no-injuries" in flags else "  [pull de lesiones en vivo…]"))

    intel = build_match_intel(
        home, away, referee_name=referee,
        pull_injuries="--no-injuries" not in flags)
    md = render_intel_markdown(intel)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{_slug(home)}_vs_{_slug(away)}_intel.md"
    path.write_text(md)
    print(f"\n→ {path.relative_to(Path(__file__).resolve().parents[3])}\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
