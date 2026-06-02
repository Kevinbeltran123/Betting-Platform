"""#7 — Tabla de árbitros desde API-Football (n grande, nombres consistentes con el fixture WC).

La tabla de StatsBomb (script 31) solo tiene el puñado de partidos de torneo por árbitro y
le faltan árbitros que no pitaron esos 4 torneos. API-Football da, por árbitro, decenas de
partidos de su liga doméstica — y CON EL MISMO formato de nombre que trae el árbitro del
fixture WC (p.ej. 'A. Taylor', 'M. Oliver') → el match de referee_by_name es fiable.

Fuente: /fixtures/statistics por partido (Yellow/Red Cards + Fouls de ambos equipos, 1 call/
fixture). NOTA: los penaltis NO están en /statistics → quedan SIN medir aquí (señal débil; la
tabla StatsBomb de fallback los cubre para el pool de élite). Reusa build_referee_tendencies.

Salida: data/cache/tsp/referee_tendencies_af.json (mismo esquema que script 31).
intel_io.referee_by_name prefiere esta tabla y cae a la de StatsBomb por árbitro.

Uso:
    uv run python scripts/spike/tsp/47_build_referee_tendencies_apifootball.py            # ligas por defecto
    uv run python scripts/spike/tsp/47_build_referee_tendencies_apifootball.py 39 140     # ids de liga
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.intel_io import _api_football_key
from bip.evaluation.tournaments.team_style_profiler.referee_tendencies import (
    MatchDiscipline,
    build_referee_tendencies,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT = PROJECT / "data" / "cache" / "tsp" / "referee_tendencies_af.json"

# Ligas domésticas donde pita el grueso del pool WC (UEFA + CONMEBOL + CONCACAF).
# country = nacionalidad-proxy del árbitro (en liga doméstica casi siempre coincide).
LEAGUES: dict[int, str] = {
    39: "England", 140: "Spain", 135: "Italy", 78: "Germany", 61: "France",
    88: "Netherlands", 94: "Portugal", 71: "Brazil", 128: "Argentina", 262: "Mexico",
}
SEASON = 2024


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _by_type(stats: list[dict]) -> dict:
    return {s["type"]: s["value"] for s in stats}


async def _collect_league(c, lid: int) -> dict[str, list[MatchDiscipline]]:
    # Métodos con @retry (tenacity) — un ReadTimeout suelto NO debe matar un run de miles de calls.
    fx = (await c.get_fixtures_by_season(lid, SEASON)).get("response", [])
    by_ref: dict[str, list[MatchDiscipline]] = defaultdict(list)
    for f in fx:
        if f["fixture"]["status"]["short"] != "FT":
            continue
        ref = (f["fixture"].get("referee") or "").split(",")[0].strip()
        if not ref:
            continue
        try:
            st = (await c.get_statistics(f["fixture"]["id"])).get("response", [])
        except Exception:
            continue  # fixture con stats no disponibles / fallo transitorio agotó retries
        if len(st) < 2:
            continue
        yel = red = fouls = 0
        for b in st:
            t = _by_type(b.get("statistics", []))
            yel += _int(t.get("Yellow Cards"))
            red += _int(t.get("Red Cards"))
            fouls += _int(t.get("Fouls"))
        by_ref[ref].append(MatchDiscipline(yellows=yel, reds=red, fouls=fouls, penalties=0))
    return by_ref


async def main() -> int:
    from bip.sports.football.client import ApiFootballClient
    key = _api_football_key()
    if not key:
        print("NO API KEY")
        return 1
    arg_ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
    leagues = {lid: LEAGUES.get(lid, "") for lid in arg_ids} if arg_ids else LEAGUES

    per_ref: dict[str, tuple[str, list[MatchDiscipline]]] = {}
    async with ApiFootballClient(api_key=key) as c:
        for lid, country in leagues.items():
            by_ref = await _collect_league(c, lid)
            for ref, matches in by_ref.items():
                if ref in per_ref:  # mismo nombre en dos ligas: acumula
                    per_ref[ref][1].extend(matches)
                else:
                    per_ref[ref] = (country, matches)
            print(f"liga {lid} ({country}): {len(by_ref)} árbitros, "
                  f"{sum(len(m) for m in by_ref.values())} partidos")

    table = build_referee_tendencies(per_ref)
    OUT.write_text(json.dumps({
        name: {
            "country": t.country, "n_matches": t.n_matches,
            "confidence": t.confidence, "strictness": t.strictness,
            "cards_per_match": round(t.cards_per_match.mean, 2),
            "yellows_per_match": round(t.yellows_per_match.mean, 2),
            "reds_per_match": round(t.reds_per_match.mean, 3),
            "fouls_per_match": round(t.fouls_per_match.mean, 1),
            "penalties_per_match": round(t.penalties_per_match.mean, 3),  # 0: no medido (ver módulo)
        }
        for name, t in sorted(table.items())
    }, indent=2, ensure_ascii=False))
    reliable = [t for t in table.values() if t.confidence in ("green", "yellow")]
    print(f"\n-> {len(table)} árbitros ({len(reliable)} con n>=4) -> {OUT.relative_to(PROJECT)}")
    for t in sorted(reliable, key=lambda x: -x.cards_per_match.mean)[:8]:
        print(f"  {t.strictness:8} {t.cards_per_match.mean:4.1f} tarj/p  {t.fouls_per_match.mean:4.0f} faltas/p  "
              f"n={t.n_matches:3}  {t.referee_name}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
