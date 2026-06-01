"""Capa de precio (#1) — pull de cuotas + merge manual + cache para el brief.

API-Football /odds trae fiable 1X2, Over/Under (goles), BTTS y Asian Handicap
(verificado en vivo 2026-06-01: 9 casas incl. Betano/Pinnacle/Betfair). NO trae
córners/tarjetas poblados pese a estar en el catálogo → esos se pegan a mano en
data/cache/tsp/manual_odds/{slug}.json (ver manual_odds_TEMPLATE.json).

Las cuotas se pueblan en ventana móvil ~7-14d pre-KO; antes de eso /odds devuelve
results=0 y este script degrada limpio (cache con auto={} y solo lo manual si lo hay).

El "justo" (fair) se de-viga desde Pinnacle (la casa más sharp): es el consenso del
mercado limpio de margen, NO un modelo nuestro. Ancla para leer la línea, no un EV.

Uso:
    uv run python scripts/spike/tsp/45_match_odds.py "Mexico" "South Africa"
    uv run python scripts/spike/tsp/45_match_odds.py "Mexico" "South Africa" --fixture 1489369

Salida: data/cache/tsp/odds/{home}_vs_{away}.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.intel_io import (
    _API_FOOTBALL_TEAM_ALIAS,
    _api_football_key,
)

PROJECT = Path(__file__).resolve().parents[3]
ODDS_DIR = PROJECT / "data" / "cache" / "tsp" / "odds"
MANUAL_DIR = PROJECT / "data" / "cache" / "tsp" / "manual_odds"

BOOKS = ("Betano", "Pinnacle", "Betfair")  # staking + dos sharp para ancla
SEASON = 2026


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _two_way_fair(a: float | None, b: float | None) -> float | None:
    """Prob de-vigada del lado A en un mercado de 2 vías (cuotas decimales)."""
    if not a or not b:
        return None
    ia, ib = 1.0 / a, 1.0 / b
    return round(ia / (ia + ib), 3)


def _by_value(bet: dict) -> dict[str, float | None]:
    return {v.get("value"): _f(v.get("odd")) for v in bet.get("values", [])}


def _books_in(fixture_block: dict) -> dict[str, dict]:
    """{book_name: {bet_name: {value: odd}}} para las casas que nos importan."""
    out: dict[str, dict] = {}
    for bm in fixture_block.get("bookmakers", []) or []:
        name = bm.get("name")
        if name not in BOOKS:
            continue
        out[name] = {bet.get("name"): _by_value(bet) for bet in bm.get("bets", []) or []}
    return out


def _market_1x2(books: dict[str, dict]) -> dict | None:
    rows: dict[str, dict] = {}
    for bk, bets in books.items():
        m = bets.get("Match Winner")
        if not m:
            continue
        rows[bk.lower()] = {"home": m.get("Home"), "draw": m.get("Draw"), "away": m.get("Away")}
    if not rows:
        return None
    pin = rows.get("pinnacle") or rows.get("betfair")
    fair = None
    if pin and all(pin.get(k) for k in ("home", "draw", "away")):
        inv = {k: 1.0 / pin[k] for k in ("home", "draw", "away")}
        s = sum(inv.values())
        fair = {k: round(inv[k] / s, 3) for k in inv}
    rows["fair_pinnacle"] = fair
    return rows


def _market_ou(books: dict[str, dict], bet_name: str) -> list[dict]:
    """Agrupa Over/Under por línea (goles). Devuelve lista ordenada por |line-2.5|."""
    by_line: dict[float, dict] = {}
    for bk, bets in books.items():
        m = bets.get(bet_name)
        if not m:
            continue
        for value, odd in m.items():
            if not value:
                continue
            side, _, ln = value.partition(" ")
            line = _f(ln)
            if line is None or side not in ("Over", "Under"):
                continue
            row = by_line.setdefault(line, {"line": line})
            row.setdefault(bk.lower(), {})[side.lower()] = odd
    out = []
    for line, row in by_line.items():
        pin = row.get("pinnacle") or row.get("betfair") or {}
        row["fair_pinnacle_over"] = _two_way_fair(pin.get("over"), pin.get("under"))
        out.append(row)
    out.sort(key=lambda r: abs(r["line"] - 2.5))
    return out


def _market_btts(books: dict[str, dict]) -> dict | None:
    rows: dict[str, dict] = {}
    for bk, bets in books.items():
        m = bets.get("Both Teams Score")
        if not m:
            continue
        rows[bk.lower()] = {"yes": m.get("Yes"), "no": m.get("No")}
    if not rows:
        return None
    pin = rows.get("pinnacle") or rows.get("betfair") or {}
    rows["fair_pinnacle_yes"] = _two_way_fair(pin.get("yes"), pin.get("no"))
    return rows


def _market_ah(books: dict[str, dict]) -> list[dict]:
    """Asian Handicap agrupado por línea de Home (p.ej. 'Home -0.5')."""
    by_line: dict[str, dict] = {}
    for bk, bets in books.items():
        m = bets.get("Asian Handicap")
        if not m:
            continue
        for value, odd in m.items():
            if not value:
                continue
            side, _, ln = value.partition(" ")
            if side not in ("Home", "Away"):
                continue
            row = by_line.setdefault(ln, {"line": ln})
            row.setdefault(bk.lower(), {})[side.lower()] = odd
    out = []
    for ln, row in by_line.items():
        pin = row.get("pinnacle") or row.get("betfair") or {}
        row["fair_pinnacle_home"] = _two_way_fair(pin.get("home"), pin.get("away"))
        out.append(row)
    # ordena por la línea numérica del hándicap si parsea
    out.sort(key=lambda r: abs(_f(r["line"].lstrip("+")) or 0.0))
    return out


async def _team_id(c, name: str) -> int | None:
    q = _API_FOOTBALL_TEAM_ALIAS.get(name, name)
    j = (await c._client.get("/teams", params={"name": q})).json().get("response", [])
    nat = [t for t in j if t.get("team", {}).get("national")]
    pick = nat[0] if nat else (j[0] if j else None)
    return pick["team"]["id"] if pick else None


async def _resolve_fixture(c, home: str, away: str) -> tuple[int | None, str | None]:
    hid, aid = await _team_id(c, home), await _team_id(c, away)
    if not hid or not aid:
        return None, None
    fx = (await c._client.get(
        "/fixtures", params={"team": hid, "season": SEASON})).json().get("response", [])
    match = next((f for f in fx
                  if {f["teams"]["home"]["id"], f["teams"]["away"]["id"]} == {hid, aid}), None)
    if match is None:
        return None, None
    return match["fixture"]["id"], match["fixture"]["date"][:10]


async def _fetch_auto(home: str, away: str, fixture_id: int | None) -> dict:
    """Devuelve el bloque 'auto' (vacío si no hay cuotas pobladas todavía)."""
    from bip.sports.football.client import ApiFootballClient
    key = _api_football_key()
    if not key:
        return {"note": "sin API key"}
    async with ApiFootballClient(api_key=key) as c:
        fdate = None
        if fixture_id is None:
            fixture_id, fdate = await _resolve_fixture(c, home, away)
        if fixture_id is None:
            return {"note": "no se resolvió el fixture en API-Football"}
        resp = (await c._client.get("/odds", params={"fixture": fixture_id})).json()
        if not resp.get("response"):
            return {"fixture_id": fixture_id, "date": fdate,
                    "note": "cuotas no publicadas aún (ventana ~7-14d pre-KO)"}
        block = resp["response"][0]
        books = _books_in(block)
        return {
            "fixture_id": fixture_id,
            "date": fdate or block.get("fixture", {}).get("date", "")[:10] or None,
            "books": list(books.keys()),
            "match_winner": _market_1x2(books),
            "over_under": _market_ou(books, "Goals Over/Under"),
            "btts": _market_btts(books),
            "asian_handicap": _market_ah(books),
        }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fid = None
    for a in sys.argv[1:]:
        if a.startswith("--fixture"):
            fid = int(a.split("=", 1)[1]) if "=" in a else int(args.pop())
    if len(args) < 2:
        print('uso: 45_match_odds.py "Home" "Away" [--fixture=ID]')
        return 1
    home, away = args[0], args[1]

    auto = asyncio.run(_fetch_auto(home, away, fid))

    slug = f"{_slug(home)}_vs_{_slug(away)}"
    manual_path = MANUAL_DIR / f"{slug}.json"
    manual = json.loads(manual_path.read_text()) if manual_path.exists() else {}

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "home": home, "away": away,
        "fetched": date.today().isoformat(),
        "auto": auto,
        "manual": manual,
    }
    path = ODDS_DIR / f"{slug}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    note = auto.get("note")
    books = auto.get("books")
    print(f"-> {path.relative_to(PROJECT)}")
    if books:
        print(f"   AUTO: casas={books} · 1X2={'sí' if auto.get('match_winner') else 'no'}"
              f" · OU={len(auto.get('over_under') or [])} líneas"
              f" · BTTS={'sí' if auto.get('btts') else 'no'}"
              f" · AH={len(auto.get('asian_handicap') or [])} líneas")
    else:
        print(f"   AUTO: {note}")
    if manual:
        print(f"   MANUAL: sí ({', '.join(manual.keys())})")
    else:
        print(f"   MANUAL: no (pega en {manual_path.relative_to(PROJECT)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
