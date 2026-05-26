"""Lens 1 — favorite-draws taxonomy.

Pre-registered sub-tests L1.1 — L1.6 (see notes/v2_hypothesis_preregister.md).
Empirical-only comparisons (predictor-implied comparison deferred to L5 stage).
"""
from __future__ import annotations

import json
from pathlib import Path

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
    load_enriched_with_mv,
    split_by,
)

OUT = CACHE / "wc2026_v3" / "patterns_v2_lens1.json"


def draw_rate(df: pl.DataFrame) -> np.ndarray:
    """1 if FT draw, 0 otherwise. Excludes ET (uses raw home/away goals)."""
    return ((df["home_goals"] == df["away_goals"]).cast(pl.Int8)).to_numpy().astype(float)


def fav_win_rate(df: pl.DataFrame) -> np.ndarray:
    """1 if favorite won, 0 if drew or lost; only for fav-defined matches."""
    return ((df["fav_outcome"] == "fav_win").cast(pl.Int8)).to_numpy().astype(float)


def report_rate(label: str, sample: np.ndarray, results: dict, min_n: int = 30) -> None:
    n = len(sample)
    point, ci_lo, ci_hi = bootstrap_ci(sample, np.mean)
    verdict = "EXPLORATORY" if n < min_n else "USABLE"
    results[label] = {
        "n": n,
        "point": point,
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "verdict": verdict,
    }
    print(f"  {label}: n={n}, rate={point:.3f} [{ci_lo:.3f}, {ci_hi:.3f}] ({verdict})")


def report_diff(label: str, a: np.ndarray, b: np.ndarray, results: dict) -> None:
    diff, ci_lo, ci_hi, p = bootstrap_diff_ci(a, b)
    results[label] = {
        "n_a": len(a),
        "n_b": len(b),
        "mean_a": float(np.mean(a)),
        "mean_b": float(np.mean(b)),
        "diff": diff,
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "p": p,
    }
    print(
        f"  {label}: Δ={diff:+.3f} [{ci_lo:+.3f}, {ci_hi:+.3f}], "
        f"p={p:.4f}, n_a={len(a)}, n_b={len(b)}"
    )


def run(df: pl.DataFrame, split_name: str, results: dict) -> None:
    print(f"\n=== {split_name} (n={len(df)}) ===")

    # Use only fav-defined matches for everything in this lens
    fav = df.filter(pl.col("favorite") != "none")

    tier_a = fav.filter(pl.col("tier") == "A")
    tier_b = fav.filter(pl.col("tier") == "B")
    tier_c = fav.filter(pl.col("tier") == "C")
    tier_d = fav.filter(pl.col("tier") == "D")

    # ---- L1.1: P(draw | Tier-A) — point estimate, no comparison
    print("\n-- L1.1: P(draw | Tier-A)")
    report_rate(f"L1.1_{split_name}", draw_rate(tier_a), results)

    # ---- L1.2: P(draw | Tier-A ∧ HT-tied) vs P(draw | Tier-A ∧ HT-decided)
    print("\n-- L1.2: P(draw | Tier-A ∧ HT-tied) vs (Tier-A ∧ HT-decided)")
    tied = tier_a.filter(pl.col("ht_state_relative") == "tied")
    decided = tier_a.filter(pl.col("ht_state_relative") != "tied")
    if len(tied) >= 5 and len(decided) >= 5:
        report_diff(f"L1.2_{split_name}", draw_rate(tied), draw_rate(decided), results)
    else:
        results[f"L1.2_{split_name}"] = {"verdict": "SKIPPED_LOW_N"}
        print(f"  L1.2_{split_name}: skipped (n_tied={len(tied)}, n_decided={len(decided)})")

    # ---- L1.3: P(draw | Tier-A ∧ knockout) vs (Tier-A ∧ group)
    print("\n-- L1.3: P(draw | Tier-A ∧ knockout) vs (Tier-A ∧ group)")
    ko = tier_a.filter(pl.col("phase") == "knockout")
    gp = tier_a.filter(pl.col("phase") == "group")
    if len(ko) >= 5 and len(gp) >= 5:
        report_diff(f"L1.3_{split_name}", draw_rate(ko), draw_rate(gp), results)
    else:
        results[f"L1.3_{split_name}"] = {"verdict": "SKIPPED_LOW_N"}

    # ---- L1.4: AFCON Tier-A: favorite-win rate vs non-AFCON Tier-A
    print("\n-- L1.4: P(fav_win | Tier-A ∧ AFCON) vs (Tier-A ∧ non-AFCON)")
    afcon = tier_a.filter(pl.col("tournament_slug") == "afcon_2023")
    non_afcon = tier_a.filter(pl.col("tournament_slug") != "afcon_2023")
    if len(afcon) >= 2 and len(non_afcon) >= 5:
        report_diff(
            f"L1.4_{split_name}",
            fav_win_rate(afcon),
            fav_win_rate(non_afcon),
            results,
        )
        if len(afcon) < 30:
            results[f"L1.4_{split_name}"]["verdict"] = "EXPLORATORY_LOW_N"
    else:
        results[f"L1.4_{split_name}"] = {"verdict": "SKIPPED_LOW_N"}

    # ---- L1.5: P(draw | Tier-D) — parity sanity check
    print("\n-- L1.5: P(draw | Tier-D)")
    if len(tier_d) >= 5:
        report_rate(f"L1.5_{split_name}", draw_rate(tier_d), results, min_n=15)

    # ---- L1.6: Tier-A MD3 dead-rubber interaction (proxy: match_week==3 group)
    print("\n-- L1.6: P(draw | Tier-A ∧ MD3 group) vs (Tier-A ∧ MD1-2 group)")
    md3 = tier_a.filter((pl.col("phase") == "group") & (pl.col("match_week") == 3))
    md12 = tier_a.filter((pl.col("phase") == "group") & (pl.col("match_week").is_in([1, 2])))
    if len(md3) >= 5 and len(md12) >= 5:
        report_diff(
            f"L1.6_{split_name}", draw_rate(md3), draw_rate(md12), results
        )
        if len(md3) < 30:
            results[f"L1.6_{split_name}"]["verdict"] = "EXPLORATORY_LOW_N"

    # ---- Reference table: P(draw) by tier (combined split)
    print(f"\n-- Reference: P(draw) by tier in {split_name}")
    for t, sub in [("A", tier_a), ("B", tier_b), ("C", tier_c), ("D", tier_d)]:
        if len(sub) >= 5:
            point, ci_lo, ci_hi = bootstrap_ci(draw_rate(sub), np.mean)
            print(
                f"  Tier-{t}: n={len(sub)}, P(draw)={point:.3f} [{ci_lo:.3f}, {ci_hi:.3f}]"
            )
            results[f"tier_{t}_draw_rate_{split_name}"] = {
                "n": len(sub),
                "point": point,
                "ci_low": ci_lo,
                "ci_high": ci_hi,
            }


def main() -> None:
    df = load_enriched_with_mv()
    results: dict = {
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_n": BOOTSTRAP_N,
        "tier_boundaries": {"A>=": 3.0, "B>=": 1.8, "C>=": 1.3, "D>=": 1.0},
    }

    print(f"Full corpus: {len(df)} matches (favorite-defined: {len(df.filter(pl.col('favorite') != 'none'))})")

    run(split_by(df, DISCOVERY_TOURNAMENTS), "discovery", results)
    run(split_by(df, VALIDATION_TOURNAMENTS), "validation", results)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
