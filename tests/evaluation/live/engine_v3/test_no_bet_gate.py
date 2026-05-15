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
    GateResult,
)
from bip.evaluation.live.engine_v3.mes import _squashed_goals_cvar
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


# ──────────────────────────────────────────────────────────────────────
# Rule 8 shadow path — horizon-squashed GOALS cvar at HT
# ──────────────────────────────────────────────────────────────────────


def _make_goals_candidate_with_cvar(cvar: float) -> MarketCandidate:
    """GOALS candidate with the given conditional_variance."""
    thesis = Thesis(
        id="GOALS_SHADOW",
        archetype=ThesisArchetype.OPEN_GAME_FORMATIONS,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=MarketFamily.GOALS,
            direction="over",
            magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 40),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="GOALS_SHADOW"),
        activated_at_minute=45,
    )
    return MarketCandidate(
        thesis=thesis,
        market_id="match_goals_over_2.5",
        family=MarketFamily.GOALS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="GOALS_SHADOW",
            market_id="match_goals_over_2.5",
            family=MarketFamily.GOALS,
            base_edge=0.05,
            signal_clarity=1.0,
            book_slowness=1.0,
            liquidity_score=1.0,
            conditional_variance=cvar,
            score=1.0,
        ),
    )


def _stub_gsv_with_minute(minute: int) -> GameStateVector:
    """_stub_gsv with a configurable minute."""
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(lines={
        "match_goals_over_2.5": MarketLine(
            market_id="match_goals_over_2.5", side_a_decimal=2.0,
            max_stake_cap=500.0,
            last_update_utc=now - timedelta(seconds=10),
        ),
    })
    return GameStateVector(
        fixture_id=99, state_version=1, timestamp_utc=now,
        home_team_id=100, away_team_id=200,
        score=ScoreState(home_goals=1, away_goals=1, goal_diff=0, dominant_team_id=100),
        time=TimeState(minute=minute, period="2H" if minute > 45 else "1H", time_remaining_match=float(90 - minute)),
        numerical=NumericalState(),
        xg=XGState(),
        flow=FlowState(),
        corners=CornerState(),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(),
        priors=PreMatchPriors(),
        markets=snapshot,
        last_critical_event_age_sec=None,
    )


def test_rule_8_shadow_goals_ht_allowed_shadow_recorded(tmp_path):
    """GOALS candidate at minute 48 with raw cvar > band but squashed <= band:
    candidate PASSES (shadow-only) and shadow denial row is recorded."""
    from bip.evaluation.live.engine_v3.shadow_logger import ShadowLogger

    # raw_cvar=1.1, band=0.08*10=0.8 → raw > band
    # squashed = 1.1/(1+1.1) ≈ 0.524 < 0.8 → squashed passes → shadow
    raw_cvar = 1.1
    assert raw_cvar > 0.08 * 10, "Precondition: raw must exceed band"
    assert _squashed_goals_cvar(raw_cvar) <= 0.08 * 10, "Precondition: squashed must pass"

    cand = _make_goals_candidate_with_cvar(raw_cvar)
    gsv = _stub_gsv_with_minute(48)
    shadow_log = ShadowLogger(output_root=tmp_path)
    verdict = rule_8_predictive_uncertainty(
        cand,
        gsv=gsv,
        shadow_logger=shadow_log,
        fixture_id=gsv.fixture_id,
        ts=gsv.timestamp_utc,
    )
    # Candidate PASSES (shadow-only)
    assert verdict.allowed is True
    # Shadow denial recorded
    assert shadow_log.buffer_size()[1] == 1, "Expected 1 shadow denial in buffer"


def test_rule_8_pre_min40_goals_still_denied(tmp_path):
    """GOALS candidate BEFORE minute 40 with raw cvar > band:
    shadow path does NOT apply — candidate is REALLY denied."""
    from bip.evaluation.live.engine_v3.shadow_logger import ShadowLogger

    raw_cvar = 1.1  # > 0.8 band
    cand = _make_goals_candidate_with_cvar(raw_cvar)
    gsv = _stub_gsv_with_minute(35)  # < 40 → no shadow
    shadow_log = ShadowLogger(output_root=tmp_path)
    verdict = rule_8_predictive_uncertainty(
        cand,
        gsv=gsv,
        shadow_logger=shadow_log,
        fixture_id=gsv.fixture_id,
        ts=gsv.timestamp_utc,
    )
    assert verdict.allowed is False
    assert verdict.rule_number == 8
    # No shadow row (real deny)
    assert shadow_log.buffer_size()[1] == 0


