"""A/B compare two Top-N filter configurations against the same picks.db.

Implements §F of the Top-N strategy doc — burn no bankroll, just re-grade
the captured DB under both configs and report which one wins. Decision rule:

  - If overlap @ Top-N ≥ 75% AND ROI delta < 2pp → call it a tie, prefer
    the simpler config.
  - If config B's ROI is materially higher (≥ 5pp lift) AND non-trivial
    composition difference (overlap < 90%) → adopt B.
  - Mixed signals → keep current, run another day.

Each config is a JSON file:

    {
      "name": "tighter_minute",
      "top_n": 25,
      "max_per_fixture": 3,
      "max_per_window": 5,
      "dedup": true,
      "use_live_priors": false,

      // Optional cascade overrides — when present, monkey-patches the
      // module constants for the duration of the comparison run.
      "edge_floor_pct": 12.0,
      "odd_floor": 1.30,
      "odd_ceil": 4.50,
      "drop_league_ids": [384],
      "window_full_match": [0, 75],
      "window_first_half": [0, 30],
      "window_second_half": [45, 70]
    }

Usage::

    uv run python -m scripts.spike.sportmonks.compare_topn \\
        configs/topn_baseline.json configs/topn_tighter.json

    # Or compare baseline against a one-off override:
    uv run python -m scripts.spike.sportmonks.compare_topn \\
        configs/topn_baseline.json --override-b '{"top_n":15,"name":"strict-15"}'
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.spike.sportmonks import topn_filter  # noqa: E402
from scripts.spike.sportmonks.topn_filter import (  # noqa: E402
    DAY1_LEAGUE_ROI,
    DAY1_MARKET_ROI,
    DEFAULT_CACHE_ROOT,
    DEFAULT_DB_PATH,
    apply_cascade,
    compute_league_priors_from_db,
    compute_market_priors_from_db,
    enrich_with_league,
    load_picks,
    score,
    top_n,
)


@dataclass
class FilterConfig:
    """One filter configuration to compare."""
    name: str
    top_n: int = 25
    max_per_fixture: int = 3
    max_per_window: int = 5
    dedup: bool = True
    use_live_priors: bool = False
    overrides: dict[str, Any] | None = None  # cascade constant overrides

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilterConfig":
        cascade_keys = {
            "edge_floor_pct", "odd_floor", "odd_ceil", "drop_league_ids",
            "window_full_match", "window_first_half", "window_second_half",
        }
        overrides = {k: v for k, v in data.items() if k in cascade_keys}
        return cls(
            name=data.get("name", "unnamed"),
            top_n=data.get("top_n", 25),
            max_per_fixture=data.get("max_per_fixture", 3),
            max_per_window=data.get("max_per_window", 5),
            dedup=data.get("dedup", True),
            use_live_priors=data.get("use_live_priors", False),
            overrides=overrides or None,
        )


@contextlib.contextmanager
def _patched_constants(overrides: dict[str, Any] | None):
    """Temporarily override topn_filter module constants for cascade tuning.

    Restores originals on exit even if the comparison errors. The overrides
    keys map directly to the UPPERCASE module constants:
      edge_floor_pct → EDGE_FLOOR_PCT
      odd_floor      → ODD_FLOOR
      odd_ceil       → ODD_CEIL
      drop_league_ids → DROP_LEAGUE_IDS (list[int] → frozenset[int])
      window_*       → tuple(start, end)
    """
    if not overrides:
        yield
        return
    saved: dict[str, Any] = {}
    try:
        for key, val in overrides.items():
            attr = key.upper()
            if not hasattr(topn_filter, attr):
                continue
            saved[attr] = getattr(topn_filter, attr)
            if attr == "DROP_LEAGUE_IDS":
                val = frozenset(val)
            elif attr.startswith("WINDOW_"):
                val = tuple(val)
            setattr(topn_filter, attr, val)
        yield
    finally:
        for attr, val in saved.items():
            setattr(topn_filter, attr, val)


def run_config(
    df: pl.DataFrame, cfg: FilterConfig, db_path: Path, cache_root: Path,
) -> pl.DataFrame:
    """Apply one config end-to-end and return the resulting Top-N DataFrame."""
    with _patched_constants(cfg.overrides):
        if cfg.use_live_priors:
            market = compute_market_priors_from_db(db_path) or DAY1_MARKET_ROI
            league = compute_league_priors_from_db(db_path, cache_root) \
                or DAY1_LEAGUE_ROI
        else:
            market = DAY1_MARKET_ROI
            league = DAY1_LEAGUE_ROI

        survivors = apply_cascade(df)
        if survivors.is_empty():
            return survivors
        scored = score(survivors, market_priors=market, league_priors=league)
        return top_n(
            scored,
            n=cfg.top_n,
            max_per_fixture=cfg.max_per_fixture,
            max_per_window=cfg.max_per_window,
            dedup=cfg.dedup,
        )


def _grading_summary(top: pl.DataFrame) -> dict[str, float | int]:
    """Per-config retro grading metrics."""
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


def compare(
    cfg_a: FilterConfig, cfg_b: FilterConfig,
    db_path: Path = DEFAULT_DB_PATH,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> dict[str, Any]:
    """Run both configs against the same picks.db, return comparison report.

    Returns dict with keys:
      - a, b: per-config grading summaries
      - lift_pp: ROI of B minus ROI of A (in percentage points)
      - overlap: count of picks shared by both Top-N (matched by id)
      - overlap_pct: overlap as fraction of min(|A|, |B|)
      - a_only / b_only: pick IDs unique to each config
      - verdict: tie | adopt_b | adopt_a | no_consensus
    """
    df = load_picks(db_path)
    if df.is_empty():
        return {"error": "picks.db empty"}
    df = enrich_with_league(df, cache_root)

    top_a = run_config(df, cfg_a, db_path, cache_root)
    top_b = run_config(df, cfg_b, db_path, cache_root)

    summary_a = _grading_summary(top_a)
    summary_b = _grading_summary(top_b)

    # Composition overlap
    ids_a = set(top_a.get_column("id").to_list()) if "id" in top_a.columns else set()
    ids_b = set(top_b.get_column("id").to_list()) if "id" in top_b.columns else set()
    overlap = ids_a & ids_b
    a_only = ids_a - ids_b
    b_only = ids_b - ids_a
    denom = min(len(ids_a), len(ids_b)) or 1
    overlap_pct = len(overlap) / denom

    lift_pp = summary_b["roi_pct"] - summary_a["roi_pct"]

    # Verdict heuristic from the strategy doc:
    if overlap_pct >= 0.75 and abs(lift_pp) < 2.0:
        verdict = "tie"
    elif lift_pp >= 5.0 and overlap_pct < 0.90:
        verdict = "adopt_b"
    elif lift_pp <= -5.0 and overlap_pct < 0.90:
        verdict = "adopt_a"
    else:
        verdict = "no_consensus"

    return {
        "a": {"name": cfg_a.name, **summary_a},
        "b": {"name": cfg_b.name, **summary_b},
        "lift_pp": lift_pp,
        "overlap": len(overlap),
        "overlap_pct": overlap_pct,
        "a_only": sorted(a_only),
        "b_only": sorted(b_only),
        "verdict": verdict,
    }


def render_comparison(result: dict[str, Any]) -> str:
    """Pretty markdown for the comparison run."""
    if "error" in result:
        return f"# Comparison failed\n\n{result['error']}\n"
    a, b = result["a"], result["b"]
    lines = [
        "# Top-N filter A/B comparison\n",
        f"**Verdict:** `{result['verdict']}`",
        f"  - Overlap: {result['overlap']} picks "
        f"({result['overlap_pct']:.0%} of min(|A|,|B|))",
        f"  - ROI lift (B - A): **{result['lift_pp']:+.2f}pp**",
        "",
        "## Per-config retro grading\n",
        "| Config | n | graded | won | win% | P/L | ROI% |",
        "|--------|---|--------|-----|------|-----|------|",
    ]
    for label, cfg in (("A", a), ("B", b)):
        win_pct = (cfg["won"] / cfg["graded"] * 100) if cfg["graded"] else 0.0
        lines.append(
            f"| {label}: {cfg['name']} | {cfg['n']} | {cfg['graded']} | "
            f"{cfg['won']} | {win_pct:.1f}% | {cfg['pl']:+.2f} | "
            f"{cfg['roi_pct']:+.2f} |"
        )
    lines.append("")
    if result["a_only"] or result["b_only"]:
        lines.append("## Composition diff\n")
        lines.append(f"- **A-only ({len(result['a_only'])} picks)**: "
                     f"{result['a_only'][:10]}{'...' if len(result['a_only']) > 10 else ''}")
        lines.append(f"- **B-only ({len(result['b_only'])} picks)**: "
                     f"{result['b_only'][:10]}{'...' if len(result['b_only']) > 10 else ''}")
        lines.append("")
    return "\n".join(lines)


def _load_config(path: Path) -> FilterConfig:
    return FilterConfig.from_dict(json.loads(path.read_text()))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config_a", type=Path, help="Baseline config JSON")
    p.add_argument("config_b", type=Path, nargs="?",
                   help="Variant config JSON (omit if using --override-b)")
    p.add_argument("--override-b", type=str,
                   help="Inline JSON to override fields from config_a for B")
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--output", type=Path,
                   help="Write markdown report to this path (default: stdout)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg_a = _load_config(args.config_a)
    if args.config_b:
        cfg_b = _load_config(args.config_b)
    elif args.override_b:
        base = json.loads(args.config_a.read_text())
        base.update(json.loads(args.override_b))
        cfg_b = FilterConfig.from_dict(base)
    else:
        print("error: must provide config_b or --override-b", file=sys.stderr)
        return 2

    print(f"[compare] A={cfg_a.name}  vs  B={cfg_b.name}")
    result = compare(cfg_a, cfg_b, args.picks_db, args.cache_root)
    report = render_comparison(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"[compare] wrote {args.output}")
    print()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
