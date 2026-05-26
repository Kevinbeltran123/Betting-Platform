"""Quantitative correlation: last-friendly MODE → WC22 outcome.

For each team:
  1. Classify their last pre-WC22 friendly into a MODE
  2. Pull their WC22 group-stage stats (or all WC matches)
  3. Compute aggregate WC metrics per mode

MODES (operator-aligned):
  - HIGH_INTENSITY_OFFENSIVE: team_gf >= 2 AND total_goals >= 3
      (team played aggressively, scored multiple, open match)
  - LOW_INTENSITY_RESERVING: total_goals <= 1 AND total_yc <= 2
      (low scoring, low cards — they were holding back)
  - COMPETITIVE: total_yc >= 5 (heated match)
  - GOLEADA_WIN: team_gf - team_ga >= 3 (team dominated)
  - GOLEADA_LOSS: team_ga - team_gf >= 3 (team got rolled)
  - NORMAL: nothing above

Output:
  Aggregate WC22 metrics per mode + correlation interpretation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_DIR = ROOT / "data" / "cache" / "tsp" / "wc22_analysis"
LAST_FRIENDLIES_PATH = ANALYSIS_DIR / "last_friendlies.json"
WC22_FIXTURES_PATH = ANALYSIS_DIR / "wc22_fixtures.json"
OUT_PATH = ANALYSIS_DIR / "mode_to_wc_correlation.json"


def classify_mode(entry: dict) -> str:
    """Operator-aligned mode classifier."""
    gf = entry["team_gf"]
    ga = entry["team_ga"]
    total = entry["total_goals"]
    total_yc = entry["team_yellow_cards"] + entry["opp_yellow_cards"]
    diff = gf - ga

    if diff >= 3:
        return "GOLEADA_WIN"
    if -diff >= 3:
        return "GOLEADA_LOSS"
    if gf >= 2 and total >= 3:
        return "HIGH_INTENSITY_OFFENSIVE"
    if total <= 1 and total_yc <= 2:
        return "LOW_INTENSITY_RESERVING"
    if total_yc >= 5:
        return "COMPETITIVE"
    return "NORMAL"


def main() -> int:
    last_friendlies = json.loads(LAST_FRIENDLIES_PATH.read_text())
    wc22_fixtures = json.loads(WC22_FIXTURES_PATH.read_text())

    # Build per-team WC22 stats
    per_team_wc: dict[int, dict] = {}
    for f in wc22_fixtures:
        for tid, gf, ga in [
            (f["home_id"], f["home_goals"] or 0, f["away_goals"] or 0),
            (f["away_id"], f["away_goals"] or 0, f["home_goals"] or 0),
        ]:
            per_team_wc.setdefault(tid, {"matches": []})
            per_team_wc[tid]["matches"].append({
                "gf": gf, "ga": ga, "total": gf + ga,
                "btts": (gf > 0) and (ga > 0),
                "over25": (gf + ga) > 2,
                "win": gf > ga, "draw": gf == ga,
            })

    # Classify each team's friendly + compute their WC aggregates
    team_modes: list[dict] = []
    for entry in last_friendlies:
        mode = classify_mode(entry)
        wc = per_team_wc.get(entry["team_id"], {}).get("matches", [])
        if not wc:
            continue
        wc_gf = np.mean([m["gf"] for m in wc])
        wc_ga = np.mean([m["ga"] for m in wc])
        wc_btts = np.mean([1 if m["btts"] else 0 for m in wc])
        wc_o25 = np.mean([1 if m["over25"] else 0 for m in wc])
        wc_win = np.mean([1 if m["win"] else 0 for m in wc])
        wc_draw = np.mean([1 if m["draw"] else 0 for m in wc])
        team_modes.append({
            "team_id": entry["team_id"],
            "team_name": entry["team_name"],
            "mode": mode,
            "friendly_score": entry["score"],
            "friendly_total_goals": entry["total_goals"],
            "friendly_gf": entry["team_gf"],
            "friendly_ga": entry["team_ga"],
            "n_wc_matches": len(wc),
            "wc_gf_avg": float(wc_gf),
            "wc_ga_avg": float(wc_ga),
            "wc_btts_rate": float(wc_btts),
            "wc_o25_rate": float(wc_o25),
            "wc_win_rate": float(wc_win),
            "wc_draw_rate": float(wc_draw),
        })

    # Per-mode aggregates
    mode_aggregates: dict[str, dict] = {}
    for m in team_modes:
        mode = m["mode"]
        mode_aggregates.setdefault(mode, {
            "teams": [], "wc_gf": [], "wc_ga": [], "wc_btts": [],
            "wc_o25": [], "wc_win": [], "wc_draw": [],
        })
        mode_aggregates[mode]["teams"].append(m["team_name"])
        mode_aggregates[mode]["wc_gf"].append(m["wc_gf_avg"])
        mode_aggregates[mode]["wc_ga"].append(m["wc_ga_avg"])
        mode_aggregates[mode]["wc_btts"].append(m["wc_btts_rate"])
        mode_aggregates[mode]["wc_o25"].append(m["wc_o25_rate"])
        mode_aggregates[mode]["wc_win"].append(m["wc_win_rate"])
        mode_aggregates[mode]["wc_draw"].append(m["wc_draw_rate"])

    # Report
    print(f"\n{'=' * 80}")
    print(f"Last-friendly MODE → WC22 outcome (n={len(team_modes)} teams)")
    print(f"{'=' * 80}\n")

    summary = {}
    for mode in sorted(mode_aggregates.keys()):
        agg = mode_aggregates[mode]
        n = len(agg["teams"])
        if n < 2:
            continue
        avg_gf = float(np.mean(agg["wc_gf"]))
        avg_ga = float(np.mean(agg["wc_ga"]))
        avg_btts = float(np.mean(agg["wc_btts"]))
        avg_o25 = float(np.mean(agg["wc_o25"]))
        avg_win = float(np.mean(agg["wc_win"]))
        avg_draw = float(np.mean(agg["wc_draw"]))
        print(f"### {mode} (n={n} teams)")
        print(f"  Teams: {', '.join(agg['teams'])}")
        print(f"  WC22 GF/match avg:   {avg_gf:.2f}")
        print(f"  WC22 GA/match avg:   {avg_ga:.2f}")
        print(f"  WC22 BTTS rate:      {avg_btts*100:.1f}%")
        print(f"  WC22 O2.5 rate:      {avg_o25*100:.1f}%")
        print(f"  WC22 win rate:       {avg_win*100:.1f}%")
        print(f"  WC22 draw rate:      {avg_draw*100:.1f}%")
        print()
        summary[mode] = {
            "n_teams": n, "teams": agg["teams"],
            "wc_gf_avg": avg_gf, "wc_ga_avg": avg_ga,
            "wc_btts_rate": avg_btts, "wc_o25_rate": avg_o25,
            "wc_win_rate": avg_win, "wc_draw_rate": avg_draw,
        }

    # Save
    OUT_PATH.write_text(json.dumps({
        "team_modes": team_modes,
        "mode_aggregates": summary,
    }, indent=2))

    # Comparative table
    print(f"\n{'=' * 90}")
    print(f"{'Mode':<28} {'n':>3} {'GF':>6} {'GA':>6} {'BTTS%':>7} "
          f"{'O2.5%':>7} {'Win%':>6} {'Draw%':>7}")
    print(f"{'=' * 90}")
    for mode, s in sorted(summary.items(), key=lambda x: -x[1]["wc_gf_avg"]):
        print(
            f"{mode:<28} {s['n_teams']:>3} "
            f"{s['wc_gf_avg']:>6.2f} {s['wc_ga_avg']:>6.2f} "
            f"{s['wc_btts_rate']*100:>6.1f}% {s['wc_o25_rate']*100:>6.1f}% "
            f"{s['wc_win_rate']*100:>5.1f}% {s['wc_draw_rate']*100:>6.1f}%"
        )

    # Direct correlation (treat mode as ordinal: high-intensity > normal > low)
    mode_score_map = {
        "GOLEADA_LOSS": -2,    # team lost badly — likely weak
        "LOW_INTENSITY_RESERVING": -1,
        "NORMAL": 0,
        "COMPETITIVE": 0,
        "HIGH_INTENSITY_OFFENSIVE": 1,
        "GOLEADA_WIN": 2,
    }
    xs, ys_gf, ys_win = [], [], []
    for m in team_modes:
        score = mode_score_map.get(m["mode"], 0)
        xs.append(score)
        ys_gf.append(m["wc_gf_avg"])
        ys_win.append(m["wc_win_rate"])
    if len(xs) >= 5:
        r_gf = float(np.corrcoef(xs, ys_gf)[0, 1])
        r_win = float(np.corrcoef(xs, ys_win)[0, 1])
        print(f"\nOrdinal correlation (mode_intensity → WC outcome):")
        print(f"  → WC GF/match:    r = {r_gf:+.3f}  (n={len(xs)})")
        print(f"  → WC win rate:    r = {r_win:+.3f}  (n={len(xs)})")

    print(f"\nSaved: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
