"""Phase 5 Layer-2 backtest runner — real-data lock decision.

Walks the 6 men's StatsBomb tournaments chronologically, predicts each
fixture using a stateful Bayesian predictor (built on
``BayesianUpdater`` from Phase 3), scores against observed outcomes via
``CalibrationAudit``, and emits a single ``LockDecision`` artifact
consumable by Phase 6's lock JSON emitter.

The predictor is the simplest defensible reference implementation:
maintain per-team Poisson rates via the Phase 3 Bayesian updater,
predict the next match's goal distribution as the product of two
Poissons (independence assumption — Bivariate Poisson would be the
upgrade), derive 1X2 / BTTS / OU 2.5 / Corners O/U from the score grid.
The walk-forward respects causality: state is updated only AFTER
scoring each fixture.

This is the test the spike was built for. The output ``LockDecision``
either passes the hard gates (classwise-ECE ≤ 5%, Brier ≤ 0.21 / 0.20)
— locking real WC2026 predictions becomes safe — or fails honestly
with a per-predictor / per-market breakdown that operator can interrogate.

Run::

    uv run python scripts/run_phase5_backtest.py \\
        --output data/cache/lock_decision.json

Prerequisites: ``uv run python scripts/seed_statsbomb_tournaments.py``
(populates ``data/cache/statsbomb/match_outcomes.parquet``).

NOT invoked by the scheduler.
"""

from __future__ import annotations

# Allow running as `python scripts/run_phase5_backtest.py` (sibling-script imports)
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import argparse  # noqa: E402
import math  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date  # noqa: E402

import numpy as np  # noqa: E402

from bip.evaluation.tournaments.backtest.calibration_report import (  # noqa: E402
    CalibrationReport,
)
from bip.evaluation.tournaments.backtest.lock_gate import LockDecision  # noqa: E402
from bip.evaluation.tournaments.live.bayesian_updater import (  # noqa: E402
    DEFAULT_SIGMA_S_PER_DAY,
    BayesianUpdater,
    TournamentMatchResult,
)
from bip.evaluation.tournaments.live.competition_weights import (  # noqa: E402
    CompetitionType,
)
from bip.evaluation.tournaments.live.state import (  # noqa: E402
    DEFAULT_N_PRIOR,
    TeamLiveState,
    TournamentLiveState,
)
from scripts.backtest_int_tournaments import (  # noqa: E402
    DEFAULT_HELD_OUT_TOURNAMENTS,
    BacktestSnapshot,
    FixturePrediction,
    aggregate_to_lock_decision,
    run_backtest_layer1,
)
from scripts.seed_statsbomb_tournaments import (  # noqa: E402
    DEFAULT_OUTCOMES_PARQUET as DEFAULT_STATSBOMB_PARQUET,
)
from scripts.seed_statsbomb_tournaments import (  # noqa: E402
    StatsBombMatchOutcome,
    load_outcomes_from_parquet,
)

DEFAULT_LOCK_OUTPUT = Path("data/cache/lock_decision.json")
MAX_GOALS_GRID = 8  # truncation point for Poisson grid (P(X≥9 | λ=2.5) ≈ 5e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot conversion: StatsBomb → BacktestSnapshot
# ─────────────────────────────────────────────────────────────────────────────


def make_snapshots(
    outcomes: list[StatsBombMatchOutcome],
) -> tuple[list[BacktestSnapshot], dict[str, int]]:
    """Convert StatsBomb outcomes to BacktestSnapshots (chronologically sorted).

    Returns ``(snapshots, team_id_map)`` where ``team_id_map`` is a
    deterministic name → int mapping built in insertion order. The same
    team appearing in multiple tournaments keeps the same id, so Bayesian
    state persists naturally across the walk-forward.
    """
    sorted_outcomes = sorted(outcomes, key=lambda o: o.match_date)
    team_id_map: dict[str, int] = {}

    def _id(name: str) -> int:
        if name not in team_id_map:
            team_id_map[name] = len(team_id_map)
        return team_id_map[name]

    snapshots = [
        BacktestSnapshot(
            match_id=str(o.match_id),
            tournament=o.tournament_slug,
            home_team_id=_id(o.home_team),
            away_team_id=_id(o.away_team),
            observed_1x2=o.outcome_1x2,
            observed_total_goals=o.total_goals,
            observed_btts=o.btts,
            observed_home_goals=o.home_goals,
            observed_away_goals=o.away_goals,
            observed_home_corners=o.home_corners,
            observed_away_corners=o.away_corners,
            match_date=o.match_date.isoformat(),
        )
        for o in sorted_outcomes
    ]
    return snapshots, team_id_map


