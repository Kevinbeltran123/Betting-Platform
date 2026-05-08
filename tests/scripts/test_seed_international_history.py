"""Tests for scripts/seed_international_history.py (Phase 3 σ_s calibrator).

Layer-1 only: validates the Held criterion C calibrator on synthetic data
so the harness ships unit-tested even before the 2010–2024 international
fixtures are loaded. The full backtest pull is gated `# requires-real-data`.
"""

from __future__ import annotations

import pytest

from bip.evaluation.tournaments.live.bayesian_updater import (
    TournamentMatchResult,
)
from bip.evaluation.tournaments.live.state import (
    TeamLiveState,
    TournamentLiveState,
)

# Direct import from the script (the script-as-module pattern used elsewhere
# in tests/scripts/). PYTHONPATH includes scripts/ via pyproject pytest config.
from scripts.seed_international_history import (
    HistoricalMatchSnapshot,
    _poisson_log_pmf,
    calibrate_sigma_s_held_criterion_c,
)


def _team(team_id: int, lam: float) -> TeamLiveState:
    return TeamLiveState(
        team_id=team_id,
        prior_goals_for=lam,
        prior_goals_against=lam,
        prior_corners_for=5.0,
        prior_corners_against=5.0,
        prior_shots_for=12.0,
        prior_sot_for=4.0,
    )


def _state_with(home_lam: float, away_lam: float) -> TournamentLiveState:
    return TournamentLiveState(
        tournament_slug="synth",
        team_states={
            1: _team(1, home_lam),
            2: _team(2, away_lam),
        },
    )


def _snapshot(
    home_goals: int,
    away_goals: int,
    home_lam: float = 1.5,
    away_lam: float = 1.5,
    days: float = 60.0,
) -> HistoricalMatchSnapshot:
    return HistoricalMatchSnapshot(
        state_before=_state_with(home_lam, away_lam),
        result=TournamentMatchResult(
            match_id=f"m_{home_goals}_{away_goals}",
            home_team_id=1,
            away_team_id=2,
            home_goals=home_goals,
            away_goals=away_goals,
        ),
        days_since_prev=days,
    )


def test_poisson_log_pmf_matches_known_value() -> None:
    # Poisson(λ=2) at k=1: log(2·exp(-2)) = log(2) - 2
    import math
    assert _poisson_log_pmf(1, 2.0) == pytest.approx(math.log(2.0) - 2.0)


def test_poisson_log_pmf_zero_lambda_is_neg_inf() -> None:
    assert _poisson_log_pmf(0, 0.0) == float("-inf")


def test_calibrator_rejects_empty_candidates() -> None:
    snaps = [_snapshot(1, 1)]
    with pytest.raises(ValueError, match="sigma_candidates"):
        calibrate_sigma_s_held_criterion_c(snaps, sigma_candidates=[])


def test_calibrator_rejects_empty_snapshots() -> None:
    with pytest.raises(ValueError, match="snapshots"):
        calibrate_sigma_s_held_criterion_c(
            [], sigma_candidates=[0.001, 0.005]
        )


def test_calibrator_returns_best_from_sweep() -> None:
    """Sweep returns the σ with maximum avg log-likelihood across snapshots."""
    snapshots = [_snapshot(1, 1), _snapshot(2, 1), _snapshot(0, 2)]
    candidates = [0.001, 0.010, 0.050]
    best, scores = calibrate_sigma_s_held_criterion_c(snapshots, candidates)

    assert best in candidates
    assert set(scores.keys()) == set(candidates)
    # The chosen σ has the highest score
    assert scores[best] == max(scores.values())


def test_calibrator_score_dict_complete() -> None:
    snapshots = [_snapshot(1, 1)]
    candidates = [0.001, 0.005, 0.010, 0.020]
    _, scores = calibrate_sigma_s_held_criterion_c(snapshots, candidates)
    assert all(c in scores for c in candidates)
    assert all(score > float("-inf") for score in scores.values())


def test_calibrator_skips_missing_team_in_snapshot() -> None:
    """Snapshot whose teams aren't in state_before is silently skipped."""
    valid_snap = _snapshot(1, 1)
    orphan_snap = HistoricalMatchSnapshot(
        state_before=TournamentLiveState(tournament_slug="empty"),
        result=TournamentMatchResult(
            match_id="orphan",
            home_team_id=999,
            away_team_id=998,
            home_goals=2,
            away_goals=0,
        ),
        days_since_prev=30.0,
    )
    best, scores = calibrate_sigma_s_held_criterion_c(
        [valid_snap, orphan_snap], sigma_candidates=[0.005, 0.010]
    )
    # No crash; best is well-defined
    assert best in {0.005, 0.010}


@pytest.mark.xfail(reason="requires-real-data: 2010–2024 int. tournament Parquet store")
def test_calibrator_on_real_2010_2024_results() -> None:
    """Layer-2: real σ_s sweep over 4,000+ historical fixtures.

    Unblocked when scripts/seed_international_history.py is approved
    and the API-Football pull has populated
    data/cache/international_history.parquet.
    """
    raise NotImplementedError(
        "Run after `uv run python scripts/seed_international_history.py "
        "--start-year 2010 --end-year 2024`"
    )