def test_rule_8_mes_score_regression_unchanged():
    """Regression test (constraint #2): an unrelated GOALS candidate's
    mes.score is identical before and after this task's changes.

    The enforced MES math must be byte-for-byte unchanged. We verify by
    computing mes.score directly via compute_mes and checking the raw
    conditional_variance matches the expected formula.

    compute_mes: score = (base_edge * clarity * slowness * liq) / cvar / 0.1
    With λ_total=2.5, horizon=45: raw_cvar = max(0.5, 2.5*45/90) = 1.25
    """
    from bip.evaluation.live.engine_v3.mes import compute_mes

    now = datetime.now(timezone.utc)
    markets = MarketSnapshot(lines={
        "match_goals_over_2.5": MarketLine(
            market_id="match_goals_over_2.5", side_a_decimal=2.0,
            max_stake_cap=1.0,  # Phase-1 placeholder → liquidity_score=1.0
            last_update_utc=now,
        ),
    })
    gsv = GameStateVector(
        fixture_id=42, state_version=1, timestamp_utc=now,
        home_team_id=1, away_team_id=2,
        score=ScoreState(home_goals=1, away_goals=0, goal_diff=1, dominant_team_id=1),
        time=TimeState(minute=45, period="1H", time_remaining_match=45.0),
        numerical=NumericalState(),
        xg=XGState(),
        flow=FlowState(),
        corners=CornerState(),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(),
        priors=PreMatchPriors(lambda_home_prematch=1.35, lambda_away_prematch=1.15),
        markets=markets,
    )
    thesis = Thesis(
        id="REGRESSION",
        archetype=ThesisArchetype.OPEN_GAME_FORMATIONS,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=MarketFamily.GOALS, direction="over", magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 45),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="REGRESSION"),
        activated_at_minute=45,
    )
    line = markets.lines["match_goals_over_2.5"]
    result = compute_mes(
        thesis, "match_goals_over_2.5", MarketFamily.GOALS, line, gsv,
        fair_prob=0.55,
    )
    # λ_total=2.5, horizon=45: raw_cvar = max(0.5, 2.5*45/90) = 1.25
    expected_cvar = max(0.5, 2.5 * 45 / 90.0)
    assert result.conditional_variance == pytest.approx(expected_cvar), (
        f"conditional_variance must be RAW formula (constraint #2): "
        f"expected {expected_cvar}, got {result.conditional_variance}"
    )
    # Verify the squash helper produces a DIFFERENT value (i.e., not equal to raw)
    squashed = _squashed_goals_cvar(result.conditional_variance)
    assert result.conditional_variance != pytest.approx(squashed), (
        "conditional_variance must be RAW (not squashed) — constraint #2"
    )


# ── Task 5: shadow_dominant_team_id + rule_11 napoli exemption ──────────────


def _make_goals_candidate(
    *,
    mes_score: float = 0.7,
    archetype: ThesisArchetype = ThesisArchetype.OPEN_GAME_FORMATIONS,
) -> MarketCandidate:
    """GOALS candidate with configurable mes_score and archetype."""
    thesis = Thesis(
        id="T-GOALS",
        archetype=archetype,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=MarketFamily.GOALS,
            direction="over",
            magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 45),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="T-GOALS"),
        activated_at_minute=45,
    )
    return MarketCandidate(
        thesis=thesis,
        market_id="match_goals_over_2.5",
        family=MarketFamily.GOALS,
        fair_prob=0.6,
        mes=MESResult(
            thesis_id="T-GOALS",
            market_id="match_goals_over_2.5",
            family=MarketFamily.GOALS,
            base_edge=0.05,
            signal_clarity=1.0,
            book_slowness=1.0,
            liquidity_score=1.0,
            conditional_variance=0.5,
            score=mes_score,
        ),
    )


