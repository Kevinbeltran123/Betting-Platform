"""Shadow-promotion report for v3 gate rules.

Reads gate_denials.parquet filtered to is_shadow=True (rule_8, rule_9) and
dominant_team_id divergence from gsv_log.parquet across a date range.
Grades the underlying theses via the canonical v3_grader (grade_picks_for_date
/ grade_v3_pick) — NOT GSV reconstruction.

For each shadow rule computes:
  - n:             number of shadow-denied candidates
  - effective_N:   number of unique fixtures (so one blowout can't dominate)
  - delta_pl:      counterfactual P/L if rule had been ENFORCED vs SHADOW
  - delta_precision: counterfactual win-rate delta
  - delta_volume:  change in bet count (ENFORCED would have reduced volume by n)
  - clv_delta:     average CLV difference when clv.parquet has coverage

Recommendation per rule: PROMOTE / KEEP-SHADOW / REVERT
  - PROMOTE:      effective_N >= MIN_EFFECTIVE_N AND delta_pl > 0 AND
                  delta_precision > 0
  - REVERT:       effective_N >= MIN_EFFECTIVE_N AND delta_pl < -REVERT_LOSS_THRESHOLD
  - KEEP-SHADOW:  anything else (insufficient data or mixed signals)

Usage::

    uv run python -m scripts.spike.v3.shadow_promotion_report \\
        --start 2026-05-10 --end 2026-05-14

    uv run python -m scripts.spike.v3.shadow_promotion_report \\
        --start 2026-05-10 --end 2026-05-14 --output report.json

Exit codes:
    0 — report generated
    1 — runtime error
    2 — no shadow data found for the date range
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from bip.evaluation.live.engine_v3.runtime.v3_grader import (
    GradeReport,
    GradedPick,
    grade_picks_for_date,
    write_outcomes_parquet,
)

log = structlog.get_logger("v3.shadow_promotion_report")

# ──────────────────────────────────────────────────────────────────────
# Thresholds for recommendation logic
# ──────────────────────────────────────────────────────────────────────

MIN_EFFECTIVE_N = 5          # minimum unique fixtures for a data-driven verdict
REVERT_LOSS_THRESHOLD = 2.0  # P/L units: below this → REVERT
PROMOTE_MIN_PRECISION = 0.0  # delta_precision must be non-negative to PROMOTE


# ──────────────────────────────────────────────────────────────────────
# Per-rule result dataclass
# ──────────────────────────────────────────────────────────────────────


@dataclass
class RulePromotionResult:
    """Promotion analysis for one shadow gate rule.

    n:             total shadow-denied candidates in the date range
    effective_N:   unique fixtures among the denied candidates (robustness metric
                   — prevents one 10-goals blowout from dominating the P/L)
    delta_pl:      sum of profit_units that shadow-denied picks WOULD have earned
                   if the rule had been enforced (positive = rule would have helped)
    delta_precision: win_rate(shadow-denied picks) minus overall shadow win_rate,
                   normalised so positive = shadow-denied picks were below-average
    delta_volume:  how many fewer bets if this rule were ENFORCED (= n, always
                   negative or zero since enforcement reduces volume)
    clv_delta:     mean CLV of shadow-denied picks minus overall CLV;
                   None when clv.parquet has no coverage for this rule
    recommendation: "PROMOTE" | "KEEP-SHADOW" | "REVERT"
    notes:         free-text rationale (data sufficiency, mixed signals, etc.)
    """
    rule: str
    n: int
    effective_N: int
    delta_pl: float
    delta_precision: float
    delta_volume: int
    clv_delta: float | None
    recommendation: str
    notes: str


@dataclass
class PromotionReport:
    """Full shadow-promotion report for a date range."""

    date_start: str
    date_end: str
    n_shadow_denials_total: int
    n_fixtures_total: int
    overall_win_rate: float | None
    overall_clv_mean: float | None
    rules: list[RulePromotionResult] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Parquet readers
# ──────────────────────────────────────────────────────────────────────


def _read_shadow_denials(
    shadow_root: Path,
    date_start: str,
    date_end: str,
) -> list[dict[str, Any]]:
    """Read gate_denials.parquet from all partitions in the date range,
    filtered to is_shadow=True."""
    import polars as pl

    rows: list[dict[str, Any]] = []
    start = datetime.strptime(date_start, "%Y-%m-%d").date()
    end = datetime.strptime(date_end, "%Y-%m-%d").date()

    for part_dir in sorted(shadow_root.iterdir()):
        if not part_dir.is_dir() or not part_dir.name.startswith("dt="):
            continue
        try:
            part_date = datetime.strptime(part_dir.name[3:], "%Y-%m-%d").date()
        except ValueError:
            continue
        if part_date < start or part_date > end:
            continue
        denial_path = part_dir / "gate_denials.parquet"
        if not denial_path.exists():
            continue
        df = pl.read_parquet(denial_path)
        if "is_shadow" not in df.columns:
            continue
        shadow_df = df.filter(pl.col("is_shadow") == True)  # noqa: E712
        for row in shadow_df.iter_rows(named=True):
            row["_date"] = part_date.isoformat()
            rows.append(row)

    return rows


def _read_gsv_dominant_diffs(
    shadow_root: Path,
    date_start: str,
    date_end: str,
) -> list[dict[str, Any]]:
    """Read gsv_log.parquet and extract rows where shadow_dominant_team_id
    differs from dominant_team_id (deserialized from gsv_json).

    Returns dicts with fixture_id, date, dominant_team_id, shadow_dominant_team_id.
    """
    import json as _json

    import polars as pl

    rows: list[dict[str, Any]] = []
    start = datetime.strptime(date_start, "%Y-%m-%d").date()
    end = datetime.strptime(date_end, "%Y-%m-%d").date()

    for part_dir in sorted(shadow_root.iterdir()):
        if not part_dir.is_dir() or not part_dir.name.startswith("dt="):
            continue
        try:
            part_date = datetime.strptime(part_dir.name[3:], "%Y-%m-%d").date()
        except ValueError:
            continue
        if part_date < start or part_date > end:
            continue
        gsv_path = part_dir / "gsv_log.parquet"
        if not gsv_path.exists():
            continue
        df = pl.read_parquet(gsv_path)
        for row in df.iter_rows(named=True):
            gsv_json = row.get("gsv_json")
            if not gsv_json:
                continue
            try:
                gsv_data = _json.loads(gsv_json)
            except Exception:  # noqa: BLE001
                continue
            # Extract nested dominant_team_id from score sub-object
            dom_id = None
            score = gsv_data.get("score") or {}
            if isinstance(score, dict):
                dom_id = score.get("dominant_team_id")
            shadow_dom_id = gsv_data.get("shadow_dominant_team_id")
            if dom_id != shadow_dom_id:
                rows.append({
                    "fixture_id": row.get("fixture_id"),
                    "date": part_date.isoformat(),
                    "dominant_team_id": dom_id,
                    "shadow_dominant_team_id": shadow_dom_id,
                    "thesis_id": None,  # GSV-level diff, not pick-level
                })

    return rows


def _read_clv_for_theses(
    shadow_root: Path,
    date_start: str,
    date_end: str,
    thesis_ids: set[str],
) -> dict[str, float]:
    """Read clv.parquet partitions and return {thesis_id: clv_percentage}
    for thesis IDs with coverage. Rows with null CLV are excluded."""
    import polars as pl

    result: dict[str, float] = {}
    start = datetime.strptime(date_start, "%Y-%m-%d").date()
    end = datetime.strptime(date_end, "%Y-%m-%d").date()

    for part_dir in sorted(shadow_root.iterdir()):
        if not part_dir.is_dir() or not part_dir.name.startswith("dt="):
            continue
        try:
            part_date = datetime.strptime(part_dir.name[3:], "%Y-%m-%d").date()
        except ValueError:
            continue
        if part_date < start or part_date > end:
            continue
        clv_path = part_dir / "clv.parquet"
        if not clv_path.exists():
            continue
        df = pl.read_parquet(clv_path)
        if "clv_percentage" not in df.columns or "thesis_id" not in df.columns:
            continue
        valid = df.filter(pl.col("clv_percentage").is_not_null())
        for row in valid.iter_rows(named=True):
            tid = str(row.get("thesis_id") or "")
            if tid in thesis_ids and tid not in result:
                result[tid] = float(row["clv_percentage"])

    return result


# ──────────────────────────────────────────────────────────────────────
# Grading integration
# ──────────────────────────────────────────────────────────────────────


def _grade_denial_rows(
    denial_rows: list[dict[str, Any]],
    graded_outcomes: dict[str, Any],  # thesis_id → GradedPick
) -> list[dict[str, Any]]:
    """Enrich denial rows with grading outcome from the canonical grader.

    Returns the same rows augmented with 'status', 'profit_units',
    'bookmaker_odd' from the corresponding GradedPick (if found).
    Rows with no matching graded outcome get status='unknown'.
    """
    enriched = []
    for row in denial_rows:
        thesis_id = str(row.get("thesis_id") or "")
        graded = graded_outcomes.get(thesis_id)
        if graded is not None:
            row = {
                **row,
                "graded_status": graded.status,
                "profit_units": graded.profit_units,
                "bookmaker_odd": graded.bookmaker_odd,
            }
        else:
            row = {
                **row,
                "graded_status": "unknown",
                "profit_units": 0.0,
                "bookmaker_odd": row.get("bookmaker_odd"),
            }
        enriched.append(row)
    return enriched


# ──────────────────────────────────────────────────────────────────────
# Promotion logic
# ──────────────────────────────────────────────────────────────────────


def _recommend(
    n: int,
    effective_N: int,
    delta_pl: float,
    delta_precision: float,
) -> tuple[str, str]:
    """Return (recommendation, notes) for a shadow rule."""
    if effective_N < MIN_EFFECTIVE_N:
        return (
            "KEEP-SHADOW",
            f"Insufficient data: effective_N={effective_N} < {MIN_EFFECTIVE_N}. "
            "Accumulate more shadow runs before deciding.",
        )
    if delta_pl < -REVERT_LOSS_THRESHOLD:
        return (
            "REVERT",
            f"Shadow-denied picks would have LOST {abs(delta_pl):.2f}u "
            f"if enforced (delta_pl={delta_pl:.2f} < -{REVERT_LOSS_THRESHOLD}). "
            "Rule is filtering bad bets — do NOT enforce.",
        )
    if delta_pl > 0 and delta_precision >= PROMOTE_MIN_PRECISION:
        return (
            "PROMOTE",
            f"Shadow-denied picks would have won {delta_pl:.2f}u "
            f"with delta_precision={delta_precision:+.3f}. "
            "Rule appears over-restrictive — consider promoting to enforced.",
        )
    return (
        "KEEP-SHADOW",
        f"Mixed signals: delta_pl={delta_pl:.2f}, delta_precision={delta_precision:+.3f}. "
        "Keep in shadow mode; more data needed.",
    )


def _compute_rule_result(
    rule: str,
    rows: list[dict[str, Any]],
    overall_win_rate: float | None,
    clv_by_thesis: dict[str, float],
    overall_clv_mean: float | None,
) -> RulePromotionResult:
    """Compute counterfactual deltas for one shadow rule."""
    n = len(rows)
    effective_N = len({int(r.get("fixture_id") or 0) for r in rows})

    # P/L delta: sum of what shadow-denied picks WOULD have earned
    # Positive delta_pl = shadow-denied picks WOULD have been profitable
    # (i.e., rule is over-restrictive)
    delta_pl = sum(float(r.get("profit_units") or 0.0) for r in rows)

    # Precision delta: win rate of shadow-denied picks vs overall
    n_won = sum(1 for r in rows if r.get("graded_status") == "won")
    n_graded = sum(1 for r in rows if r.get("graded_status") in ("won", "lost"))
    rule_win_rate = (n_won / n_graded) if n_graded > 0 else None

    if rule_win_rate is not None and overall_win_rate is not None:
        delta_precision = rule_win_rate - overall_win_rate
    else:
        delta_precision = 0.0

    # Volume delta: enforcement would REDUCE volume by n
    delta_volume = -n

    # CLV delta: mean CLV of shadow-denied theses vs overall
    thesis_ids = {str(r.get("thesis_id") or "") for r in rows}
    rule_clv_values = [clv_by_thesis[tid] for tid in thesis_ids if tid in clv_by_thesis]
    if rule_clv_values and overall_clv_mean is not None:
        rule_clv_mean = sum(rule_clv_values) / len(rule_clv_values)
        clv_delta: float | None = rule_clv_mean - overall_clv_mean
    else:
        clv_delta = None

    recommendation, notes = _recommend(n, effective_N, delta_pl, delta_precision)
    return RulePromotionResult(
        rule=rule,
        n=n,
        effective_N=effective_N,
        delta_pl=round(delta_pl, 4),
        delta_precision=round(delta_precision, 4),
        delta_volume=delta_volume,
        clv_delta=round(clv_delta, 4) if clv_delta is not None else None,
        recommendation=recommendation,
        notes=notes,
    )


# ──────────────────────────────────────────────────────────────────────
# Public callable
# ──────────────────────────────────────────────────────────────────────


async def build_promotion_report(
    *,
    date_start: str,
    date_end: str,
    shadow_root: Path,
    grader_client: Any | None = None,
) -> PromotionReport:
    """Build the shadow-promotion report for a date range.

    Args:
        date_start: ISO date string "YYYY-MM-DD" (inclusive).
        date_end: ISO date string "YYYY-MM-DD" (inclusive).
        shadow_root: Root of the v3_shadow partition tree.
        grader_client: SportmonksClient (or compatible duck-type) used to
            call grade_picks_for_date for canonical grading. When None,
            grading is skipped (all picks get status="unknown", profit=0).

    Returns:
        PromotionReport with per-rule recommendations.
    """
    log.info(
        "promotion_report_start",
        date_start=date_start,
        date_end=date_end,
        shadow_root=str(shadow_root),
    )

    # ── 1. Read shadow denials (is_shadow=True) ──────────────────────
    shadow_rows = _read_shadow_denials(shadow_root, date_start, date_end)
    log.info("shadow_denials_loaded", n=len(shadow_rows))

    # ── 2. Read GSV dominant-team divergence rows ─────────────────────
    dom_diff_rows = _read_gsv_dominant_diffs(shadow_root, date_start, date_end)
    log.info("dominant_team_diffs_loaded", n=len(dom_diff_rows))

    # ── 3. Grade the shadow-denied picks via canonical v3_grader ─────
    # Collect unique dates and grade picks for each date
    all_dates = sorted({r.get("_date") or date_start for r in shadow_rows})
    graded_by_thesis: dict[str, GradedPick] = {}

    if grader_client is not None:
        for date_iso in all_dates:
            try:
                graded, report = await grade_picks_for_date(
                    date_iso,
                    shadow_root=shadow_root,
                    client=grader_client,
                )
                for gp in graded:
                    graded_by_thesis[gp.thesis_id] = gp
                log.info(
                    "date_graded",
                    date=date_iso,
                    n_picks=report.n_picks_input,
                    n_won=report.n_won,
                    n_lost=report.n_lost,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("grade_picks_failed", date=date_iso, error=str(exc))
    else:
        log.warning(
            "no_grader_client",
            note="Grading skipped; all denials will have status=unknown.",
        )

    # ── 4. Enrich shadow rows with grading outcome ────────────────────
    enriched_rows = _grade_denial_rows(shadow_rows, graded_by_thesis)

    # ── 5. Compute overall win rate + CLV ─────────────────────────────
    n_won_all = sum(1 for r in enriched_rows if r.get("graded_status") == "won")
    n_graded_all = sum(1 for r in enriched_rows if r.get("graded_status") in ("won", "lost"))
    overall_win_rate = (n_won_all / n_graded_all) if n_graded_all > 0 else None

    all_thesis_ids = {str(r.get("thesis_id") or "") for r in shadow_rows}
    clv_by_thesis = _read_clv_for_theses(shadow_root, date_start, date_end, all_thesis_ids)
    all_clv_values = list(clv_by_thesis.values())
    overall_clv_mean = (sum(all_clv_values) / len(all_clv_values)) if all_clv_values else None

    # ── 6. Bucket rows by shadow rule ─────────────────────────────────
    # Shadow denials: rule_8 and rule_9 (tagged by rule_number in denial rows)
    rule_8_rows = [r for r in enriched_rows if int(r.get("rule_number") or 0) == 8]
    rule_9_rows = [r for r in enriched_rows if int(r.get("rule_number") or 0) == 9]

    # Dominant-team gap divergence: treated as a separate "dom_gap" analysis
    # (these are GSV-level diffs, not pick-level, so we compute volume impact only)
    dom_gap_n = len(dom_diff_rows)
    dom_gap_effective_N = len({r.get("fixture_id") for r in dom_diff_rows})

    rules: list[RulePromotionResult] = []

    if rule_8_rows:
        rules.append(_compute_rule_result(
            "rule_8",
            rule_8_rows,
            overall_win_rate,
            clv_by_thesis,
            overall_clv_mean,
        ))
    else:
        rules.append(RulePromotionResult(
            rule="rule_8",
            n=0, effective_N=0,
            delta_pl=0.0, delta_precision=0.0, delta_volume=0,
            clv_delta=None,
            recommendation="KEEP-SHADOW",
            notes="No rule_8 shadow denials found in date range.",
        ))

    if rule_9_rows:
        rules.append(_compute_rule_result(
            "rule_9",
            rule_9_rows,
            overall_win_rate,
            clv_by_thesis,
            overall_clv_mean,
        ))
    else:
        rules.append(RulePromotionResult(
            rule="rule_9",
            n=0, effective_N=0,
            delta_pl=0.0, delta_precision=0.0, delta_volume=0,
            clv_delta=None,
            recommendation="KEEP-SHADOW",
            notes="No rule_9 shadow denials found in date range.",
        ))

    # Dominant-team gap report (volume-only; no graded picks to compute P/L from)
    dom_gap_rec, dom_gap_notes = _recommend(
        dom_gap_n,
        dom_gap_effective_N,
        delta_pl=0.0,  # no pick-level P/L for GSV-level diffs
        delta_precision=0.0,
    )
    rules.append(RulePromotionResult(
        rule="dom_gap_0.025vs0.04",
        n=dom_gap_n,
        effective_N=dom_gap_effective_N,
        delta_pl=0.0,
        delta_precision=0.0,
        delta_volume=-dom_gap_n,
        clv_delta=None,
        recommendation=dom_gap_rec,
        notes=(
            f"GSV-level dominant_team_id divergence between shadow (0.025 gap) "
            f"and enforced (0.04 gap): {dom_gap_n} frames across "
            f"{dom_gap_effective_N} unique fixtures. "
            "P/L impact not computable at GSV level (no pick-level P/L). "
            + dom_gap_notes
        ),
    ))

    report = PromotionReport(
        date_start=date_start,
        date_end=date_end,
        n_shadow_denials_total=len(shadow_rows),
        n_fixtures_total=len({int(r.get("fixture_id") or 0) for r in shadow_rows + dom_diff_rows}),
        overall_win_rate=round(overall_win_rate, 4) if overall_win_rate is not None else None,
        overall_clv_mean=round(overall_clv_mean, 4) if overall_clv_mean is not None else None,
        rules=rules,
    )

    log.info(
        "promotion_report_complete",
        n_shadow_denials=report.n_shadow_denials_total,
        n_fixtures=report.n_fixtures_total,
        rules=[r.rule for r in rules],
    )
    return report


# ──────────────────────────────────────────────────────────────────────
# Formatting
# ──────────────────────────────────────────────────────────────────────


def _format_markdown(report: PromotionReport) -> str:
    """Render the report as markdown."""
    lines = [
        f"# Shadow Promotion Report: {report.date_start} to {report.date_end}",
        "",
        "## Summary",
        f"- Shadow denials (is_shadow=True): {report.n_shadow_denials_total}",
        f"- Unique fixtures: {report.n_fixtures_total}",
        f"- Overall win rate: "
        + (f"{report.overall_win_rate:.1%}" if report.overall_win_rate is not None else "N/A"),
        f"- Overall CLV mean: "
        + (f"{report.overall_clv_mean:+.2f}%" if report.overall_clv_mean is not None else "N/A"),
        "",
        "## Per-Rule Recommendations",
        "",
        "| Rule | n | effective_N | delta_P/L | delta_precision | delta_volume "
        "| CLV delta | Recommendation |",
        "| ---- | - | ----------- | --------- | --------------- | ------------ "
        "| --------- | -------------- |",
    ]
    for r in report.rules:
        clv_str = f"{r.clv_delta:+.2f}%" if r.clv_delta is not None else "N/A"
        lines.append(
            f"| {r.rule} | {r.n} | {r.effective_N} | "
            f"{r.delta_pl:+.2f}u | {r.delta_precision:+.3f} | "
            f"{r.delta_volume} | {clv_str} | **{r.recommendation}** |"
        )

    lines += ["", "## Detailed Notes", ""]
    for r in report.rules:
        lines.append(f"### {r.rule} — {r.recommendation}")
        lines.append(r.notes)
        lines.append("")

    return "\n".join(lines)


def _format_json(report: PromotionReport) -> str:
    """Render the report as JSON."""

    def _convert(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 6)
        return obj

    d = {
        "date_start": report.date_start,
        "date_end": report.date_end,
        "n_shadow_denials_total": report.n_shadow_denials_total,
        "n_fixtures_total": report.n_fixtures_total,
        "overall_win_rate": report.overall_win_rate,
        "overall_clv_mean": report.overall_clv_mean,
        "rules": [asdict(r) for r in report.rules],
    }
    return json.dumps(d, indent=2, default=_convert)


# ──────────────────────────────────────────────────────────────────────
# CLI entrypoint
# ──────────────────────────────────────────────────────────────────────


async def _main(args: argparse.Namespace) -> int:
    shadow_root = Path(args.shadow_root)
    if not shadow_root.exists():
        log.error("shadow_root_not_found", path=str(shadow_root))
        return 1

    # Build Sportmonks client (only if we have credentials)
    grader_client = None
    if not args.no_grade:
        try:
            from bip.core.config import Settings
            from bip.sports.football.sportmonks.client import SportmonksClient

            settings = Settings()
            grader_client = SportmonksClient(api_key=settings.sportmonks_api_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("grader_client_init_failed", error=str(exc))
            log.warning("grading_disabled", note="Run with --no-grade to suppress this warning")

    report = await build_promotion_report(
        date_start=args.start,
        date_end=args.end,
        shadow_root=shadow_root,
        grader_client=grader_client,
    )

    if report.n_shadow_denials_total == 0 and report.n_fixtures_total == 0:
        log.warning("no_shadow_data", date_start=args.start, date_end=args.end)
        return 2

    if args.format == "json":
        output = _format_json(report)
    else:
        output = _format_markdown(report)

    if args.output:
        Path(args.output).write_text(output)
        log.info("report_written", path=args.output)
    else:
        print(output)

    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Shadow-promotion report for v3 gate rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--start",
        required=True,
        metavar="YYYY-MM-DD",
        help="Start date (inclusive).",
    )
    parser.add_argument(
        "--end",
        required=True,
        metavar="YYYY-MM-DD",
        help="End date (inclusive).",
    )
    parser.add_argument(
        "--shadow-root",
        default="data/cache/v3_shadow",
        metavar="PATH",
        help="Root of the v3_shadow partition tree (default: data/cache/v3_shadow).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Write report to FILE instead of stdout.",
    )
    parser.add_argument(
        "--no-grade",
        action="store_true",
        help="Skip grading (use when Sportmonks API key is unavailable).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
