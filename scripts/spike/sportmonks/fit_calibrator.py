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
    _ece,
)


DEFAULT_PICKS = Path("reports/sportmonks_live/exports/picks_graded.parquet")
DEFAULT_OUTPUT = Path("data/calibration/isotonic_v1.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--picks", type=Path, default=DEFAULT_PICKS,
                    help="Path to picks_graded.parquet")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                    help="Where to write the calibrator JSON")
    ap.add_argument("--min-samples", type=int, default=100,
                    help="Refuse to fit if fewer settled picks than this")
    ap.add_argument("--diagnostic-only", action="store_true",
                    help="Print ECE before/after, do not write file")
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

    cal = IsotonicProbabilityCalibrator.fit(raw_probs, outcomes, n_train=n)

    print("\nCalibration result:")
    print(f"  breakpoints fit: {len(cal._x)}")  # type: ignore[attr-defined]
    print(f"  ECE before: {cal.ece_before:.4f}")
    print(f"  ECE after:  {cal.ece_after:.4f}")
    print(f"  delta:      {cal.ece_after - cal.ece_before:+.4f}")

    # Pretty-print the calibration curve at decile prediction levels
    print("\nReliability after calibration (decile-by-decile):")
    print(f"{'raw_p':<8} {'cal_p':<8} {'emp_wr':<8} {'n':<5}")
    raw_probs_sorted_idx = np.argsort(raw_probs)
    deciles = np.array_split(raw_probs_sorted_idx, 10)
    for i, idx in enumerate(deciles):
        rp_mean = raw_probs[idx].mean()
        cp_mean = cal.transform_batch(raw_probs[idx]).mean()
        emp = outcomes[idx].mean()
        print(f"{rp_mean:.4f}  {cp_mean:.4f}  {emp:.4f}  {len(idx):<5}")

    if args.diagnostic_only:
        print("\n--diagnostic-only set; not writing file.")
        return 0

    cal.save_json(args.output)
    print(f"\nWrote calibrator to {args.output}")
    print(f"  fitted_at: {cal.fitted_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
