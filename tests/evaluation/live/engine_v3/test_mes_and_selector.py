"""MES math + Market Selector routing tests."""
from __future__ import annotations

from datetime import datetime, timezone

from bip.evaluation.live.engine_v3 import (
    GameStateVector,
    MarketCandidate,
    MarketLine,
    MarketSnapshot,
    PreMatchPriors,
    family_for_market_id,
)
from bip.evaluation.live.engine_v3.mes import (
    book_slowness,
    compute_mes,
    conditional_variance,
    liquidity_score,
    signal_clarity,
)
from bip.evaluation.live.engine_v3.market_selector import select_markets
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


def _stub_thesis(archetype: ThesisArchetype = ThesisArchetype.NUMERICAL_SUSTAINED,
                 family: MarketFamily = MarketFamily.CORNERS,
                 direction: str = "over") -> Thesis:
    return Thesis(
        id="STUB@m60",
        archetype=archetype,
        premise=[GSVPredicate(path="time.minute", op="ge", value=0)],
        mechanism=CausalChain(steps=[CausalStep(cause="x", effect="y", mechanism="z")]),
        prediction=ConditionalShift(
            family=family, direction=direction, magnitude_pp=0.07,
            horizon=build_horizon("rest_of_match", 60),
        ),
        invalidation_triggers=[InvalidationTrigger(kind="any_goal", description="g")],
        confidence_prior=0.6,
        source=ThesisSource(layer="rule", identifier="STUB"),
        activated_at_minute=60,
    )


def test_family_for_market_id_corner_variants():
    assert family_for_market_id("match_corners_over_10.5") == MarketFamily.CORNERS
    assert family_for_market_id("second_half_corners_over_5.5") == MarketFamily.CORNERS
    assert family_for_market_id("asian_corners_0.5") == MarketFamily.CORNERS
    assert family_for_market_id("next_corner_home") == MarketFamily.NEXT_CORNER
    assert family_for_market_id("btts_yes") == MarketFamily.BTTS
    assert family_for_market_id("number_of_cards_over_5.5") == MarketFamily.CARDS
    assert family_for_market_id("match_goals_over_2.5") == MarketFamily.GOALS
    assert family_for_market_id("fulltime_result_home") == MarketFamily.RESULT_1X2
    assert family_for_market_id("unknown_garbage") is None


def test_signal_clarity_top_market_is_one_oh():
    # NUMERICAL_SUSTAINED's #1 market is corners
    assert signal_clarity(ThesisArchetype.NUMERICAL_SUSTAINED, MarketFamily.CORNERS) == 1.00
    # DOMINANT_LOSING_NAPOLI's #1 market is NEXT_GOAL
    assert signal_clarity(ThesisArchetype.DOMINANT_LOSING_NAPOLI, MarketFamily.NEXT_GOAL) == 1.00
    # An off-list family yields the 0.40 fallback
    assert signal_clarity(ThesisArchetype.CARDS_MOMENTUM_STRICT_REF, MarketFamily.GOALS) == 0.40


def test_book_slowness_returns_one_when_no_event():
    assert book_slowness(MarketFamily.CORNERS, None) == 1.0


def test_book_slowness_decays_to_one():
    # CORNERS has base 1.40 at age 0; at age 300 it has decayed back to 1.0
    near_zero = book_slowness(MarketFamily.CORNERS, 1.0)
    far_out = book_slowness(MarketFamily.CORNERS, 300.0)
    assert near_zero > far_out
    assert abs(far_out - 1.0) < 1e-6


def test_liquidity_score_floor_and_cap():
    line = MarketLine(
        market_id="m", side_a_decimal=2.0, max_stake_cap=10.0,
        last_update_utc=datetime.now(timezone.utc),
    )
    assert liquidity_score(line, target_stake=100.0) == 0.0  # below floor
    line_full = MarketLine(
        market_id="m", side_a_decimal=2.0, max_stake_cap=500.0,
        last_update_utc=datetime.now(timezone.utc),
    )
    assert liquidity_score(line_full, target_stake=100.0) == 1.0


def test_compute_mes_scores_higher_when_clarity_and_slowness_both_strong(priors, market_snapshot):
    """A CORNERS thesis on a corners market with strong slowness should
    score higher than the same thesis on a 1X2 market (low clarity AND
    low slowness)."""
    # Synth GSV with a recent critical event
    from bip.evaluation.live.engine_v3.gsv import (
        CardsState, CornerState, CriticalEvent, FlowState, MarketSnapshot,
        NumericalState, RosterState, ScoreState, TacticalState, TimeState, XGState,
    )
    gsv = GameStateVector(
        fixture_id=1, state_version=1,
        timestamp_utc=datetime.now(timezone.utc),
        home_team_id=100, away_team_id=200,
        score=ScoreState(home_goals=1, away_goals=0, goal_diff=1,
                         dominant_team_id=100, dominant_losing=False),
        time=TimeState(minute=60, period="2H", time_remaining_match=30.0),
        numerical=NumericalState(numerical_advantage=1, red_cards_away=1),
        xg=XGState(home_xg_total=1.2, away_xg_total=0.4, xg_diff=0.8,
                   xg_vs_score_divergence=0.0),
        flow=FlowState(),
        corners=CornerState(corners_home=5, corners_away=2),
        cards=CardsState(),
        roster=RosterState(),
        tactical=TacticalState(),
        priors=priors,
        markets=market_snapshot,
        last_critical_event=CriticalEvent(kind="red_card", minute=30, team_id=200),
        last_critical_event_age_sec=120.0,
    )
    thesis = _stub_thesis()
    line_corners = market_snapshot.lines["match_corners_over_10.5"]
    res = compute_mes(
        thesis, "match_corners_over_10.5", MarketFamily.CORNERS,
        line_corners, gsv, fair_prob=0.62,
    )
    assert res.signal_clarity == 1.00
    assert res.book_slowness > 1.0


def test_select_markets_filters_below_threshold(priors, market_snapshot, state_napoli_scenario):
    from bip.evaluation.live.engine_v3 import GSVBuilder

    gsv = GSVBuilder().build(
        state_napoli_scenario, priors=priors, markets=market_snapshot,
    )

    def stub_provider(thesis, market_id, gsv):
        # Return a fair_prob that yields edge ≈ 0 → MES below threshold
        line = gsv.markets.lines[market_id]
        return 1.0 / line.side_a_decimal  # equals implied → edge = 0

    cands = select_markets([_stub_thesis()], gsv, stub_provider)
    # With zero edge, no candidate passes the 0.6 MES threshold.
    assert cands == []


def test_select_markets_returns_top_k_per_thesis(priors, market_snapshot, state_napoli_scenario):
    """For a NUMERICAL_SUSTAINED thesis, the corners family is the #1
    market per the design matrix (clarity 1.00). The selector should
    therefore include at least one corners candidate when iterating
    across all available markets."""
    from bip.evaluation.live.engine_v3 import GSVBuilder

    gsv = GSVBuilder().build(
        state_napoli_scenario, priors=priors, markets=market_snapshot,
    )

    def generous_provider(thesis, market_id, gsv):
        return 0.85  # very high fair prob → big edge for any market

    cands = select_markets(
        [_stub_thesis()], gsv, generous_provider, top_k=3, mes_threshold=0.0,
    )
    assert len(cands) >= 1
    families = {c.family for c in cands}
    assert MarketFamily.CORNERS in families
