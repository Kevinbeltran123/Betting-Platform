"""#2 — Player-prop profiles desde API-Football (selección actual, DT actual).

Reemplaza el StatsBomb-torneo 2022-24 (script 30) como fuente del prop board:
por cada selección WC toma sus fixtures FT bajo el DT actual (reusa COACH_SINCE de 41),
baja /fixtures/players + /fixtures/events, parsea por jugador y reusa la MISMA agregación
(player_props.build_player_profiles + prop_board), agnóstica de fuente.

Salida: data/cache/tsp/player_props_af/{slug}.json (mismo esquema que script 30 + source).
intel_io.load_props prefiere player_props_af/ sobre player_props/ (StatsBomb) cuando existe.

Uso:
    uv run python scripts/spike/tsp/46_build_player_props_apifootball.py            # todas
    uv run python scripts/spike/tsp/46_build_player_props_apifootball.py Spain Senegal "Curaçao"
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.intel_io import (
    _API_FOOTBALL_TEAM_ALIAS,
    _api_football_key,
)
from bip.evaluation.tournaments.team_style_profiler.player_props import (
    build_player_profiles,
    prop_board,
)
from bip.evaluation.tournaments.team_style_profiler.player_props_apifootball import parse_fixture

PROJECT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "player_props_af"
SCRIPT41 = Path(__file__).resolve().parent / "41_team_stats_by_coach.py"

_spec = importlib.util.spec_from_file_location("script41", SCRIPT41)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
COACH_SINCE: dict[str, tuple[str, str]] = _mod.COACH_SINCE

SCAN_FIXTURES = 30   # fixtures recientes a escanear
MAX_MATCHES = 20     # tope de partidos con datos por equipo


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


async def _team_id(c, name: str) -> int | None:
    q = _API_FOOTBALL_TEAM_ALIAS.get(name, name)
    j = (await c._client.get("/teams", params={"name": q})).json().get("response", [])
    nat = [t for t in j if t.get("team", {}).get("national")]
    pick = nat[0] if nat else (j[0] if j else None)
    return pick["team"]["id"] if pick else None


async def _collect(c, tid: int, since: str) -> list:
    fx = (await c._client.get(
        "/fixtures", params={"team": tid, "last": SCAN_FIXTURES})).json().get("response", [])
    per_match = []
    for f in fx:
        if f["fixture"]["status"]["short"] != "FT":
            continue
        if f["fixture"]["date"][:10] < since:
            continue
        fid = f["fixture"]["id"]
        players = (await c._client.get(
            "/fixtures/players", params={"fixture": fid})).json().get("response", [])
        events = (await c._client.get(
            "/fixtures/events", params={"fixture": fid})).json().get("response", [])
        counts, meta, minutes = parse_fixture(players, events, tid)
        if counts:
            per_match.append((counts, meta, minutes))
        if len(per_match) >= MAX_MATCHES:
            break
    return per_match


def _to_json(team: str, profiles: list) -> dict:
    profiles = sorted(profiles, key=lambda x: -x.minutes_total)
    board = prop_board(profiles)
    return {
        "team": team,
        "source": "api_football",
        "n_players": len(profiles),
        "players": [{
            "name": p.player_name, "position": p.position,
            "n_matches": p.n_matches, "minutes": round(p.minutes_total),
            "confidence": p.confidence,
            "shots_per90": round(p.shots_per90.mean, 2),
            "sot_per90": round(p.shots_on_target_per90.mean, 2),
            "xg_per90": round(p.xg_per90.mean, 3),
            "goals_per90": round(p.goals_per90.mean, 3),
            "fouls_per90": round(p.fouls_committed_per90.mean, 2),
            "fouls_drawn_per90": round(p.fouls_drawn_per90.mean, 2),
            "yellows_per90": round(p.yellow_cards_per90.mean, 3),
            "assists_per90": round(p.assists_per90.mean, 3),
            "p_anytime_scorer": round(p.p_anytime_scorer, 3),
            "penalties_taken": p.penalties_taken,
        } for p in profiles],
        "prop_board": [{
            "market": c.market, "player": c.player_name, "position": c.position,
            "stat": c.stat, "softness": c.softness, "confidence": c.confidence,
        } for c in board],
    }


async def main() -> int:
    from bip.sports.football.client import ApiFootballClient
    key = _api_football_key()
    if not key:
        print("NO API KEY")
        return 1
    wanted = [a for a in sys.argv[1:]]
    teams = wanted or list(COACH_SINCE.keys())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    async with ApiFootballClient(api_key=key) as c:
        for name in teams:
            if name not in COACH_SINCE:
                print(f"{name:24} — no está en COACH_SINCE")
                continue
            _, since = COACH_SINCE[name]
            tid = await _team_id(c, name)
            if tid is None:
                print(f"{name:24} — no team id")
                continue
            per_match = await _collect(c, tid, since)
            if not per_match:
                print(f"{name:24} — 0 fixtures con datos desde {since}")
                continue
            profiles = build_player_profiles(per_match, source="api_football")
            data = _to_json(name, profiles)
            (OUT_DIR / f"{_slug(name)}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False))
            n_ok += 1
            soft = [c for c in data["prop_board"] if c["softness"] == 1][:3]
            print(f"{name:22} n_fx={len(per_match):2} jug={data['n_players']:2}  "
                  + " | ".join(f"{c['player']} ({c['market'].split()[0]})" for c in soft))
    print(f"\n-> {n_ok} equipos -> {OUT_DIR.relative_to(PROJECT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
