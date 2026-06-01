"""Strength-of-schedule (SoS) para corregir las stats crudas de §6.6.

Problema (mejora #5 del roadmap): los promedios de §6.6 (GF/GA, posesión, remates...)
son CRUDOS → inflados/deflactados por la calidad del rival. Noruega 37 GF e Inglaterra
0 GA se lograron vs grupos flojos; un 2.5 GF de UEFA-débil != uno de CONMEBOL.

Solución offline y reproducible:
1. Computa un Elo (estilo World Football Elo: peso por torneo + margen de victoria +
   ventaja de local) para TODAS las selecciones desde data/cache/martj42_international_results.csv (CC0).
2. Para cada selección WC, toma sus últimos <=20 partidos JUGADOS bajo el DT actual
   (fecha >= nombramiento, reusando COACH_SINCE del script 41) y promedia el Elo ACTUAL
   de los rivales = SoS. También su propio Elo y GF/GA en esa ventana.
3. Marca el calendario como duro/medio/flojo vs la media de las 48 → flag de inflado/deflactado.

Output: data/cache/tsp/strength_of_schedule.json + tabla impresa.
NOTA: la ventana de partidos del CSV (todos los jugados) difiere levemente de la de §6.6
(solo partidos con stats de API-Football); para SoS la diferencia es despreciable.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
CSV = PROJECT / "data" / "cache" / "martj42_international_results.csv"
OUT = PROJECT / "data" / "cache" / "tsp" / "strength_of_schedule.json"
SCRIPT41 = Path(__file__).resolve().parent / "41_team_stats_by_coach.py"

# Reusa COACH_SINCE del script 41 (módulo con nombre que empieza por dígito -> importlib).
_spec = importlib.util.spec_from_file_location("script41", SCRIPT41)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
COACH_SINCE: dict[str, tuple[str, str]] = _mod.COACH_SINCE

# Nombres lock.json -> nombres martj42 (solo donde difieren; martj42 usa nombres estándar
# como "United States", "Ivory Coast", "South Korea", "DR Congo", etc. → casi todos identidad).
ALIAS: dict[str, str] = {}

WINDOW = 20  # últimos N partidos bajo el DT actual (CSV corta en 2026-03-31)


def _tournament_weight(t: str) -> float:
    t = t.lower()
    if "world cup" in t and "qual" not in t:
        return 60.0
    if any(k in t for k in ("nations league",)):
        return 45.0
    if "qualif" in t:
        return 40.0
    if any(k in t for k in ("euro", "copa am", "cup of nations", "asian cup", "gold cup", "confederations")):
        return 50.0
    return 20.0  # friendly / minor


def _mov_multiplier(gd: int) -> float:
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0  # gd=3 -> 1.75, gd=4 -> 1.875, ...


def compute_elo() -> dict[str, float]:
    """World-Football-Elo simplificado, cronológico, base 1500, ventaja local 100."""
    rows = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("", "NA") or r["away_score"] in ("", "NA"):
                continue
            rows.append(r)
    rows.sort(key=lambda r: r["date"])
    elo: dict[str, float] = {}
    for r in rows:
        h, a = r["home_team"], r["away_team"]
        eh = elo.get(h, 1500.0)
        ea = elo.get(a, 1500.0)
        ha = 0.0 if r["neutral"].upper() == "TRUE" else 100.0
        we = 1.0 / (1.0 + 10 ** (-((eh + ha) - ea) / 400.0))
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        wh = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        k = _tournament_weight(r["tournament"]) * _mov_multiplier(hs - as_)
        delta = k * (wh - we)
        elo[h] = eh + delta
        elo[a] = ea - delta
    return elo


def team_matches(name: str, since: str) -> list[dict]:
    key = ALIAS.get(name, name)
    out = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("", "NA"):
                continue
            if r["date"] < since:
                continue
            if r["home_team"] == key or r["away_team"] == key:
                out.append(r)
    out.sort(key=lambda r: r["date"], reverse=True)
    return out[:WINDOW]


def main() -> None:
    elo = compute_elo()
    result: dict[str, dict] = {}
    missing = []
    for name, (coach, since) in COACH_SINCE.items():
        key = ALIAS.get(name, name)
        if key not in elo:
            missing.append(f"{name} (->{key})")
            continue
        ms = team_matches(name, since)
        if not ms:
            missing.append(f"{name} (0 matches since {since})")
            continue
        opp_elos, gf, ga = [], [], []
        for r in ms:
            is_home = r["home_team"] == key
            opp = r["away_team"] if is_home else r["home_team"]
            opp_elos.append(elo.get(opp, 1500.0))
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            gf.append(hs if is_home else as_)
            ga.append(as_ if is_home else hs)
        result[name] = {
            "coach": coach,
            "own_elo": round(elo[key], 0),
            "sos_opp_elo": round(sum(opp_elos) / len(opp_elos), 0),
            "n": len(ms),
            "gf_window": round(sum(gf) / len(gf), 2),
            "ga_window": round(sum(ga) / len(ga), 2),
        }
    # flag vs media de las 48
    sos_vals = [v["sos_opp_elo"] for v in result.values()]
    mean_sos = sum(sos_vals) / len(sos_vals)
    for v in result.values():
        d = v["sos_opp_elo"] - mean_sos
        v["schedule"] = "DURO" if d >= 80 else ("FLOJO" if d <= -80 else "medio")
        v["sos_delta_vs_mean"] = round(d, 0)

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Media SoS (avg opp Elo) de las {len(result)} selecciones: {mean_sos:.0f}\n")
    print(f"{'Equipo':24} {'Elo':>5} {'SoS':>5} {'Δ':>5}  {'n':>2} {'GF/GA':>9}  cal")
    for name, v in sorted(result.items(), key=lambda kv: -kv[1]["sos_opp_elo"]):
        print(f"{name:24} {v['own_elo']:5.0f} {v['sos_opp_elo']:5.0f} "
              f"{v['sos_delta_vs_mean']:+5.0f}  {v['n']:2} "
              f"{v['gf_window']:.1f}/{v['ga_window']:.1f}".ljust(9)
              + f"  {v['schedule']}")
    if missing:
        print("\nSIN match/Elo:", "; ".join(missing))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
