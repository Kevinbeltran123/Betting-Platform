"""Pre-jornada dry-run — show what the filter will do BEFORE the watcher starts.

Loads all current configuration sources (YAMLs, priors cache, edge buckets,
cascade thresholds) and emits a structured snapshot. Use this to verify
the filter is set up correctly before kicking off live capture.

What it answers:
- Which empirical windows are loaded? Per-market lo/hi range.
- Which (league, market) cells will be blocked or bonused?
- What live priors will the scorer use? (latest cache snapshot)
- What edge calibration factors are in effect?
- What are the cascade thresholds (F1 markets, F3 floor, F4 odds, F5 leagues)?
- What are the Top-N quotas (per-fixture, per-window)?

If any source is missing (e.g., YAMLs not yet generated, no priors cache),
the report calls out the fallback that will fire.

Usage::

    uv run python -m scripts.spike.sportmonks.precheck

    # Custom paths
    uv run python -m scripts.spike.sportmonks.precheck \\
        --windows-yaml configs/topn/market_minute_windows.yaml \\
        --policy-yaml  configs/topn/league_market_policy.yaml

Read-only on every source. Does not touch picks.db beyond computing
edge calibration factors (skippable with --no-edge-cal).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.spike.sportmonks.topn_filter import (  # noqa: E402
    DEFAULT_DB_PATH,
    DROP_LEAGUE_IDS,
    EDGE_FLOOR_PCT,
    KEEP_COND,
    KEEP_UNCOND,
    ODD_CEIL,
    ODD_FLOOR,
    POLICY_YAML_PATH,
    PRIORS_CACHE_PATH,
    WINDOW_FIRST_HALF,
    WINDOW_FULL_MATCH,
    WINDOW_SECOND_HALF,
    WINDOWS_YAML_PATH,
    compute_edge_buckets_from_db,
    load_cached_priors,
    load_league_market_policy,
    load_market_windows,
)


def precheck(
    windows_yaml: Path = WINDOWS_YAML_PATH,
    policy_yaml: Path = POLICY_YAML_PATH,
    priors_cache: Path = PRIORS_CACHE_PATH,
    picks_db: Path = DEFAULT_DB_PATH,
    skip_edge_cal: bool = False,
) -> dict:
    """Gather all current config state. Returns a dict for rendering."""
    # Windows
    windows = load_market_windows(windows_yaml)
    # Policy
    blocks, bonuses = load_league_market_policy(policy_yaml)
    # Priors cache
    cached = load_cached_priors(priors_cache)
    market_priors, league_priors = cached if cached else ({}, {})
    # Edge calibration
    edge_factors: dict | None = None
    if not skip_edge_cal and picks_db.exists():
        try:
            edge_factors = compute_edge_buckets_from_db(picks_db)
        except Exception as e:
            edge_factors = {"_error": str(e)}

    return {
        "generated_at": datetime.now().isoformat(),
        "sources": {
            "windows_yaml": str(windows_yaml),
            "windows_yaml_present": windows_yaml.exists(),
            "policy_yaml": str(policy_yaml),
            "policy_yaml_present": policy_yaml.exists(),
            "priors_cache": str(priors_cache),
            "priors_cache_present": priors_cache.exists(),
            "picks_db": str(picks_db),
            "picks_db_present": picks_db.exists(),
        },
        "windows": windows,
        "policy_blocks": sorted(blocks),
        "policy_bonuses": dict(sorted(bonuses.items())),
        "market_priors": market_priors,
        "league_priors": league_priors,
        "edge_factors": edge_factors,
        "cascade_thresholds": {
            "F1_keep_uncond": sorted(KEEP_UNCOND),
            "F1_keep_cond": dict(sorted(KEEP_COND.items())),
            "F2_window_full_match": list(WINDOW_FULL_MATCH),
            "F2_window_first_half": list(WINDOW_FIRST_HALF),
            "F2_window_second_half": list(WINDOW_SECOND_HALF),
            "F3_edge_floor_pct": EDGE_FLOOR_PCT,
            "F4_odd_band": [ODD_FLOOR, ODD_CEIL],
            "F5_drop_leagues": sorted(DROP_LEAGUE_IDS),
        },
    }


def render_report(state: dict) -> str:
    """Render the precheck dict as markdown."""
    lines = [f"# Filter pre-flight check — {state['generated_at']}\n"]

    # Source presence
    src = state["sources"]
    lines.append("## Configuration sources\n")
    for key in ("windows_yaml", "policy_yaml", "priors_cache", "picks_db"):
        present = src[f"{key}_present"]
        marker = "✓" if present else "✗"
        path = src[key]
        lines.append(f"- `{key}` {marker} `{path}`")
    lines.append("")

    # Windows
    windows = state["windows"]
    lines.append(f"## Empirical minute windows ({len(windows)} configured)\n")
    if not windows:
        lines.append("_No windows YAML — F2 will use class defaults only:_")
        thr = state["cascade_thresholds"]
        lines.append(f"- full-match: `{thr['F2_window_full_match']}`")
        lines.append(f"- first-half: `{thr['F2_window_first_half']}`")
        lines.append(f"- second-half: `{thr['F2_window_second_half']}`")
    else:
        lines.append("| Market | Empirical window | Note |")
        lines.append("|--------|------------------|------|")
        thr = state["cascade_thresholds"]
        for m, (lo, hi) in sorted(windows.items()):
            if m.startswith("first_half_") or m == "btts_first_half":
                cls = thr["F2_window_first_half"]
            elif m == "btts_second_half":
                cls = thr["F2_window_second_half"]
            else:
                cls = thr["F2_window_full_match"]
            final_lo = max(cls[0], lo)
            final_hi = min(cls[1], hi)
            note = f"final after intersect with class: [{final_lo}, {final_hi}]"
            lines.append(f"| `{m}` | [{lo}, {hi}] | {note} |")
    lines.append("")

    # Policy
    blocks = state["policy_blocks"]
    bonuses = state["policy_bonuses"]
    lines.append(
        f"## Policy overrides ({len(blocks)} blocks, {len(bonuses)} bonuses)\n"
    )
    if blocks:
        lines.append("### Blocks (will drop in F5)")
        for lid, m in blocks:
            lines.append(f"- L{lid} × `{m}`")
        lines.append("")
    if bonuses:
        lines.append("### Bonuses (will boost score in score())")
        for (lid, m), mult in bonuses.items():
            lines.append(f"- L{lid} × `{m}` → ×{mult:.2f}")
        lines.append("")
    if not blocks and not bonuses:
        lines.append("_No policy overrides loaded._\n")

    # Priors cache
    market_priors = state["market_priors"]
    league_priors = state["league_priors"]
    lines.append(
        f"## Live priors cache "
        f"({len(market_priors)} markets, {len(league_priors)} leagues)\n"
    )
    if market_priors:
        lines.append("### Market priors (sorted by ROI desc)")
        sorted_markets = sorted(
            market_priors.items(), key=lambda kv: -kv[1][0]
        )
        lines.append("| Market | observed_roi | n |")
        lines.append("|--------|--------------|---|")
        for m, (roi, n) in sorted_markets:
            lines.append(f"| `{m}` | {roi*100:+.2f}% | {n} |")
        lines.append("")
    if league_priors:
        lines.append("### League priors (sorted by ROI desc)")
        sorted_leagues = sorted(
            league_priors.items(), key=lambda kv: -kv[1][0]
        )
        lines.append("| league_id | observed_roi | n |")
        lines.append("|-----------|--------------|---|")
        for lid, (roi, n) in sorted_leagues:
            lines.append(f"| {lid} | {roi*100:+.2f}% | {n} |")
        lines.append("")
    if not market_priors and not league_priors:
        lines.append("_Empty cache — score() will fall back to DAY1 hardcoded._\n")

    # Edge calibration
    factors = state["edge_factors"]
    lines.append("## Edge calibration factors\n")
    if factors is None:
        lines.append("_Skipped (--no-edge-cal or picks.db missing)._\n")
    elif "_error" in factors:
        lines.append(f"_Error computing factors: {factors['_error']}_\n")
    elif not factors:
        lines.append("_No factors computed (no graded picks)._\n")
    else:
        lines.append("| Edge bucket (%) | Realization factor |")
        lines.append("|-----------------|--------------------|")
        for (lo, hi), f in sorted(factors.items()):
            hi_disp = "∞" if hi >= 1000 else f"{hi:.0f}"
            lines.append(f"| [{lo:.0f}, {hi_disp}) | {f:.2f} |")
        lines.append("")

    # Cascade thresholds
    thr = state["cascade_thresholds"]
    lines.append("## Cascade thresholds (static)\n")
    lines.append(f"- **F1 keep_uncond** ({len(thr['F1_keep_uncond'])} markets): "
                 f"`{thr['F1_keep_uncond']}`")
    lines.append(f"- **F1 keep_cond** (with min edge): `{thr['F1_keep_cond']}`")
    lines.append(f"- **F3 edge floor**: ≥ {thr['F3_edge_floor_pct']:.0f}%")
    lines.append(f"- **F4 odd band**: {thr['F4_odd_band']}")
    lines.append(f"- **F5 hard-drop leagues**: {thr['F5_drop_leagues']}")
    lines.append("")

    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--windows-yaml", type=Path, default=WINDOWS_YAML_PATH)
    p.add_argument("--policy-yaml", type=Path, default=POLICY_YAML_PATH)
    p.add_argument("--priors-cache", type=Path, default=PRIORS_CACHE_PATH)
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--no-edge-cal", action="store_true",
                   help="Skip computing edge calibration factors from picks.db")
    p.add_argument("--output", type=Path,
                   help="Write report to file (default: stdout)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    state = precheck(
        windows_yaml=args.windows_yaml,
        policy_yaml=args.policy_yaml,
        priors_cache=args.priors_cache,
        picks_db=args.picks_db,
        skip_edge_cal=args.no_edge_cal,
    )
    report = render_report(state)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"[precheck] wrote {args.output}")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
