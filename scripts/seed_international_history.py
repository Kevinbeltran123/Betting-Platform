"""International tournament history seed — Phase 3 Layer-2 (σ_s calibration).

Pulls 2010–2024 international tournament results (WC, Euros, Copa América,
AFCON, qualifiers) and persists them as a partitioned Parquet store so the
``BayesianUpdater.between_window_step`` σ_s parameter can be calibrated via
Held criterion C (one-step-ahead predictive log-likelihood maximization).

This is the **Layer-2** companion to Phase 3 of the WC2026 calibration spike
(see ``.planning/spikes/SPIKE-wc2026-calibration-lock.md``). Layer-1 ships
the structural refactor (3 timescale-specific updater methods, explicit
``prior_var_*`` fields, competition weights). Layer-2 — this script — is
gated ``# requires-real-data`` until the operator approves the API-Football
historical pull (≈4,000–6,000 fixtures across 14 years × 4 confederations).

Status (2026-05-08): SKELETON ONLY. The CLI / parquet writer / API client
wiring is intentionally stubbed; running the script raises
``NotImplementedError`` so it cannot silently emit empty data. The Held
criterion C sweep (``calibrate_sigma_s_held_criterion_c``) is implemented
against a generic iterable of (state_before, observed_result, days_elapsed)
tuples and is unit-testable with synthetic data.

Run when data is approved:

    uv run python scripts/seed_international_history.py \\
        --start-year 2010 --end-year 2024 \\
        --output data/cache/international_history.parquet

NOT invoked by the scheduler.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from bip.evaluation.tournaments.live.bayesian_updater import (
    BayesianUpdater,
    TournamentMatchResult,
)
from bip.evaluation.tournaments.live.state import TournamentLiveState

# ─────────────────────────────────────────────────────────────────────────────
# Parquet schema (target — see DATA model below)
# ─────────────────────────────────────────────────────────────────────────────
#
# Columns:
#   match_id           : str    — API-Football fixture id (canonical key)
#   match_date         : date
#   tournament         : str    — wc2010, wc2014, ..., euro2016, ..., copa2024
#   competition_type   : str    — CompetitionType.value (wc / qualifier / etc.)
#   home_team_id       : int    — API-Football team id
#   away_team_id       : int
#   home_team_name     : str
#   away_team_name     : str
#   home_goals         : int
#   away_goals         : int
#   home_corners       : int?   — null pre-2014 (Pro tier coverage gap)
#   away_corners       : int?
#   home_shots         : int?
#   away_shots         : int?
#   home_sot           : int?
#   away_sot           : int?
#   days_since_prev    : float  — gap between this match and prev int. match
#                                 for the home team (key for between-window σ_s)
#
# Partitioning: by tournament for fast σ_s sweep over a single tournament.

SUPPORTED_TOURNAMENTS = (
    # World Cups
    "wc2010", "wc2014", "wc2018", "wc2022",
    # Euros
    "euro2012", "euro2016", "euro2020", "euro2024",
    # Copa América
    "copa2011", "copa2015", "copa2016", "copa2019", "copa2021", "copa2024",
    # AFCON (Africa Cup of Nations)
    "afcon2012", "afcon2013", "afcon2015", "afcon2017", "afcon2019",
    "afcon2021", "afcon2023",
    # Asian Cup
    "asian2011", "asian2015", "asian2019", "asian2023",
    # Qualifiers (rolled up by year cycle)
    "wc_qual_2010_2014", "wc_qual_2014_2018",
    "wc_qual_2018_2022", "wc_qual_2022_2026",
)


# ─────────────────────────────────────────────────────────────────────────────
# Held criterion C — σ_s calibration (testable on synthetic data)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HistoricalMatchSnapshot:
    """One historical fixture + the state snapshot just before it.

    ``state_before`` is the TournamentLiveState that the updater would have
    held immediately before this match (i.e., after applying all prior matches
    in chronological order). ``days_since_prev`` is the gap between this
    match and the previous international match for either team.
    """

    state_before: TournamentLiveState
    result: TournamentMatchResult
    days_since_prev: float


def calibrate_sigma_s_held_criterion_c(
    snapshots: Iterable[HistoricalMatchSnapshot],
    sigma_candidates: list[float],
) -> tuple[float, dict[float, float]]:
    """Pick σ_s maximizing average one-step-ahead log-likelihood (Held Eq. 6).

    For each σ candidate, replay the snapshots: apply between_window_step
    with the gap, then score the actual result against the predicted Poisson
    rate (using λ = ts.lambda_goals_for + opponent.lambda_goals_against
    averaged via the standard match-rate convention). Return the σ that
    maximizes the average log-Poisson score.

    Implementation note: this is a Layer-1 reference implementation against
    the existing per-90 lambda properties; once the predictors gain a
    ``predict_match_proba(home_state, away_state)`` method, replace the
    Poisson-only scoring with the full predictive distribution from the
    chosen predictor (Bivariate Poisson recommended per SYNTHESIS Conclusion 2).
    """
    if not sigma_candidates:
        raise ValueError("sigma_candidates must not be empty")

    snapshots_list = list(snapshots)
    if not snapshots_list:
        raise ValueError("snapshots must not be empty")

    scores: dict[float, float] = {}
    for sigma in sigma_candidates:
        log_lik_total = 0.0
        n_scored = 0
        updater = BayesianUpdater(sigma_s_per_day=sigma)
        for snap in snapshots_list:
            # Clone the state so each candidate starts from the same point.
            # Layer-1 uses a shallow replay — Layer-2 should deep-copy to
            # avoid cross-σ contamination once the script wires real data.
            state = snap.state_before
            updater.between_window_step(state, days_elapsed=snap.days_since_prev)
            home_ts = state.team_states.get(snap.result.home_team_id)
            away_ts = state.team_states.get(snap.result.away_team_id)
            if home_ts is None or away_ts is None:
                continue
            lam_home = max(home_ts.lambda_goals_for, 1e-6)
            lam_away = max(away_ts.lambda_goals_for, 1e-6)
            log_lik_total += _poisson_log_pmf(snap.result.home_goals, lam_home)
            log_lik_total += _poisson_log_pmf(snap.result.away_goals, lam_away)
            n_scored += 2
        scores[sigma] = log_lik_total / n_scored if n_scored else float("-inf")

    best_sigma = max(scores, key=lambda s: scores[s])
    return best_sigma, scores


def _poisson_log_pmf(k: int, lam: float) -> float:
    """log P(K=k | λ) = k·log(λ) - λ - log(k!)."""
    if lam <= 0:
        return float("-inf")
    return k * math.log(lam) - lam - math.lgamma(k + 1)


# ─────────────────────────────────────────────────────────────────────────────
# CLI / API-Football pull (Layer-2 — gated)
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-year", type=int, default=2010)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("data/cache/international_history.parquet"),
    )
    p.add_argument(
        "--sigma-sweep",
        nargs="+",
        type=float,
        default=[0.001, 0.002, 0.005, 0.010, 0.015, 0.020, 0.030, 0.050],
        help="σ_s candidates for Held criterion C (per-day fractional volatility)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    raise NotImplementedError(
        "scripts/seed_international_history.py is Layer-2 (requires-real-data). "
        "Pulling 2010–2024 international tournaments needs operator approval — "
        "see SPIKE-wc2026-calibration-lock.md Phase 3 deadline 2026-05-22. "
        f"Args parsed OK: {args}"
    )


if __name__ == "__main__":
    main()
