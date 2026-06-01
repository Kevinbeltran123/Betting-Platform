"""Viaje + descanso por fixture WC2026 (mejora C, Tier-1). Offline.

La asimetría de descanso/viaje es un factor de fatiga conocible HOY (sedes + calendario
confirmados) que el read de estilo ignora. Computa, por equipo, su secuencia de partidos
de FASE DE GRUPOS y, entre partidos consecutivos: días de descanso, viaje (misma ciudad /
intra-cluster / cross-cluster) y cambio de huso horario. Luego, por fixture, la ASIMETRÍA
local-vs-visitante.

Fuentes (todo ya en repo, offline):
- data/cache/martj42_international_results.csv  (fixtures WC: fecha, equipos, ciudad)
- data/cache/tsp/wc2026_venues.json             (cluster + huso por ciudad)

Output: data/cache/tsp/travel_rest.json (por fixture) + tabla impresa.
NOTA: viaje por cluster/huso (proxy honesto), no km exactos. MD1 no tiene 'descanso previo'.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
C = PROJECT / "data" / "cache"
CSV = C / "martj42_international_results.csv"
VENUES = json.loads((C / "tsp" / "wc2026_venues.json").read_text())
OUT = C / "tsp" / "travel_rest.json"

TZ_OFFSET = {"Pacific": -8, "Mountain": -7, "Central": -6, "Eastern": -5}


def _days(d1: str, d2: str) -> int:
    from datetime import date
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return (b - a).days


def group_fixtures() -> list[dict]:
    """Partidos de fase de grupos WC2026 (11-jun..27-jun), en orden."""
    out = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            if "World Cup" not in r["tournament"]:
                continue
            if "2026-06-11" <= r["date"] <= "2026-06-27":
                out.append(r)
    out.sort(key=lambda r: r["date"])
    return out


def team_schedules(fx: list[dict]) -> dict[str, list[dict]]:
    sched: dict[str, list[dict]] = {}
    for r in fx:
        for t in (r["home_team"], r["away_team"]):
            sched.setdefault(t, []).append({"date": r["date"], "city": r["city"]})
    for t in sched:
        sched[t].sort(key=lambda m: m["date"])
    return sched


def leg(prev_city: str | None, city: str) -> tuple[str, int]:
    """Devuelve (descripción de viaje, cambio de huso) desde prev_city a city."""
    if prev_city is None:
        return ("—", 0)
    v0, v1 = VENUES.get(prev_city), VENUES.get(city)
    if not v0 or not v1:
        return ("?", 0)
    tz = abs(TZ_OFFSET.get(v0["tz"], -6) - TZ_OFFSET.get(v1["tz"], -6))
    if prev_city == city:
        return ("misma ciudad", tz)
    if v0["cluster"] == v1["cluster"]:
        return (f"intra-cluster {v0['cluster']}", tz)
    return (f"cross-cluster {v0['cluster']}→{v1['cluster']}", tz)


def main() -> None:
    fx = group_fixtures()
    sched = team_schedules(fx)

    def leg_for(team: str, date: str) -> dict:
        ms = sched[team]
        idx = next(i for i, m in enumerate(ms) if m["date"] == date)
        if idx == 0:
            return {"rest_days": None, "travel": "—(debut)", "tz_shift": 0, "matchday": 1}
        prev = ms[idx - 1]
        cur = ms[idx]
        desc, tz = leg(prev["city"], cur["city"])
        return {"rest_days": _days(prev["date"], cur["date"]), "travel": desc,
                "tz_shift": tz, "matchday": idx + 1}

    result: dict[str, dict] = {}
    for r in fx:
        h, a = r["home_team"], r["away_team"]
        lh, la = leg_for(h, r["date"]), leg_for(a, r["date"])
        rest_edge = None
        if lh["rest_days"] is not None and la["rest_days"] is not None:
            d = lh["rest_days"] - la["rest_days"]
            if d >= 1:
                rest_edge = f"{h} +{d}d descanso"
            elif d <= -1:
                rest_edge = f"{a} +{-d}d descanso"
            else:
                rest_edge = "igual"
        result[f"{h} vs {a}"] = {
            "date": r["date"], "city": r["city"], "home": lh, "away": la, "rest_edge": rest_edge,
        }

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"{'Fixture':38} {'fecha':10} {'local: desc/viaje':32} {'visit: desc/viaje':32} edge")
    for k, v in result.items():
        def fmt(x):
            rd = "MD1" if x["rest_days"] is None else f"{x['rest_days']}d"
            tz = f" +{x['tz_shift']}h" if x["tz_shift"] else ""
            return f"{rd} {x['travel']}{tz}"[:31]
        print(f"{k:38} {v['date']:10} {fmt(v['home']):32} {fmt(v['away']):32} {v['rest_edge'] or ''}")
    print(f"\n-> {OUT}  ({len(result)} fixtures)")


if __name__ == "__main__":
    main()
