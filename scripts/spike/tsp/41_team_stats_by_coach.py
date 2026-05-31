"""Corroborate the qualitative playing-style overlay with API-Football match stats,
aggregated ONLY over fixtures played under the CURRENT head coach.

Why current-coach-only: playing style is the coach's, not the federation's — mixing
in a previous manager's matches pollutes the signature (operator directive 2026-05-31).

Coach appointment dates are from the 2024-2026 web research that built §6 of
notes/PLAYING_STYLES_REFERENCE.md (month-level; approximate but enough to exclude
the previous regime). API-Football's /coachs endpoint is too noisy to trust here.

Output: data/cache/tsp/api_team_stats_by_coach.json + a printed corroboration table.
Stats available for competitive internationals: possession, passes%, shots (for/against),
corners (for/against), fouls, cards, goals (for/against). xG is None for internationals.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.intel_io import (
    _API_FOOTBALL_TEAM_ALIAS,
    _api_football_key,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT = PROJECT / "data" / "cache" / "tsp" / "api_team_stats_by_coach.json"

MAX_MATCHES = 20          # cap stats-bearing matches per team (recent under current DT)
SCAN_FIXTURES = 45        # how many recent fixtures to scan back through

# team (lock.json name) -> current coach + ISO appointment date (from §6 research).
COACH_SINCE: dict[str, tuple[str, str]] = {
    "Argentina": ("Scaloni", "2018-08-01"),
    "France": ("Deschamps", "2012-07-01"),
    "Spain": ("de la Fuente", "2022-12-01"),
    "Brazil": ("Ancelotti", "2025-05-01"),
    "England": ("Tuchel", "2025-01-01"),
    "Germany": ("Nagelsmann", "2023-09-01"),
    "Portugal": ("Martínez", "2023-01-01"),
    "Netherlands": ("Koeman", "2023-06-01"),
    "Belgium": ("Rudi Garcia", "2025-01-01"),
    "Croatia": ("Dalić", "2017-10-01"),
    "Switzerland": ("Yakin", "2021-08-01"),
    "Austria": ("Rangnick", "2022-06-01"),
    "Norway": ("Solbakken", "2020-12-01"),
    "Scotland": ("Clarke", "2019-05-01"),
    "Czech Republic": ("Koubek", "2025-12-01"),
    "Sweden": ("Potter", "2025-10-20"),
    "Turkey": ("Montella", "2024-09-01"),
    "Bosnia and Herzegovina": ("Barbarez", "2024-04-01"),
    "Uruguay": ("Bielsa", "2023-05-01"),
    "Colombia": ("Lorenzo", "2022-06-01"),
    "Ecuador": ("Beccacece", "2024-08-01"),
    "Paraguay": ("Alfaro", "2024-08-01"),
    "Mexico": ("Aguirre", "2024-07-01"),
    "United States": ("Pochettino", "2024-09-01"),
    "Canada": ("Marsch", "2024-05-01"),
    "Panama": ("Christiansen", "2020-08-01"),
    "Curaçao": ("Advocaat", "2024-03-01"),
    "Haiti": ("Migné", "2024-01-01"),
    "Morocco": ("Ouahbi", "2026-03-05"),   # Regragui depuesto tras final AFCON 2025
    "Senegal": ("Pape Thiaw", "2024-12-13"),
    "Egypt": ("Hossam Hassan", "2024-07-01"),
    "Algeria": ("Petković", "2024-02-01"),
    "Tunisia": ("Lamouchi", "2026-01-14"),
    "Ivory Coast": ("Faé", "2024-01-01"),
    "Ghana": ("Queiroz", "2026-04-01"),
    "Cape Verde": ("Bubista", "2020-01-01"),
    "South Africa": ("Broos", "2021-05-01"),
    "DR Congo": ("Desabre", "2022-09-01"),
    "Japan": ("Moriyasu", "2021-07-01"),
    "South Korea": ("Hong Myung-bo", "2024-07-01"),
    "Iran": ("Ghalenoei", "2023-03-01"),
    "Australia": ("Popovic", "2024-09-01"),
    "Saudi Arabia": ("Donis", "2026-04-24"),
    "Qatar": ("Lopetegui", "2025-05-01"),
    "Uzbekistan": ("Cannavaro", "2025-10-01"),
    "Jordan": ("Sellami", "2024-06-01"),
    "Iraq": ("Graham Arnold", "2026-01-01"),
    "New Zealand": ("Bazeley", "2023-01-01"),
}


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.replace("%", "").strip()
        if not v:
            return None
    try:
        return float(v)
    except ValueError:
        return None


def _by_type(stats: list[dict]) -> dict[str, float | None]:
    return {s["type"]: _num(s["value"]) for s in stats}


async def _team_id(c, name: str) -> int | None:
    q = _API_FOOTBALL_TEAM_ALIAS.get(name, name)
    j = (await c._client.get("/teams", params={"name": q})).json().get("response", [])
    nat = [t for t in j if t.get("team", {}).get("national")]
    pick = nat[0] if nat else (j[0] if j else None)
    return pick["team"]["id"] if pick else None


async def _aggregate(c, name: str, tid: int, since: str) -> dict | None:
    fx = (await c._client.get(
        "/fixtures", params={"team": tid, "last": SCAN_FIXTURES})).json().get("response", [])
    rows: list[dict] = []
    for f in fx:
        if f["fixture"]["status"]["short"] != "FT":
            continue
        if f["fixture"]["date"][:10] < since:        # exclude previous-coach era
            continue
        fid = f["fixture"]["id"]
        st = (await c._client.get(
            "/fixtures/statistics", params={"fixture": fid})).json().get("response", [])
        if len(st) < 2:
            continue
        mine = next((b for b in st if b["team"]["id"] == tid), None)
        opp = next((b for b in st if b["team"]["id"] != tid), None)
        if mine is None or opp is None:
            continue
        is_home = f["teams"]["home"]["id"] == tid
        gf = f["goals"]["home"] if is_home else f["goals"]["away"]
        ga = f["goals"]["away"] if is_home else f["goals"]["home"]
        m, o = _by_type(mine["statistics"]), _by_type(opp["statistics"])
        rows.append({
            "poss": m.get("Ball Possession"), "pass_pct": m.get("Passes %"),
            "shots_f": m.get("Total Shots"), "sot_f": m.get("Shots on Goal"),
            "shots_a": o.get("Total Shots"),
            "corn_f": m.get("Corner Kicks"), "corn_a": o.get("Corner Kicks"),
            "fouls": m.get("Fouls"), "gf": gf, "ga": ga,
        })
        if len(rows) >= MAX_MATCHES:
            break
    if not rows:
        return None

    def avg(k):
        vals = [r[k] for r in rows if r[k] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "coach": COACH_SINCE[name][0], "since": since, "n_matches": len(rows),
        "possession": avg("poss"), "pass_pct": avg("pass_pct"),
        "shots_for": avg("shots_f"), "sot_for": avg("sot_f"), "shots_against": avg("shots_a"),
        "corners_for": avg("corn_f"), "corners_against": avg("corn_a"),
        "fouls": avg("fouls"), "goals_for": avg("gf"), "goals_against": avg("ga"),
    }


async def main() -> None:
    from bip.sports.football.client import ApiFootballClient
    key = _api_football_key()
    if not key:
        print("NO API KEY")
        return
    out: dict[str, dict] = {}
    async with ApiFootballClient(api_key=key) as c:
        for name, (coach, since) in COACH_SINCE.items():
            tid = await _team_id(c, name)
            if tid is None:
                print(f"{name:24} — no team id")
                continue
            agg = await _aggregate(c, name, tid, since)
            if agg is None:
                print(f"{name:24} — 0 stats matches under {coach} (since {since})")
                continue
            out[name] = agg
            print(f"{name:22} {coach[:14]:14} n={agg['n_matches']:2} "
                  f"pos={agg['possession']} pass%={agg['pass_pct']} "
                  f"sh {agg['shots_for']}/{agg['shots_against']} "
                  f"corn {agg['corners_for']}/{agg['corners_against']} "
                  f"GF/GA {agg['goals_for']}/{agg['goals_against']}")
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n-> {len(out)} teams -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
