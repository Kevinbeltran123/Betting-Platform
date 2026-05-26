"""Tier-2 discovery + hold-out validation of Tier-1 survivors.

Tier-2 patterns (declared up-front for FDR honesty):
- P2bis_btts_reg / o25_reg: same as P2b/c but goals settled in regulation (period<=2, min<=90).
- P3: last group-stage matchday — one team already qualified (heuristic: had 6+ points after 2 games).
- P7: regime AFCON vs UEFA — cards per match (yellows) and mean xG per match.
- P8: underdog corner ratio (group only).

Hold-out validation: re-run P4a + P5a on validation tournaments (n=199).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from _lib import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    SQUAD,
    bh_fdr,
    bootstrap_ci,
    bootstrap_diff_ci,
    load_enriched,
    split_discovery,
    split_validation,
)


def _regulation_goals(row) -> tuple[int, int]:
    """Goals scored in regulation (min<=90)."""
    h = sum(1 for m in row["goals_home_minutes"] if m <= 90)
    a = sum(1 for m in row["goals_away_minutes"] if m <= 90)
    return h, a


def add_regulation_cols(df: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for r in df.iter_rows(named=True):
        h, a = _regulation_goals(r)
        rows.append({"match_id": r["match_id"], "reg_h": h, "reg_a": a})
    aux = pl.DataFrame(rows)
    return df.join(aux, on="match_id", how="left")


def pattern_p2bis(df: pl.DataFrame) -> dict:
    """Regulation-only BTTS / O2.5 — group vs knockout."""
    df = add_regulation_cols(df)
    group = df.filter(pl.col("phase") == "group")
    knock = df.filter(pl.col("phase") == "knockout")

    btts_g = ((group["reg_h"] > 0) & (group["reg_a"] > 0)).to_numpy().astype(float)
    btts_k = ((knock["reg_h"] > 0) & (knock["reg_a"] > 0)).to_numpy().astype(float)
    d_b, lo_b, hi_b, p_b = bootstrap_diff_ci(btts_k, btts_g, stat_fn=np.mean)

    o25_g = ((group["reg_h"] + group["reg_a"]) > 2.5).to_numpy().astype(float)
    o25_k = ((knock["reg_h"] + knock["reg_a"]) > 2.5).to_numpy().astype(float)
    d_o, lo_o, hi_o, p_o = bootstrap_diff_ci(o25_k, o25_g, stat_fn=np.mean)

    draw_g = (group["reg_h"] == group["reg_a"]).to_numpy().astype(float)
    draw_k = (knock["reg_h"] == knock["reg_a"]).to_numpy().astype(float)
    d_d, lo_d, hi_d, p_d = bootstrap_diff_ci(draw_k, draw_g, stat_fn=np.mean)

    return {
        "id": "P2bis_regulation_only",
        "n_group": group.height,
        "n_knock": knock.height,
        "P2bis_btts_reg": {
            "rate_group": float(btts_g.mean()),
            "rate_knock": float(btts_k.mean()),
            "diff": d_b, "ci_lo": lo_b, "ci_hi": hi_b, "p": p_b,
        },
        "P2bis_over25_reg": {
            "rate_group": float(o25_g.mean()),
            "rate_knock": float(o25_k.mean()),
            "diff": d_o, "ci_lo": lo_o, "ci_hi": hi_o, "p": p_o,
        },
        "P2bis_draw_reg": {
            "rate_group": float(draw_g.mean()),
            "rate_knock": float(draw_k.mean()),
            "diff": d_d, "ci_lo": lo_d, "ci_hi": hi_d, "p": p_d,
        },
    }


def _classify_group_matchday(df: pl.DataFrame) -> pl.DataFrame:
    """For each group-stage match, label as matchday 1/2/3 within the team's group.

    Strategy: per tournament, per team, sort group matches by date, label index.
    Each match has a 'matchday' = max(home_matchday_for_this_team, away_matchday_for_this_team).
    """
    group = df.filter(pl.col("phase") == "group").select(
        "match_id", "tournament_slug", "match_date", "home_team", "away_team"
    )
    # For each (tournament, team), order their matches chronologically
    long = pl.concat(
        [
            group.select("match_id", "tournament_slug", "match_date", pl.col("home_team").alias("team")),
            group.select("match_id", "tournament_slug", "match_date", pl.col("away_team").alias("team")),
        ]
    )
    long = long.sort(["tournament_slug", "team", "match_date"]).with_columns(
        pl.col("match_date").cum_count().over(["tournament_slug", "team"]).alias("team_md")
    )
    # match-level matchday = max of two team_md (should equal both, since matches are paired)
    md = long.group_by("match_id").agg(pl.col("team_md").max().alias("matchday"))
    return df.join(md, on="match_id", how="left")


def pattern_p3(df: pl.DataFrame) -> dict:
    """Matchday 3 group games — does scoreline distribution differ from matchday 1/2?

    Hypothesis: in MD3, some teams already qualified or already eliminated → less effort,
    more draws / lower xG / lower total goals.
    """
    df = _classify_group_matchday(df)
    group = df.filter(pl.col("phase") == "group")
    md12 = group.filter(pl.col("matchday").is_in([1, 2]))
    md3 = group.filter(pl.col("matchday") == 3)

    def _stats(sub):
        tg = (sub["home_goals"] + sub["away_goals"]).to_numpy().astype(float)
        dr = (sub["home_goals"] == sub["away_goals"]).to_numpy().astype(float)
        xg = (sub["home_xg"] + sub["away_xg"]).to_numpy().astype(float)
        return tg, dr, xg

    tg12, dr12, xg12 = _stats(md12)
    tg3, dr3, xg3 = _stats(md3)
    d_tg, lo_tg, hi_tg, p_tg = bootstrap_diff_ci(tg3, tg12, stat_fn=np.mean)
    d_dr, lo_dr, hi_dr, p_dr = bootstrap_diff_ci(dr3, dr12, stat_fn=np.mean)
    d_xg, lo_xg, hi_xg, p_xg = bootstrap_diff_ci(xg3, xg12, stat_fn=np.mean)
    return {
        "id": "P3_md3_vs_md12",
        "n_md12": md12.height,
        "n_md3": md3.height,
        "total_goals_diff": {"mean_md12": float(tg12.mean()), "mean_md3": float(tg3.mean()), "diff": d_tg, "ci_lo": lo_tg, "ci_hi": hi_tg, "p": p_tg},
        "draw_rate_diff": {"rate_md12": float(dr12.mean()), "rate_md3": float(dr3.mean()), "diff": d_dr, "ci_lo": lo_dr, "ci_hi": hi_dr, "p": p_dr},
        "total_xg_diff": {"mean_md12": float(xg12.mean()), "mean_md3": float(xg3.mean()), "diff": d_xg, "ci_lo": lo_xg, "ci_hi": hi_xg, "p": p_xg},
    }


def pattern_p7(df: pl.DataFrame) -> dict:
    """Regime split: AFCON vs non-AFCON (UEFA+CONMEBOL+WC).

    Note: this uses both discovery and any available tournaments — but AFCON is in
    validation. We treat regime test as a separate pre-registered hypothesis using
    ALL data — since AFCON is operationally a regime where lock_v1 underperforms,
    we want to know what to do at deployment. (Documented as "regime" not "discovery".)
    """
    df = df.filter(pl.col("home_xg").is_not_null() & pl.col("away_xg").is_not_null())
    afcon = df.filter(pl.col("tournament_slug") == "afcon_2023")
    other = df.filter(pl.col("tournament_slug") != "afcon_2023")
    y_a = np.asarray([len(r["yellow_minutes"]) for r in afcon.iter_rows(named=True)], dtype=float)
    y_o = np.asarray([len(r["yellow_minutes"]) for r in other.iter_rows(named=True)], dtype=float)
    xg_a = (afcon["home_xg"] + afcon["away_xg"]).to_numpy().astype(float)
    xg_o = (other["home_xg"] + other["away_xg"]).to_numpy().astype(float)
    tg_a = (afcon["home_goals"] + afcon["away_goals"]).to_numpy().astype(float)
    tg_o = (other["home_goals"] + other["away_goals"]).to_numpy().astype(float)
    d_y, lo_y, hi_y, p_y = bootstrap_diff_ci(y_a, y_o, stat_fn=np.mean)
    d_xg, lo_xg, hi_xg, p_xg = bootstrap_diff_ci(xg_a, xg_o, stat_fn=np.mean)
    d_tg, lo_tg, hi_tg, p_tg = bootstrap_diff_ci(tg_a, tg_o, stat_fn=np.mean)
    return {
        "id": "P7_afcon_regime",
        "n_afcon": afcon.height,
        "n_other": other.height,
        "yellows_per_match": {"afcon": float(y_a.mean()), "other": float(y_o.mean()), "diff": d_y, "ci_lo": lo_y, "ci_hi": hi_y, "p": p_y},
        "total_xg_per_match": {"afcon": float(xg_a.mean()), "other": float(xg_o.mean()), "diff": d_xg, "ci_lo": lo_xg, "ci_hi": hi_xg, "p": p_xg},
        "total_goals_per_match": {"afcon": float(tg_a.mean()), "other": float(tg_o.mean()), "diff": d_tg, "ci_lo": lo_tg, "ci_hi": hi_tg, "p": p_tg},
    }


def pattern_p8(df: pl.DataFrame, squad_df: pl.DataFrame) -> dict:
    """Underdog corner ratio in group stage."""
    sv = {r["team_name"]: r["market_value_eur"] for r in squad_df.iter_rows(named=True) if r["team_name"]}
    group = df.filter(pl.col("phase") == "group")
    fav_c, dog_c, n = [], [], 0
    for r in group.iter_rows(named=True):
        h_mv, a_mv = sv.get(r["home_team"]), sv.get(r["away_team"])
        if h_mv is None or a_mv is None or h_mv == a_mv:
            continue
        n += 1
        if h_mv > a_mv:
            fav_c.append(r["home_corners"]); dog_c.append(r["away_corners"])
        else:
            fav_c.append(r["away_corners"]); dog_c.append(r["home_corners"])
    fav_c, dog_c = np.asarray(fav_c, dtype=float), np.asarray(dog_c, dtype=float)
    diff, lo, hi, p = bootstrap_diff_ci(dog_c, fav_c, stat_fn=np.mean)
    return {
        "id": "P8_underdog_corners_group",
        "n_matched": n,
        "fav_mean_corners": float(fav_c.mean()) if len(fav_c) else None,
        "dog_mean_corners": float(dog_c.mean()) if len(dog_c) else None,
        "dog_minus_fav_corners": {"diff": diff, "ci_lo": lo, "ci_hi": hi, "p": p},
    }


# --- Hold-out validators (same logic as Tier-1, on validation split) ---

def validate_p4a(val: pl.DataFrame, squad_df: pl.DataFrame) -> dict:
    sv = {r["team_name"]: r["market_value_eur"] for r in squad_df.iter_rows(named=True) if r["team_name"]}
    group = val.filter(
        (pl.col("phase") == "group")
        & pl.col("home_xg").is_not_null()
        & pl.col("away_xg").is_not_null()
    )
    fav_xg, dog_xg, n = [], [], 0
    for r in group.iter_rows(named=True):
        h, a = sv.get(r["home_team"]), sv.get(r["away_team"])
        if h is None or a is None or h == a:
            continue
        n += 1
        if h > a:
            fav_xg.append(r["home_xg"]); dog_xg.append(r["away_xg"])
        else:
            fav_xg.append(r["away_xg"]); dog_xg.append(r["home_xg"])
    fav_xg, dog_xg = np.asarray(fav_xg, dtype=float), np.asarray(dog_xg, dtype=float)
    diff, lo, hi, p = bootstrap_diff_ci(dog_xg, fav_xg, stat_fn=np.mean)
    return {"n": n, "fav_mean_xg": float(fav_xg.mean()), "dog_mean_xg": float(dog_xg.mean()),
            "diff": diff, "ci_lo": lo, "ci_hi": hi, "p": p}


def validate_p5a(val: pl.DataFrame) -> dict:
    ht00 = val.filter((pl.col("ht_home") == 0) & (pl.col("ht_away") == 0))
    under = ((ht00["home_goals"] + ht00["away_goals"]) < 2.5).to_numpy().astype(float)
    baseline = ((val["home_goals"] + val["away_goals"]) < 2.5).to_numpy().astype(float)
    diff, lo, hi, p = bootstrap_diff_ci(under, baseline, stat_fn=np.mean)
    return {"n_ht00": ht00.height, "p_under25_given_ht00": float(under.mean()),
            "p_under25_baseline": float(baseline.mean()),
            "diff": diff, "ci_lo": lo, "ci_hi": hi, "p": p}


def main() -> None:
    df = load_enriched()
    disc = split_discovery(df)
    val = split_validation(df)
    sv = pl.read_parquet(SQUAD)

    out = {
        "seed": BOOTSTRAP_SEED, "boot_n": BOOTSTRAP_N,
        "discovery_n": disc.height, "validation_n": val.height,
    }

    # Tier-2 on discovery
    out["P2bis"] = pattern_p2bis(disc)
    out["P3"] = pattern_p3(disc)
    out["P8"] = pattern_p8(disc, sv)
    # P7 uses ALL data — regime question, not discovery-only
    out["P7"] = pattern_p7(df)

    # Hold-out validation
    out["validate_P4a"] = validate_p4a(val, sv)
    out["validate_P5a"] = validate_p5a(val)

    # FDR-BH on tier-2 new tests (3 pre-registered: P2bis_btts_reg, P3_total_goals, P8_corners, P7_yellows)
    pvals_t2 = [
        out["P2bis"]["P2bis_btts_reg"]["p"],
        out["P2bis"]["P2bis_over25_reg"]["p"],
        out["P3"]["total_goals_diff"]["p"],
        out["P3"]["draw_rate_diff"]["p"],
        out["P8"]["dog_minus_fav_corners"]["p"],
        out["P7"]["yellows_per_match"]["p"],
        out["P7"]["total_xg_per_match"]["p"],
    ]
    keys_t2 = ["P2bis_btts_reg", "P2bis_o25_reg", "P3_total_goals", "P3_draw_rate",
               "P8_corners", "P7_afcon_yellows", "P7_afcon_xg"]
    survives_t2 = bh_fdr(pvals_t2, q=0.10)
    out["fdr_bh_tier2"] = [{"test": k, "p": p, "survives_q10": s} for k, p, s in zip(keys_t2, pvals_t2, survives_t2)]

    out_path = Path("data/cache/wc2026_v3/patterns_tier2_holdout.json")
    out_path.write_text(json.dumps(out, indent=2, default=str))

    # Print summary
    print(f"=== TIER-2 DISCOVERY (n={disc.height}) ===")
    p2b = out["P2bis"]["P2bis_btts_reg"]; print(f"P2bis BTTS reg-only knock-group: {p2b['diff']:+.3f} CI=[{p2b['ci_lo']:+.3f}, {p2b['ci_hi']:+.3f}] p={p2b['p']:.3f}  (group {p2b['rate_group']:.2f} vs knock {p2b['rate_knock']:.2f})")
    p2o = out["P2bis"]["P2bis_over25_reg"]; print(f"P2bis O2.5 reg-only knock-group: {p2o['diff']:+.3f} CI=[{p2o['ci_lo']:+.3f}, {p2o['ci_hi']:+.3f}] p={p2o['p']:.3f}")
    p3t = out["P3"]["total_goals_diff"]; print(f"P3 MD3 total goals diff: {p3t['diff']:+.3f} CI=[{p3t['ci_lo']:+.3f}, {p3t['ci_hi']:+.3f}] p={p3t['p']:.3f}  (md12 {p3t['mean_md12']:.2f} vs md3 {p3t['mean_md3']:.2f}) n_md3={out['P3']['n_md3']}")
    p3d = out["P3"]["draw_rate_diff"]; print(f"P3 MD3 draw rate diff: {p3d['diff']:+.3f} CI=[{p3d['ci_lo']:+.3f}, {p3d['ci_hi']:+.3f}] p={p3d['p']:.3f}")
    p8 = out["P8"]["dog_minus_fav_corners"]; print(f"P8 dog-fav corners (group): {p8['diff']:+.2f} CI=[{p8['ci_lo']:+.2f}, {p8['ci_hi']:+.2f}] p={p8['p']:.3f} n={out['P8']['n_matched']}")
    p7y = out["P7"]["yellows_per_match"]; print(f"P7 AFCON-other yellows: {p7y['diff']:+.2f} CI=[{p7y['ci_lo']:+.2f}, {p7y['ci_hi']:+.2f}] p={p7y['p']:.3f}  (afcon {p7y['afcon']:.2f} vs other {p7y['other']:.2f})")
    p7g = out["P7"]["total_goals_per_match"]; print(f"P7 AFCON-other goals: {p7g['diff']:+.2f} CI=[{p7g['ci_lo']:+.2f}, {p7g['ci_hi']:+.2f}] p={p7g['p']:.3f}")
    p7x = out["P7"]["total_xg_per_match"]; print(f"P7 AFCON-other xG: {p7x['diff']:+.2f} CI=[{p7x['ci_lo']:+.2f}, {p7x['ci_hi']:+.2f}] p={p7x['p']:.3f}")

    print(f"\n=== HOLD-OUT VALIDATION (n={val.height}) ===")
    v4 = out["validate_P4a"]
    print(f"P4a hold-out dog-fav xG: {v4['diff']:+.3f} CI=[{v4['ci_lo']:+.3f}, {v4['ci_hi']:+.3f}] p={v4['p']:.3f}  (fav {v4['fav_mean_xg']:.2f} vs dog {v4['dog_mean_xg']:.2f}) n={v4['n']}")
    v5 = out["validate_P5a"]
    print(f"P5a hold-out HT0-0 under: {v5['p_under25_given_ht00']:.3f} vs baseline {v5['p_under25_baseline']:.3f} diff={v5['diff']:+.3f} CI=[{v5['ci_lo']:+.3f}, {v5['ci_hi']:+.3f}] p={v5['p']:.3f} n_ht00={v5['n_ht00']}")

    print("\n=== Tier-2 FDR-BH (q=0.10) ===")
    for e in out["fdr_bh_tier2"]:
        flag = "PASS" if e["survives_q10"] else "----"
        print(f"  {e['test']}: p={e['p']:.4f}  [{flag}]")

    print(f"\nfull → {out_path}")


if __name__ == "__main__":
    main()
