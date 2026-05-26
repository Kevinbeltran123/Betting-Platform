"""Lens 3 — HT → FT 9-state conditional matrix (favorite-stratified).

Extends v1's P9 (4-state HT bin → FT marginals) by adding favorite-position
stratification — so we can see when HT 1-0 is "favorite-up" vs "underdog-up"
and how that conditions FT distribution.

Pre-registered tests: L3.1 — L3.5 (see notes/v2_hypothesis_preregister.md).
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
    load_enriched_with_mv,
    split_by,
)

OUT = CACHE / "wc2026_v3" / "patterns_v2_lens3.json"


def labels(df: pl.DataFrame) -> dict[str, np.ndarray]:
    return {
        "draw": (df["home_goals"] == df["away_goals"]).cast(pl.Int8).to_numpy().astype(float),
        "btts": ((df["home_goals"] > 0) & (df["away_goals"] > 0))
        .cast(pl.Int8)
        .to_numpy()
        .astype(float),
        "over25": ((df["home_goals"] + df["away_goals"]) > 2.5)
        .cast(pl.Int8)
        .to_numpy()
        .astype(float),
        "fav_win": (df["fav_outcome"] == "fav_win")
        .cast(pl.Int8)
        .to_numpy()
        .astype(float),
        "fav_loss": (df["fav_outcome"] == "fav_loss")
        .cast(pl.Int8)
        .to_numpy()
        .astype(float),
    }


def cell(df: pl.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {"n": 0}
    out = {"n": n}
    lab = labels(df)
    for k, arr in lab.items():
        # Only compute when defined (fav-stratified cells exclude fav==none)
        if not np.isnan(arr).all():
            point, lo, hi = bootstrap_ci(arr, np.mean)
            out[k] = {"point": point, "ci_low": lo, "ci_high": hi}
    # FT-state distribution: how often does the match end in each of the FT buckets?
    out["mean_total_goals"] = float((df["home_goals"] + df["away_goals"]).mean())
    return out


def build_matrix(df: pl.DataFrame) -> dict:
    """Per HT-state-relative, return cell of FT statistics."""
    fav = df.filter(pl.col("favorite") != "none")
    matrix: dict = {}
    for ht_state in ["tied", "fav_up", "fav_down"]:
        sub = fav.filter(pl.col("ht_state_relative") == ht_state)
        matrix[ht_state] = cell(sub)
        # also sub-stratify by HT goal-bin
        sub_bins = {}
        for ht_bin in ["0-0", "1-1", "X-X", "home_up", "away_up"]:
            ss = sub.filter(pl.col("ht_state") == ht_bin)
            if len(ss) >= 5:
                sub_bins[ht_bin] = cell(ss)
        matrix[ht_state]["sub_bins"] = sub_bins
    # Also the v1 P9 view (HT-bin without fav-stratification) for cross-check
    matrix["v1_marginals"] = {}
    for ht_bin in ["0-0", "1-0", "0-1", "1-1"]:
        if ht_bin == "0-0":
            ss = df.filter((pl.col("ht_home") == 0) & (pl.col("ht_away") == 0))
        elif ht_bin == "1-1":
            ss = df.filter((pl.col("ht_home") == 1) & (pl.col("ht_away") == 1))
        elif ht_bin == "1-0":
            ss = df.filter((pl.col("ht_home") == 1) & (pl.col("ht_away") == 0))
        else:  # 0-1
            ss = df.filter((pl.col("ht_home") == 0) & (pl.col("ht_away") == 1))
        matrix["v1_marginals"][ht_bin] = cell(ss)
    return matrix


def run_tests(df: pl.DataFrame, split_name: str, results: dict) -> None:
    print(f"\n=== {split_name} (n={len(df)}) ===")

    fav = df.filter(pl.col("favorite") != "none")

    # L3.1: P(favorite wins FT | HT 0-0) -- needs comparison to baseline fav win rate
    print("\n-- L3.1: P(fav wins FT | HT 0-0) — vs baseline Tier-A fav-win")
    ht00 = fav.filter((pl.col("ht_home") == 0) & (pl.col("ht_away") == 0))
    if len(ht00) >= 10:
        lab = labels(ht00)
        point, lo, hi = bootstrap_ci(lab["fav_win"], np.mean)
        print(f"  L3.1_{split_name}: n={len(ht00)}, P(fav_win|HT00)={point:.3f} [{lo:.3f}, {hi:.3f}]")
        results[f"L3.1_{split_name}"] = {
            "n": len(ht00),
            "point": point,
            "ci_low": lo,
            "ci_high": hi,
        }

    # L3.2: P(draw FT | HT 1-1)
    print("\n-- L3.2: P(draw FT | HT 1-1)")
    ht11 = fav.filter((pl.col("ht_home") == 1) & (pl.col("ht_away") == 1))
    if len(ht11) >= 10:
        lab = labels(ht11)
        point, lo, hi = bootstrap_ci(lab["draw"], np.mean)
        print(f"  L3.2_{split_name}: n={len(ht11)}, P(draw|HT11)={point:.3f} [{lo:.3f}, {hi:.3f}]")
        results[f"L3.2_{split_name}"] = {"n": len(ht11), "point": point, "ci_low": lo, "ci_high": hi}

    # L3.3: P(BTTS FT | HT 0-0) -- v1 said 22% in P9; check here with fav-defined subset
    print("\n-- L3.3: P(BTTS FT | HT 0-0)")
    if len(ht00) >= 10:
        lab = labels(ht00)
        point, lo, hi = bootstrap_ci(lab["btts"], np.mean)
        print(f"  L3.3_{split_name}: n={len(ht00)}, P(BTTS|HT00)={point:.3f} [{lo:.3f}, {hi:.3f}]")
        results[f"L3.3_{split_name}"] = {"n": len(ht00), "point": point, "ci_low": lo, "ci_high": hi}

    # L3.4: Descriptive — already covered by build_matrix

    # L3.5: HT favorite-up 1-0 vs HT underdog-up 1-0: divergence
    print("\n-- L3.5: HT fav-up 1-0 vs HT dog-up 1-0 — P(losing-side equalizes-or-leads)")
    fav_up = fav.filter(
        ((pl.col("favorite") == "home") & (pl.col("ht_home") == 1) & (pl.col("ht_away") == 0))
        | ((pl.col("favorite") == "away") & (pl.col("ht_home") == 0) & (pl.col("ht_away") == 1))
    )
    dog_up = fav.filter(
        ((pl.col("favorite") == "home") & (pl.col("ht_home") == 0) & (pl.col("ht_away") == 1))
        | ((pl.col("favorite") == "away") & (pl.col("ht_home") == 1) & (pl.col("ht_away") == 0))
    )
    # "Losing side equalizes-or-leads" = FT not won by current HT leader
    if len(fav_up) >= 5 and len(dog_up) >= 5:
        # In fav_up: P(FT is NOT fav_win) = P(draw) + P(fav_loss) — the comeback rate AGAINST favorite
        # In dog_up: P(FT is NOT fav_loss) = P(draw) + P(fav_win) — the comeback rate FOR favorite (vs underdog leading)
        lab_fu = labels(fav_up)
        lab_du = labels(dog_up)
        comeback_against_fav = 1.0 - lab_fu["fav_win"]
        comeback_for_fav = 1.0 - lab_du["fav_loss"]
        diff, lo, hi, p = bootstrap_diff_ci(comeback_for_fav, comeback_against_fav)
        print(
            f"  L3.5_{split_name}: n_favup={len(fav_up)}, n_dogup={len(dog_up)}, "
            f"comeback_for_fav={float(comeback_for_fav.mean()):.3f}, "
            f"comeback_against_fav={float(comeback_against_fav.mean()):.3f}, "
            f"Δ={diff:+.3f} [{lo:+.3f}, {hi:+.3f}], p={p:.4f}"
        )
        results[f"L3.5_{split_name}"] = {
            "n_fav_up": len(fav_up),
            "n_dog_up": len(dog_up),
            "comeback_for_fav": float(comeback_for_fav.mean()),
            "comeback_against_fav": float(comeback_against_fav.mean()),
            "diff": diff,
            "ci_low": lo,
            "ci_high": hi,
            "p": p,
        }


def main() -> None:
    df = load_enriched_with_mv()
    results: dict = {"bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_n": BOOTSTRAP_N}

    run_tests(split_by(df, DISCOVERY_TOURNAMENTS), "discovery", results)
    run_tests(split_by(df, VALIDATION_TOURNAMENTS), "validation", results)

    # Full matrices over both splits + combined
    print("\n\n=== Full HT-relative matrix (combined corpus, n=255 fav-defined) ===\n")
    matrix_full = build_matrix(df)
    results["matrix_combined"] = matrix_full
    for state, c in matrix_full.items():
        if state == "v1_marginals":
            continue
        if "n" in c and c["n"] >= 5:
            print(f"\n  HT-state = '{state}' (n={c['n']})")
            for k in ["draw", "btts", "over25", "fav_win", "fav_loss"]:
                if k in c:
                    print(
                        f"    P({k})={c[k]['point']:.3f} "
                        f"[{c[k]['ci_low']:.3f}, {c[k]['ci_high']:.3f}]"
                    )
            print(f"    mean_total_goals={c['mean_total_goals']:.2f}")

    print("\n\n=== v1 P9 marginals replication (full corpus) ===")
    for ht, c in matrix_full["v1_marginals"].items():
        if c.get("n", 0) >= 5:
            print(f"  HT {ht}: n={c['n']}, P(U2.5)={1-c['over25']['point']:.3f}, "
                  f"P(BTTS)={c['btts']['point']:.3f}, mean_total={c['mean_total_goals']:.2f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
