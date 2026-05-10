"""Discover empirical filter policies from picks.db.

Two artifacts emitted:

1. ``configs/topn/market_minute_windows.yaml`` — per-market minute window
   where realized ROI is positive with adequate confidence. Replaces the
   one-size-fits-all class window in F2 (full-match=0-75, first-half=0-30,
   second-half=45-70).

2. ``configs/topn/league_market_policy.yaml`` — sparse (league, market)
   overrides. Encodes hard BLOCKS for cells that consistently lose
   (n>=10, shrunk_roi < -10%) and BONUSES for cells that consistently
   win (n>=10, shrunk_roi > +25%). Most cells fall through to the
   independent F1/F5 + market/league priors.

Algorithm — windows:
  For each market with n_total >= MIN_MARKET_N:
    1. Bucket picks into 10-minute chunks (0-9, 10-19, ..., 80-89)
    2. Shrunk ROI per bucket: (n*roi + k*roi_market) / (n+k), k=10
    3. Find peak bucket; expand outward while shrunk_roi >= MIN_ROI_FLOOR
    4. Emit (lo, hi) inclusive minute range
  Markets with n < MIN_MARKET_N → class default fallback (no override).

Algorithm — policy:
  For each (league, market) cell with n >= MIN_CELL_N:
    1. 3-way Bayesian pooling: market prior, league prior, cell observed
       shrunk_roi = (n*c + k_m*roi_m + k_l*roi_l) / (n+k_m+k_l)
    2. shrunk_roi < BLOCK_THRESHOLD → encode BLOCK
       shrunk_roi > BONUS_THRESHOLD → encode BONUS (multiplier 1.20)
  Other cells: no override (filter falls through to existing F1/F5).

Both YAMLs are regenerable on every run — designed to be re-derived as
data accumulates. Day-1 output is the calibration baseline; Day-3 should
re-run after analyze_jornada to incorporate fresh picks.

Usage::

    uv run python -m scripts.spike.sportmonks.discover_policies

    # Custom output paths
    uv run python -m scripts.spike.sportmonks.discover_policies \\
        --output-windows configs/topn/market_minute_windows.yaml \\
        --output-policy  configs/topn/league_market_policy.yaml

Read-only on picks.db.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.spike.sportmonks.topn_filter import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    DEFAULT_DB_PATH,
    enrich_with_league,
    load_picks,
)


# ── Window discovery thresholds ────────────────────────────────────────


MIN_MARKET_N: int = 30
"""Markets below this graded count fall back to class default (no override)."""

WINDOW_BUCKET_MINUTES: int = 10
"""Bucket width for window discovery."""

WINDOW_SHRINKAGE_K: int = 10
"""Bayesian shrinkage strength toward market mean for per-bucket ROI."""

WINDOW_ROI_FLOOR: float = 0.0
"""Buckets with shrunk ROI below this are excluded from the window."""

WINDOW_MIN_BUCKET_N: int = 3
"""Buckets with fewer than this many picks are not anchors (too noisy)."""


# ── Policy thresholds ──────────────────────────────────────────────────


MIN_CELL_N: int = 10
"""(league, market) cells below this are not encoded — fall through to defaults."""

POLICY_K_MARKET: int = 15
POLICY_K_LEAGUE: int = 15

BLOCK_THRESHOLD: float = -0.10
"""shrunk_roi below this triggers a BLOCK rule."""

BONUS_THRESHOLD: float = 0.25
"""shrunk_roi above this triggers a BONUS rule."""

BONUS_MULTIPLIER: float = 1.20
"""Score boost factor for cells in the BONUS list."""


# ── Window discovery ───────────────────────────────────────────────────


def _bucket_minute(minute: int, width: int = WINDOW_BUCKET_MINUTES) -> int:
    """Floor minute to bucket start (e.g., 27 → 20 with width=10)."""
    return (minute // width) * width


def discover_market_windows(
    df: pl.DataFrame,
    min_n: int = MIN_MARKET_N,
    bucket_width: int = WINDOW_BUCKET_MINUTES,
    k: int = WINDOW_SHRINKAGE_K,
    roi_floor: float = WINDOW_ROI_FLOOR,
    min_bucket_n: int = WINDOW_MIN_BUCKET_N,
) -> dict[str, dict]:
    """Discover empirical minute windows per market.

    Returns dict keyed by market with shape:
      {
        market: {
          "window": [lo, hi] | null,   # null = use class default
          "n_total": int,
          "shrunk_market_roi": float,
          "buckets": [{"lo": int, "hi": int, "n": int, "raw_roi": float,
                        "shrunk_roi": float, "in_window": bool}, ...]
        }
      }
    """
    graded = df.filter(pl.col("status").is_in(["won", "lost"]))
    out: dict[str, dict] = {}
    for market in sorted(graded.get_column("market").unique().to_list()):
        sub = graded.filter(pl.col("market") == market)
        n_total = sub.height
        if n_total < min_n:
            out[market] = {
                "window": None,
                "n_total": n_total,
                "shrunk_market_roi": None,
                "buckets": [],
                "reason": f"n={n_total} < min_n={min_n}, fallback to class default",
            }
            continue

        market_roi = float(sub.select(pl.col("profit_units").sum()).item()) / n_total

        # Bucket picks
        buckets: dict[int, list[float]] = defaultdict(list)
        for r in sub.iter_rows(named=True):
            b = _bucket_minute(r["minute"], bucket_width)
            buckets[b].append(r["profit_units"] or 0.0)

        # Per-bucket stats with shrinkage to market mean
        bucket_rows = []
        for b in sorted(buckets):
            pts = buckets[b]
            n = len(pts)
            raw_roi = sum(pts) / n
            shrunk = (n * raw_roi + k * market_roi) / (n + k)
            bucket_rows.append({
                "lo": b, "hi": b + bucket_width - 1, "n": n,
                "raw_roi": raw_roi, "shrunk_roi": shrunk,
                "in_window": False,
            })

        # Find peak bucket (must have at least min_bucket_n picks)
        eligible = [b for b in bucket_rows if b["n"] >= min_bucket_n]
        if not eligible:
            out[market] = {
                "window": None,
                "n_total": n_total,
                "shrunk_market_roi": market_roi,
                "buckets": bucket_rows,
                "reason": "no bucket meets min_bucket_n",
            }
            continue

        peak = max(eligible, key=lambda b: b["shrunk_roi"])
        peak_idx = bucket_rows.index(peak)

        # Expand outward from peak while shrunk_roi >= floor
        in_window_idxs = {peak_idx}
        # Expand right
        for i in range(peak_idx + 1, len(bucket_rows)):
            if bucket_rows[i]["shrunk_roi"] >= roi_floor:
                in_window_idxs.add(i)
            else:
                break
        # Expand left
        for i in range(peak_idx - 1, -1, -1):
            if bucket_rows[i]["shrunk_roi"] >= roi_floor:
                in_window_idxs.add(i)
            else:
                break

        for i in in_window_idxs:
            bucket_rows[i]["in_window"] = True

        sorted_idxs = sorted(in_window_idxs)
        window_lo = bucket_rows[sorted_idxs[0]]["lo"]
        window_hi = bucket_rows[sorted_idxs[-1]]["hi"]

        out[market] = {
            "window": [window_lo, window_hi],
            "n_total": n_total,
            "shrunk_market_roi": market_roi,
            "buckets": bucket_rows,
        }
    return out


# ── Policy discovery ───────────────────────────────────────────────────


def _shrunk_3way(
    n_cell: int, roi_cell: float,
    roi_market: float | None, roi_league: float | None,
    k_market: int = POLICY_K_MARKET, k_league: int = POLICY_K_LEAGUE,
) -> float:
    """3-way Bayesian pooling: cell observation + market prior + league prior.

    When market or league prior is None (sparse), that term contributes 0
    weight — all the mass goes to the available informants.
    """
    num = n_cell * roi_cell
    denom = n_cell
    if roi_market is not None:
        num += k_market * roi_market
        denom += k_market
    if roi_league is not None:
        num += k_league * roi_league
        denom += k_league
    return num / denom if denom > 0 else roi_cell


def discover_league_market_policy(
    df: pl.DataFrame,
    min_cell_n: int = MIN_CELL_N,
    block_threshold: float = BLOCK_THRESHOLD,
    bonus_threshold: float = BONUS_THRESHOLD,
    bonus_multiplier: float = BONUS_MULTIPLIER,
) -> dict:
    """Discover BLOCK and BONUS rules for (league_id, market) cells.

    Returns dict with shape:
      {
        "blocks": [{league_id, market, n, raw_roi, shrunk_roi, reason}, ...],
        "bonuses": [{league_id, market, n, raw_roi, shrunk_roi, multiplier}, ...],
        "stats": {n_cells_total, n_cells_eligible, ...}
      }
    """
    graded = df.filter(
        pl.col("status").is_in(["won", "lost"]) &
        pl.col("league_id").is_not_null()
    )

    # Per-market priors (with mild k=15 shrinkage to global mean of +0.10)
    market_roi: dict[str, float] = {}
    for r in (graded.group_by("market").agg(
        pl.len().alias("n"),
        pl.col("profit_units").sum().alias("pl"),
    )).iter_rows(named=True):
        if r["n"] >= 5:
            market_roi[r["market"]] = r["pl"] / r["n"]

    # Per-league priors (same)
    league_roi: dict[int, float] = {}
    for r in (graded.group_by("league_id").agg(
        pl.len().alias("n"),
        pl.col("profit_units").sum().alias("pl"),
    )).iter_rows(named=True):
        if r["n"] >= 5:
            league_roi[r["league_id"]] = r["pl"] / r["n"]

    # Per-cell aggregation
    cells = graded.group_by(["league_id", "market"]).agg(
        pl.len().alias("n"),
        pl.col("profit_units").sum().alias("pl"),
        (pl.col("status") == "won").cast(pl.Int32).sum().alias("won"),
    )

    blocks: list[dict] = []
    bonuses: list[dict] = []
    n_eligible = 0
    for r in cells.iter_rows(named=True):
        if r["n"] < min_cell_n:
            continue
        n_eligible += 1
        raw_roi = r["pl"] / r["n"]
        shrunk = _shrunk_3way(
            n_cell=r["n"], roi_cell=raw_roi,
            roi_market=market_roi.get(r["market"]),
            roi_league=league_roi.get(r["league_id"]),
        )
        cell = {
            "league_id": int(r["league_id"]),
            "market": r["market"],
            "n": r["n"],
            "won": r["won"],
            "raw_roi": round(raw_roi, 4),
            "shrunk_roi": round(shrunk, 4),
        }
        if shrunk < block_threshold:
            cell["reason"] = f"{r['won']}/{r['n']} won, shrunk ROI {shrunk*100:+.1f}%"
            blocks.append(cell)
        elif shrunk > bonus_threshold:
            cell["multiplier"] = bonus_multiplier
            bonuses.append(cell)

    return {
        "blocks": sorted(blocks, key=lambda c: c["shrunk_roi"]),
        "bonuses": sorted(bonuses, key=lambda c: -c["shrunk_roi"]),
        "stats": {
            "n_cells_total": cells.height,
            "n_cells_eligible": n_eligible,
            "block_threshold": block_threshold,
            "bonus_threshold": bonus_threshold,
        },
    }


# ── YAML emission ──────────────────────────────────────────────────────


def emit_windows_yaml(
    windows: dict[str, dict],
    out_path: Path,
) -> Path:
    """Write market_minute_windows.yaml.

    Schema:
      generated_at: ISO timestamp
      thresholds: {min_market_n, bucket_width, shrinkage_k, roi_floor}
      markets:
        ou_3_5:
          window: [10, 49]
          n_total: 42
          shrunk_market_roi: 0.7369
        cards_total_5_5:
          window: null
          n_total: 16
          reason: "n=16 < min_n=30, fallback to class default"
    """
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "min_market_n": MIN_MARKET_N,
            "bucket_width_minutes": WINDOW_BUCKET_MINUTES,
            "shrinkage_k": WINDOW_SHRINKAGE_K,
            "roi_floor_pct": WINDOW_ROI_FLOOR,
            "min_bucket_n": WINDOW_MIN_BUCKET_N,
        },
        "markets": {
            m: {k: v for k, v in info.items() if k != "buckets"}
            for m, info in windows.items()
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))
    return out_path


def emit_policy_yaml(policy: dict, out_path: Path) -> Path:
    """Write league_market_policy.yaml."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "min_cell_n": MIN_CELL_N,
            "block_threshold": BLOCK_THRESHOLD,
            "bonus_threshold": BONUS_THRESHOLD,
            "bonus_multiplier": BONUS_MULTIPLIER,
            "k_market": POLICY_K_MARKET,
            "k_league": POLICY_K_LEAGUE,
        },
        "stats": policy["stats"],
        "blocks": policy["blocks"],
        "bonuses": policy["bonuses"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--output-windows", type=Path,
                   default=Path("configs/topn/market_minute_windows.yaml"))
    p.add_argument("--output-policy", type=Path,
                   default=Path("configs/topn/league_market_policy.yaml"))
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    print(f"[load] {args.picks_db}")
    df = load_picks(args.picks_db)
    if df.is_empty():
        print("[error] picks.db empty")
        return 1
    df = enrich_with_league(df, args.cache_root)
    graded_n = df.filter(pl.col("status").is_in(["won", "lost"])).height
    print(f"[load] {df.height} picks, {graded_n} graded")

    # Q1 — windows
    windows = discover_market_windows(df)
    n_with_window = sum(1 for w in windows.values() if w.get("window"))
    n_fallback = len(windows) - n_with_window
    print(f"\n[windows] {n_with_window} markets with empirical window, "
          f"{n_fallback} fall back to class default")
    for m, info in sorted(windows.items()):
        if info.get("window"):
            w = info["window"]
            print(f"  {m:24s} window=[{w[0]:3d}, {w[1]:3d}]  n={info['n_total']}")

    path_w = emit_windows_yaml(windows, args.output_windows)
    print(f"[windows] wrote {path_w}")

    # Q2 — policy
    policy = discover_league_market_policy(df)
    print(f"\n[policy] eligible cells (n>={MIN_CELL_N}): "
          f"{policy['stats']['n_cells_eligible']} / "
          f"{policy['stats']['n_cells_total']} total")
    print(f"[policy] {len(policy['blocks'])} BLOCKS:")
    for b in policy["blocks"]:
        print(f"  L{b['league_id']:4d} {b['market']:24s} "
              f"n={b['n']:3d} shrunk_roi={b['shrunk_roi']*100:+6.2f}%  "
              f"({b['reason']})")
    print(f"[policy] {len(policy['bonuses'])} BONUSES:")
    for b in policy["bonuses"]:
        print(f"  L{b['league_id']:4d} {b['market']:24s} "
              f"n={b['n']:3d} shrunk_roi={b['shrunk_roi']*100:+6.2f}%  "
              f"x{b['multiplier']:.2f}")
    path_p = emit_policy_yaml(policy, args.output_policy)
    print(f"[policy] wrote {path_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
