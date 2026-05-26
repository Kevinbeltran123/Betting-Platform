"""Hold-out validation for P8 (underdog corners) + descriptive extras.

Extras:
- P9: HT scoreline distribution → P(FT BTTS) given various HT scores
- P10: Extra-time goal distribution in knockouts (descriptive)
- P11: P(FT scoreline in {0-0, 1-0, 0-1, 1-1} | HT 0-0)  — distribution of outcomes given dull HT
- P5b validated: HT-trailing comeback rate on hold-out
- P4a per-tournament breakdown (so we know if any single tournament drives it)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from _lib import (
    SQUAD,
    bh_fdr,
    bootstrap_ci,
    bootstrap_diff_ci,
    load_enriched,
    split_discovery,
    split_validation,
)


def validate_p8(val: pl.DataFrame, squad_df: pl.DataFrame) -> dict:
    sv = {r["team_name"]: r["market_value_eur"] for r in squad_df.iter_rows(named=True) if r["team_name"]}
    group = val.filter(pl.col("phase") == "group")
    fav_c, dog_c, n = [], [], 0
    unmatched = []
    for r in group.iter_rows(named=True):
        h, a = sv.get(r["home_team"]), sv.get(r["away_team"])
        if h is None or a is None or h == a:
            unmatched.append((r["home_team"] if h is None else r["away_team"]))
            continue
        n += 1
        if h > a:
            fav_c.append(r["home_corners"]); dog_c.append(r["away_corners"])
        else:
            fav_c.append(r["away_corners"]); dog_c.append(r["home_corners"])
    fav_c, dog_c = np.asarray(fav_c, dtype=float), np.asarray(dog_c, dtype=float)
    diff, lo, hi, p = bootstrap_diff_ci(dog_c, fav_c, stat_fn=np.mean)
    return {"n": n, "fav_mean_corners": float(fav_c.mean()), "dog_mean_corners": float(dog_c.mean()),
            "diff": diff, "ci_lo": lo, "ci_hi": hi, "p": p,
            "n_unmatched": len(unmatched)}


def p9_ht_to_ft_distribution(df: pl.DataFrame) -> dict:
    """Conditional FT outcome distributions given HT scoreline."""
    df = df.with_columns(
        pl.format("{}-{}", pl.col("ht_home"), pl.col("ht_away")).alias("ht_score"),
        pl.format("{}-{}", pl.col("home_goals"), pl.col("away_goals")).alias("ft_score"),
        (pl.col("home_goals") + pl.col("away_goals")).alias("ft_total"),
    )

    results = {}
    for ht in ["0-0", "1-0", "0-1", "1-1"]:
        sub = df.filter(pl.col("ht_score") == ht)
        n = sub.height
        if n < 15:
            results[ht] = {"n": n, "skipped": "n<15"}
            continue
        # P(BTTS) given this HT
        btts = ((sub["home_goals"] > 0) & (sub["away_goals"] > 0)).to_numpy().astype(float)
        u25 = (sub["ft_total"] < 2.5).to_numpy().astype(float)
        o25 = (sub["ft_total"] > 2.5).to_numpy().astype(float)
        draw = (sub["home_goals"] == sub["away_goals"]).to_numpy().astype(float)
        # bootstrap CIs
        def ci(arr):
            pt, lo, hi = bootstrap_ci(arr, np.mean)
            return {"rate": pt, "ci_lo": lo, "ci_hi": hi}
        results[ht] = {
            "n": n,
            "p_btts": ci(btts),
            "p_under25": ci(u25),
            "p_over25": ci(o25),
            "p_draw": ci(draw),
            "mean_ft_total": float(sub["ft_total"].mean()),
        }
    return results


def p10_extra_time_goals(df: pl.DataFrame) -> dict:
    """Extra-time goal distribution in knockouts (descriptive only)."""
    knock = df.filter(pl.col("phase") == "knockout")
    et_goals = []
    reg_goals = []
    for r in knock.iter_rows(named=True):
        for m in r["goals_home_minutes"] + r["goals_away_minutes"]:
            if m > 90:
                et_goals.append(m)
            else:
                reg_goals.append(m)
    return {
        "n_knockout": knock.height,
        "n_reg_goals": len(reg_goals),
        "n_et_goals": len(et_goals),
        "share_et_of_all_goals": len(et_goals) / max(1, len(reg_goals) + len(et_goals)),
        "et_goals_per_knockout_match": len(et_goals) / max(1, knock.height),
    }


def p4a_per_tournament(df: pl.DataFrame, squad_df: pl.DataFrame) -> dict:
    sv = {r["team_name"]: r["market_value_eur"] for r in squad_df.iter_rows(named=True) if r["team_name"]}
    out = {}
    for t in df["tournament_slug"].unique().to_list():
        group = df.filter((pl.col("tournament_slug") == t) & (pl.col("phase") == "group")
                          & pl.col("home_xg").is_not_null() & pl.col("away_xg").is_not_null())
        fav_xg, dog_xg = [], []
        for r in group.iter_rows(named=True):
            h, a = sv.get(r["home_team"]), sv.get(r["away_team"])
            if h is None or a is None or h == a: continue
            if h > a: fav_xg.append(r["home_xg"]); dog_xg.append(r["away_xg"])
            else: fav_xg.append(r["away_xg"]); dog_xg.append(r["home_xg"])
        fav_xg, dog_xg = np.asarray(fav_xg, dtype=float), np.asarray(dog_xg, dtype=float)
        if len(fav_xg) < 10:
            out[t] = {"n": len(fav_xg), "skipped": "n<10"}
            continue
        diff, lo, hi, p = bootstrap_diff_ci(dog_xg, fav_xg, stat_fn=np.mean)
        out[t] = {"n": len(fav_xg), "fav_mean_xg": float(fav_xg.mean()),
                  "dog_mean_xg": float(dog_xg.mean()),
                  "diff": diff, "ci_lo": lo, "ci_hi": hi, "p": p}
    return out


def p5b_validate(val: pl.DataFrame) -> dict:
    """Comeback rate for HT-trailing teams on hold-out."""
    trailing = val.filter(pl.col("ht_home") != pl.col("ht_away"))
    if trailing.height < 10:
        return {"n": trailing.height, "skipped": "n<10"}
    cb = []
    for r in trailing.iter_rows(named=True):
        if r["ht_home"] < r["ht_away"]:
            cb.append(1 if r["home_goals"] >= r["away_goals"] else 0)
        else:
            cb.append(1 if r["away_goals"] >= r["home_goals"] else 0)
    cb = np.asarray(cb, dtype=float)
    pt, lo, hi = bootstrap_ci(cb, np.mean)
    return {"n": trailing.height, "comeback_rate": pt, "ci_lo": lo, "ci_hi": hi}


def main() -> None:
    df = load_enriched()
    disc = split_discovery(df)
    val = split_validation(df)
    sv = pl.read_parquet(SQUAD)
    out = {}

    # Hold-out P8
    out["validate_P8"] = validate_p8(val, sv)
    print(f"=== Hold-out P8 ===")
    v = out["validate_P8"]
    print(f"P8 hold-out dog-fav corners: {v['diff']:+.2f} CI=[{v['ci_lo']:+.2f}, {v['ci_hi']:+.2f}] p={v['p']:.3f} (n={v['n']})")
    print(f"  fav mean corners: {v['fav_mean_corners']:.2f}, dog mean: {v['dog_mean_corners']:.2f}")

    # P9 HT→FT distribution on ALL DATA (n=314, since it's descriptive — no testing against null)
    out["P9_ht_to_ft_all"] = p9_ht_to_ft_distribution(df)
    out["P9_ht_to_ft_discovery"] = p9_ht_to_ft_distribution(disc)
    out["P9_ht_to_ft_validation"] = p9_ht_to_ft_distribution(val)
    print("\n=== P9 HT→FT (ALL n=314) ===")
    for ht, d in out["P9_ht_to_ft_all"].items():
        if "skipped" in d: continue
        print(f"  HT {ht} (n={d['n']}): under2.5={d['p_under25']['rate']:.3f} [{d['p_under25']['ci_lo']:.3f},{d['p_under25']['ci_hi']:.3f}]  "
              f"BTTS={d['p_btts']['rate']:.3f}  draw={d['p_draw']['rate']:.3f}  mean_total={d['mean_ft_total']:.2f}")

    # P10 ET goals
    out["P10_et_goals"] = p10_extra_time_goals(df)
    print(f"\n=== P10 Extra-time goals (knockouts, n={out['P10_et_goals']['n_knockout']}) ===")
    print(f"  share of goals in ET: {out['P10_et_goals']['share_et_of_all_goals']:.3f}")
    print(f"  ET goals per knockout match: {out['P10_et_goals']['et_goals_per_knockout_match']:.2f}")

    # P4a per tournament
    out["P4a_per_tournament"] = p4a_per_tournament(df, sv)
    print(f"\n=== P4a dog-fav xG per tournament (group only) ===")
    for t, d in sorted(out["P4a_per_tournament"].items()):
        if "skipped" in d:
            print(f"  {t}: SKIPPED (n={d['n']})")
        else:
            print(f"  {t}: n={d['n']} dog-fav={d['diff']:+.3f} CI=[{d['ci_lo']:+.3f},{d['ci_hi']:+.3f}] p={d['p']:.3f}")

    out["P5b_validate"] = p5b_validate(val)
    p5b = out["P5b_validate"]
    print(f"\n=== P5b hold-out HT-trailing comeback ===")
    print(f"  n={p5b['n']} comeback_rate={p5b['comeback_rate']:.3f} CI=[{p5b['ci_lo']:.3f}, {p5b['ci_hi']:.3f}]")

    out_path = Path("data/cache/wc2026_v3/patterns_holdout_extras.json")
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nfull → {out_path}")


if __name__ == "__main__":
    main()