def _make_drift_monitor_drifted(family: MarketFamily, minute: int = 60):
    """Return a CalibrationDriftMonitor whose cell for (family, minute) is drifted.

    We feed enough observations with predicted_p=0.9 but outcome=0 to make
    the KS test register drift (empirical WR much lower than predicted).
    Default minute=60 matches the _stub_gsv() time.minute=60 bucket.
    """
    from bip.evaluation.live.engine_v3.drift_monitor import CalibrationDriftMonitor

    monitor = CalibrationDriftMonitor()
    # Need ≥30 obs to warm (default min_observations=30). Use 35 with strong
    # signal: predicted 90% but lose every one → KS drift detected.
    for _ in range(35):
        monitor.observe(family=family, minute=minute, predicted_p=0.9, outcome=0)
    return monitor


def _make_thesis_for_archetype(archetype: ThesisArchetype, family: MarketFamily = MarketFamily.GOALS) -> Thesis:
    return Thesis(
        id="T-TEST",
        archetype=archetype,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=family, direction="over", magnitude_pp=0.05,
            horizon=build_horizon("rest_of_match", 45),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="T-TEST"),
        activated_at_minute=45,
    )


def test_shadow_dominant_team_id_field_in_model_dump():
    """GSV exposes shadow_dominant_team_id and it appears in model_dump."""
    gsv = _stub_gsv()
    dumped = gsv.model_dump()
    assert "shadow_dominant_team_id" in dumped, (
        "shadow_dominant_team_id must be serialized by model_dump"
    )
    # Default is None (backward-compatible with existing parquet readers)
    assert dumped["shadow_dominant_team_id"] is None


def test_shadow_dominant_team_id_can_be_set():
    """shadow_dominant_team_id accepts an int team id."""
    now = datetime.now(timezone.utc)
    gsv = GameStateVector(
        fixture_id=999,
        state_version=1,
        timestamp_utc=now,
        home_team_id=10,
        away_team_id=20,
        score=ScoreState(home_goals=0, away_goals=0, goal_diff=0),
        time=TimeState(minute=45, period="1H"),
        numerical=NumericalState(),
        xg=XGState(),
        flow=FlowState(),
        corners=CornerState(),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(),
        priors=PreMatchPriors(lambda_home_prematch=1.35, lambda_away_prematch=1.15),
        markets=MarketSnapshot(),
        shadow_dominant_team_id=10,
    )
    assert gsv.shadow_dominant_team_id == 10
    dumped = gsv.model_dump()
    assert dumped["shadow_dominant_team_id"] == 10


def test_rule_11_napoli_exemption_with_drifted_monitor():
    """DOMINANT_LOSING_NAPOLI candidate passes rule_11 even when monitor is drifted.

    This guards the forensic insight: napoli is graded on P/L (+96u/14 Day-3),
    not win rate — so the win-rate-derived KS drift gate must not block it.
    """
    from bip.evaluation.live.engine_v3.no_bet_gate import rule_11_calibration_drift

    gsv = _stub_gsv()  # minute=60, bucket "60-75"
    monitor = _make_drift_monitor_drifted(MarketFamily.GOALS, minute=60)
    # Confirm monitor is actually drifted for this cell
    status = monitor.status(MarketFamily.GOALS, gsv.time.minute)
    assert status.is_warm and status.is_drifted, (
        "Test precondition failed: drift monitor not drifted after 25 observations"
    )

    cand = _make_goals_candidate(mes_score=0.7, archetype=ThesisArchetype.DOMINANT_LOSING_NAPOLI)

    verdict = rule_11_calibration_drift(cand, gsv, monitor)
    assert verdict.allowed, (
        "DOMINANT_LOSING_NAPOLI must be exempt from rule_11 drift gate"
    )


def test_rule_11_non_napoli_still_denied_when_drifted():
    """Non-napoli candidates are still denied by rule_11 when the cell is drifted."""
    from bip.evaluation.live.engine_v3.no_bet_gate import rule_11_calibration_drift

    gsv = _stub_gsv()  # minute=60, bucket "60-75"
    monitor = _make_drift_monitor_drifted(MarketFamily.GOALS, minute=60)
    status = monitor.status(MarketFamily.GOALS, gsv.time.minute)
    assert status.is_warm and status.is_drifted, (
        "Test precondition: drift monitor must be drifted"
    )

    # A non-napoli archetype — open_game_formations
    cand = _make_goals_candidate(mes_score=0.7, archetype=ThesisArchetype.OPEN_GAME_FORMATIONS)
    verdict = rule_11_calibration_drift(cand, gsv, monitor)
    assert not verdict.allowed
    assert verdict.rule_number == 11
