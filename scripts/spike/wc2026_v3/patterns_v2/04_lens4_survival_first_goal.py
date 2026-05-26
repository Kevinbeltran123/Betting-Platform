"""Lens 4 — Survival to first goal (Kaplan-Meier).

Pre-registered tests L4.1 — L4.5 (see notes/v2_hypothesis_preregister.md).

Operational target: time-of-first-goal Under/Over X minutes props.
- log-rank test for group differences
- bootstrap CI for "P(no goal by min K)" at K ∈ {15, 25, 35, 45}
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from _lib_v2 import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    CACHE,
    DISCOVERY_TOURNAMENTS,
    VALIDATION_TOURNAMENTS,
    bootstrap_ci,
    bootstrap_diff_ci,
    first_goal_minutes,
    kaplan_meier,
    load_enriched_with_mv,
    log_rank_test,
    split_by,
)

OUT = CACHE / "wc2026_v3" / "patterns_v2_lens4.json"


def survival_at(times: np.ndarray, observed: np.ndarray, K: int) -> float:
    """P(first goal occurs AFTER minute K) = survival at K."""
    # "No goal by min K" means times > K (or times == K with no event).
    # For our use case: time of first goal > K → no goal yet at minute K.
    return float(np.mean(times > K))


def p_no_goal_at(times: np.ndarray, observed: np.ndarray, K: int) -> np.ndarray:
    """Returns 1/0 per match indicating no goal by minute K."""
    return (times > K).astype(float)


def run_split(df: pl.DataFrame, split_name: str, results: dict) -> None:
    print(f"\n=== {split_name} (n={len(df)}) ===")

    fav = df.filter(pl.col("favorite") != "none")

    times_all, obs_all = first_goal_minutes(df)

    # Baseline survival snapshots
    print("\n-- Baseline survival (no conditioning)")
    for K in [15, 25, 35, 45]:
        arr = p_no_goal_at(times_all, obs_all, K)
        point, lo, hi = bootstrap_ci(arr, np.mean)
        print(f"  P(no goal by min {K}): {point:.3f} [{lo:.3f}, {hi:.3f}], n={len(arr)}")
        results[f"baseline_no_goal_by_{K}_{split_name}"] = {
            "n": len(arr),
            "point": point,
            "ci_low": lo,
            "ci_high": hi,
        }

    # L4.1 — log-rank group vs knockout
    print("\n-- L4.1: KM curves — group vs knockout")
    group = df.filter(pl.col("phase") == "group")
    knockout = df.filter(pl.col("phase") == "knockout")
    t_g, e_g = first_goal_minutes(group)
    t_k, e_k = first_goal_minutes(knockout)
    if len(t_g) >= 10 and len(t_k) >= 10:
        stat, p = log_rank_test(t_g, e_g, t_k, e_k)
        med_g = float(np.median(t_g))
        med_k = float(np.median(t_k))
        print(
            f"  L4.1_{split_name}: stat={stat:.3f}, p={p:.4f}, "
            f"n_group={len(t_g)}, n_knockout={len(t_k)}, "
            f"median_group={med_g:.0f}min, median_knockout={med_k:.0f}min"
        )
        results[f"L4.1_{split_name}"] = {
            "n_group": len(t_g),
            "n_knockout": len(t_k),
            "logrank_stat": stat,
            "p": p,
            "median_group": med_g,
            "median_knockout": med_k,
        }

    # L4.2 — log-rank Tier-A vs Tier-D (asymmetric vs parity)
    print("\n-- L4.2: KM curves — Tier-A asymmetric vs Tier-D parity")
    tier_a = fav.filter(pl.col("tier") == "A")
    tier_d_combined = fav.filter(pl.col("tier").is_in(["C", "D"]))
    t_a, e_a = first_goal_minutes(tier_a)
    t_d, e_d = first_goal_minutes(tier_d_combined)
    if len(t_a) >= 10 and len(t_d) >= 10:
        stat, p = log_rank_test(t_a, e_a, t_d, e_d)
        med_a = float(np.median(t_a))
        med_d = float(np.median(t_d))
        print(
            f"  L4.2_{split_name}: stat={stat:.3f}, p={p:.4f}, "
            f"n_A={len(t_a)}, n_CD={len(t_d)}, "
            f"median_A={med_a:.0f}min, median_CD={med_d:.0f}min"
        )
        results[f"L4.2_{split_name}"] = {
            "n_a": len(t_a),
            "n_cd": len(t_d),
            "logrank_stat": stat,
            "p": p,
            "median_a": med_a,
            "median_cd": med_d,
        }

    # L4.3 — P(no goal by 25) | Tier-A vs base rate
    print("\n-- L4.3: P(no goal by 25) | Tier-A vs base rate")
    arr_a = p_no_goal_at(t_a, e_a, 25)
    arr_base = p_no_goal_at(times_all, obs_all, 25)
    if len(arr_a) >= 10:
        diff, lo, hi, p = bootstrap_diff_ci(arr_a, arr_base)
        print(
            f"  L4.3_{split_name}: Tier-A={float(arr_a.mean()):.3f}, "
            f"base={float(arr_base.mean()):.3f}, "
            f"Δ={diff:+.3f} [{lo:+.3f}, {hi:+.3f}], p={p:.4f}"
        )
        results[f"L4.3_{split_name}"] = {
            "n_a": len(arr_a),
            "n_base": len(arr_base),
            "tier_a_rate": float(arr_a.mean()),
            "base_rate": float(arr_base.mean()),
            "diff": diff,
            "ci_low": lo,
            "ci_high": hi,
            "p": p,
        }

    # L4.4 — P(no goal by 45) [HT 0-0] | Tier-A vs Tier-D
    print("\n-- L4.4: P(no goal by 45) | Tier-A vs Tier-D")
    arr_a_45 = p_no_goal_at(t_a, e_a, 45)
    arr_d_45 = p_no_goal_at(t_d, e_d, 45)
    if len(arr_a_45) >= 10 and len(arr_d_45) >= 10:
        diff, lo, hi, p = bootstrap_diff_ci(arr_a_45, arr_d_45)
        print(
            f"  L4.4_{split_name}: Tier-A={float(arr_a_45.mean()):.3f}, "
            f"Tier-CD={float(arr_d_45.mean()):.3f}, "
            f"Δ={diff:+.3f} [{lo:+.3f}, {hi:+.3f}], p={p:.4f}"
        )
        results[f"L4.4_{split_name}"] = {
            "tier_a_no_goal_45": float(arr_a_45.mean()),
            "tier_cd_no_goal_45": float(arr_d_45.mean()),
            "diff": diff,
            "ci_low": lo,
            "ci_high": hi,
            "p": p,
        }

    # L4.5 — AFCON vs non-AFCON median time
    print("\n-- L4.5: AFCON vs non-AFCON time-to-first-goal")
    afcon = df.filter(pl.col("tournament_slug") == "afcon_2023")
    non_afcon = df.filter(pl.col("tournament_slug") != "afcon_2023")
    if len(afcon) >= 10 and len(non_afcon) >= 10:
        t_af, e_af = first_goal_minutes(afcon)
        t_na, e_na = first_goal_minutes(non_afcon)
        stat, p = log_rank_test(t_af, e_af, t_na, e_na)
        med_af = float(np.median(t_af))
        med_na = float(np.median(t_na))
        no_goal_45_af = float(np.mean(t_af > 45))
        no_goal_45_na = float(np.mean(t_na > 45))
        print(
            f"  L4.5_{split_name}: stat={stat:.3f}, p={p:.4f}, "
            f"median_AFCON={med_af:.0f}min, median_other={med_na:.0f}min, "
            f"P(no goal by 45)_AFCON={no_goal_45_af:.3f}, _other={no_goal_45_na:.3f}"
        )
        results[f"L4.5_{split_name}"] = {
            "n_afcon": len(t_af),
            "n_other": len(t_na),
            "logrank_stat": stat,
            "p": p,
            "median_afcon": med_af,
            "median_other": med_na,
            "no_goal_45_afcon": no_goal_45_af,
            "no_goal_45_other": no_goal_45_na,
        }


def main() -> None:
    df = load_enriched_with_mv()
    results: dict = {"bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_n": BOOTSTRAP_N}

    run_split(split_by(df, DISCOVERY_TOURNAMENTS), "discovery", results)
    run_split(split_by(df, VALIDATION_TOURNAMENTS), "validation", results)

    # Combined corpus survival snapshots for operational reference
    print("\n\n=== Combined corpus reference table ===")
    times_all, obs_all = first_goal_minutes(df)
    print(
        f"  Full corpus (n={len(df)}):"
        f"\n    P(no goal by 15)={float(np.mean(times_all > 15)):.3f}"
        f"\n    P(no goal by 25)={float(np.mean(times_all > 25)):.3f}"
        f"\n    P(no goal by 35)={float(np.mean(times_all > 35)):.3f}"
        f"\n    P(no goal by 45)={float(np.mean(times_all > 45)):.3f} (HT 0-0)"
        f"\n    median time-to-first-goal: {float(np.median(times_all)):.0f}min"
    )

    fav = df.filter(pl.col("favorite") != "none")
    for t in ["A", "B", "C", "D"]:
        sub = fav.filter(pl.col("tier") == t)
        if len(sub) >= 10:
            t_t, e_t = first_goal_minutes(sub)
            print(
                f"  Tier-{t} (n={len(sub)}):"
                f" P(no goal by 25)={float(np.mean(t_t > 25)):.3f},"
                f" P(no goal by 45)={float(np.mean(t_t > 45)):.3f},"
                f" median={float(np.median(t_t)):.0f}min"
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
