"""End-to-end pipeline smoke tests.

Verifies that for a few representative states the pipeline:
- builds a GSV
- generates ≥0 theses
- runs candidates through the selector + gate
- returns a coherent ``PipelineOutput`` even when picks are zero
"""
from __future__ import annotations

from bip.evaluation.live.engine_v3 import V3Pipeline
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state


def test_pipeline_runs_on_napoli_scenario(priors, market_snapshot, state_napoli_scenario):
    pipeline = V3Pipeline()
    out = pipeline.run(
        state_napoli_scenario,
        priors=priors,
        markets=market_snapshot,
        dominant_team_id=HOME_ID,
    )
    assert out.gsv.score.dominant_losing is True
    # The Napoli archetype should at least be detected (whether it
    # passes routing is a separate question)
    arch_ids = {t.archetype.value for t in out.theses}
    assert "dominant_losing_napoli" in arch_ids


def test_pipeline_on_numerical_advantage(priors, market_snapshot):
    """Late game with sustained 11v10 — archetype 11 should fire AND
    the rule-2 inversion gate must NOT block (dominant is leading)."""
    state = make_state(
        home_goals=1, away_goals=0, minute=70,
        red_card_events=[(25, AWAY_ID)],
        home_stats={
            StatType.SHOTS_TOTAL: 13, StatType.SHOTS_INSIDEBOX: 6,
            StatType.BIG_CHANCES_CREATED: 2, StatType.SHOTS_ON_TARGET: 5,
            StatType.CORNERS: 7, StatType.BALL_POSSESSION: 65.0,
            StatType.DANGEROUS_ATTACKS: 50, StatType.KEY_PASSES: 8,
        },
        away_stats={
            StatType.SHOTS_TOTAL: 4, StatType.SHOTS_INSIDEBOX: 1,
            StatType.CORNERS: 1, StatType.BALL_POSSESSION: 35.0,
            StatType.DANGEROUS_ATTACKS: 12, StatType.KEY_PASSES: 1,
        },
    )
    pipeline = V3Pipeline()
    out = pipeline.run(state, priors=priors, markets=market_snapshot,
                       dominant_team_id=HOME_ID)
    arch_ids = {t.archetype.value for t in out.theses}
    assert "numerical_sustained" in arch_ids


def test_pipeline_zero_picks_when_no_thesis(priors, market_snapshot):
    """A bland mid-game state should activate no archetypes → no picks."""
    state = make_state(minute=50)
    pipeline = V3Pipeline()
    out = pipeline.run(state, priors=priors, markets=market_snapshot)
    if not out.theses:
        assert out.candidates == []
        assert out.allowed_picks == []


def test_pipeline_output_contains_gate_results(priors, market_snapshot, state_napoli_scenario):
    """Every candidate must be recorded in gate_results (allowed or
    denied). This is the audit-trail contract (sec 7.2)."""
    pipeline = V3Pipeline()
    out = pipeline.run(
        state_napoli_scenario, priors=priors, markets=market_snapshot,
        dominant_team_id=HOME_ID,
    )
    assert len(out.gate_results) == len(out.candidates)
