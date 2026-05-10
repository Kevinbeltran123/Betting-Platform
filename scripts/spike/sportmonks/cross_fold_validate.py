"""Cross-fold validation — verify the empirical YAMLs aren't just overfitting.

Critical caveat baked into the prior commits: the windows/policy YAMLs
emitted by ``discover_policies`` were derived from the same picks they're
later scored against. The Day-1 retro lift could be data leakage rather
than genuine signal.

This script splits picks.db into temporal halves and runs:

  1. Derive YAMLs from early half ONLY (no peeking at late picks)
  2. Apply filter on late half WITH derived YAMLs → top-25, ROI
  3. Apply filter on late half WITHOUT YAMLs (class defaults only) → top-25, ROI
  4. Compare lift + composition overlap → emit verdict

Verdict heuristic mirrors compare_topn.py:
  lift_pp >= +5 AND overlap < 90%   → "generalizes" (YAMLs add signal)
  |lift_pp| < 2                     → "neutral" (YAMLs ~equivalent to defaults)
  lift_pp <= -5                     → "overfit" (YAMLs hurt out-of-sample)
  otherwise                         → "no_consensus"

KNOWN LIMITATION on Day-1 data: 813 graded picks / 2 = ~400 per half.
Most markets fall below MIN_MARKET_N=30 in the early half, so windows
yields a sparse YAML. Cross-fold signal will be WEAK on Day-1; the tool
becomes more conclusive after Day-3+ when each half exceeds 1500 picks.

Usage::

    uv run python -m scripts.spike.sportmonks.cross_fold_validate

    # Custom split point (default: median emitted_at)
    uv run python -m scripts.spike.sportmonks.cross_fold_validate \\
        --split-at 2026-05-10T15:00:00+00:00

Read-only on picks.db.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.spike.sportmonks.discover_policies import (  # noqa: E402
    discover_league_market_policy,
    discover_market_windows,
)
from scripts.spike.sportmonks.topn_filter import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    DEFAULT_DB_PATH,
    GLOBAL_PRIOR_ROI,
    apply_cascade,
    enrich_with_league,
    load_picks,
    score,
    top_n,
)


# Verdict thresholds (mirror compare_topn.py)
LIFT_ADOPT_PP: float = 5.0
LIFT_TIE_PP: float = 2.0
LIFT_REJECT_PP: float = -5.0


# ── Helpers ────────────────────────────────────────────────────────────


def _split_by_timestamp(
    df: pl.DataFrame, split_at: str | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, str]:
    """Split df into (early, late) by emitted_at timestamp.

    If split_at is None, uses the median emitted_at as the splitter.
    Returns (early_df, late_df, split_ts_iso).
    """
    if "emitted_at" not in df.columns:
        raise ValueError("emitted_at column required for cross-fold split")

    sorted_df = df.sort("emitted_at")
    if split_at is None:
        # Median by row count — half-and-half
        split_idx = sorted_df.height // 2
        split_at = sorted_df.row(split_idx, named=True)["emitted_at"]

    early = sorted_df.filter(pl.col("emitted_at") < split_at)
    late = sorted_df.filter(pl.col("emitted_at") >= split_at)
    return early, late, split_at


def _priors_from_df(
    df: pl.DataFrame, key_col: str, min_n: int = 5,
) -> dict[Any, tuple[float, int]]:
    """Compute observed ROI per (key_col) from a graded subset of df.

    Same shape as ``compute_*_priors_from_db`` but operates on a
    pre-filtered DataFrame so cross-fold can isolate early-only stats.
    """
    graded = df.filter(pl.col("status").is_in(["won", "lost"]))
    if graded.is_empty():
        return {}

    by: dict = defaultdict(list)
    for r in graded.iter_rows(named=True):
        key = r.get(key_col)
        if key is None:
            continue
        by[key].append(r.get("profit_units") or 0.0)
    return {
        k: (sum(v) / len(v), len(v))
        for k, v in by.items()
        if len(v) >= min_n
    }


def _derive_configs(
    early_df: pl.DataFrame,
) -> tuple[
    dict[str, tuple[int, int]],
    set[tuple[int, str]],
    dict[tuple[int, str], float],
    dict[str, tuple[float, int]],
    dict[int, tuple[float, int]],
]:
    """From the early half, derive empirical YAMLs + priors.

    Returns (empirical_windows, policy_blocks, policy_bonuses,
              market_priors, league_priors).
    """
    windows_dict = discover_market_windows(early_df)
    empirical_windows: dict[str, tuple[int, int]] = {}
    for m, info in windows_dict.items():
        win = info.get("window")
        if win and len(win) == 2:
            empirical_windows[m] = (int(win[0]), int(win[1]))

    policy = discover_league_market_policy(early_df)
    policy_blocks: set[tuple[int, str]] = {
        (int(b["league_id"]), b["market"]) for b in policy["blocks"]
    }
    policy_bonuses: dict[tuple[int, str], float] = {
        (int(b["league_id"]), b["market"]): float(b.get("multiplier", 1.20))
        for b in policy["bonuses"]
    }

    market_priors = _priors_from_df(early_df, "market")
    league_priors = _priors_from_df(early_df, "league_id")

    return (empirical_windows, policy_blocks, policy_bonuses,
            market_priors, league_priors)


def _grade_topn(top: pl.DataFrame) -> dict[str, Any]:
    """Compute retro grading metrics for a Top-N DataFrame."""
    if top.is_empty():
        return {"n": 0, "graded": 0, "won": 0, "pl": 0.0, "roi_pct": 0.0}
    graded = top.filter(pl.col("status").is_in(["won", "lost"]))
    n_graded = graded.height
    n_won = graded.filter(pl.col("status") == "won").height
    pl_total = float(graded.select(pl.col("profit_units").sum()).item() or 0.0)
    return {
        "n": top.height, "graded": n_graded, "won": n_won, "pl": pl_total,
        "roi_pct": (pl_total / n_graded * 100) if n_graded else 0.0,
    }


def _verdict(lift_pp: float, overlap_pct: float) -> str:
    """Map (lift, overlap) → categorical verdict."""
    if lift_pp >= LIFT_ADOPT_PP and overlap_pct < 0.90:
        return "generalizes"
    if abs(lift_pp) < LIFT_TIE_PP:
        return "neutral"
    if lift_pp <= LIFT_REJECT_PP:
        return "overfit"
    return "no_consensus"


# ── Cross-fold orchestration ──────────────────────────────────────────


def cross_fold(
    db_path: Path = DEFAULT_DB_PATH,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    split_at: str | None = None,
    top_n_size: int = 25,
) -> dict[str, Any]:
    """Run the full cross-fold pipeline and return structured results."""
    df = load_picks(db_path)
    if df.is_empty():
        return {"error": "picks.db empty"}
    df = enrich_with_league(df, cache_root)

    try:
        early, late, split_ts = _split_by_timestamp(df, split_at)
    except ValueError as e:
        return {"error": str(e)}

    if early.is_empty() or late.is_empty():
        return {"error": "split produced empty half"}

    # Derive configs from EARLY only
    (windows, blocks, bonuses, mk_priors, lg_priors) = _derive_configs(early)

    # Apply on LATE with derived configs
    survivors_with = apply_cascade(late, empirical_windows=windows,
                                    policy_blocks=blocks)
    scored_with = score(survivors_with, market_priors=mk_priors,
                        league_priors=lg_priors,
                        policy_bonuses=bonuses)
    top_with = top_n(scored_with, n=top_n_size)

    # Apply on LATE WITHOUT derived configs (class defaults only)
    survivors_without = apply_cascade(late)
    scored_without = score(survivors_without, market_priors=mk_priors,
                            league_priors=lg_priors)
    top_without = top_n(scored_without, n=top_n_size)

    # Grade both
    grade_with = _grade_topn(top_with)
    grade_without = _grade_topn(top_without)

    # Composition overlap
    ids_with = set(top_with.get_column("id").to_list()) if not top_with.is_empty() else set()
    ids_without = set(top_without.get_column("id").to_list()) if not top_without.is_empty() else set()
    overlap = ids_with & ids_without
    denom = min(len(ids_with), len(ids_without)) or 1
    overlap_pct = len(overlap) / denom

    lift_pp = grade_with["roi_pct"] - grade_without["roi_pct"]

    return {
        "split_ts": split_ts,
        "early": {"total": early.height,
                   "graded": early.filter(pl.col("status").is_in(["won","lost"])).height},
        "late": {"total": late.height,
                  "graded": late.filter(pl.col("status").is_in(["won","lost"])).height},
        "derived": {
            "n_windows": len(windows),
            "windows": {m: list(w) for m, w in sorted(windows.items())},
            "n_blocks": len(blocks),
            "blocks": sorted([(int(lid), m) for lid, m in blocks]),
            "n_bonuses": len(bonuses),
            "bonuses": {f"{lid}/{m}": mult for (lid, m), mult in sorted(bonuses.items())},
            "n_market_priors": len(mk_priors),
            "n_league_priors": len(lg_priors),
        },
        "with_yamls": grade_with,
        "without_yamls": grade_without,
        "lift_pp": lift_pp,
        "overlap": len(overlap),
        "overlap_pct": overlap_pct,
        "verdict": _verdict(lift_pp, overlap_pct),
    }


def render_report(result: dict[str, Any]) -> str:
    """Markdown render of cross-fold result."""
    if "error" in result:
        return f"# Cross-fold validation failed\n\n**Error:** {result['error']}\n"

    lines = [
        f"# Cross-fold validation — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"**Verdict:** `{result['verdict']}`",
        f"  - ROI lift (with YAMLs - without): **{result['lift_pp']:+.2f}pp**",
        f"  - Composition overlap: {result['overlap']} picks "
        f"({result['overlap_pct']:.0%})",
        "",
        f"**Split point:** `{result['split_ts']}`",
        f"  - Early half: {result['early']['total']} picks "
        f"({result['early']['graded']} graded)",
        f"  - Late half:  {result['late']['total']} picks "
        f"({result['late']['graded']} graded)",
        "",
        "## Configs derived from early half",
        f"- Empirical windows: {result['derived']['n_windows']}",
        f"- Policy blocks:     {result['derived']['n_blocks']}",
        f"- Policy bonuses:    {result['derived']['n_bonuses']}",
        f"- Market priors:     {result['derived']['n_market_priors']}",
        f"- League priors:     {result['derived']['n_league_priors']}",
        "",
    ]

    if result["derived"]["windows"]:
        lines.append("### Windows derived (early half)")
        for m, w in result["derived"]["windows"].items():
            lines.append(f"- `{m}`: [{w[0]}, {w[1]}]")
        lines.append("")
    if result["derived"]["blocks"]:
        lines.append("### Blocks derived (early half)")
        for lid, m in result["derived"]["blocks"]:
            lines.append(f"- L{lid} × `{m}`")
        lines.append("")
    if result["derived"]["bonuses"]:
        lines.append("### Bonuses derived (early half)")
        for k, mult in result["derived"]["bonuses"].items():
            lines.append(f"- `{k}` × {mult:.2f}")
        lines.append("")

    lines.append("## Top-N performance on LATE half\n")
    lines.append("| Config | n | graded | won | win% | P/L | ROI% |")
    lines.append("|--------|---|--------|-----|------|-----|------|")
    for label, g in (("with YAMLs", result["with_yamls"]),
                      ("without YAMLs (class defaults)", result["without_yamls"])):
        win_pct = (g["won"] / g["graded"] * 100) if g["graded"] else 0.0
        lines.append(
            f"| {label} | {g['n']} | {g['graded']} | {g['won']} | "
            f"{win_pct:.1f}% | {g['pl']:+.2f} | {g['roi_pct']:+.2f} |"
        )
    lines.append("")

    # Caveat
    early_g = result["early"]["graded"]
    late_g = result["late"]["graded"]
    if early_g < 800 or late_g < 800:
        lines.append("> **Caveat:** sample sizes per half are small "
                     f"(early={early_g}, late={late_g}); few markets meet "
                     "MIN_MARKET_N=30 in the early half so the derived YAMLs "
                     "are sparse. Cross-fold signal becomes more conclusive "
                     "with more accumulated jornadas.\n")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--split-at", type=str, default=None,
                   help="ISO timestamp to split at (default: median emitted_at)")
    p.add_argument("--top-n", type=int, default=25)
    p.add_argument("--output", type=Path,
                   help="Write markdown report to this path (default: stdout)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    print(f"[cross-fold] picks_db={args.picks_db}")
    result = cross_fold(
        db_path=args.picks_db,
        cache_root=args.cache_root,
        split_at=args.split_at,
        top_n_size=args.top_n,
    )
    report = render_report(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"[cross-fold] wrote {args.output}")
    print()
    print(report)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
