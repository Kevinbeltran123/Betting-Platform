"""Tests for BayesianUpdater and TournamentLiveState."""

from __future__ import annotations

import json

import pytest

from bip.evaluation.tournaments.live.bayesian_updater import (
    BayesianUpdater,
    TournamentMatchResult,
)
from bip.evaluation.tournaments.live.state import (
    DEFAULT_N_PRIOR,
    TeamLiveState,
    TournamentLiveState,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_team(team_id: int, goals_for: float = 1.8) -> TeamLiveState:
    return TeamLiveState(
        team_id=team_id,
        prior_goals_for=goals_for,
        prior_goals_against=1.2,
        prior_corners_for=5.0,
        prior_corners_against=4.5,
        prior_shots_for=12.0,
        prior_sot_for=4.0,
    )


def _make_state(*team_ids: int) -> TournamentLiveState:
    state = TournamentLiveState(tournament_slug="test_tournament")
    for tid in team_ids:
        state.team_states[tid] = _make_team(tid)
    return state


def _result(
    match_id: str = "m001",
    home: int = 1,
    away: int = 2,
    hg: int = 2,
    ag: int = 1,
    **kwargs,
) -> TournamentMatchResult:
    return TournamentMatchResult(
        match_id=match_id,
        home_team_id=home,
        away_team_id=away,
        home_goals=hg,
        away_goals=ag,
        **kwargs,
    )


# ── Prior passthrough ─────────────────────────────────────────────────────────


def test_lambda_equals_prior_before_any_match() -> None:
    state = _make_state(1)
    ts = state.team_states[1]
    assert ts.lambda_goals_for == pytest.approx(1.8)
    assert ts.n_matches_played == 0


# ── Bayesian blend after one match ───────────────────────────────────────────


def test_lambda_blends_toward_observation_after_one_match() -> None:
    state = _make_state(1, 2)
    updater = BayesianUpdater()
    updater.update(state, _result(hg=4, ag=0))

    ts1 = state.team_states[1]
    # λ_new = (10 * 1.8 + 4) / (10 + 1) ≈ 2.0
    expected = (DEFAULT_N_PRIOR * 1.8 + 4) / (DEFAULT_N_PRIOR + 1)
    assert ts1.lambda_goals_for == pytest.approx(expected)
    assert ts1.n_matches_played == 1


def test_lambda_goals_against_updated_correctly() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(hg=2, ag=3))

    ts1 = state.team_states[1]
    # home conceded 3
    expected = (DEFAULT_N_PRIOR * 1.2 + 3) / (DEFAULT_N_PRIOR + 1)
    assert ts1.lambda_goals_against == pytest.approx(expected)


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_same_match_id_not_double_counted() -> None:
    state = _make_state(1, 2)
    updater = BayesianUpdater()
    result = _result(hg=2, ag=1)

    updater.update(state, result)
    updater.update(state, result)  # second call → no-op

    assert state.team_states[1].n_matches_played == 1
    assert len(state.completed_match_ids) == 1


# ── Corners and optional stats ────────────────────────────────────────────────


def test_corners_accumulated_when_provided() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(
        state,
        _result(home_corners=7, away_corners=4),
    )
    assert state.team_states[1].obs_corners_for == 7.0
    assert state.team_states[2].obs_corners_for == 4.0


def test_corners_not_updated_when_none() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result())  # no corners supplied
    assert state.team_states[1].obs_corners_for == 0.0


# ── Player events ─────────────────────────────────────────────────────────────


def test_injury_added_to_injured_list() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(injured_home=(99,)))
    assert 99 in state.team_states[1].injured_player_ids


def test_yellow_card_tracked() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(yellow_home=(10,)))
    assert state.team_states[1].yellow_cards[10] == 1
    assert 10 not in state.team_states[1].suspended_player_ids


def test_two_yellows_trigger_suspension() -> None:
    state = _make_state(1, 2)
    updater = BayesianUpdater()
    updater.update(state, _result(match_id="m1", yellow_home=(10,)))
    updater.update(state, _result(match_id="m2", yellow_home=(10,)))
    assert 10 in state.team_states[1].suspended_player_ids


def test_red_card_triggers_suspension_immediately() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(red_home=(77,)))
    assert 77 in state.team_states[1].suspended_player_ids


# ── Wipe group-stage bookings ─────────────────────────────────────────────────


def test_wipe_clears_yellows_and_suspensions() -> None:
    state = _make_state(1, 2)
    updater = BayesianUpdater()
    updater.update(state, _result(yellow_home=(10,), red_home=(20,)))
    updater.wipe_group_stage_bookings(state)

    ts = state.team_states[1]
    assert ts.yellow_cards == {}
    assert ts.suspended_player_ids == []


# ── Suspension risk ───────────────────────────────────────────────────────────


def test_suspension_risk_identifies_one_yellow_players() -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(yellow_home=(10, 20)))
    risk = state.team_states[1].suspension_risk_ids()
    assert set(risk) == {10, 20}


# ── JSON round-trip ───────────────────────────────────────────────────────────


def test_save_load_round_trip(tmp_path) -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(hg=3, ag=1, yellow_home=(55,)))

    path = tmp_path / "state.json"
    state.save(path)
    loaded = TournamentLiveState.load(path)

    ts = loaded.team_states[1]
    assert ts.n_matches_played == 1
    assert ts.obs_goals_for == 3.0
    assert ts.yellow_cards == {55: 1}
    assert loaded.completed_match_ids == ["m001"]


def test_yellow_card_keys_are_ints_after_load(tmp_path) -> None:
    state = _make_state(1, 2)
    BayesianUpdater().update(state, _result(yellow_home=(42,)))

    path = tmp_path / "state.json"
    state.save(path)
    loaded = TournamentLiveState.load(path)

    keys = list(loaded.team_states[1].yellow_cards.keys())
    assert all(isinstance(k, int) for k in keys)
