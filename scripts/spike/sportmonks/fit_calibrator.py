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
from bip.evaluation.live.calibration import (
    IsotonicProbabilityCalibrator,
    PerMarketCalibrator,
    _ece,
)


DEFAULT_PICKS = Path("reports/sportmonks_live/exports/picks_graded.parquet")
DEFAULT_OUTPUT_GLOBAL = Path("data/calibration/isotonic_v1.json")
DEFAULT_OUTPUT_PER_MARKET = Path("data/calibration/per_market_v1.json")
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


if __name__ == "__main__":
    raise SystemExit(main())
