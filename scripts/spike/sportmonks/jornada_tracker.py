#!/usr/bin/env python3
"""Per-jornada ROI tracker — historical performance across all data on disk.

Groups settled picks by emission date (= jornada) and produces:

- Per-jornada table: n_emit, n_won, win_rate, profit, stake, ROI,
  cumulative ROI, vs expected ROI band from selected stack profile
- Cumulative summary: total profit, total ROI, peak, drawdown
- Trial countdown if a target deadline is set

Output is markdown (paste into reports) and optionally writes a JSON
sidecar with the structured data for downstream automation.

Usage:

    # Table for all settled jornadas in picks_graded.parquet
    uv run python scripts/spike/sportmonks/jornada_tracker.py

    # Anchored to a specific stack profile
    uv run python scripts/spike/sportmonks/jornada_tracker.py \\
        --profile aggressive

    # Compare against an expected ROI band manually
    uv run python scripts/spike/sportmonks/jornada_tracker.py \\
        --expected-roi-mean 50.6 --expected-roi-std 15.07

    # Persist structured data alongside the table
    uv run python scripts/spike/sportmonks/jornada_tracker.py \\
        --json-out reports/sportmonks_live/jornada_tracker.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

from bip.evaluation.live.stack_profiles import PROFILES

DEFAULT_PICKS_PATH = Path("reports/sportmonks_live/exports/picks_graded.parquet")


@dataclass
class JornadaSummary:
    """Per-jornada aggregated stats."""

    date: str
    n_emit: int
    n_settled: int
    n_won: int
    win_rate: float
    profit_units: float
    stake_pct_total: float
    roi_pct: float


def _classify_status(df: pl.DataFrame) -> pl.DataFrame:
    """Add `is_won` and `is_settled` flags."""
    return df.with_columns([
        (pl.col("status") == "won").alias("is_won"),
        pl.col("status").is_in(["won", "lost"]).alias("is_settled"),
    ])


def _group_by_jornada(df: pl.DataFrame) -> list[JornadaSummary]:
    """Return per-date summaries sorted ascending by date."""
    if len(df) == 0:
        return []
    df = df.with_columns(
        pl.col("emitted_at").str.slice(0, 10).alias("jornada_date"),
    )
    df = _classify_status(df)
    grouped = df.group_by("jornada_date").agg([
        pl.len().alias("n_emit"),
        pl.col("is_settled").sum().alias("n_settled"),
        pl.col("is_won").sum().alias("n_won"),
        # Only sum profit/stake on settled picks
        pl.when(pl.col("is_settled")).then(pl.col("profit_units"))
          .otherwise(0).sum().alias("profit_units"),
        pl.when(pl.col("is_settled")).then(pl.col("suggested_stake_pct"))
          .otherwise(0).sum().alias("stake_pct_total"),
    ]).sort("jornada_date")

    out: list[JornadaSummary] = []
    for r in grouped.iter_rows(named=True):
        n_settled = r["n_settled"]
        n_won = r["n_won"]
        profit = r["profit_units"]
        stake = r["stake_pct_total"]
        win_rate = n_won / n_settled * 100 if n_settled else 0.0
        roi = profit / stake * 100 if stake > 0 else 0.0
        out.append(JornadaSummary(
            date=r["jornada_date"],
            n_emit=r["n_emit"],
            n_settled=n_settled,
            n_won=n_won,
            win_rate=win_rate,
            profit_units=profit,
            stake_pct_total=stake,
            roi_pct=roi,
        ))
    return out


def _fmt_table_md(rows: list[list], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def _cumulative(summaries: list[JornadaSummary]) -> list[float]:
    """Return cumulative ROI after each jornada."""
    cum_profit = 0.0
    cum_stake = 0.0
    out = []
    for s in summaries:
        cum_profit += s.profit_units
        cum_stake += s.stake_pct_total
        out.append(cum_profit / cum_stake * 100 if cum_stake > 0 else 0.0)
    return out


def _vs_expected(roi: float, mean: float, std: float) -> str:
    """Annotate ROI vs expected band (±1σ)."""
    lo, hi = mean - std, mean + std
    if roi < lo - std:
        return f"❌ {roi - mean:+.1f} pp below mean (>2σ)"
    if roi < lo:
        return f"⚠ {roi - mean:+.1f} pp (below 1σ band)"
    if roi > hi + std:
        return f"🚀 {roi - mean:+.1f} pp above mean (>2σ)"
    if roi > hi:
        return f"✨ {roi - mean:+.1f} pp (above 1σ band)"
    return f"✓ within band ({roi - mean:+.1f} pp)"


def render_report(
    summaries: list[JornadaSummary],
    *,
    expected_roi_mean: float | None = None,
    expected_roi_std: float | None = None,
    profile_name: str | None = None,
    trial_deadline: str | None = None,
) -> str:
    """Build the full markdown report."""
    if not summaries:
        return "No settled picks found in the picks file."

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"JORNADA ROI TRACKER · {len(summaries)} jornada(s) on disk")
    if profile_name:
        lines.append(f"Stack profile reference: {profile_name}")
    if expected_roi_mean is not None and expected_roi_std is not None:
        lines.append(
            f"Expected ROI band (1σ): "
            f"{expected_roi_mean - expected_roi_std:+.1f}% → "
            f"{expected_roi_mean + expected_roi_std:+.1f}% "
            f"(mean {expected_roi_mean:+.1f}%, std {expected_roi_std:.1f})"
        )
    if trial_deadline:
        lines.append(f"Trial deadline: {trial_deadline}")
    lines.append("=" * 70)
    lines.append("")

    cum_roi = _cumulative(summaries)
    headers = ["date", "n_emit", "n_set", "won", "wr%", "profit", "stake", "ROI%", "cum ROI%"]
    if expected_roi_mean is not None and expected_roi_std is not None:
        headers.append("vs expected")
    rows = []
    for s, cr in zip(summaries, cum_roi):
        row = [
            s.date, s.n_emit, s.n_settled, s.n_won,
            f"{s.win_rate:.1f}",
            f"{s.profit_units:+.2f}",
            f"{s.stake_pct_total:.2f}",
            f"{s.roi_pct:+.2f}",
            f"{cr:+.2f}",
        ]
        if expected_roi_mean is not None and expected_roi_std is not None:
            row.append(_vs_expected(s.roi_pct, expected_roi_mean, expected_roi_std))
        rows.append(row)
    lines.append("**Per-jornada breakdown:**")
    lines.append("")
    lines.append(_fmt_table_md(rows, headers))
    lines.append("")

    # Cumulative summary
    total_profit = sum(s.profit_units for s in summaries)
    total_stake = sum(s.stake_pct_total for s in summaries)
    total_emit = sum(s.n_emit for s in summaries)
    total_settled = sum(s.n_settled for s in summaries)
    total_won = sum(s.n_won for s in summaries)
    total_roi = total_profit / total_stake * 100 if total_stake > 0 else 0.0
    win_rate = total_won / total_settled * 100 if total_settled else 0.0
    peak_cum = max(cum_roi) if cum_roi else 0.0
    drawdown = peak_cum - cum_roi[-1] if cum_roi else 0.0

    lines.append("**Cumulative:**")
    lines.append("")
    lines.append(f"- Total picks emitted: **{total_emit:,}** (settled {total_settled:,})")
    lines.append(f"- Total wins: **{total_won:,}** ({win_rate:.1f}%)")
    lines.append(f"- Cumulative profit: **{total_profit:+.2f} u**")
    lines.append(f"- Cumulative stake: **{total_stake:.2f}**")
    lines.append(f"- Cumulative ROI: **{total_roi:+.2f}%**")
    lines.append(f"- Peak cumulative ROI: **{peak_cum:+.2f}%**")
    lines.append(f"- Current drawdown from peak: **−{drawdown:.2f} pp**")
    if expected_roi_mean is not None and expected_roi_std is not None:
        lines.append(
            f"- Cumulative vs expected: "
            f"{_vs_expected(total_roi, expected_roi_mean, expected_roi_std)}"
        )

    # Variance sanity check (only if 3+ jornadas)
    if len(summaries) >= 3:
        rois = [s.roi_pct for s in summaries]
        import statistics
        realized_std = statistics.stdev(rois)
        realized_mean = statistics.mean(rois)
        lines.append("")
        lines.append("**Variance check:**")
        lines.append(
            f"- Realized per-jornada ROI mean: **{realized_mean:+.2f}%**"
        )
        lines.append(
            f"- Realized per-jornada ROI std: **{realized_std:.2f}**"
        )
        if expected_roi_std is not None:
            if realized_std > 2 * expected_roi_std:
                lines.append(
                    f"⚠ Realized variance ({realized_std:.1f}) "
                    f"materially exceeds expected ({expected_roi_std:.1f}). "
                    f"Consider switching to a lower-variance profile."
                )
            elif realized_std < 0.5 * expected_roi_std:
                lines.append(
                    f"ℹ Realized variance ({realized_std:.1f}) is much "
                    f"smaller than expected ({expected_roi_std:.1f}) — "
                    f"either sample too small or profile too conservative."
                )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--picks", type=Path, default=DEFAULT_PICKS_PATH,
                   help="Path to picks_graded.parquet")
    p.add_argument("--profile", type=str, default=None,
                   help="Anchor expected ROI band to a stack profile name "
                        "(tier_1_only, balanced, aggressive, low_variance)")
    p.add_argument("--expected-roi-mean", type=float, default=None,
                   help="Override profile-provided expected ROI mean (%%)")
    p.add_argument("--expected-roi-std", type=float, default=None,
                   help="Override profile-provided expected ROI std (%%)")
    p.add_argument("--trial-deadline", type=str, default=None,
                   help="ISO date label for the trial deadline (display only)")
    p.add_argument("--json-out", type=Path, default=None,
                   help="Optional sidecar JSON output path")
    args = p.parse_args(argv)

    if not args.picks.exists():
        print(f"ERROR: picks file not found: {args.picks}", file=sys.stderr)
        return 1

    df = pl.read_parquet(args.picks)
    summaries = _group_by_jornada(df)

    # Resolve expected band
    expected_mean = args.expected_roi_mean
    expected_std = args.expected_roi_std
    profile_name = args.profile
    if profile_name and expected_mean is None:
        if profile_name not in PROFILES:
            print(f"ERROR: unknown profile {profile_name!r}", file=sys.stderr)
            return 2
        prof = PROFILES[profile_name]
        expected_mean = prof.expected_roi_mean
        expected_std = prof.expected_roi_std

    report = render_report(
        summaries,
        expected_roi_mean=expected_mean,
        expected_roi_std=expected_std,
        profile_name=profile_name,
        trial_deadline=args.trial_deadline,
    )
    print(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profile": profile_name,
            "expected_roi_mean": expected_mean,
            "expected_roi_std": expected_std,
            "jornadas": [asdict(s) for s in summaries],
        }
        args.json_out.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote structured JSON to {args.json_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
