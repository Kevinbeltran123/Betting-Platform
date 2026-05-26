"""Iter 1 — WC-only subset (n=128 from WC2018 + WC2022).

Does the v2 favorite-stratified HT->FT matrix hold WHEN restricted to
World Cup matches only? If magnitudes attenuate, the signal is "general
tournament" — limited transfer to WC2026. If magnitudes hold or amplify,
the signal is genuinely WC-relevant.

OBJECTIVE: filter ALL non-WC signal from the analysis. Report only what
will predict WC2026.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "wc2026_v3" / "patterns_v2"))

from _lib_v2 import (  # noqa: E402
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    CACHE,
    bootstrap_ci,
    bootstrap_diff_ci,
    load_enriched_with_mv,
)

OUT = CACHE / "wc2026_v3" / "patterns_v2_iter1_wc_only.json"

WC_TOURNAMENTS = ["wc_2018", "wc_2022"]


def cell_stats(df: pl.DataFrame, label: str) -> dict:
    n = len(df)
    if n < 5:
        return {"n": n, "label": label, "skipped": True}
    out: dict = {"n": n, "label": label}
    # FT outcomes
    draw = (df["home_goals"] == df["away_goals"]).cast(pl.Int8).to_numpy().astype(float)
    btts = (
        ((df["home_goals"] > 0) & (df["away_goals"] > 0))
        .cast(pl.Int8)
        .to_numpy()
        .astype(float)
    )
    over25 = (
        ((df["home_goals"] + df["away_goals"]) > 2.5)
        .cast(pl.Int8)
        .to_numpy()
        .astype(float)
    )
    fav_win = (df["fav_outcome"] == "fav_win").cast(pl.Int8).to_numpy().astype(float)
    fav_loss = (df["fav_outcome"] == "fav_loss").cast(pl.Int8).to_numpy().astype(float)
    for k, arr in (("draw", draw), ("btts", btts), ("over25", over25),
                    ("fav_win", fav_win), ("fav_loss", fav_loss)):
        if not np.isnan(arr).all():
            p, lo, hi = bootstrap_ci(arr, np.mean)
            out[k] = {"point": p, "ci_low": lo, "ci_high": hi}
    out["mean_total_goals"] = float((df["home_goals"] + df["away_goals"]).mean())
    return out


def run_matrix(df: pl.DataFrame, label: str) -> dict:
    print(f"\n=== {label} (n={len(df)}) ===")
    fav = df.filter(pl.col("favorite") != "none")
    matrix = {"label": label, "n_total": len(df), "n_fav_defined": len(fav)}
    print(f"  fav-defined: {len(fav)}")
    for state in ["tied", "fav_up", "fav_down"]:
        sub = fav.filter(pl.col("ht_state_relative") == state)
        m = cell_stats(sub, f"{label}_{state}")
        matrix[state] = m
        if m.get("skipped"):
            print(f"  {state}: SKIPPED n={m['n']}")
        else:
            print(
                f"  {state}: n={m['n']}, P(fav_win)={m['fav_win']['point']:.3f} "
                f"[{m['fav_win']['ci_low']:.3f}, {m['fav_win']['ci_high']:.3f}], "
                f"P(draw)={m['draw']['point']:.3f}, mean_total={m['mean_total_goals']:.2f}"
            )
    return matrix


def main() -> None:
    df = load_enriched_with_mv()

    # 1) WC-only matrix
    wc_only = df.filter(pl.col("tournament_slug").is_in(WC_TOURNAMENTS))
    wc_matrix = run_matrix(wc_only, "WC-only (WC18 + WC22)")

    # 2) Combined non-WC matrix for comparison
    non_wc = df.filter(~pl.col("tournament_slug").is_in(WC_TOURNAMENTS))
    non_wc_matrix = run_matrix(non_wc, "Non-WC (Euro20+Euro24+AFCON23+Copa24)")

    # 3) Modern-WC only (WC22) — closest in style to WC2026
    wc_modern = df.filter(pl.col("tournament_slug") == "wc_2022")
    wc_modern_matrix = run_matrix(wc_modern, "WC22 modern (closest to WC26)")

    # 4) Per-state magnitude comparison
    print("\n\n=== Per-state magnitude comparison (P(fav_win)) ===")
    for state in ["tied", "fav_up", "fav_down"]:
        wc_p = wc_matrix[state].get("fav_win", {}).get("point")
        non_wc_p = non_wc_matrix[state].get("fav_win", {}).get("point")
        wc_modern_p = wc_modern_matrix[state].get("fav_win", {}).get("point")
        full_p = {"tied": 0.468, "fav_up": 0.809, "fav_down": 0.162}[state]
        print(
            f"  {state}: full(n=255)={full_p:.3f} | "
            f"WC-only={wc_p:.3f} | non-WC={non_wc_p:.3f} | WC22-modern={wc_modern_p:.3f}"
        )

    # 5) Test that magnitude differences across slices are not artifacts
    fav = df.filter(pl.col("favorite") != "none")
    print("\n=== WC vs Non-WC paired bootstrap (P(fav_win)) ===")
    for state in ["tied", "fav_up", "fav_down"]:
        wc_arr = (
            fav.filter(
                (pl.col("ht_state_relative") == state)
                & pl.col("tournament_slug").is_in(WC_TOURNAMENTS)
            )["fav_outcome"]
            == "fav_win"
        ).cast(pl.Int8).to_numpy().astype(float)
        nwc_arr = (
            fav.filter(
                (pl.col("ht_state_relative") == state)
                & ~pl.col("tournament_slug").is_in(WC_TOURNAMENTS)
            )["fav_outcome"]
            == "fav_win"
        ).cast(pl.Int8).to_numpy().astype(float)
        if len(wc_arr) >= 5 and len(nwc_arr) >= 5:
            diff, lo, hi, p = bootstrap_diff_ci(wc_arr, nwc_arr)
            print(
                f"  {state}: WC(n={len(wc_arr)})={float(wc_arr.mean()):.3f}, "
                f"non-WC(n={len(nwc_arr)})={float(nwc_arr.mean()):.3f}, "
                f"Δ={diff:+.3f} [{lo:+.3f}, {hi:+.3f}], p={p:.4f}"
            )

    results = {
        "wc_only_matrix": wc_matrix,
        "non_wc_matrix": non_wc_matrix,
        "wc_modern_matrix": wc_modern_matrix,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
