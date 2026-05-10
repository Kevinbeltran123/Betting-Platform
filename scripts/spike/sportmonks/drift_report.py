"""Priors drift report — track how market/league ROI estimates move over time.

The Top-N filter caches recomputed priors to ``data/cache/sportmonks/priors.parquet``
on every run with --use-live-priors (default). That cache is append-only:
each run inserts a new snapshot identified by ``updated_at``. Over a
multi-day trial, this builds a longitudinal record of how ROI estimates
drift as more graded picks accumulate.

This script reads the cache and produces a markdown report comparing the
LATEST snapshot to a baseline (first by default; pinnable to any earlier
snapshot via --baseline-snapshot). Drift is reported as percentage points
(pp) of ROI change. Thresholds:

  - |Δ| < 5pp  : stable
  - |Δ| ≥ 5pp  : drifting
  - |Δ| ≥ 10pp : alert (significant calibration shift)

Day-3+ use case: spot when a market's "true" ROI is settling vs Day-1's
small-sample noise. Operator decision aid for which markets to keep,
trim, or watch.

Usage::

    uv run python -m scripts.spike.sportmonks.drift_report

    # Pin baseline to a specific snapshot (oldest by default)
    uv run python -m scripts.spike.sportmonks.drift_report \\
        --baseline-snapshot 2026-05-10T22:29:04+00:00

    # Just markets, no leagues
    uv run python -m scripts.spike.sportmonks.drift_report --kind market

Read-only on the cache; writes a markdown report.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.spike.sportmonks.topn_filter import PRIORS_CACHE_PATH  # noqa: E402


DRIFT_PP_DRIFTING: float = 5.0
DRIFT_PP_ALERT: float = 10.0


def _list_snapshots(cache_path: Path) -> list[str]:
    """Return sorted unique ``updated_at`` timestamps in the cache."""
    if not cache_path.exists():
        return []
    df = pl.read_parquet(cache_path)
    if df.is_empty():
        return []
    return sorted(df.get_column("updated_at").unique().to_list())


def compute_drift(
    cache_path: Path = PRIORS_CACHE_PATH,
    kind_filter: str | None = None,
    baseline_snapshot: str | None = None,
) -> dict:
    """Compute drift table per (kind, key) between baseline and latest snapshot.

    Returns dict with shape:
      {
        "n_snapshots": int,
        "baseline_ts": str | None,
        "latest_ts": str | None,
        "rows": [
          {
            "kind": str, "key": str,
            "first_roi": float, "first_n": int,
            "last_roi": float, "last_n": int,
            "delta_roi_pp": float, "delta_n": int,
            "status": "stable" | "drifting" | "alert" | "new" | "dropped",
          },
          ...
        ],
        "error": str | None,
      }
    """
    snapshots = _list_snapshots(cache_path)
    if not snapshots:
        return {"error": "priors cache missing or empty",
                "n_snapshots": 0, "rows": []}
    if len(snapshots) < 2:
        return {"error": f"need at least 2 snapshots (have {len(snapshots)}); "
                f"run topn_filter with --use-live-priors more days",
                "n_snapshots": len(snapshots), "rows": [],
                "baseline_ts": snapshots[0], "latest_ts": snapshots[0]}

    df = pl.read_parquet(cache_path)
    if kind_filter:
        df = df.filter(pl.col("kind") == kind_filter)

    baseline_ts = baseline_snapshot or snapshots[0]
    latest_ts = snapshots[-1]

    if baseline_ts not in snapshots:
        return {"error": f"baseline snapshot {baseline_ts} not found; "
                f"available: {snapshots}", "n_snapshots": len(snapshots),
                "rows": []}

    first = df.filter(pl.col("updated_at") == baseline_ts).select(
        ["kind", "key", "observed_roi", "n"]
    ).rename({"observed_roi": "first_roi", "n": "first_n"})

    last = df.filter(pl.col("updated_at") == latest_ts).select(
        ["kind", "key", "observed_roi", "n"]
    ).rename({"observed_roi": "last_roi", "n": "last_n"})

    merged = first.join(last, on=["kind", "key"], how="full", coalesce=True)

    rows: list[dict] = []
    for r in merged.iter_rows(named=True):
        first_roi = r.get("first_roi")
        last_roi = r.get("last_roi")
        first_n = r.get("first_n")
        last_n = r.get("last_n")

        if first_roi is None and last_roi is not None:
            status = "new"
            delta_roi_pp = 0.0
        elif last_roi is None and first_roi is not None:
            status = "dropped"
            delta_roi_pp = 0.0
        else:
            delta_roi_pp = (last_roi - first_roi) * 100.0
            abs_delta = abs(delta_roi_pp)
            if abs_delta >= DRIFT_PP_ALERT:
                status = "alert"
            elif abs_delta >= DRIFT_PP_DRIFTING:
                status = "drifting"
            else:
                status = "stable"

        rows.append({
            "kind": r["kind"],
            "key": r["key"],
            "first_roi": first_roi,
            "first_n": first_n,
            "last_roi": last_roi,
            "last_n": last_n,
            "delta_roi_pp": delta_roi_pp,
            "delta_n": (last_n or 0) - (first_n or 0),
            "status": status,
        })

    # Sort by abs drift descending — alerts to the top
    rows.sort(key=lambda r: -abs(r["delta_roi_pp"]))

    return {
        "n_snapshots": len(snapshots),
        "baseline_ts": baseline_ts,
        "latest_ts": latest_ts,
        "rows": rows,
        "error": None,
    }


def _fmt_roi(v: float | None) -> str:
    return f"{v*100:+.2f}%" if v is not None else "—"


def _fmt_n(v: int | None) -> str:
    return str(v) if v is not None else "—"


def render_report(drift: dict) -> str:
    """Render a markdown report from compute_drift output."""
    lines = [f"# Priors drift report — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

    if drift.get("error"):
        lines.append(f"**Error:** {drift['error']}\n")
        if drift.get("n_snapshots"):
            lines.append(f"_Snapshots in cache: {drift['n_snapshots']}_")
        return "\n".join(lines)

    lines.append(f"**Snapshots compared:**")
    lines.append(f"- Baseline: `{drift['baseline_ts']}`")
    lines.append(f"- Latest:   `{drift['latest_ts']}`")
    lines.append(f"- Total snapshots in cache: {drift['n_snapshots']}\n")

    rows = drift["rows"]
    if not rows:
        lines.append("_No rows to report._\n")
        return "\n".join(lines)

    # Counts by status
    from collections import Counter
    by_status = Counter(r["status"] for r in rows)
    lines.append("## Summary")
    for s in ("alert", "drifting", "stable", "new", "dropped"):
        if by_status.get(s):
            lines.append(f"- `{s}`: {by_status[s]}")
    lines.append("")

    # Split markets vs leagues
    for kind in ("market", "league"):
        sub = [r for r in rows if r["kind"] == kind]
        if not sub:
            continue
        lines.append(f"## {kind.capitalize()}s — drift detail\n")
        lines.append("| Key | Baseline ROI (n) | Latest ROI (n) | Δ ROI (pp) | Δ n | Status |")
        lines.append("|-----|------------------|----------------|------------|-----|--------|")
        for r in sub:
            lines.append(
                f"| {r['key']} | "
                f"{_fmt_roi(r['first_roi'])} ({_fmt_n(r['first_n'])}) | "
                f"{_fmt_roi(r['last_roi'])} ({_fmt_n(r['last_n'])}) | "
                f"{r['delta_roi_pp']:+.2f} | "
                f"{r['delta_n']:+d} | "
                f"`{r['status']}` |"
            )
        lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cache-path", type=Path, default=PRIORS_CACHE_PATH)
    p.add_argument("--kind", choices=["market", "league"],
                   help="Filter to one kind of prior")
    p.add_argument("--baseline-snapshot", type=str,
                   help="Pin baseline to a specific updated_at timestamp "
                        "(default: oldest snapshot)")
    p.add_argument("--output", type=Path,
                   help="Write report to this path (default: stdout)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    drift = compute_drift(
        cache_path=args.cache_path,
        kind_filter=args.kind,
        baseline_snapshot=args.baseline_snapshot,
    )
    report = render_report(drift)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"[drift] wrote {args.output}")
    print(report)
    return 0 if not drift.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
