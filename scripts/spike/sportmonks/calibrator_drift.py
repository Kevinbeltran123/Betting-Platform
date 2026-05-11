#!/usr/bin/env python3
"""Calibrator drift detector — compare two calibrator JSONs.

When the operator refits the calibrator after a new jornada, the resulting
JSON may shift materially from the previous fit. Large shifts mean:

- The reliability curve changed substantially (data shift, distribution
  change, predictor drift).
- The per-market fits gained/lost markets as data crosses thresholds.
- Specific probability ranges now map to different calibrated values.

This script computes the shift at common probability checkpoints and
flags when the absolute change exceeds a threshold. Output is markdown
suitable for the operator's post-fit review (or paste into a memo).

Usage:

    # Compare two global calibrators
    uv run python scripts/spike/sportmonks/calibrator_drift.py \\
        --old data/calibration/isotonic_v1.day1.json \\
        --new data/calibration/isotonic_v1.json

    # Compare two per-market calibrators
    uv run python scripts/spike/sportmonks/calibrator_drift.py \\
        --old data/calibration/per_market_v1.day1.json \\
        --new data/calibration/per_market_v1.json \\
        --kind per_market

    # Stricter alert threshold
    uv run python scripts/spike/sportmonks/calibrator_drift.py \\
        --old <...> --new <...> --alert-threshold 0.05
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from bip.evaluation.live.calibration import (
    IsotonicProbabilityCalibrator, PerMarketCalibrator,
)


CHECKPOINTS = [0.10, 0.25, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]


def _fmt_table_md(rows: list[tuple], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def _drift_table(
    old_cal, new_cal, *, market: str | None = None,
    alert_threshold: float = 0.10,
) -> tuple[list[tuple], int]:
    """Return (rows, n_alerts) for the checkpoint shift table."""
    rows = []
    n_alerts = 0
    for p in CHECKPOINTS:
        if isinstance(old_cal, PerMarketCalibrator):
            o = old_cal.transform(p, market=market)
        else:
            o = old_cal.transform(p)
        if isinstance(new_cal, PerMarketCalibrator):
            n = new_cal.transform(p, market=market)
        else:
            n = new_cal.transform(p)
        delta = n - o
        marker = " ⚠️" if abs(delta) >= alert_threshold else ""
        if abs(delta) >= alert_threshold:
            n_alerts += 1
        rows.append((
            f"{p:.2f}", f"{o:.4f}", f"{n:.4f}",
            f"{delta:+.4f}{marker}",
        ))
    return rows, n_alerts


def compare_global(
    old_path: Path, new_path: Path, *, alert_threshold: float,
) -> int:
    old_cal = IsotonicProbabilityCalibrator.load_json(old_path)
    new_cal = IsotonicProbabilityCalibrator.load_json(new_path)

    print("=" * 70)
    print("GLOBAL CALIBRATOR DRIFT")
    print("=" * 70)
    print()
    print(f"**Old:** `{old_path}`")
    print(f"  fitted_at: {old_cal.fitted_at}")
    print(f"  n_train: {old_cal.n_train}, ECE before: {old_cal.ece_before:.4f}")
    print()
    print(f"**New:** `{new_path}`")
    print(f"  fitted_at: {new_cal.fitted_at}")
    print(f"  n_train: {new_cal.n_train}, ECE before: {new_cal.ece_before:.4f}")
    print()
    print(
        f"**Reliability shift at checkpoints** "
        f"(alert threshold ±{alert_threshold:.2f}):"
    )
    rows, n_alerts = _drift_table(
        old_cal, new_cal, alert_threshold=alert_threshold,
    )
    print(_fmt_table_md(
        rows, ["raw_p", "old_cal_p", "new_cal_p", "Δ"],
    ))
    print()
    if n_alerts > 0:
        print(
            f"⚠️  **{n_alerts} checkpoint(s) shifted ≥{alert_threshold:.2f}.** "
            f"Investigate: data shift, distribution change, or predictor drift."
        )
    else:
        print(
            f"✅ All shifts within ±{alert_threshold:.2f}. "
            f"Calibrator is stable across the refits."
        )

    # Training-size change
    n_diff = new_cal.n_train - old_cal.n_train
    print()
    print(f"**Training-data change:** "
          f"{old_cal.n_train} → {new_cal.n_train} ({n_diff:+d})")
    return n_alerts


def compare_per_market(
    old_path: Path, new_path: Path, *, alert_threshold: float,
) -> int:
    old_cal = PerMarketCalibrator.load_json(old_path)
    new_cal = PerMarketCalibrator.load_json(new_path)

    print("=" * 70)
    print("PER-MARKET CALIBRATOR DRIFT")
    print("=" * 70)
    print()
    print(f"**Old:** `{old_path}` (fitted {old_cal.fitted_at})")
    print(f"**New:** `{new_path}` (fitted {new_cal.fitted_at})")
    print()
    print(
        f"**Coverage change:** {len(old_cal.per_market)} → "
        f"{len(new_cal.per_market)} markets with own fit"
    )
    print()

    # Markets added / removed
    old_set = set(old_cal.per_market.keys())
    new_set = set(new_cal.per_market.keys())
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    if added:
        print(f"**Markets gaining own fit (n now ≥ threshold):** "
              f"{', '.join(added)}")
    if removed:
        print(f"**Markets losing own fit (regressed below threshold):** "
              f"{', '.join(removed)}  ⚠️")
    if added or removed:
        print()

    # Per-market drift table (only for markets in BOTH)
    common = sorted(old_set & new_set)
    total_alerts = 0
    print(f"### Fallback (global) shift")
    print()
    rows, alerts = _drift_table(
        old_cal, new_cal, market="__nonexistent__",
        alert_threshold=alert_threshold,
    )
    print(_fmt_table_md(
        rows, ["raw_p", "old_cal_p", "new_cal_p", "Δ"],
    ))
    total_alerts += alerts
    print()

    print(f"### Per-market shift ({len(common)} common markets)")
    print()
    for mkt in common:
        rows, alerts = _drift_table(
            old_cal, new_cal, market=mkt, alert_threshold=alert_threshold,
        )
        # Only show markets with at least one alert (or all if --verbose)
        if alerts == 0:
            continue
        total_alerts += alerts
        print(f"**{mkt}** ({alerts} alert(s)):")
        print(_fmt_table_md(
            rows, ["raw_p", "old_cal_p", "new_cal_p", "Δ"],
        ))
        print()

    print()
    if total_alerts == 0:
        print(
            f"✅ All checkpoints within ±{alert_threshold:.2f}. "
            f"Calibrator stable."
        )
    else:
        print(
            f"⚠️  **{total_alerts} alert(s) across markets.** "
            f"Investigate the listed markets — material data shift or "
            f"sample-size induced fit volatility."
        )
    return total_alerts


def _detect_kind(path: Path) -> str:
    """Sniff the calibrator type from the JSON 'type' field."""
    with path.open() as f:
        head = json.load(f)
    return head.get("type", "")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old", type=Path, required=True,
                   help="Path to the older calibrator JSON")
    p.add_argument("--new", type=Path, required=True,
                   help="Path to the newer calibrator JSON")
    p.add_argument("--kind", choices=["auto", "global", "per_market"],
                   default="auto",
                   help="Calibrator type (auto-detect from JSON 'type' by default)")
    p.add_argument("--alert-threshold", type=float, default=0.10,
                   help="Flag checkpoint shifts ≥ this absolute value")
    args = p.parse_args(argv)

    if not args.old.exists():
        print(f"ERROR: old file not found: {args.old}", file=sys.stderr)
        return 1
    if not args.new.exists():
        print(f"ERROR: new file not found: {args.new}", file=sys.stderr)
        return 1

    kind = args.kind
    if kind == "auto":
        old_kind = _detect_kind(args.old)
        new_kind = _detect_kind(args.new)
        if old_kind != new_kind:
            print(
                f"ERROR: old/new calibrators are different types "
                f"({old_kind!r} vs {new_kind!r}). Cannot compare.",
                file=sys.stderr,
            )
            return 2
        kind = "per_market" if old_kind == "per_market" else "global"

    if kind == "global":
        n_alerts = compare_global(
            args.old, args.new, alert_threshold=args.alert_threshold,
        )
    else:
        n_alerts = compare_per_market(
            args.old, args.new, alert_threshold=args.alert_threshold,
        )

    # Exit code reflects alert count for shell scripting
    return 0 if n_alerts == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
