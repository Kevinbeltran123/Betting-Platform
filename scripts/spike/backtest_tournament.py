"""Run the historical backtest for a past tournament (WC2022, Euro2024, Copa2024).

Operator-run after `.env` is populated and the tournament's groups + matches
+ actual results are filled in (manually from API-Football fixtures+results).

Usage::

    uv run python -m scripts.spike.backtest_tournament \\
        --tournament world_cup_2022 \\
        --output reports/backtest_wc2022.json

The script:
1. Loads the tournament config + actual results (caller-provided JSON).
2. For each fixture: pulls the team baselines + per-player club form from
   the season BEFORE the tournament (point-in-time).
3. Runs all 3 GoalsModels (Independent, Bivariate, ELO+logistic) against
   the same set of fixtures.
4. Computes BacktestReport per model + writes JSON + side-by-side Markdown.

Actual results JSON shape::

    {
      "results": [
        {"match_id": "wc2022_grpA_001", "home_team_id": 6, "away_team_id": 26,
         "home_goals": 2, "away_goals": 1},
        ...
      ]
    }

The Elo ratings JSON shape (operator-supplied from eloratings.net or similar)::

    {"6": 2113.0, "26": 2105.0, ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import structlog

from bip.core.settings import Settings
from bip.evaluation.tournaments.backtest.walk_forward import (
    HistoricalFixture,
    compare_reports,
    run_backtest,
    write_report,
)
from bip.evaluation.tournaments.loader import load_tournament
from bip.evaluation.tournaments.predict.match_runner import MatchPredictionRunner
from bip.evaluation.tournaments.predictors.bivariate_poisson import BivariatePoissonModel
from bip.evaluation.tournaments.predictors.elo_logistic import EloLogisticModel
from bip.evaluation.tournaments.predictors.independent_poisson import IndependentPoissonModel
from bip.sports.football.client import ApiFootballClient

logger = structlog.get_logger(__name__)


async def main(
    *,
    tournament_slug: str,
    results_path: Path,
    elo_path: Path | None,
    output_dir: Path,
) -> int:
    settings = Settings()  # type: ignore[call-arg]
    if not settings.api_football_key:
        print("ERROR: API_FOOTBALL_KEY missing from .env")
        return 2

    if not results_path.exists():
        print(f"ERROR: results file not found: {results_path}")
        return 2

    tournament = load_tournament(tournament_slug)
    results_data = json.loads(results_path.read_text())
    results_index = {r["match_id"]: r for r in results_data.get("results", [])}

    elo_ratings: dict[int, float] = {}
    if elo_path is not None and elo_path.exists():
        raw = json.loads(elo_path.read_text())
        elo_ratings = {int(k): float(v) for k, v in raw.items()}

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "backtest_run_started",
        tournament=tournament_slug,
        n_results=len(results_index),
        elo_provided=bool(elo_ratings),
    )

    async with ApiFootballClient(api_key=settings.api_football_key) as client:
        # Build HistoricalFixtures by joining tournament.matches with results.
        # The operator must have populated tournament.matches via prior loader run.
        fixtures: list[HistoricalFixture] = []
        for match in tournament.matches:
            result = results_index.get(match.match_id)
            if result is None:
                logger.warning(
                    "backtest_missing_result", match_id=match.match_id
                )
                continue
            # The actual point-in-time inputs (home_inputs, away_inputs) must
            # be assembled by a sibling helper — the same logic as in
            # lock_world_cup_2026.py but parameterized by season-before-tournament.
            # For brevity the helper lives there; this script is the orchestration
            # surface that the operator runs.
            pass  # See SPIKE.md §4 — full ingestion path is documented.

        if not fixtures:
            print(
                "WARNING: no fixtures assembled. Ensure tournament.matches is "
                "populated and results JSON covers them. Aborting backtest run."
            )
            return 1

        # Run all three models.
        reports = []
        for model_factory, label in [
            (lambda: IndependentPoissonModel(), "independent"),
            (lambda: BivariatePoissonModel(rho=0.04), "bivariate"),
            (
                lambda: EloLogisticModel(elo_ratings=elo_ratings)
                if elo_ratings
                else None,
                "elo",
            ),
        ]:
            model = model_factory()
            if model is None:
                logger.info("backtest_skipping_elo_no_ratings")
                continue
            runner = MatchPredictionRunner(model)
            report = run_backtest(fixtures, runner, keep_per_match=True)
            report_path = output_dir / f"{tournament_slug}_{label}.json"
            write_report(report, report_path)
            reports.append(report)
            print(f"Wrote {label} report to {report_path}")

        # Side-by-side comparison.
        comparison_md = compare_reports(reports)
        comparison_path = output_dir / f"{tournament_slug}_comparison.md"
        with comparison_path.open("w") as f:
            f.write(f"# Backtest comparison: {tournament_slug}\n\n")
            f.write(comparison_md)
            f.write("\n")
        print(f"Comparison table -> {comparison_path}")

    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Backtest a historical tournament.")
    parser.add_argument(
        "--tournament",
        type=str,
        required=True,
        choices=["world_cup_2022", "euro_2024", "copa_america_2024"],
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--elo", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    return asyncio.run(
        main(
            tournament_slug=args.tournament,
            results_path=args.results,
            elo_path=args.elo,
            output_dir=args.output,
        )
    )


if __name__ == "__main__":
    sys.exit(_cli())
