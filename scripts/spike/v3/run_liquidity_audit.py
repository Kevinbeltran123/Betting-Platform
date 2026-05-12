"""CLI for the v3 liquidity (stake-cap) audit.

Reads operator-supplied stake-cap observations + v3 shadow picks,
emits a markdown report with per-family bucket distributions and
recommended min-cap thresholds.

Usage::

    uv run python -m scripts.spike.v3.run_liquidity_audit \\
        --caps-csv data/cache/v3_shadow/betano_stake_caps.csv \\
        --shadow-root data/cache/v3_shadow \\
        --out reports/v3/liquidity_audit_2026-05-12.md

The output drives a manual MES config update — there's no automatic
write-back to source. The operator decides which families to
blacklist or apply a stricter min_stake_cap to in market_selector.py.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3.runtime.cohort_accountant import (  # noqa: E402
    load_v3_picks,
)
from bip.evaluation.live.engine_v3.runtime.liquidity_audit import (  # noqa: E402
    LiquidityAuditReport,
    run_audit,
)
from bip.evaluation.live.engine_v3.shadow_logger import (  # noqa: E402
    DEFAULT_SHADOW_ROOT,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--caps-csv",
        type=Path,
        required=True,
        help="Operator-supplied stake-cap observations CSV",
    )
    p.add_argument(
        "--shadow-root",
        type=Path,
        default=DEFAULT_SHADOW_ROOT,
        help="Root of v3 shadow log partitions",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output report markdown path (default: reports/v3/liquidity_audit_TODAY.md)",
    )
    p.add_argument(
        "--target-coverage",
        type=float,
        default=0.80,
        help="Target % of v3 candidates to retain (default 0.80)",
    )
    return p.parse_args(argv)


def write_markdown(report: LiquidityAuditReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# v3 liquidity audit — {today}",
        "",
        "## Coverage",
        f"- v3 candidates total: {report.overall_n_candidates}",
        f"- candidates with measured stake cap: {report.overall_n_with_cap}",
        f"- observed coverage: {report.overall_observed_pct:.1%}",
        f"- markets in caps CSV: {len(report.by_market)}",
        "",
        "## Per-family distribution + recommendations",
        "",
        "| family | n_candidates | observed mkts | unobserved mkts | recommended min cap (EUR) | top bucket |",
        "|---|---|---|---|---|---|",
    ]
    for fd in report.by_family:
        top_bucket = (
            max(fd.bucket_pct.items(), key=lambda kv: kv[1])[0]
            if fd.bucket_pct else "-"
        )
        lines.append(
            f"| {fd.family} | {fd.n_candidates} | {fd.n_markets_observed} | "
            f"{fd.n_markets_unobserved} | {fd.recommended_min_cap_eur:.0f} | "
            f"{top_bucket} |"
        )

    lines.extend([
        "",
        "## Bucket detail per family",
        "",
    ])
    for fd in report.by_family:
        lines.append(f"### {fd.family} (n_candidates={fd.n_candidates})")
        lines.append("")
        lines.append("| bucket EUR | n | % |")
        lines.append("|---|---|---|")
        for b, n in fd.bucket_counts.items():
            lines.append(
                f"| {b} | {n} | {fd.bucket_pct.get(b, 0.0):.1%} |"
            )
        lines.append("")

    lines.extend([
        "## Per-market median caps",
        "",
        "| market_id | family | n obs | median EUR | min EUR | max EUR |",
        "|---|---|---|---|---|---|",
    ])
    for m in report.by_market:
        lines.append(
            f"| `{m.market_id}` | {m.family} | {m.n_observations} | "
            f"{m.median_cap_eur:.0f} | {m.min_cap_eur:.0f} | "
            f"{m.max_cap_eur:.0f} |"
        )

    lines.extend([
        "",
        "## Caveats",
        "",
        "- Recommendation: families with `unobserved markets > 0` need more sampling rounds before the min-cap call is binding.",
        "- Target coverage is a heuristic; lower it to be stricter, raise to be permissive.",
        "- Caps observed only on Betano. Other bookmakers are ignored.",
        "",
        "## Action items for operator",
        "",
        "1. Review per-family recommended min caps.",
        "2. For each family where `recommended >= 250 EUR`, consider adding a hard floor in `market_selector.py`.",
        "3. For families with `n_markets_unobserved > 5`, schedule another sampling round before promoting changes.",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.caps_csv.exists():
        print(
            f"ERROR: caps CSV not found at {args.caps_csv}. "
            "See Papers/STAKE_CAPS_MEASUREMENT_PLAN.md for the sampling protocol "
            "and template path.",
            file=sys.stderr,
        )
        return 1

    picks = load_v3_picks(shadow_root=args.shadow_root)
    if picks.is_empty():
        print(
            f"WARN: no shadow picks found at {args.shadow_root}. "
            "Audit will only emit the per-market caps table.",
            file=sys.stderr,
        )

    report = run_audit(
        shadow_picks=picks,
        stake_caps_csv=args.caps_csv,
        target_coverage=args.target_coverage,
    )

    out_path = args.out or Path(
        f"reports/v3/liquidity_audit_"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    )
    write_markdown(report, out_path)
    print(f"liquidity audit report → {out_path}")
    print(
        f"overall coverage={report.overall_observed_pct:.1%}  "
        f"n_candidates={report.overall_n_candidates}  "
        f"n_families={len(report.by_family)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
