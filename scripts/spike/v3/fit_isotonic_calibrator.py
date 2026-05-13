"""Fit the Phase-2 isotonic calibrator from v2 picks_graded history.

Loads settled picks from ``reports/sportmonks_live/exports/picks_graded.parquet``,
maps each pick's market to a v3 ``MarketFamily``, builds a
``CalibrationSample`` list, fits the ``IsotonicCalibrator``, and persists
to ``data/cache/isotonic_calibrator_v1.pkl``.

After fit:
- Reports coverage (which (family, bucket) cells have ≥30 samples)
- Reports the miscalibration delta per family (mean predicted vs mean
  actual)
- Reports the calibration *correction* the model would have made on the
  full 1087-pick set: ROI before vs ROI after (with all picks of
  post-cal edge < 0 dropped)

This is the empirical learning step the operator asked for: "puedes
aprender y mejorar con esa información que vas recolectando".

Usage:
    uv run python scripts/spike/v3/fit_isotonic_calibrator.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.calibrator import (  # noqa: E402
    CalibrationSample,
    IsotonicCalibrator,
    map_v2_market_to_family,
    minute_bucket,
)
from bip.evaluation.live.engine_v3.thesis import MarketFamily  # noqa: E402


def load_samples(picks_path: Path) -> tuple[list[CalibrationSample], pl.DataFrame]:
    df = pl.read_parquet(picks_path)
    # Keep settled picks with non-null predicted prob.
    df = df.filter(
        pl.col("status").is_in(["won", "lost"])
        & pl.col("our_probability").is_not_null()
    )
    samples: list[CalibrationSample] = []
    rows = df.select(
        ["our_probability", "minute", "market", "status"]
    ).to_dicts()
    for r in rows:
        fam = map_v2_market_to_family(r["market"])
        if fam is None:
            continue
        samples.append(
            CalibrationSample(
                family=fam,
                minute=int(r["minute"] or 0),
                predicted_p=float(r["our_probability"]),
                outcome=1 if r["status"] == "won" else 0,
            )
        )
    return samples, df


def report_miscalibration(df: pl.DataFrame, calibrator: IsotonicCalibrator) -> None:
    """Per-family: raw vs calibrated predicted probability against outcome."""
    print("\n=== Miscalibration report ===")
    print(f"{'family':<18}  {'n':>5}  {'avg_pred_raw':>12}  {'avg_pred_cal':>12}  {'actual_wr':>9}  {'roi_raw':>8}")
    families_seen: set[str] = set()
    for f in MarketFamily:
        fam_value = f.value
        sub = df.filter(
            pl.col("market").map_elements(
                lambda m, fv=f: map_v2_market_to_family(m) == fv if m else False,
                return_dtype=pl.Boolean,
            )
        )
        if sub.height == 0:
            continue
        families_seen.add(fam_value)
        avg_raw = float(sub["our_probability"].mean())
        actual_wr = float((sub["status"] == "won").cast(pl.Float64).mean())
        roi_raw = float(sub["profit_units"].sum()) / max(sub.height, 1)
        # Apply calibrator to each row's (p, minute)
        cal_vals = [
            calibrator.transform(float(p), f, int(m or 0))
            for p, m in zip(sub["our_probability"], sub["minute"])
        ]
        avg_cal = float(np.mean(cal_vals))
        print(
            f"{fam_value:<18}  {sub.height:>5}  {avg_raw:>12.3f}  "
            f"{avg_cal:>12.3f}  {actual_wr:>9.3f}  {roi_raw:>+8.3f}"
        )


def report_calibrated_filter_impact(
    df: pl.DataFrame, calibrator: IsotonicCalibrator
) -> None:
    """For each settled pick, compute edge with raw vs calibrated prob.
    Report how ROI changes if we drop picks whose calibrated edge ≤ 0."""
    print("\n=== Calibrated-filter contrafactual ===")
    keep_raw_pl: float = 0.0
    keep_raw_n: int = 0
    keep_cal_pl: float = 0.0
    keep_cal_n: int = 0
    drop_n: int = 0
    drop_pl: float = 0.0
    for row in df.iter_rows(named=True):
        market = row["market"]
        fam = map_v2_market_to_family(market) if market else None
        if fam is None:
            continue
        odd = row.get("bookmaker_odd")
        if odd is None or odd <= 1.0:
            continue
        p_raw = float(row["our_probability"])
        p_cal = calibrator.transform(p_raw, fam, int(row["minute"] or 0))
        implied = 1.0 / float(odd)
        edge_raw = p_raw - implied
        edge_cal = p_cal - implied
        pl_value = float(row["profit_units"])
        keep_raw_pl += pl_value
        keep_raw_n += 1
        if edge_cal > 0.0:
            keep_cal_pl += pl_value
            keep_cal_n += 1
        else:
            drop_n += 1
            drop_pl += pl_value
        _ = edge_raw  # silence linter
    print(f"Before calibrator filter: {keep_raw_n} picks, P/L {keep_raw_pl:+.2f}u, ROI {100 * keep_raw_pl / max(keep_raw_n, 1):+.2f}%")
    print(f"After calibrator filter:  {keep_cal_n} picks, P/L {keep_cal_pl:+.2f}u, ROI {100 * keep_cal_pl / max(keep_cal_n, 1):+.2f}%")
    print(f"Dropped:                  {drop_n} picks, P/L {drop_pl:+.2f}u (negative drops = we correctly skipped losers)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("reports/sportmonks_live/exports/picks_graded.parquet"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/cache/isotonic_calibrator_v1.pkl"),
    )
    args = parser.parse_args()

    print(f"Loading v2 picks from {args.src}…")
    samples, df = load_samples(args.src)
    print(f"Loaded {len(samples)} settled picks mapped to v3 families "
          f"(from {df.height} settled total)")

    cal = IsotonicCalibrator().fit(samples)
    print(f"\nFitted: per_family={len(cal.per_family)}  per_cell={len(cal.per_cell)}")
    print(f"Coverage:")
    cov = cal.coverage()
    for fam, buckets in cov.items():
        total = buckets.pop("_total", 0)
        cells = ", ".join(f"{b}={n}" for b, n in sorted(buckets.items()))
        print(f"  {fam:<14}  total={total:>4}  cells={{{cells}}}")

    report_miscalibration(df, cal)
    report_calibrated_filter_impact(df, cal)

    out_path = cal.save(args.out)
    print(f"\nPersisted to: {out_path}  ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
