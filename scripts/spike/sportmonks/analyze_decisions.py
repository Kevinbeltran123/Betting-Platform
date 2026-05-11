#!/usr/bin/env python3
"""Decisions.db analytics CLI.

Inspect drop_reason distribution, per-market emit/drop ratios, and gate
effectiveness from the decisions table exported by the watch pipeline.

Usage:

    # Top-level summary
    uv run python scripts/spike/sportmonks/analyze_decisions.py summary

    # Drop-reason breakdown with cumulative percentages
    uv run python scripts/spike/sportmonks/analyze_decisions.py gates

    # Per-market emit/drop ratio
    uv run python scripts/spike/sportmonks/analyze_decisions.py markets

    # Filter by date range (ISO date or full timestamp)
    uv run python scripts/spike/sportmonks/analyze_decisions.py summary \\
        --since 2026-05-13 --until 2026-05-14

    # Compare two date ranges
    uv run python scripts/spike/sportmonks/analyze_decisions.py compare \\
        --range-a 2026-05-10:2026-05-11 \\
        --range-b 2026-05-13:2026-05-14
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

DEFAULT_DECISIONS_PATH = Path("reports/sportmonks_live/exports/decisions.parquet")


def _load(path: Path, since: str | None, until: str | None) -> pl.DataFrame:
    if not path.exists():
        print(f"ERROR: decisions file not found: {path}", file=sys.stderr)
        sys.exit(1)
    df = pl.read_parquet(path)
    # Time filter via snapshot_taken_at
    if since:
        df = df.filter(pl.col("snapshot_taken_at") >= since)
    if until:
        df = df.filter(pl.col("snapshot_taken_at") < until)
    return df


def _fmt_table_md(rows: list[tuple], headers: list[str]) -> str:
    """Tiny Markdown table renderer (no jinja, no deps)."""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def cmd_summary(df: pl.DataFrame) -> None:
    """Top-level summary: totals + decision distribution + top-5 drops."""
    total = len(df)
    if total == 0:
        print("No decisions in the selected window.")
        return

    decision_counts = (
        df.group_by("decision").agg(pl.len().alias("n"))
        .sort("n", descending=True)
    )
    print("=" * 70)
    print(f"DECISIONS SUMMARY · n={total:,}")
    if df["snapshot_taken_at"].drop_nulls().len() > 0:
        print(
            f"Window: {df['snapshot_taken_at'].min()} "
            f"→ {df['snapshot_taken_at'].max()}"
        )
    print("=" * 70)
    print()
    print("**Decision distribution:**")
    rows = []
    for d, n in decision_counts.iter_rows():
        rows.append((d, f"{n:,}", f"{n/total*100:.1f}%"))
    print(_fmt_table_md(rows, ["decision", "n", "%"]))
    print()

    # Top drop reasons
    drops = df.filter(pl.col("decision") == "drop")
    if len(drops) == 0:
        return
    top = (
        drops.group_by("drop_reason").agg(pl.len().alias("n"))
        .sort("n", descending=True).head(10)
    )
    print(f"**Top drop reasons (of {len(drops):,} total drops):**")
    rows = [
        (str(r[0]), f"{r[1]:,}", f"{r[1]/len(drops)*100:.1f}%")
        for r in top.iter_rows()
    ]
    print(_fmt_table_md(rows, ["drop_reason", "n", "% of drops"]))


def cmd_gates(df: pl.DataFrame) -> None:
    """Detailed per-gate breakdown with cumulative percentages."""
    drops = df.filter(pl.col("decision") == "drop")
    if len(drops) == 0:
        print("No drops in the selected window.")
        return

    n_drops = len(drops)
    by_reason = (
        drops.group_by("drop_reason").agg(pl.len().alias("n"))
        .sort("n", descending=True)
    )
    print("=" * 70)
    print(f"GATE BREAKDOWN · n_drops={n_drops:,}")
    print("=" * 70)
    print()
    rows = []
    cum = 0
    for reason, n in by_reason.iter_rows():
        cum += n
        rows.append((
            str(reason),
            f"{n:,}",
            f"{n/n_drops*100:.1f}%",
            f"{cum/n_drops*100:.1f}%",
        ))
    print(_fmt_table_md(
        rows, ["drop_reason", "n", "% of drops", "cumulative %"],
    ))


def cmd_markets(df: pl.DataFrame) -> None:
    """Per-market emit/drop ratio + dominant drop reason per market."""
    by_market = df.group_by(["market", "decision"]).agg(pl.len().alias("n"))
    pivoted = by_market.pivot(
        values="n", index="market", on="decision", aggregate_function="sum",
    ).fill_null(0)
    # Add total column
    pivoted = pivoted.with_columns(
        (pl.col("emit") if "emit" in pivoted.columns else pl.lit(0)).alias("emit_n"),
        (pl.col("flag") if "flag" in pivoted.columns else pl.lit(0)).alias("flag_n"),
        (pl.col("drop") if "drop" in pivoted.columns else pl.lit(0)).alias("drop_n"),
    ).with_columns(
        (pl.col("emit_n") + pl.col("flag_n") + pl.col("drop_n")).alias("total_n")
    ).sort("total_n", descending=True)

    print("=" * 80)
    print(f"PER-MARKET BREAKDOWN · {len(pivoted)} markets observed")
    print("=" * 80)
    print()
    rows = []
    for r in pivoted.iter_rows(named=True):
        total = r["total_n"]
        emit_pct = r["emit_n"] / total * 100 if total else 0
        flag_pct = r["flag_n"] / total * 100 if total else 0
        drop_pct = r["drop_n"] / total * 100 if total else 0
        rows.append((
            r["market"],
            f"{total:,}",
            f"{r['emit_n']:,} ({emit_pct:.1f}%)",
            f"{r['flag_n']:,} ({flag_pct:.1f}%)",
            f"{r['drop_n']:,} ({drop_pct:.1f}%)",
        ))
    print(_fmt_table_md(
        rows, ["market", "total", "emit", "flag", "drop"],
    ))


def cmd_compare(
    path: Path, range_a: tuple[str, str], range_b: tuple[str, str],
) -> None:
    """Side-by-side comparison of two date ranges (gates + markets)."""
    df_a = _load(path, range_a[0], range_a[1])
    df_b = _load(path, range_b[0], range_b[1])
    print("=" * 80)
    print(f"COMPARE · A=[{range_a[0]} → {range_a[1]}] (n={len(df_a):,})")
    print(f"        · B=[{range_b[0]} → {range_b[1]}] (n={len(df_b):,})")
    print("=" * 80)
    print()

    def _gate_pct(df: pl.DataFrame) -> dict[str, float]:
        drops = df.filter(pl.col("decision") == "drop")
        nd = len(drops)
        if nd == 0:
            return {}
        return {
            str(r[0]): r[1] / nd * 100
            for r in drops.group_by("drop_reason")
            .agg(pl.len().alias("n")).iter_rows()
        }

    ga, gb = _gate_pct(df_a), _gate_pct(df_b)
    all_reasons = sorted(set(ga.keys()) | set(gb.keys()))
    print("**Drop-rate shift per gate (% of total drops):**")
    rows = []
    for reason in all_reasons:
        a = ga.get(reason, 0.0)
        b = gb.get(reason, 0.0)
        delta = b - a
        rows.append((
            reason, f"{a:.1f}%", f"{b:.1f}%",
            f"{delta:+.1f} pp",
        ))
    print(_fmt_table_md(rows, ["drop_reason", "A %", "B %", "Δ"]))


def _parse_range(s: str) -> tuple[str, str]:
    if ":" not in s:
        raise argparse.ArgumentTypeError(
            f"Expected START:END (e.g. 2026-05-10:2026-05-11), got {s!r}"
        )
    a, b = s.split(":", 1)
    return a.strip(), b.strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["summary", "gates", "markets", "compare"])
    p.add_argument("--path", type=Path, default=DEFAULT_DECISIONS_PATH,
                   help="Path to decisions.parquet")
    p.add_argument("--since", type=str, default=None,
                   help="Filter decisions on/after this ISO date/timestamp")
    p.add_argument("--until", type=str, default=None,
                   help="Filter decisions before this ISO date/timestamp")
    p.add_argument("--range-a", type=_parse_range, default=None,
                   help="For 'compare': START:END for first range")
    p.add_argument("--range-b", type=_parse_range, default=None,
                   help="For 'compare': START:END for second range")
    args = p.parse_args(argv)

    if args.command == "compare":
        if not args.range_a or not args.range_b:
            print("ERROR: 'compare' requires --range-a and --range-b",
                  file=sys.stderr)
            return 2
        cmd_compare(args.path, args.range_a, args.range_b)
        return 0

    df = _load(args.path, args.since, args.until)
    if args.command == "summary":
        cmd_summary(df)
    elif args.command == "gates":
        cmd_gates(df)
    elif args.command == "markets":
        cmd_markets(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
