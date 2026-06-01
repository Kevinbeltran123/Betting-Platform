"""Brief de pre-partido WC2026 — ENSAMBLADOR de evidencia (mejora A, Tier-1).

Fusiona deterministamente las capas ya construidas para UN fixture y emite una hoja
de evidencia ordenada para análisis HUMANO. NO puntúa ni emite picks
(respeta feedback_analyst_approach): calcula los cruces mecánicos + señala dónde leer
la prosa de notes/PLAYING_STYLES_REFERENCE.md.

Uso:
    uv run python scripts/spike/tsp/43_match_brief.py "Mexico" "South Africa"
    uv run python scripts/spike/tsp/43_match_brief.py "Czech Republic" "South Africa"
    (acepta alias: USA, Czechia, Korea, etc. Sede/fecha se resuelven del CSV de fixtures.)

Fuentes (markdown = fuente de verdad; aquí solo se DERIVA):
- data/cache/tsp/api_team_stats_by_coach.json   (§6.6 stats, live)
- data/cache/tsp/strength_of_schedule.json      (§6.6-bis SoS, live)
- data/cache/tsp/wc2026_venues.json             (entorno de sede)
- data/cache/martj42_international_results.csv   (fixture: sede/fecha)
- TEAM_META abajo                                (derivado de §6.8: rating ABP def, deliverer, GK débil, host)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
C = PROJECT / "data" / "cache"
STATS = json.loads((C / "tsp" / "api_team_stats_by_coach.json").read_text())
SOS = json.loads((C / "tsp" / "strength_of_schedule.json").read_text())
VENUES = json.loads((C / "tsp" / "wc2026_venues.json").read_text())
_TR = C / "tsp" / "travel_rest.json"
TRAVEL = json.loads(_TR.read_text()) if _TR.exists() else {}
CSV = C / "martj42_international_results.csv"
ODDS = C / "tsp" / "odds"   # caché de cuotas (mejora #1, escrita por 45_match_odds.py)

# Derivado de §6.8 (rating ABP DEFENSIVA) + síntesis. Actualizar si §6.8 cambia.
# r=rating defensa-ABP, dlv=ataque-ABP fuerte (deliverer), gk=portero débil saliendo, host=anfitrión.
TEAM_META: dict[str, dict] = {
    "England": {"r": "🟡", "dlv": True, "gk": False, "cf": "UEFA"},
    "France": {"r": "🟡", "dlv": False, "gk": True, "cf": "UEFA"},
    "Spain": {"r": "🟢", "dlv": False, "gk": False, "cf": "UEFA"},
    "Germany": {"r": "🟢", "dlv": True, "gk": False, "cf": "UEFA"},
    "Portugal": {"r": "🟡", "dlv": False, "gk": True, "cf": "UEFA"},
    "Netherlands": {"r": "🟡", "dlv": False, "gk": True, "cf": "UEFA"},
    "Belgium": {"r": "🟡", "dlv": False, "gk": False, "cf": "UEFA"},
    "Croatia": {"r": "🟢", "dlv": False, "gk": False, "cf": "UEFA"},
    "Switzerland": {"r": "🟢", "dlv": False, "gk": False, "cf": "UEFA"},
    "Austria": {"r": "🟢", "dlv": False, "gk": False, "cf": "UEFA"},
    "Norway": {"r": "🟡", "dlv": True, "gk": False, "cf": "UEFA"},
    "Scotland": {"r": "🟡", "dlv": True, "gk": True, "cf": "UEFA"},
    "Czech Republic": {"r": "🟡", "dlv": True, "gk": False, "cf": "UEFA"},
    "Sweden": {"r": "🔴", "dlv": True, "gk": True, "cf": "UEFA"},
    "Turkey": {"r": "🟡", "dlv": False, "gk": False, "cf": "UEFA"},
    "Bosnia and Herzegovina": {"r": "🟡", "dlv": False, "gk": True, "cf": "UEFA"},
    "Argentina": {"r": "🟢", "dlv": False, "gk": False, "cf": "CONMEBOL"},
    "Brazil": {"r": "🟢", "dlv": False, "gk": False, "cf": "CONMEBOL"},
    "Uruguay": {"r": "🟢", "dlv": False, "gk": False, "cf": "CONMEBOL"},
    "Colombia": {"r": "🟡", "dlv": True, "gk": True, "cf": "CONMEBOL"},
    "Ecuador": {"r": "🟢", "dlv": False, "gk": True, "cf": "CONMEBOL"},
    "Paraguay": {"r": "🟢", "dlv": True, "gk": False, "cf": "CONMEBOL"},
    "Mexico": {"r": "🔴", "dlv": False, "gk": True, "cf": "CONCACAF", "host": True},
    "United States": {"r": "🟡", "dlv": False, "gk": False, "cf": "CONCACAF", "host": True},
    "Canada": {"r": "🟡", "dlv": False, "gk": True, "cf": "CONCACAF", "host": True},
    "Panama": {"r": "🟡", "dlv": False, "gk": True, "cf": "CONCACAF"},
    "Curaçao": {"r": "🔴", "dlv": False, "gk": True, "cf": "CONCACAF"},
    "Haiti": {"r": "🟡", "dlv": False, "gk": True, "cf": "CONCACAF"},
    "Morocco": {"r": "🟡", "dlv": False, "gk": False, "cf": "CAF"},
    "Senegal": {"r": "🟡", "dlv": True, "gk": False, "cf": "CAF"},
    "Egypt": {"r": "🟢", "dlv": False, "gk": False, "cf": "CAF"},
    "Algeria": {"r": "🟡", "dlv": False, "gk": True, "cf": "CAF"},
    "Tunisia": {"r": "🟢", "dlv": False, "gk": False, "cf": "CAF"},
    "Ivory Coast": {"r": "🟡", "dlv": True, "gk": True, "cf": "CAF"},
    "Ghana": {"r": "🟡", "dlv": False, "gk": False, "cf": "CAF"},
    "Cape Verde": {"r": "🟢", "dlv": False, "gk": False, "cf": "CAF"},
    "South Africa": {"r": "🔴", "dlv": False, "gk": True, "cf": "CAF"},
    "DR Congo": {"r": "🟢", "dlv": False, "gk": False, "cf": "CAF"},
    "Japan": {"r": "🟡", "dlv": False, "gk": False, "cf": "AFC"},
    "South Korea": {"r": "🔴", "dlv": False, "gk": True, "cf": "AFC"},
    "Iran": {"r": "🟢", "dlv": False, "gk": False, "cf": "AFC"},
    "Australia": {"r": "🟢", "dlv": True, "gk": False, "cf": "AFC"},
    "Saudi Arabia": {"r": "🟡", "dlv": False, "gk": False, "cf": "AFC"},
    "Qatar": {"r": "🔴", "dlv": False, "gk": True, "cf": "AFC"},
    "Uzbekistan": {"r": "🟢", "dlv": False, "gk": False, "cf": "AFC"},
    "Jordan": {"r": "🟡", "dlv": False, "gk": True, "cf": "AFC"},
    "Iraq": {"r": "🟡", "dlv": False, "gk": True, "cf": "AFC"},
    "New Zealand": {"r": "🟡", "dlv": True, "gk": True, "cf": "OFC"},
}

ALIASES = {  # input cómodo -> nombre lock
    "usa": "United States", "us": "United States", "czechia": "Czech Republic",
    "korea": "South Korea", "south korea": "South Korea", "ivory coast": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast", "bosnia": "Bosnia and Herzegovina",
    "dr congo": "DR Congo", "drc": "DR Congo", "cape verde": "Cape Verde",
    "türkiye": "Turkey", "turkey": "Turkey", "curacao": "Curaçao",
}

# Señales de confederación (project_wc2026_operational_signals)
CONF_EDGE = {"CONMEBOL": "+5% vs UEFA (histórico)", "CAF": "CAF×AFC edge ×1.40 si enfrenta AFC"}


def resolve(name: str) -> str | None:
    if name in TEAM_META:
        return name
    low = name.strip().lower()
    if low in ALIASES:
        return ALIASES[low]
    for k in TEAM_META:
        if k.lower() == low:
            return k
    return None


def matchday(date: str) -> str:
    if "2026-06-11" <= date <= "2026-06-15":
        return "J1"
    if "2026-06-16" <= date <= "2026-06-21":
        return "J2"
    if "2026-06-22" <= date <= "2026-06-27":
        return "J3"
    return "KO/otro"


def find_fixture(home: str, away: str) -> dict | None:
    """Busca el fixture (en cualquier orden) en el CSV; devuelve {date, city, country, tournament, home, away}."""
    with open(CSV) as f:
        for r in csv.DictReader(f):
            pair = {r["home_team"], r["away_team"]}
            if pair == {home, away} and r["date"] >= "2026-06-01":
                return r
    return None


def stat_line(name: str) -> str:
    s = STATS.get(name)
    if not s:
        return "(sin §6.6 — DT muy reciente)"
    return (f"pos {s['possession']}% · SOT {s['sot_for']}/{s.get('sot_against','?')} · "
            f"córn {s['corners_for']}/{s['corners_against']} · faltas {s['fouls']} · "
            f"TA {s['yellow_cards']} · GF/GA {s['goals_for']}/{s['goals_against']} (n={s['n_matches']})")


def sos_line(name: str) -> tuple[str, float | None, str | None]:
    v = SOS.get(name)
    if not v:
        return "(sin SoS — DT desde abril; usar §6.6 crudo con cautela)", None, None
    return (f"Elo {v['own_elo']:.0f} · SoS {v['sos_opp_elo']:.0f} ({v['schedule']}, Δ{v['sos_delta_vs_mean']:+.0f})",
            v["own_elo"], v["schedule"])


def aerial_flag(att: str, dfn: str) -> str | None:
    a, d = TEAM_META[att], TEAM_META[dfn]
    if a["dlv"] and (d["r"] == "🔴" or d["gk"]):
        why = []
        if d["r"] == "🔴":
            why.append("zaga 🔴")
        if d["gk"]:
            why.append("portero débil saliendo")
        return f"🎯 {att} (ataque ABP fuerte) × {dfn} ({', '.join(why)}) → córner/header de {att}"
    return None


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


def load_odds(h: str, a: str) -> dict | None:
    f = ODDS / f"{_slug(h)}_vs_{_slug(a)}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _exp_corners(h: str, a: str) -> float | None:
    """Total de córners esperado (crudo, no SoS-aj): mezcla F propio con C del rival."""
    sh, sa = STATS.get(h), STATS.get(a)
    if not sh or not sa:
        return None
    vals = (sh.get("corners_for"), sh.get("corners_against"),
            sa.get("corners_for"), sa.get("corners_against"))
    if any(v is None for v in vals):
        return None
    cfh, cah, cfa, caa = vals
    return round((cfh + caa) / 2 + (cfa + cah) / 2, 1)


def _exp_cards(h: str, a: str) -> float | None:
    """Amarillas combinadas esperadas (proxy: TA propia de cada lado, sin árbitro)."""
    sh, sa = STATS.get(h), STATS.get(a)
    if not sh or not sa:
        return None
    yh, ya = sh.get("yellow_cards"), sa.get("yellow_cards")
    if yh is None or ya is None:
        return None
    return round(yh + ya, 1)


def price_section(h: str, a: str, eh: float | None, ea: float | None) -> list[str]:
    """Puente evidencia<->mercado. AUTO = API-Football (de-vig Pinnacle); MANUAL = pegado."""
    out = ["\n## Precio y línea"]
    odds = load_odds(h, a)
    if not odds:
        out.append(f"- Sin caché de cuotas. Corre `45_match_odds.py \"{h}\" \"{a}\"` cerca del KO "
                   "(ventana ~7-14d) y/o pega líneas blandas en data/cache/tsp/manual_odds/.")
        return out
    auto = odds.get("auto") or {}
    manual = odds.get("manual") or {}

    mw = auto.get("match_winner")
    if mw and mw.get("fair_pinnacle"):
        fp, bet = mw["fair_pinnacle"], (mw.get("betano") or {})
        out.append(f"- [AUTO] 1X2 justo (Pinnacle de-vig): {h} {fp['home']:.0%} / X {fp['draw']:.0%} / {a} {fp['away']:.0%}"
                   + (f" · Betano {bet.get('home')}/{bet.get('draw')}/{bet.get('away')}" if bet else ""))
        if eh and ea:
            mkt_fav = h if fp["home"] > fp["away"] else a
            elo_fav = h if eh > ea else a
            if mkt_fav != elo_fav:
                out.append(f"  · ⚠️ Elo favorece a **{elo_fav}** pero el mercado a **{mkt_fav}** → discrepancia, investiga.")
    ou = auto.get("over_under") or []
    if ou and ou[0].get("fair_pinnacle_over") is not None:
        r, bet = ou[0], (ou[0].get("betano") or {})
        out.append(f"- [AUTO] Totales O/U {r['line']}: justo Over {r['fair_pinnacle_over']:.0%}"
                   + (f" · Betano {bet.get('over')}/{bet.get('under')}" if bet else ""))
    btts = auto.get("btts")
    if btts and btts.get("fair_pinnacle_yes") is not None:
        out.append(f"- [AUTO] BTTS: justo Sí {btts['fair_pinnacle_yes']:.0%}.")
    ah = auto.get("asian_handicap") or []
    if ah and ah[0].get("fair_pinnacle_home") is not None:
        r, bet = ah[0], (ah[0].get("betano") or {})
        out.append(f"- [AUTO] AH {h} {r['line']}: justo {r['fair_pinnacle_home']:.0%}"
                   + (f" · Betano {bet.get('home')}/{bet.get('away')}" if bet else ""))
    if not auto.get("books"):
        out.append(f"- [AUTO] {auto.get('note', 'sin cuotas API todavía')}.")

    co = manual.get("corners_ou")
    if co:
        exp, tag = _exp_corners(h, a), ""
        if exp is not None:
            d = exp - co["line"]
            soft = " — parece BLANDA" if abs(d) >= 1.0 else ""
            tag = f" · rate combinado ~{exp}/p (crudo, no SoS-aj) → lean {'Over' if d > 0 else 'Under'} {d:+.1f}{soft}"
        out.append(f"- [MANUAL] Córners O/U {co['line']} ({co.get('book','?')} {co.get('over')}/{co.get('under')}){tag}")
    ca = manual.get("cards_ou")
    if ca:
        exp, tag = _exp_cards(h, a), ""
        if exp is not None:
            d = exp - ca["line"]
            tag = f" · TA combinadas ~{exp}/p (proxy, sin árbitro #3) → lean {'Over' if d > 0 else 'Under'} {d:+.1f}"
        out.append(f"- [MANUAL] Tarjetas O/U {ca['line']} ({ca.get('book','?')} {ca.get('over')}/{ca.get('under')}){tag}")
    for pp in manual.get("player_props", []):
        out.append(f"- [MANUAL] Prop {pp.get('player')}: {pp.get('market')} {pp.get('line')} "
                   f"({pp.get('book','?')} {pp.get('over') or pp.get('odd')})")
    out.append("> AUTO = API-Football (justo = Pinnacle de-vig). MANUAL = línea que pegaste tú. "
               "Evidencia vs línea — NO es EV ni pick.")
    return out


def main() -> None:
    if len(sys.argv) < 3:
        print("uso: 43_match_brief.py <local> <visitante>")
        sys.exit(1)
    h, a = resolve(sys.argv[1]), resolve(sys.argv[2])
    if not h or not a:
        print(f"equipo no reconocido: {sys.argv[1] if not h else sys.argv[2]}")
        sys.exit(1)

    fx = find_fixture(h, a)
    if fx:  # respeta el orden real local/visitante del fixture
        h, a = fx["home_team"], fx["away_team"]
        date, city, tourn = fx["date"], fx["city"], fx["tournament"]
    else:
        date = city = tourn = None
    ven = VENUES.get(city) if city else None
    mh, ma = TEAM_META[h], TEAM_META[a]

    L = []
    L.append(f"# BRIEF PRE-PARTIDO — {h} vs {a}")
    loc = f"{ven['stadium']} ({city})" if ven else (city or "sede n/d")
    L.append(f"{loc} · {date or 'fecha n/d'} · {tourn or ''} · {matchday(date) if date else ''}".strip(" ·"))
    L.append("> Evidencia para decidir TÚ. No es pick. Re-verificar XI/lesiones del día (§6.7).\n")

    # 1. Régimen / señales
    L.append("## Régimen y señales")
    is_wc = bool(tourn and "World Cup" in tourn)
    L.append(f"- Competición: {'**WC2026 (torneo)**' if is_wc else (tourn or 'amistoso/n/d')}"
             + (f" — {matchday(date)}" if date else ""))
    if date and matchday(date) == "J3":
        L.append("- **J3: formato 48 → sin dead-rubbers, terceros persiguen goles → sesgo OVER/ataque** (no cagey).")
    for t, m in ((h, mh), (a, ma)):
        if m.get("host"):
            L.append(f"- ⚠️ **{t} ANFITRIÓN** → recordar host-fade histórico (-12-18pp).")
    if mh["cf"] != ma["cf"]:
        for t, m in ((h, mh), (a, ma)):
            if m["cf"] in CONF_EDGE:
                L.append(f"- Confederación {t} ({m['cf']}): {CONF_EDGE[m['cf']]}.")

    # 2. Entorno de sede
    L.append("\n## Entorno (sede)")
    if ven:
        if ven["heat"] == "controlado":
            L.append(f"- Techo {ven['roof']}+AC → **calor NEUTRALIZADO**; tratar como neutro.")
        elif ven["heat"] in ("alto", "MAX"):
            L.append(f"- **Calor {ven['heat']}** (sede abierta) → si franja de día, lean **Under/ritmo↓ 2ª parte**. Cruzar con pronóstico real.")
        else:
            L.append(f"- Clima templado ({ven['stadium']}).")
        if ven["altitude_m"] >= 1500:
            L.append(f"- **Altitud {ven['altitude_note']}** → ritmo/Over + ventaja del aclimatado.")
        L.append(f"- Cluster {ven['cluster']} / huso {ven['tz']}.")
    else:
        L.append("- Sede no mapeada (pasar ciudad del CSV o revisar venues.json).")

    # 2b. Viaje / descanso (mejora C)
    tr = TRAVEL.get(f"{h} vs {a}")
    if tr:
        L.append("\n## Viaje / descanso")
        def leg_txt(side):
            x = tr[side]
            if x["rest_days"] is None:
                return "debut (MD1, sin asimetría de descanso previa)"
            jet = f" · **jet-lag +{x['tz_shift']}h**" if x["tz_shift"] else ""
            return f"{x['rest_days']}d descanso · viaje: {x['travel']}{jet}"
        L.append(f"- {h}: {leg_txt('home')}")
        L.append(f"- {a}: {leg_txt('away')}")
        if tr["rest_edge"] and tr["rest_edge"] != "igual":
            L.append(f"- ⚠️ **Ventaja de descanso: {tr['rest_edge']}** (tilt fatiga → Under/favorito-frena del lado cansado).")

    # 3. Fuerza ajustada (SoS) + stats
    L.append("\n## Fuerza (SoS-ajustada) y stats DT")
    sh, eh, calh = sos_line(h)
    sa, ea, cala = sos_line(a)
    L.append(f"- **{h}**: {sh}")
    L.append(f"  · {stat_line(h)}")
    L.append(f"- **{a}**: {sa}")
    L.append(f"  · {stat_line(a)}")
    if eh and ea:
        fav = h if eh > ea else a
        L.append(f"- Edge de Elo: **{fav}** (+{abs(eh-ea):.0f}).")
    for t, cal in ((h, calh), (a, cala)):
        if cal == "FLOJO":
            L.append(f"- ⚠️ Stats de {t} **INFLADAS** (calendario flojo) → descontar GA/GF bajos vs este rival.")
        elif cal == "DURO":
            L.append(f"- {t}: stats **deflactadas** (calendario duro) → mejor de lo que el crudo sugiere.")

    # 4. Mismatches ABP (el valor)
    L.append("\n## Mismatches a balón parado (§6.8)")
    L.append(f"- ABP defensiva: {h} {mh['r']} · {a} {ma['r']}")
    flags = [f for f in (aerial_flag(h, a), aerial_flag(a, h)) if f]
    if flags:
        L.extend(f"- {f}" for f in flags)
    else:
        L.append("- Sin mismatch aéreo claro (ningún lado combina ataque-ABP fuerte × zaga frágil).")

    # 5. Tarjetas
    L.append("\n## Tarjetas")
    fh, fa = STATS.get(h, {}), STATS.get(a, {})
    if fh and fa:
        L.append(f"- Faltas {h} {fh['fouls']} / {a} {fa['fouls']} · TA {h} {fh['yellow_cards']} / {a} {fa['yellow_cards']}.")
    L.append("- Recordar: **faltas ≠ tarjetas** (priorizar TA/p alto, no volumen de faltas). Árbitro = co-driver (pendiente #3).")

    # 5b. Precio y línea (mejora #1) — puente evidencia<->mercado
    L.extend(price_section(h, a, eh, ea))

    # 6. Profundización (leer prosa)
    L.append("\n## Profundización — LEER prosa")
    L.append(f"- notes/PLAYING_STYLES_REFERENCE.md → §6.7 y §6.8 de **{h}** y **{a}**; §6.5 arquetipo; §6.6-bis para el SoS.")
    L.append("- ⚠️ §6.7 caduca: confirmar XI, lesiones y portero del día antes de cualquier pick.")

    print("\n".join(L))


if __name__ == "__main__":
    main()
