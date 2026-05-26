"""Tier-1 pattern discovery on n=115 (WC2018 + Euro2020).

Tests six betting-translatable hypotheses, each with bootstrap CIs.
Hypotheses are pre-registered (declared in HYPOTHESES list) so FDR-BH is
honest. Output: JSON + console table.

Usage:
    uv run python scripts/spike/wc2026_v3/patterns/01_tier1_discovery.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from _lib import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    bh_fdr,
    bootstrap_ci,
    bootstrap_diff_ci,
    btts_mask,
    draw_mask,
    load_enriched,
    over25_mask,
    split_discovery,
    total_goals,
)

# Pre-registered hypotheses (each row = one test that contributes to FDR-BH)
HYPOTHESES = [
    "P1a_late_goal_share_above_uniform",  # share of goals in 76-90+ > 25% (uniform=16.7%)
    "P2a_knockout_lower_total_goals",  # mean total goals lower in knockout vs group
    "P2b_knockout_lower_btts",  # %BTTS lower in knockout
    "P2c_knockout_lower_over25",  # %O2.5 lower in knockout
    "P2d_knockout_higher_draw",  # draw rate higher in knockout (regulation only)
    "P4a_underdog_lower_xg",  # underdog (low MV) xG < favorite xG (group only)
    "P5a_ht_00_to_ft_under25",  # P(FT under 2.5 | HT 0-0) > unconditional
    "P5b_ht_10_comeback",  # P(team trailing at HT comes back to draw or win) baseline
    "P6a_knockout_more_yellows",  # mean yellows higher in knockout
]


def pattern_p1(df: pl.DataFrame) -> dict:
    """Goal distribution by minute-bucket. Hypothesis: late bucket (76-90) > 1/6 share."""
    all_goals = []
    for row in df.iter_rows(named=True):
        all_goals.extend(row["goals_home_minutes"])
        all_goals.extend(row["goals_away_minutes"])
    all_goals = np.asarray(all_goals)
    n_total = len(all_goals)

    buckets = [(0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90), (91, 200)]
    counts = []
    for lo, hi in buckets:
        c = int(np.sum((all_goals >= lo) & (all_goals <= hi)))
        counts.append(c)

    shares = [c / n_total for c in counts]
    # P1a: bootstrap share of late (76-90, excluding 90+) over total
    late_mask = ((all_goals >= 76) & (all_goals <= 90)).astype(float)
    point, lo, hi = bootstrap_ci(late_mask, np.mean)
    # 6 regulation buckets → uniform null share = 1/6 = 0.1667
    null = 1 / 6
    # one-sided p approx via bootstrap: prob bootstrap mean <= null
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    boots = np.array([late_mask[rng.integers(0, len(late_mask), len(late_mask))].mean() for _ in range(BOOTSTRAP_N)])
    p = 2 * float(np.minimum(np.mean(boots <= null), np.mean(boots >= null)))
    return {
        "id": "P1",
        "n_goals": n_total,
        "buckets": [{"range": f"{lo_}-{hi_}", "n": c, "share": s} for (lo_, hi_), c, s in zip(buckets, counts, shares)],
        "P1a_late_share": {"point": point, "ci_lo": lo, "ci_hi": hi, "null": null, "p": p},
    }


def pattern_p2(df: pl.DataFrame) -> dict:
    """Group vs knockout."""
    group = df.filter(pl.col("phase") == "group")
    knock = df.filter(pl.col("phase") == "knockout")
    out = {"id": "P2", "n_group": group.height, "n_knock": knock.height}

    # P2a total goals
    t_g = total_goals(group).astype(float)
    t_k = total_goals(knock).astype(float)
    diff, lo, hi, p = bootstrap_diff_ci(t_k, t_g, stat_fn=np.mean)
    out["P2a_mean_total_diff_knock_minus_group"] = {
        "mean_group": float(t_g.mean()),
        "mean_knock": float(t_k.mean()),
        "diff": diff,
        "ci_lo": lo,
        "ci_hi": hi,
        "p": p,
    }

    # P2b BTTS rate
    btts_g = btts_mask(group).astype(float)
    btts_k = btts_mask(knock).astype(float)
    diff, lo, hi, p = bootstrap_diff_ci(btts_k, btts_g, stat_fn=np.mean)
    out["P2b_btts_rate_diff"] = {
        "rate_group": float(btts_g.mean()),
        "rate_knock": float(btts_k.mean()),
        "diff": diff,
        "ci_lo": lo,
        "ci_hi": hi,
        "p": p,
    }

    # P2c O2.5
    o_g = over25_mask(group).astype(float)
    o_k = over25_mask(knock).astype(float)
    diff, lo, hi, p = bootstrap_diff_ci(o_k, o_g, stat_fn=np.mean)
    out["P2c_over25_rate_diff"] = {
        "rate_group": float(o_g.mean()),
        "rate_knock": float(o_k.mean()),
        "diff": diff,
        "ci_lo": lo,
        "ci_hi": hi,
        "p": p,
    }

    # P2d Draw rate (regulation only — but goals_*_minutes excludes pens already by construction)
    d_g = draw_mask(group).astype(float)
    d_k = draw_mask(knock).astype(float)
    diff, lo, hi, p = bootstrap_diff_ci(d_k, d_g, stat_fn=np.mean)
    out["P2d_draw_rate_diff"] = {
        "rate_group": float(d_g.mean()),
        "rate_knock": float(d_k.mean()),
        "diff": diff,
        "ci_lo": lo,
        "ci_hi": hi,
        "p": p,
    }
    return out


def pattern_p4(df: pl.DataFrame, squad_df: pl.DataFrame) -> dict:
    """Underdog vs favorite — xG and shots in group stage.

    Strategy: per match, label home/away as 'fav' or 'dog' based on current TM market value.
    Then compute mean xG of dog vs fav within group-stage matches.
    """
    group = df.filter(pl.col("phase") == "group")

    sv = {row["team_name"]: row["market_value_eur"] for row in squad_df.iter_rows(named=True) if row["team_name"]}

    fav_xg = []
    dog_xg = []
    fav_shots = []
    dog_shots = []
    n_matched = 0
    n_unmatched = 0
    for row in group.iter_rows(named=True):
        home_mv = sv.get(row["home_team"])
        away_mv = sv.get(row["away_team"])
        if home_mv is None or away_mv is None or home_mv == away_mv:
            n_unmatched += 1
            continue
        n_matched += 1
        if home_mv > away_mv:
            fav_xg.append(row["home_xg"])
            dog_xg.append(row["away_xg"])
            fav_shots.append(row["home_shots"])
            dog_shots.append(row["away_shots"])
        else:
            fav_xg.append(row["away_xg"])
            dog_xg.append(row["home_xg"])
            fav_shots.append(row["away_shots"])
            dog_shots.append(row["home_shots"])

    fav_xg = np.asarray(fav_xg, dtype=float)
    dog_xg = np.asarray(dog_xg, dtype=float)
    fav_shots = np.asarray(fav_shots, dtype=float)
    dog_shots = np.asarray(dog_shots, dtype=float)
    diff_xg, lo_xg, hi_xg, p_xg = bootstrap_diff_ci(dog_xg, fav_xg, stat_fn=np.mean)
    diff_sh, lo_sh, hi_sh, p_sh = bootstrap_diff_ci(dog_shots, fav_shots, stat_fn=np.mean)
    return {
        "id": "P4",
        "n_matched_group": n_matched,
        "n_unmatched_group": n_unmatched,
        "fav_mean_xg": float(fav_xg.mean()) if len(fav_xg) else None,
        "dog_mean_xg": float(dog_xg.mean()) if len(dog_xg) else None,
        "P4a_dog_minus_fav_xg": {"diff": diff_xg, "ci_lo": lo_xg, "ci_hi": hi_xg, "p": p_xg},
        "dog_minus_fav_shots": {"diff": diff_sh, "ci_lo": lo_sh, "ci_hi": hi_sh, "p": p_sh},
    }


def pattern_p5(df: pl.DataFrame) -> dict:
    """HT→FT transitions."""
    # Build HT/FT scoreline strings
    rows = []
    for r in df.iter_rows(named=True):
        rows.append(
            {
                "ht_h": r["ht_home"],
                "ht_a": r["ht_away"],
                "ft_h": r["home_goals"],
                "ft_a": r["away_goals"],
                "tot_ft": r["home_goals"] + r["away_goals"],
            }
        )
    dfx = pl.DataFrame(rows)

    out: dict = {"id": "P5", "n": dfx.height}

    # P5a: P(FT under 2.5 | HT 0-0)
    ht00 = dfx.filter((pl.col("ht_h") == 0) & (pl.col("ht_a") == 0))
    n_ht00 = ht00.height
    if n_ht00 >= 10:
        under = (ht00["tot_ft"] < 2.5).to_numpy().astype(float)
        baseline = (dfx["tot_ft"] < 2.5).to_numpy().astype(float)
        diff, lo, hi, p = bootstrap_diff_ci(under, baseline, stat_fn=np.mean)
        out["P5a_ht00_under25_vs_baseline"] = {
            "n_ht00": n_ht00,
            "p_under25_given_ht00": float(under.mean()),
            "p_under25_baseline": float(baseline.mean()),
            "diff": diff,
            "ci_lo": lo,
            "ci_hi": hi,
            "p": p,
        }
    else:
        out["P5a_ht00_under25_vs_baseline"] = {"n_ht00": n_ht00, "skipped": "n<10"}

    # P5b: HT-trailing team comeback rate (draw or win)
    # Define trailing team = team with fewer goals at HT (skip if tied)
    trailing = dfx.filter(pl.col("ht_h") != pl.col("ht_a"))
    if trailing.height >= 10:
        # comeback = trailing team draws or wins at FT
        def _comeback(r):
            if r["ht_h"] < r["ht_a"]:
                return 1 if r["ft_h"] >= r["ft_a"] else 0
            else:
                return 1 if r["ft_a"] >= r["ft_h"] else 0

        cb = np.asarray([_comeback(r) for r in trailing.iter_rows(named=True)], dtype=float)
        point, lo, hi = bootstrap_ci(cb, np.mean)
        out["P5b_ht_trailing_comeback_rate"] = {
            "n_ht_trailing": trailing.height,
            "comeback_rate": point,
            "ci_lo": lo,
            "ci_hi": hi,
        }
    return out


def pattern_p6(df: pl.DataFrame) -> dict:
    """Cards by phase."""
    group = df.filter(pl.col("phase") == "group")
    knock = df.filter(pl.col("phase") == "knockout")
    y_g = np.asarray([len(r["yellow_minutes"]) for r in group.iter_rows(named=True)], dtype=float)
    y_k = np.asarray([len(r["yellow_minutes"]) for r in knock.iter_rows(named=True)], dtype=float)
    diff_y, lo_y, hi_y, p_y = bootstrap_diff_ci(y_k, y_g, stat_fn=np.mean)
    r_g = np.asarray([len(r["red_minutes"]) for r in group.iter_rows(named=True)], dtype=float)
    r_k = np.asarray([len(r["red_minutes"]) for r in knock.iter_rows(named=True)], dtype=float)
    diff_r, lo_r, hi_r, p_r = bootstrap_diff_ci(r_k, r_g, stat_fn=np.mean)
    return {
        "id": "P6",
        "n_group": group.height,
        "n_knock": knock.height,
        "P6a_yellows_diff": {
            "mean_group": float(y_g.mean()),
            "mean_knock": float(y_k.mean()),
            "diff": diff_y,
            "ci_lo": lo_y,
            "ci_hi": hi_y,
            "p": p_y,
        },
        "reds_diff": {
            "mean_group": float(r_g.mean()),
            "mean_knock": float(r_k.mean()),
            "diff": diff_r,
            "ci_lo": lo_r,
            "ci_hi": hi_r,
            "p": p_r,
        },
    }


def main() -> None:
    df = load_enriched()
    disc = split_discovery(df)
    print(f"discovery n={disc.height}")

    sv = pl.read_parquet(__import__("_lib").SQUAD)
    print(f"squad values n={sv.height}")

    results = {
        "split": "discovery",
        "n": disc.height,
        "tournaments": sorted(disc["tournament_slug"].unique().to_list()),
        "seed": BOOTSTRAP_SEED,
        "bootstrap_n": BOOTSTRAP_N,
    }
    results["P1"] = pattern_p1(disc)
    results["P2"] = pattern_p2(disc)
    results["P4"] = pattern_p4(disc, sv)
    results["P5"] = pattern_p5(disc)
    results["P6"] = pattern_p6(disc)

    # FDR-BH on the 9 pre-registered tests
    pvals = []
    keys = []
    pvals.append(results["P1"]["P1a_late_share"]["p"]); keys.append("P1a")
    pvals.append(results["P2"]["P2a_mean_total_diff_knock_minus_group"]["p"]); keys.append("P2a")
    pvals.append(results["P2"]["P2b_btts_rate_diff"]["p"]); keys.append("P2b")
    pvals.append(results["P2"]["P2c_over25_rate_diff"]["p"]); keys.append("P2c")
    pvals.append(results["P2"]["P2d_draw_rate_diff"]["p"]); keys.append("P2d")
    pvals.append(results["P4"]["P4a_dog_minus_fav_xg"]["p"]); keys.append("P4a")
    p5a = results["P5"]["P5a_ht00_under25_vs_baseline"]
    pvals.append(p5a.get("p", 1.0)); keys.append("P5a")
    pvals.append(1.0); keys.append("P5b_descr")  # P5b is descriptive (no null hypothesis test)
    pvals.append(results["P6"]["P6a_yellows_diff"]["p"]); keys.append("P6a")

    survives = bh_fdr(pvals, q=0.10)
    results["fdr_bh"] = [
        {"test": k, "p": p, "survives_q10": s} for k, p, s in zip(keys, pvals, survives)
    ]

    out_path = Path("data/cache/wc2026_v3/patterns_discovery_tier1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))

    # Pretty print summary
    print("\n=== DISCOVERY (n=115) SUMMARY ===")
    print(f"P1 late-goal share (76-90): {results['P1']['P1a_late_share']['point']:.3f} "
          f"[{results['P1']['P1a_late_share']['ci_lo']:.3f}, {results['P1']['P1a_late_share']['ci_hi']:.3f}] "
          f"vs null {results['P1']['P1a_late_share']['null']:.3f} (p={results['P1']['P1a_late_share']['p']:.3f})")
    for k in ("P2a_mean_total_diff_knock_minus_group", "P2b_btts_rate_diff", "P2c_over25_rate_diff", "P2d_draw_rate_diff"):
        d = results["P2"][k]
        print(f"P2 {k}: diff={d['diff']:+.3f} CI=[{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}] p={d['p']:.3f}")
    d = results["P4"]["P4a_dog_minus_fav_xg"]
    print(f"P4a dog-fav xG (group): {d['diff']:+.3f} CI=[{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}] p={d['p']:.3f} (n={results['P4']['n_matched_group']})")
    if "diff" in results["P5"]["P5a_ht00_under25_vs_baseline"]:
        d = results["P5"]["P5a_ht00_under25_vs_baseline"]
        print(f"P5a HT0-0 under2.5: {d['p_under25_given_ht00']:.3f} vs baseline {d['p_under25_baseline']:.3f} diff={d['diff']:+.3f} CI=[{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}] p={d['p']:.3f} (n_ht00={d['n_ht00']})")
    if "comeback_rate" in results["P5"].get("P5b_ht_trailing_comeback_rate", {}):
        d = results["P5"]["P5b_ht_trailing_comeback_rate"]
        print(f"P5b HT-trailing comeback (descr): {d['comeback_rate']:.3f} CI=[{d['ci_lo']:.3f}, {d['ci_hi']:.3f}] n={d['n_ht_trailing']}")
    d = results["P6"]["P6a_yellows_diff"]
    print(f"P6a yellows diff (knock-group): {d['diff']:+.2f} CI=[{d['ci_lo']:+.2f}, {d['ci_hi']:+.2f}] p={d['p']:.3f}")

    print("\n=== FDR-BH (q=0.10) ===")
    for entry in results["fdr_bh"]:
        flag = "PASS" if entry["survives_q10"] else "----"
        print(f"  {entry['test']}: p={entry['p']:.4f}  [{flag}]")

    print(f"\nfull JSON → {out_path}")


if __name__ == "__main__":
    main()