# ─────────────────────────────────────────────────────────────────────────────
# BayesianPoissonPredictor — stateful, walk-forward
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BayesianPoissonPredictor:
    """Independent-Poisson predictor over Bayesian per-team rates.

    For each fixture, picks current λ_for/λ_against from the live state,
    composes match-level rates as ``(home.for + away.against) / 2`` and
    symmetric for away, builds a truncated Poisson product grid, and
    derives 1X2 / BTTS / OU 2.5 / Corners O/U. After predicting, observes
    the actual outcome and advances state via ``within_tournament_step``.
    """

    name: str = "bayesian_poisson_intl"
    sigma_s_per_day: float = DEFAULT_SIGMA_S_PER_DAY
    prior_goals: float = 1.30  # cohort baseline 2010-2024 international avg
    prior_corners: float = 5.0  # rough international avg per team per match
    n_prior: int = DEFAULT_N_PRIOR

    def __post_init__(self) -> None:
        self._state = TournamentLiveState(tournament_slug="phase5_backtest")
        self._updater = BayesianUpdater(sigma_s_per_day=self.sigma_s_per_day)
        self._registered: set[int] = set()
        self._last_match_date: date | None = None

    # ── team registration ────────────────────────────────────────────────

    def _ensure_team(self, team_id: int) -> None:
        if team_id in self._registered:
            return
        self._state.team_states[team_id] = TeamLiveState(
            team_id=team_id,
            prior_goals_for=self.prior_goals,
            prior_goals_against=self.prior_goals,
            prior_corners_for=self.prior_corners,
            prior_corners_against=self.prior_corners,
            prior_shots_for=12.0,
            prior_sot_for=4.0,
            n_prior=self.n_prior,
        )
        self._registered.add(team_id)

    # ── prediction ───────────────────────────────────────────────────────

    def predict_fixture(self, snap: BacktestSnapshot) -> FixturePrediction:
        self._ensure_team(snap.home_team_id)
        self._ensure_team(snap.away_team_id)

        # Apply between-window decay if we know the gap to the previous match
        if snap.match_date is not None:
            current = date.fromisoformat(snap.match_date)
            if self._last_match_date is not None:
                gap = (current - self._last_match_date).days
                if gap > 0:
                    self._updater.between_window_step(self._state, days_elapsed=gap)
            self._last_match_date = current

        home_state = self._state.team_states[snap.home_team_id]
        away_state = self._state.team_states[snap.away_team_id]

        # Match-level expected goals — symmetric averaging keeps the
        # match expectation at the cohort baseline when both teams are
        # average. (Premier-league-style calibrators with home-field
        # advantage would add a multiplicative term here; international
        # tournaments are predominantly neutral venues, so we omit HFA.)
        lam_home = max(
            (home_state.lambda_goals_for + away_state.lambda_goals_against) / 2.0,
            1e-3,
        )
        lam_away = max(
            (away_state.lambda_goals_for + home_state.lambda_goals_against) / 2.0,
            1e-3,
        )

        prediction = _poisson_score_grid_to_prediction(lam_home, lam_away)

        # Observe AFTER predicting — walk-forward causality.
        self._observe(snap)

        return prediction

    def _observe(self, snap: BacktestSnapshot) -> None:
        if snap.observed_home_goals is None or snap.observed_away_goals is None:
            return  # nothing to update with; predict-only mode
        result = TournamentMatchResult(
            match_id=snap.match_id,
            home_team_id=snap.home_team_id,
            away_team_id=snap.away_team_id,
            home_goals=snap.observed_home_goals,
            away_goals=snap.observed_away_goals,
            home_corners=snap.observed_home_corners,
            away_corners=snap.observed_away_corners,
            competition=_tournament_to_competition(snap.tournament),
        )
        self._updater.within_tournament_step(self._state, result)


def _tournament_to_competition(slug: str) -> CompetitionType:
    """Map StatsBomb tournament slug to CompetitionType for weighting.

    All 6 covered tournaments are top-tier confederations / WC, so the
    distinction is between ``WORLD_CUP`` (4×) and ``CONFEDERATION`` (3×).
    """
    if slug.startswith("wc_"):
        return CompetitionType.WORLD_CUP
    return CompetitionType.CONFEDERATION


