"""No-Bet gate unit tests for rules 1, 3, 4, 5, 7, 8, 12.

Rule 2 (Napoli) gets exhaustive coverage in ``test_anti_napoli.py``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bip.evaluation.live.engine_v3 import (
    GameStateVector,
    MarketLine,
    MarketSnapshot,
    PreMatchPriors,
)
from bip.evaluation.live.engine_v3.gsv import (
    CardsState,
    CornerState,
    FlowState,
    NumericalState,
    RosterState,
    ScoreState,
    TacticalState,
    TimeState,
    XGState,
)
from bip.evaluation.live.engine_v3.market_selector import MarketCandidate
from bip.evaluation.live.engine_v3.mes import MESResult
from bip.evaluation.live.engine_v3.no_bet_gate import (
    rule_1_thesis_present,
    rule_3_critical_event_freshness,
    rule_4_line_freshness,
    rule_5_thesis_market_mismatch,
    rule_7_liquidity_gate,
    rule_8_predictive_uncertainty,
    rule_12_mes_dead_zone,
    run_gate,
)
from bip.evaluation.live.engine_v3.thesis import (
    CausalChain,
    CausalStep,
    ConditionalShift,
    GSVPredicate,
    InvalidationTrigger,
    MarketFamily,
    Thesis,
    ThesisArchetype,
    ThesisSource,
    build_horizon,
)


def _stub_gsv(*, last_event_age: float | None = None, line_age_sec: float = 10.0,
              dominant_losing: bool = False) -> GameStateVector:
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(lines={
        "match_corners_over_10.5": MarketLine(
            market_id="match_corners_over_10.5", side_a_decimal=2.0,
            max_stake_cap=500.0,
            last_update_utc=now - timedelta(seconds=line_age_sec),
        ),
    })
    return GameStateVector(
        fixture_id=1, state_version=1, timestamp_utc=now,
        home_team_id=100, away_team_id=200,
        score=ScoreState(home_goals=1, away_goals=0, goal_diff=1,
                         dominant_team_id=100, dominant_losing=dominant_losing),
        time=TimeState(minute=60, period="2H", time_remaining_match=30.0),
        numerical=NumericalState(),
        xg=XGState(),
        flow=FlowState(),
        corners=CornerState(),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(),
        priors=PreMatchPriors(),
        markets=snapshot,
        last_critical_event_age_sec=last_event_age,
    )


def _stub_candidate(score: float = 1.0, lscore: float = 1.0, cvar: float = 1.0,
                    direction: str = "over") -> MarketCandidate:
    thesis = Thesis(
        id="STUB", archetype=ThesisArchetype.NUMERICAL_SUSTAINED,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(family=MarketFamily.CORNERS, direction=direction,
                                    magnitude_pp=0.05,
                                    horizon=build_horizon("rest_of_match", 60)),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="STUB"),
        activated_at_minute=60,
    )
    return MarketCandidate(
        thesis=thesis,
        market_id="match_corners_over_10.5",
        family=MarketFamily.CORNERS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="STUB", market_id="match_corners_over_10.5",
            family=MarketFamily.CORNERS,
            base_edge=0.05, signal_clarity=1.0, book_slowness=1.0,
            liquidity_score=lscore, conditional_variance=cvar, score=score,
        ),
    )


def test_rule_1_denies_empty_theses():
    v = rule_1_thesis_present([])
    assert not v.allowed and v.rule_number == 1


def test_rule_1_passes_with_thesis():
    v = rule_1_thesis_present([_stub_candidate().thesis])
    assert v.allowed


def test_rule_3_blocks_within_90s():
    gsv = _stub_gsv(last_event_age=30.0)
    v = rule_3_critical_event_freshness(gsv)
    assert not v.allowed and v.rule_number == 3


def test_rule_3_passes_after_90s():
    gsv = _stub_gsv(last_event_age=120.0)
    assert rule_3_critical_event_freshness(gsv).allowed


def test_rule_4_blocks_stale_line():
    # Corners family threshold is 1800s by default (Sportmonks corners
    # markets refresh slowly; see no_bet_gate._LINE_MAX_AGE_BY_FAMILY).
    # Use 2000s to land genuinely past the threshold.
    gsv = _stub_gsv(line_age_sec=2000.0)
    cand = _stub_candidate()
    v = rule_4_line_freshness(cand, gsv)
    assert not v.allowed and v.rule_number == 4


def test_rule_4_family_specific_corners_threshold():
    """Corners markets get a 1800s threshold (vs btts 300s) because
    their underlying state only changes on the next corner event."""
    # 1000s on a corners market: still fresh (under 1800s threshold)
    gsv = _stub_gsv(line_age_sec=1000.0)
    cand = _stub_candidate()  # corners family
    v = rule_4_line_freshness(cand, gsv)
    assert v.allowed, "1000s on corners should pass family-specific threshold"


def test_rule_4_explicit_max_age_overrides_family_default():
    """Callers can still pass a single threshold to override the
    family-specific defaults (back-compat)."""
    gsv = _stub_gsv(line_age_sec=200.0)
    cand = _stub_candidate()
    v = rule_4_line_freshness(cand, gsv, max_age_sec=60.0)
    assert not v.allowed and v.rule_number == 4


def test_rule_5_blocks_low_mes():
    cand = _stub_candidate(score=0.3)
    v = rule_5_thesis_market_mismatch(cand)
    assert not v.allowed and v.rule_number == 5


def test_rule_5_passes_at_threshold():
    cand = _stub_candidate(score=0.7)
    v = rule_5_thesis_market_mismatch(cand)
    assert v.allowed


def test_rule_7_blocks_zero_liquidity():
    cand = _stub_candidate(lscore=0.0)
    v = rule_7_liquidity_gate(cand)
    assert not v.allowed and v.rule_number == 7


def test_rule_8_blocks_high_variance():
    cand = _stub_candidate(cvar=5.0)
    v = rule_8_predictive_uncertainty(cand)
    assert not v.allowed and v.rule_number == 8


def test_run_gate_records_all_results_including_denials():
    """Sec 7.2 requirement: every candidate is logged with verdict
    (allowed or denied + rule number + reason)."""
    gsv = _stub_gsv(last_event_age=30.0)  # rule 3 will fire
    cand = _stub_candidate()
    results = run_gate([cand.thesis], [cand], gsv)
    assert len(results) == 1
    assert not results[0].verdict.allowed
    assert results[0].verdict.rule_number == 3


# ──────────────────────────────────────────────────────────────────────
# Rule 12 — cruise_mode/goals MES dead-zone [2.5, 4.0)
# ──────────────────────────────────────────────────────────────────────


def _cruise_goals_candidate(mes_score: float) -> MarketCandidate:
    """cruise_mode archetype + GOALS family candidate at the given MES score."""
    thesis = Thesis(
        id="CRUISE",
        archetype=ThesisArchetype.CRUISE_MODE,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=MarketFamily.GOALS,
            direction="under",
            magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 60),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="CRUISE"),
        activated_at_minute=60,
    )
    return MarketCandidate(
        thesis=thesis,
        market_id="match_goals_under_2.5",
        family=MarketFamily.GOALS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="CRUISE",
            market_id="match_goals_under_2.5",
            family=MarketFamily.GOALS,
            base_edge=0.05,
            signal_clarity=1.0,
            book_slowness=1.0,
            liquidity_score=1.0,
            conditional_variance=1.0,
            score=mes_score,
        ),
    )


@pytest.mark.parametrize(
    "mes_score, expected_allowed",
    [
        (2.49, True),   # below dead-zone → rule_5 handles it; rule_12 passes
        (2.5,  False),  # exact lower boundary → deny
        (3.99, False),  # just inside dead-zone → deny
        (4.0,  True),   # exact upper boundary → allow (half-open [2.5, 4.0))
    ],
)
def test_rule_12_cruise_goals_boundaries(mes_score, expected_allowed):
    """Parametrized boundary test: 2.49 allow / 2.5 deny / 3.99 deny / 4.0 allow."""
    cand = _cruise_goals_candidate(mes_score)
    verdict = rule_12_mes_dead_zone(cand)
    assert verdict.allowed is expected_allowed
    if not expected_allowed:
        assert verdict.rule_number == 12
        assert "cruise_mode/goals MES dead-zone" in verdict.reason


def test_rule_12_control_cruise_corners_passes():
    """cruise_mode + CORNERS at score=3.0 → rule_12 is NOT triggered
    (wrong family)."""
    thesis = Thesis(
        id="CRUISE_C",
        archetype=ThesisArchetype.CRUISE_MODE,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=MarketFamily.CORNERS,
            direction="under",
            magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 60),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="CRUISE_C"),
        activated_at_minute=60,
    )
    cand = MarketCandidate(
        thesis=thesis,
        market_id="match_corners_under_10.5",
        family=MarketFamily.CORNERS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="CRUISE_C",
            market_id="match_corners_under_10.5",
            family=MarketFamily.CORNERS,
            base_edge=0.05,
            signal_clarity=1.0,
            book_slowness=1.0,
            liquidity_score=1.0,
            conditional_variance=1.0,
            score=3.0,
        ),
    )
    assert rule_12_mes_dead_zone(cand).allowed


def test_rule_12_control_non_cruise_goals_passes():
    """non-cruise archetype + GOALS at score=3.0 → rule_12 is NOT triggered
    (wrong archetype)."""
    cand = MarketCandidate(
        thesis=Thesis(
            id="OPEN",
            archetype=ThesisArchetype.OPEN_GAME_FORMATIONS,
            premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
            mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
            prediction=ConditionalShift(
                family=MarketFamily.GOALS,
                direction="over",
                magnitude_pp=0.05,
                horizon=build_horizon("rest_of_match", 60),
            ),
            invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
            confidence_prior=0.6,
            source=ThesisSource(layer="rule", identifier="OPEN"),
            activated_at_minute=60,
        ),
        market_id="match_goals_over_2.5",
        family=MarketFamily.GOALS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="OPEN",
            market_id="match_goals_over_2.5",
            family=MarketFamily.GOALS,
            base_edge=0.05,
            signal_clarity=1.0,
            book_slowness=1.0,
            liquidity_score=1.0,
            conditional_variance=1.0,
            score=3.0,
        ),
    )
    assert rule_12_mes_dead_zone(cand).allowed
