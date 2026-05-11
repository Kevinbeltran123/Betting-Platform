#!/usr/bin/env python3
"""Fit isotonic probability calibrator from picks_graded.parquet.

Usage:
    uv run python scripts/spike/sportmonks/fit_calibrator.py
    uv run python scripts/spike/sportmonks/fit_calibrator.py \\
        --picks reports/sportmonks_live/exports/picks_graded.parquet \\
        --output data/calibration/isotonic_v1.json

Reads settled (won/lost) picks, fits an isotonic regression of
(our_probability → won_int), and persists thresholds to JSON.

Run after each jornada. The calibrator is consumed by ValueDetector at
init via `IsotonicProbabilityCalibrator.load_json(path)`.

When a calibrator is deployed, set ValueDetector's
`high_prob_haircut_threshold=1.01` to disable the stopgap Tier 1.4
haircut and avoid double-correcting.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

# Repo root → src is on path via uv run
from sklearn.model_selection import KFold

from bip.evaluation.live.calibration import (
    IsotonicProbabilityCalibrator,
    PerMarketCalibrator,
    _ece,
)


DEFAULT_PICKS = Path("reports/sportmonks_live/exports/picks_graded.parquet")
DEFAULT_OUTPUT_GLOBAL = Path("data/calibration/isotonic_v1.json")
DEFAULT_OUTPUT_PER_MARKET = Path("data/calibration/per_market_v1.json")
# 2026-05-11 CV finding (see reports 11_cv_validation.md):
# - Threshold 25 (default): held-out ECE worse than global (0.097 vs 0.065)
#   BUT CV ROI is BEST (+50.6% vs global +43.1%) — captures market-specific
#   underconfidence (ou_3_5) and dropout patterns better than uniform fit.
# - Trade-off: higher variance (std 15% vs 8%). Operator can move to 100
#   for lower variance / lower upside if they prefer.
# Re-evaluate at Day-5 with n~2500.
DEFAULT_MIN_SAMPLES_PER_MARKET = 25


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--picks", type=Path, default=DEFAULT_PICKS,
                    help="Path to picks_graded.parquet")
    ap.add_argument("--mode", choices=["global", "per_market", "both"],
                    default="both",
                    help="Which calibrator(s) to fit")
    ap.add_argument("--output", type=Path, default=None,
                    help="Override output path (only when mode != 'both')")
    ap.add_argument("--min-samples", type=int, default=100,
                    help="Refuse to fit if fewer settled picks than this")
    ap.add_argument("--min-samples-per-market", type=int,
                    default=DEFAULT_MIN_SAMPLES_PER_MARKET,
                    help="Minimum settled picks per market to fit its own "
                         "calibrator (smaller markets use the global fallback)")
    ap.add_argument("--diagnostic-only", action="store_true",
                    help="Print ECE before/after, do not write file(s)")
    ap.add_argument("--cv-folds", type=int, default=0,
                    help="Run k-fold cross-validation for honest ECE (0 = skip)")
    args = ap.parse_args(argv)

    if not args.picks.exists():
        print(f"ERROR: picks file not found: {args.picks}", file=sys.stderr)
        return 1

    picks = pl.read_parquet(args.picks).filter(
        pl.col("status").is_in(["won", "lost"])
    )
    n = len(picks)
    print(f"Loaded {n} settled picks from {args.picks}")

    if n < args.min_samples:
        print(
            f"ERROR: only {n} settled picks; need >= {args.min_samples}. "
            f"Skipping fit.",
            file=sys.stderr,
        )
        return 2

    raw_probs = picks["our_probability"].to_numpy()
    outcomes = (picks["status"] == "won").to_numpy().astype(float)
    markets = picks["market"].to_numpy()

    if args.cv_folds > 1:
        _cv_evaluate(
            raw_probs, outcomes, markets,
            k=args.cv_folds,
            min_samples_per_market=args.min_samples_per_market,
        )

    if args.mode in ("global", "both"):
        out = DEFAULT_OUTPUT_GLOBAL
        if args.mode == "global" and args.output is not None:
            out = args.output
        _fit_and_report_global(
            raw_probs, outcomes, output=out, n=n,
            diagnostic_only=args.diagnostic_only,
        )

    if args.mode in ("per_market", "both"):
        out = DEFAULT_OUTPUT_PER_MARKET
        if args.mode == "per_market" and args.output is not None:
            out = args.output
        _fit_and_report_per_market(
            raw_probs, outcomes, markets,
            output=out,
            min_samples_per_market=args.min_samples_per_market,
            diagnostic_only=args.diagnostic_only,
        )

    return 0


def _fit_and_report_global(raw_probs, outcomes, *, output, n, diagnostic_only):
    print("\n" + "=" * 70)
    print("GLOBAL ISOTONIC CALIBRATOR")
    print("=" * 70)
    cal = IsotonicProbabilityCalibrator.fit(raw_probs, outcomes, n_train=n)

    print(f"  breakpoints fit: {len(cal._x)}")  # type: ignore[attr-defined]
    print(f"  ECE before: {cal.ece_before:.4f}")
    print(f"  ECE after:  {cal.ece_after:.4f}")
    print(f"  delta:      {cal.ece_after - cal.ece_before:+.4f}")

    print("\nReliability after calibration (decile-by-decile):")
    print(f"{'raw_p':<8} {'cal_p':<8} {'emp_wr':<8} {'n':<5}")
    sorted_idx = np.argsort(raw_probs)
    deciles = np.array_split(sorted_idx, 10)
    for idx in deciles:
        rp_mean = raw_probs[idx].mean()
        cp_mean = cal.transform_batch(raw_probs[idx]).mean()
        emp = outcomes[idx].mean()
        print(f"{rp_mean:.4f}  {cp_mean:.4f}  {emp:.4f}  {len(idx):<5}")

    if diagnostic_only:
        print("\n--diagnostic-only set; not writing global calibrator file.")
        return
    cal.save_json(output)
    print(f"\nWrote global calibrator to {output}")
    print(f"  fitted_at: {cal.fitted_at}")


def _fit_and_report_per_market(
    raw_probs, outcomes, markets, *, output, min_samples_per_market,
    diagnostic_only,
):
    print("\n" + "=" * 70)
    print("PER-MARKET CALIBRATOR")
    print("=" * 70)
    cal = PerMarketCalibrator.fit(
        raw_probs, outcomes, markets,
        min_samples_per_market=min_samples_per_market,
    )
    print(f"  markets with own fit: {len(cal.per_market)}")
    print(f"  markets using fallback: {len(cal.markets_using_fallback)}")
    print(f"  min_samples_per_market threshold: {min_samples_per_market}")

    print("\nPer-market ECE before/after:")
    print(f"{'market':<25} {'n':<5} {'ECE_before':<11} {'ECE_after':<11} {'pred_mean':<10} {'emp_mean':<10}")
    print("-" * 80)
    for mkt in cal.markets_with_own_fit:
        sub_mask = markets == mkt
        n_m = int(sub_mask.sum())
        sub_probs = raw_probs[sub_mask]
        sub_out = outcomes[sub_mask]
        c = cal.per_market[mkt]
        pred_mean = sub_probs.mean()
        emp_mean = sub_out.mean()
        print(
            f"{mkt:<25} {n_m:<5} {c.ece_before:<11.4f} {c.ece_after:<11.4f} "
            f"{pred_mean:<10.4f} {emp_mean:<10.4f}"
        )
    print("\nMarkets using fallback (n < threshold):")
    for mkt in cal.markets_using_fallback:
        sub_mask = markets == mkt
        n_m = int(sub_mask.sum())
        print(f"  {mkt:<25} n={n_m}")

    if diagnostic_only:
        print("\n--diagnostic-only set; not writing per-market calibrator file.")
        return
    cal.save_json(output)
    print(f"\nWrote per-market calibrator to {output}")
    print(f"  fitted_at: {cal.fitted_at}")


def _cv_evaluate(
    raw_probs: np.ndarray,
    outcomes: np.ndarray,
    markets: np.ndarray,
    *,
    k: int = 5,
    min_samples_per_market: int = 25,
) -> None:
    """K-fold cross-validation for HONEST ECE estimation.

    In-sample ECE is always 0 for isotonic regression (by construction).
    To estimate real-world performance, we partition picks into k folds,
    fit on k-1, and score on the held-out fold. This gives a realistic
    measure of how the calibrator will perform on Day-2+ data.
    """
    print("\n" + "=" * 70)
    print(f"{k}-FOLD CROSS-VALIDATION (honest ECE estimate)")
    print("=" * 70)
    kf = KFold(n_splits=k, shuffle=True, random_state=42)

    global_ece_held = []
    pm_ece_held = []
    raw_ece_held = []
    for fold_i, (train_idx, test_idx) in enumerate(kf.split(raw_probs), 1):
        train_probs = raw_probs[train_idx]
        train_out = outcomes[train_idx]
        train_mkts = markets[train_idx]
        test_probs = raw_probs[test_idx]
        test_out = outcomes[test_idx]
        test_mkts = markets[test_idx]

        # Raw (no calibration)
        ece_raw = _ece(test_probs, test_out)
        raw_ece_held.append(ece_raw)

        # Global calibrator
        try:
            global_cal = IsotonicProbabilityCalibrator.fit(
                train_probs, train_out,
            )
            cal_probs = np.array([global_cal.transform(p) for p in test_probs])
            ece_g = _ece(cal_probs, test_out)
            global_ece_held.append(ece_g)
        except Exception as e:
            print(f"  fold {fold_i} global fit failed: {e}")
            continue

        # Per-market calibrator
        try:
            pm_cal = PerMarketCalibrator.fit(
                train_probs, train_out, train_mkts,
                min_samples_per_market=min_samples_per_market,
            )
            cal_probs_pm = np.array([
                pm_cal.transform(p, market=m)
                for p, m in zip(test_probs, test_mkts)
            ])
            ece_pm = _ece(cal_probs_pm, test_out)
            pm_ece_held.append(ece_pm)
        except Exception as e:
            print(f"  fold {fold_i} per-market fit failed: {e}")

    print(f"\nHeld-out ECE (mean ± std across {k} folds, n_test ≈ {len(raw_probs)//k}):")
    print(f"  Raw (no calibrator):  {np.mean(raw_ece_held):.4f} ± {np.std(raw_ece_held):.4f}")
    print(f"  Global calibrator:    {np.mean(global_ece_held):.4f} ± {np.std(global_ece_held):.4f}  "
          f"(Δ vs raw: {np.mean(global_ece_held) - np.mean(raw_ece_held):+.4f})")
    if pm_ece_held:
        print(f"  Per-market cal:       {np.mean(pm_ece_held):.4f} ± {np.std(pm_ece_held):.4f}  "
              f"(Δ vs raw: {np.mean(pm_ece_held) - np.mean(raw_ece_held):+.4f})")

    print("\nInterpretation:")
    print("  - Lower held-out ECE = better real-world calibration.")
    print("  - If held-out ECE > raw ECE → calibrator is OVERFITTING (bad).")
    print("  - Per-market should beat global when it has enough per-market data.")
    print("  - Day-1 n=813 is borderline; expect held-out ECE 0.03-0.08.")


if __name__ == "__main__":
    raise SystemExit(main())