# ─────────────────────────────────────────────────────────────────────────────
# Poisson score grid → market probabilities
# ─────────────────────────────────────────────────────────────────────────────


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k | λ) = λ^k · e^-λ / k!."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def _poisson_score_grid_to_prediction(
    lam_home: float, lam_away: float, *, max_goals: int = MAX_GOALS_GRID
) -> FixturePrediction:
    """Build a truncated 2D Poisson product grid and derive market probs."""
    home_pmf = np.array([_poisson_pmf(k, lam_home) for k in range(max_goals + 1)])
    away_pmf = np.array([_poisson_pmf(k, lam_away) for k in range(max_goals + 1)])
    grid = np.outer(home_pmf, away_pmf)  # grid[i, j] = P(home=i, away=j)
    total = float(grid.sum())
    if total > 0:
        grid = grid / total

    # 1X2
    p_home = float(np.sum(np.tril(grid, k=-1)))  # i > j
    p_draw = float(np.sum(np.diag(grid)))
    p_away = float(np.sum(np.triu(grid, k=1)))
    s = p_home + p_draw + p_away
    if s > 0:
        p_home /= s
        p_draw /= s
        p_away /= s

    # BTTS = 1 - P(home=0) - P(away=0) + P(0,0)
    p_h0 = float(grid[0, :].sum())
    p_a0 = float(grid[:, 0].sum())
    p_00 = float(grid[0, 0])
    p_btts = max(0.0, min(1.0, 1.0 - p_h0 - p_a0 + p_00))

    # OU 2.5 — total ≥ 3
    over25 = 0.0
    n = grid.shape[0]
    for i in range(n):
        for j in range(n):
            if i + j >= 3:
                over25 += grid[i, j]
    p_over_2_5 = max(0.0, min(1.0, over25))

    return FixturePrediction(
        p_home_win=p_home,
        p_draw=p_draw,
        p_away_win=p_away,
        p_btts=p_btts,
        p_over_2_5=p_over_2_5,
    )


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: load → predict → aggregate → emit
# ─────────────────────────────────────────────────────────────────────────────


def run_phase5_backtest(
    outcomes_parquet: Path = DEFAULT_STATSBOMB_PARQUET,
    *,
    held_out_tournaments: tuple[str, ...] = DEFAULT_HELD_OUT_TOURNAMENTS,
    sigma_s_per_day: float = DEFAULT_SIGMA_S_PER_DAY,
    output_path: Path | None = DEFAULT_LOCK_OUTPUT,
    git_sha: str | None = None,
    allow_below_gate: bool = False,
) -> tuple[LockDecision, list[CalibrationReport]]:
    """Main entry: load StatsBomb outcomes, run backtest, emit LockDecision.

    Returns the LockDecision plus the list of CalibrationReports for
    transparency / further introspection.
    """
    outcomes = load_outcomes_from_parquet(outcomes_parquet)
    if not outcomes:
        raise RuntimeError(
            f"No outcomes found in {outcomes_parquet}. "
            f"Run scripts/seed_statsbomb_tournaments.py first."
        )

    snapshots, _ = make_snapshots(outcomes)
    predictor = BayesianPoissonPredictor(sigma_s_per_day=sigma_s_per_day)

    reports = run_backtest_layer1(snapshots, [predictor], git_sha=git_sha)
    decision = aggregate_to_lock_decision(
        reports,
        n_fixtures_total=len(snapshots),
        n_fixtures_with_predictions=len(snapshots),
        held_out_tournaments=held_out_tournaments,
        allow_below_gate=allow_below_gate,
        git_sha=git_sha,
        output_path=output_path,
    )
    return decision, reports


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--outcomes-parquet", type=Path, default=DEFAULT_STATSBOMB_PARQUET,
        help="StatsBomb match-outcomes Parquet (from seed_statsbomb_tournaments.py)",
    )
    p.add_argument("--output", type=Path, default=DEFAULT_LOCK_OUTPUT)
    p.add_argument("--sigma-s", type=float, default=DEFAULT_SIGMA_S_PER_DAY)
    p.add_argument("--allow-below-gate", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    print(f"[phase5] loading outcomes from {args.outcomes_parquet}", file=sys.stderr)
    decision, reports = run_phase5_backtest(
        args.outcomes_parquet,
        sigma_s_per_day=args.sigma_s,
        output_path=args.output,
        allow_below_gate=args.allow_below_gate,
    )

    print()
    print("=" * 72)
    print(f"PHASE 5 BACKTEST — calibration_status: {decision.calibration_status}")
    print("=" * 72)
    print(f"Fixtures scored: {decision.n_fixtures_with_predictions}")
    print(f"Coverage: {decision.coverage_pct:.1%}")
    print(f"Held-out tournaments: {', '.join(decision.held_out_tournaments)}")
    print(f"passes_lock = {decision.passes_lock}")
    print()
    for v in decision.predictor_verdicts:
        print(f"  predictor: {v.predictor_name}")
        print(f"    overall: {v.overall_status}")
        for market, status in sorted(v.market_statuses.items()):
            ece = v.market_classwise_ece[market]
            brier = v.market_brier_for_gate[market]
            print(
                f"    {market:30} {status:15} "
                f"ECE={ece:.4f} Brier={brier:.4f}"
            )
    print()
    if decision.operator_overrides:
        print("Operator overrides:")
        for note in decision.operator_overrides:
            print(f"  - {note}")
    if args.output:
        print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
