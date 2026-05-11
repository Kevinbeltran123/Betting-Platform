"""Conditional Predictor sanity tests for the Phase-1 corners+goals scaffold."""
from __future__ import annotations

from bip.evaluation.live.engine_v3 import (
    ConditionalPredictor,
    CornersPredictor,
    GameStateVector,
    Goals2HPredictor,
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
from datetime import datetime, timezone


def _gsv(*, minute: int = 60, corners_home: int = 4, corners_away: int = 2,
         game_phase: str = "open_attacking") -> GameStateVector:
    return GameStateVector(
        fixture_id=1, state_version=1,
        timestamp_utc=datetime.now(timezone.utc),
        home_team_id=100, away_team_id=200,
        score=ScoreState(home_goals=1, away_goals=1, goal_diff=0,
                         dominant_team_id=100, dominant_losing=False),
        time=TimeState(minute=minute, period="2H",
                       time_remaining_match=max(0, 90 - minute)),
        numerical=NumericalState(),
        xg=XGState(),
        flow=FlowState(),
        corners=CornerState(corners_home=corners_home, corners_away=corners_away),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(game_phase=game_phase),  # type: ignore[arg-type]
        priors=PreMatchPriors(expected_corners_total=10.4),
        markets=MarketSnapshot(),
    )


def _thesis(family: MarketFamily = MarketFamily.CORNERS,
            direction: str = "over",
            magnitude: float = 0.07) -> Thesis:
    return Thesis(
        id="T@m60", archetype=ThesisArchetype.NUMERICAL_SUSTAINED,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(family=family, direction=direction,
                                    magnitude_pp=magnitude,
                                    horizon=build_horizon("rest_of_match", 60)),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="x")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="T"),
        activated_at_minute=60,
    )


def test_corners_predictor_basic_over_line():
    pred = CornersPredictor()
    gsv = _gsv(minute=60, corners_home=4, corners_away=3)  # 7 already
    out = pred.predict(_thesis(direction="over"), "match_corners_over_10.5", gsv)
    assert out is not None
    # 7 already + Poisson expected ≈ 3.5 more → P(>=4 more) is non-trivial.
    assert 0.0 < out.p < 1.0


def test_corners_predictor_handles_no_line():
    pred = CornersPredictor()
    gsv = _gsv()
    out = pred.predict(_thesis(), "match_corners_over_bogus", gsv)
    assert out is None  # no parseable line


def test_corners_predictor_returns_none_for_wrong_family():
    pred = CornersPredictor()
    gsv = _gsv()
    out = pred.predict(_thesis(family=MarketFamily.GOALS), "match_corners_over_10.5", gsv)
    assert out is None


def test_goals_predictor_lower_p_in_cagey_phase():
    pred = Goals2HPredictor()
    cagey = _gsv(minute=80, game_phase="cagey_closed")
    open_g = _gsv(minute=80, game_phase="open_attacking")
    cagey_p = pred.predict(_thesis(family=MarketFamily.GOALS, direction="over"),
                           "match_goals_over_2.5", cagey)
    open_p = pred.predict(_thesis(family=MarketFamily.GOALS, direction="over"),
                          "match_goals_over_2.5", open_g)
    assert cagey_p is not None and open_p is not None
    # Cagey phase has 0.55× multiplier vs open → lower P(over)
    assert cagey_p.p < open_p.p


def test_composite_predictor_dispatches_by_family():
    cp = ConditionalPredictor.default()
    gsv = _gsv()
    corners = cp.predict(_thesis(family=MarketFamily.CORNERS),
                          "match_corners_over_10.5", gsv)
    goals = cp.predict(_thesis(family=MarketFamily.GOALS),
                        "match_goals_over_2.5", gsv)
    assert corners is not None
    assert goals is not None
    assert corners.family == MarketFamily.CORNERS
    assert goals.family == MarketFamily.GOALS
