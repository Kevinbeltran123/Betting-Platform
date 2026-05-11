"""GSV builder smoke + derived-signal correctness tests.

The critical contract: the load-bearing derived fields
(``dominant_losing``, ``xg_vs_score_divergence``, ``tactical.home_phase``)
must be set correctly. If the builder gets these wrong, every
downstream archetype detector misfires.
"""
from __future__ import annotations

from bip.evaluation.live.engine_v3 import GSVBuilder, MarketSnapshot
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import HOME_ID, make_state


def test_gsv_builder_smoke(priors, market_snapshot):
    state = make_state()
    out = GSVBuilder().build(state, priors=priors, markets=market_snapshot)
    assert out.fixture_id == state.fixture_id
    assert out.state_version == 1
    assert out.home_team_id == state.home_team_id
    # state_version monotonically increases per-fixture
    out2 = GSVBuilder().build(state, priors=priors, markets=market_snapshot)
    assert out2.state_version == 1  # different builder


def test_gsv_builder_versions_increment_per_call():
    builder = GSVBuilder()
    state = make_state()
    priors_arg = builder.build(state, priors=__import__(
        "bip.evaluation.live.engine_v3", fromlist=["PreMatchPriors"]
    ).PreMatchPriors(), markets=MarketSnapshot())
    second = builder.build(state, priors=priors_arg.priors, markets=MarketSnapshot())
    assert second.state_version == priors_arg.state_version + 1


def test_dominant_losing_true_when_favourite_trails(priors, market_snapshot, state_napoli_scenario):
    """Home is dominant per priors (λ_home > λ_away). Home is trailing 0-1.
    Therefore dominant_losing must be True — the load-bearing predicate
    for the no-bet rule #2."""
    out = GSVBuilder().build(
        state_napoli_scenario,
        priors=priors,
        markets=market_snapshot,
    )
    assert out.score.dominant_team_id == HOME_ID
    assert out.score.dominant_losing is True
    assert out.is_dominant_losing is True


def test_xg_vs_score_divergence_positive_for_dominant_underdog(priors, market_snapshot, state_napoli_scenario):
    """At Napoli scenario: home outshoots heavily but trails. Expected
    xg_diff_for_score(-1) ≈ -0.8 → actual xg_diff is strongly positive
    → divergence very positive."""
    out = GSVBuilder().build(
        state_napoli_scenario,
        priors=priors,
        markets=market_snapshot,
    )
    # Home has 3 big_chances + 6 shots_in_box → live xG well over 1.0;
    # away has 0 big_chances + 1 sib → xG near 0.1
    assert out.xg.home_xg_total > out.xg.away_xg_total
    assert out.xg.xg_vs_score_divergence > 0.5


def test_tactical_phase_chasing_when_losing_with_pressure(priors, market_snapshot, state_napoli_scenario):
    """A dominant-losing team that's pressing hard (lots of dangerous
    attacks + key passes) should be tagged ``chasing`` or ``pressing``.
    Either qualifies — the v3 doesn't distinguish them strictly here."""
    out = GSVBuilder().build(
        state_napoli_scenario,
        priors=priors,
        markets=market_snapshot,
    )
    assert out.tactical.home_phase in ("chasing", "pressing")


def test_numerical_advantage_after_red_card(priors, market_snapshot):
    state = make_state(red_card_events=[(15, 200)])  # AWAY_ID red
    out = GSVBuilder().build(state, priors=priors, markets=market_snapshot)
    assert out.numerical.numerical_advantage == 1
    assert out.numerical.red_cards_away == 1


def test_cruise_mode_phase_late_lead(priors, market_snapshot):
    """Leader at minute 82 with 1-0 and modest shot rate should be
    tagged ``parking_bus`` or ``controlling``, enabling cruise_mode."""
    stats_home = {StatType.SHOTS_TOTAL: 10, StatType.BALL_POSSESSION: 68.0,
                  StatType.SHOTS_INSIDEBOX: 5}
    stats_away = {StatType.SHOTS_TOTAL: 8, StatType.BALL_POSSESSION: 32.0,
                  StatType.SHOTS_INSIDEBOX: 2}
    state = make_state(home_goals=1, away_goals=0, minute=82,
                       home_stats=stats_home, away_stats=stats_away)
    out = GSVBuilder().build(state, priors=priors, markets=market_snapshot)
    assert out.tactical.home_phase in ("parking_bus", "controlling")
    assert out.score.goal_diff == 1
