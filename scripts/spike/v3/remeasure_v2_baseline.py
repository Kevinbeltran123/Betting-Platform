"""Re-measure the v2 Day-1+2 baseline against the corrected grading.

Reads `reports/sportmonks_live/exports/picks_graded.parquet` (already
re-graded by `analyze_jornada` after commit 9107188 + bd9564f) and
produces an honest measurement vs the inflated numbers reported in
operator memory and spike memos.

Read-only by construction: never mutates the parquet, never re-grades,
never talks to APIs. Emits a markdown table to stdout and writes a
JSON audit blob to `reports/v3/v2_baseline_remeasure.json`.

Usage:
    uv run python -m scripts.spike.v3.remeasure_v2_baseline

    # Override paths
    uv run python -m scripts.spike.v3.remeasure_v2_baseline \\
        --picks reports/sportmonks_live/exports/picks_graded.parquet \\
        --out   reports/v3/v2_baseline_remeasure.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import polars as pl


# ── Old (inflated) numbers, transcribed verbatim from operator memory
#    (project_sportmonks_spike.md + project_sportmonks_post_day1_stack.md)
#    so the diff is auditable.
INFLATED_BASELINE = {
    "day1": {
        "n_picks": 937,
        "wr_pct": 60.8,
        "roi_pct": 13.19,
        "source": "project_sportmonks_spike.md (pre-9107188 fix)",
    },
    # Day-2 isn't explicitly logged with inflated numbers in memory —
    # the bd9564f commit already reports honest Day-2 (-12.18% ROI).
    # We record this so the doc is explicit about what we know vs assume.
    "day2": {
        "n_picks": None,
        "wr_pct": None,
        "roi_pct": None,
        "source": "no pre-fix Day-2 memo found",
    },
}


@dataclass
class CohortMetrics:
    label: str
    n_picks: int
    n_settled: int  # won + lost
    n_won: int
    n_lost: int
    n_void: int
    n_pending: int
    wr_pct: float  # won / (won+lost)
    roi_flat_pct: float  # using $1 per pick
    roi_kelly_pct: float  # using suggested_stake_pct as stake
    pl_flat_units: float
    pl_kelly_units: float


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den > 0 else default


def _payoff_flat(row: dict) -> float:
    """$1 flat stake per pick. Won → odds-1; lost → -1; void/pending → 0."""
    status = row["status"]
    if status == "won":
        return float(row["bookmaker_odd"]) - 1.0
    if status == "lost":
        return -1.0
    return 0.0


def _payoff_kelly(row: dict) -> tuple[float, float]:
    """Returns (stake, profit) using suggested_stake_pct as the stake size."""
    stake = float(row["suggested_stake_pct"] or 0.0)
    status = row["status"]
    if status == "won":
        return stake, stake * (float(row["bookmaker_odd"]) - 1.0)
    if status == "lost":
        return stake, -stake
    return stake if status == "pending" else 0.0, 0.0


def _measure(df: pl.DataFrame, label: str) -> CohortMetrics:
    n = df.height
    won = int((df["status"] == "won").sum())
    lost = int((df["status"] == "lost").sum())
    void = int((df["status"] == "void").sum())
    pending = int((df["status"] == "pending").sum())
    settled = won + lost

    # Flat-stake math: $1 per pick, sum profit / sum stake (stake = $1 × n_settled).
    flat_pl = sum(_payoff_flat(r) for r in df.iter_rows(named=True))
    flat_roi = _safe_div(flat_pl, float(settled)) * 100.0

    # Kelly-sized: stake from suggested_stake_pct, only count settled picks
    # so void doesn't inflate denominator.
    kelly_settled_pl = 0.0
    kelly_settled_stake = 0.0
    for r in df.iter_rows(named=True):
        if r["status"] not in ("won", "lost"):
            continue
        stake, profit = _payoff_kelly(r)
        kelly_settled_pl += profit
        kelly_settled_stake += stake
    kelly_roi = _safe_div(kelly_settled_pl, kelly_settled_stake) * 100.0

    return CohortMetrics(
        label=label,
        n_picks=n,
        n_settled=settled,
        n_won=won,
        n_lost=lost,
        n_void=void,
        n_pending=pending,
        wr_pct=_safe_div(float(won), float(settled)) * 100.0,
        roi_flat_pct=flat_roi,
        roi_kelly_pct=kelly_roi,
        pl_flat_units=flat_pl,
        pl_kelly_units=kelly_settled_pl,
    )


def _by_market(df: pl.DataFrame) -> list[dict]:
    """Per-market settled-only metrics, sorted by volume."""
    out: list[dict] = []
    for market in df["market"].unique().sort().to_list():
        sub = df.filter(pl.col("market") == market)
        m = _measure(sub, market)
        out.append({
            "market": market,
            "n_picks": m.n_picks,
            "n_settled": m.n_settled,
            "wr_pct": round(m.wr_pct, 2),
            "roi_flat_pct": round(m.roi_flat_pct, 2),
            "pl_flat_units": round(m.pl_flat_units, 3),
        })
    out.sort(key=lambda x: x["n_picks"], reverse=True)
    return out


def _by_flagged_reason(df: pl.DataFrame) -> list[dict]:
    """Distribution by flagged_reason (v2 proxy for tier — null vs the heuristic)."""
    out: list[dict] = []
    for fr in df["flagged_reason"].unique().to_list():
        label = fr if fr is not None else "(unflagged)"
        sub = df.filter(
            pl.col("flagged_reason").is_null() if fr is None
            else pl.col("flagged_reason") == fr
        )
        m = _measure(sub, label)
        out.append({
            "flagged_reason": label,
            "n_picks": m.n_picks,
            "n_settled": m.n_settled,
            "wr_pct": round(m.wr_pct, 2),
            "roi_flat_pct": round(m.roi_flat_pct, 2),
        })
    out.sort(key=lambda x: x["n_picks"], reverse=True)
    return out


def _md_cohort_table(rows: list[CohortMetrics]) -> str:
    head = (
        "| Cohort | N | Settled | W | L | V | P | WR % | "
        "ROI flat % | ROI kelly % | P/L flat | P/L kelly |"
    )
    sep = "|" + "|".join(["---"] * 11) + "|"
    body = "\n".join(
        f"| {r.label} | {r.n_picks} | {r.n_settled} | {r.n_won} | {r.n_lost} | "
        f"{r.n_void} | {r.n_pending} | {r.wr_pct:.2f} | {r.roi_flat_pct:.2f} | "
        f"{r.roi_kelly_pct:.2f} | {r.pl_flat_units:+.3f} | {r.pl_kelly_units:+.3f} |"
        for r in rows
    )
    return "\n".join([head, sep, body])


def _md_inflated_vs_honest(day1: CohortMetrics, day2: CohortMetrics) -> str:
    rows = [
        ("Day-1 — inflated (memos)", INFLATED_BASELINE["day1"]),
        ("Day-1 — honest (this run)", {
            "n_picks": day1.n_picks,
            "wr_pct": round(day1.wr_pct, 2),
            "roi_pct": round(day1.roi_flat_pct, 2),
        }),
        ("Day-2 — honest (this run)", {
            "n_picks": day2.n_picks,
            "wr_pct": round(day2.wr_pct, 2),
            "roi_pct": round(day2.roi_flat_pct, 2),
        }),
    ]
    head = "| Cohort | N | WR % | ROI % |"
    sep = "|---|---|---|---|"
    body_lines = []
    for label, m in rows:
        wr = m.get("wr_pct")
        roi = m.get("roi_pct")
        body_lines.append(
            f"| {label} | {m.get('n_picks')} | "
            f"{wr if wr is not None else '—'} | "
            f"{roi if roi is not None else '—'} |"
        )
    return "\n".join([head, sep, *body_lines])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--picks",
        type=Path,
        default=Path("reports/sportmonks_live/exports/picks_graded.parquet"),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("reports/v3/v2_baseline_remeasure.json"),
    )
    args = p.parse_args()

    if not args.picks.exists():
        raise SystemExit(f"picks parquet not found: {args.picks}")

    df = pl.read_parquet(args.picks).with_columns(
        pl.col("emitted_at").str.slice(0, 10).alias("_day"),
    )

    day1 = df.filter(pl.col("_day") == "2026-05-10")
    day2 = df.filter(pl.col("_day") == "2026-05-11")

    m_all = _measure(df, "all")
    m_day1 = _measure(day1, "day1")
    m_day2 = _measure(day2, "day2")
    m_day1_set = _measure(
        day1.filter(pl.col("status").is_in(["won", "lost", "void"])),
        "day1 (settled+void)",
    )

    audit = {
        "source": str(args.picks),
        "grading_baseline": "post-9107188 + bd9564f re-fit",
        "totals_by_cohort": [asdict(m) for m in (m_all, m_day1, m_day2, m_day1_set)],
        "day1": {
            "honest": asdict(m_day1),
            "inflated_from_memory": INFLATED_BASELINE["day1"],
            "delta_wr_points": round(
                m_day1.wr_pct - float(INFLATED_BASELINE["day1"]["wr_pct"]), 2,
            ),
            "delta_roi_points": round(
                m_day1.roi_flat_pct - float(INFLATED_BASELINE["day1"]["roi_pct"]), 2,
            ),
        },
        "day2": {
            "honest": asdict(m_day2),
            "inflated_from_memory": INFLATED_BASELINE["day2"],
        },
        "by_market_all": _by_market(df),
        "by_market_day1": _by_market(day1),
        "by_market_day2": _by_market(day2),
        "by_flagged_reason_all": _by_flagged_reason(df),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2))

    # ── stdout markdown report ───────────────────────────────────────
    print("# v2 Baseline — Honest Re-measurement\n")
    print(f"Source: `{args.picks}`")
    print("Grading baseline: post-9107188 + bd9564f re-fit\n")

    print("## Headline comparison: inflated vs honest\n")
    print(_md_inflated_vs_honest(m_day1, m_day2))
    print()
    print(
        f"Day-1 delta:  WR {audit['day1']['delta_wr_points']:+.2f}pp · "
        f"ROI {audit['day1']['delta_roi_points']:+.2f}pp\n"
    )

    print("## Cohort breakdown\n")
    print(_md_cohort_table([m_all, m_day1, m_day2]))
    print()

    print("## Top markets by volume\n")
    print("| Market | N | Settled | WR % | ROI flat % | P/L flat |")
    print("|---|---|---|---|---|---|")
    for row in _by_market(df)[:10]:
        print(
            f"| {row['market']} | {row['n_picks']} | {row['n_settled']} | "
            f"{row['wr_pct']} | {row['roi_flat_pct']} | "
            f"{row['pl_flat_units']:+.3f} |"
        )
    print()

    print("## By flagged_reason (v2 tier proxy)\n")
    print("| Reason | N | Settled | WR % | ROI flat % |")
    print("|---|---|---|---|---|")
    for row in _by_flagged_reason(df):
        print(
            f"| {row['flagged_reason']} | {row['n_picks']} | "
            f"{row['n_settled']} | {row['wr_pct']} | {row['roi_flat_pct']} |"
        )
    print()
    print(f"Audit JSON written to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
