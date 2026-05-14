"""GSV builder smoke + derived-signal correctness tests.

The critical contract: the load-bearing derived fields
(``dominant_losing``, ``xg_vs_score_divergence``, ``tactical.home_phase``)
must be set correctly. If the builder gets these wrong, every
downstream archetype detector misfires.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bip.evaluation.live.engine_v3 import (
    GSVBuilder,
    MarketLine,
    MarketSnapshot,
    PreMatchPriors,
)
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state


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


# ── Dominant-team-id resolution (T2 fix) ────────────────────────────────


def _markets_with_ft_1x2(home_decimal: float, away_decimal: float) -> MarketSnapshot:
    """Synthesize a MarketSnapshot carrying only the moneyline lines."""
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
        lines={
            "fulltime_result_1": MarketLine(
                market_id="fulltime_result_1",
                side_a_decimal=home_decimal,
                line_value=None,
                max_stake_cap=200.0,
                last_update_utc=now,
            ),
            "fulltime_result_2": MarketLine(
                market_id="fulltime_result_2",
                side_a_decimal=away_decimal,
                line_value=None,
                max_stake_cap=200.0,
                last_update_utc=now,
            ),
        }
    )


def test_dominant_uses_priors_when_lambda_gap_is_wide():
    """|λ_h − λ_a| ≥ 0.25 → priors win. Backward-compat with the
    legacy heuristic for clearly-favoured matches (Day-4: 28/31)."""
    priors = PreMatchPriors(
        lambda_home_prematch=1.80, lambda_away_prematch=0.90,
    )
    state = make_state()
    # Market disagrees (away favorite) but priors are clear → priors win
    markets = _markets_with_ft_1x2(home_decimal=2.50, away_decimal=1.80)
    out = GSVBuilder().build(state, priors=priors, markets=markets)
    assert out.score.dominant_team_id == HOME_ID


def test_dominant_uses_market_when_lambda_gap_is_tight():
    """|λ_h − λ_a| < 0.25 AND market disagrees → market wins.

    Day-4 empirical case: Charlotte (λ_h=1.35) vs NY City (λ_a=1.10),
    gap = 0.25 — exactly on boundary. Market had r1=r2=2.60 (no signal).
    But Espanyol (λ_h=1.19) vs Athletic (λ_a=1.28), gap = 0.09 with
    r1=2.75 r2=2.87 (home favourite). The fix flips the dominant to
    match the market for the second case.
    """
    priors = PreMatchPriors(
        lambda_home_prematch=1.19, lambda_away_prematch=1.28,
    )
    state = make_state()
    # Market clearly favors HOME (2.75 < 2.87 by enough)
    markets = _markets_with_ft_1x2(home_decimal=2.75, away_decimal=2.87)
    out = GSVBuilder().build(state, priors=priors, markets=markets)
    # Without the tiebreaker dominant would be AWAY (la > lh). With the
    # market tiebreaker, dominant flips to HOME.
    assert out.score.dominant_team_id == HOME_ID


def test_dominant_falls_back_to_priors_when_market_is_coin_flip():
    """|λ_h − λ_a| < 0.25 BUT market is dead even → priors win.

    Charlotte-NYC case: r1 == r2 → market gives no signal, so we keep
    the lambda-based pick instead of arbitrary tie-breaking."""
    priors = PreMatchPriors(
        lambda_home_prematch=1.35, lambda_away_prematch=1.10,
    )
    state = make_state()
    markets = _markets_with_ft_1x2(home_decimal=2.60, away_decimal=2.60)
    out = GSVBuilder().build(state, priors=priors, markets=markets)
    assert out.score.dominant_team_id == HOME_ID


def test_dominant_falls_back_to_priors_when_market_lines_absent():
    """No FT 1X2 lines → can't tiebreak → use priors."""
    priors = PreMatchPriors(
        lambda_home_prematch=1.27, lambda_away_prematch=1.14,
    )
    state = make_state()
    out = GSVBuilder().build(state, priors=priors, markets=MarketSnapshot())
    # 1.27 > 1.14 → home dominant
    assert out.score.dominant_team_id == HOME_ID


def test_dominant_uses_strong_elo_diff_when_available():
    """elo_diff ≥ 25 trumps both priors-λ and market signal.

    Currently always 0.0 in production but the precedence is wired so
    when the upstream feed populates elo we automatically use it.
    """
    priors = PreMatchPriors(
        lambda_home_prematch=1.10, lambda_away_prematch=1.50,
        elo_diff=120.0,  # home strongly favoured by elo
    )
    state = make_state()
    # Market also says away — both contradict elo
    markets = _markets_with_ft_1x2(home_decimal=2.50, away_decimal=1.70)
    out = GSVBuilder().build(state, priors=priors, markets=markets)
    assert out.score.dominant_team_id == HOME_ID


def test_dominant_explicit_arg_still_overrides_everything():
    """Caller-provided ``dominant_team_id`` short-circuits the heuristic
    entirely — the anti-Napoli regression suite relies on this."""
    priors = PreMatchPriors(
        lambda_home_prematch=1.80, lambda_away_prematch=0.90,
    )
    state = make_state()
    out = GSVBuilder().build(
        state, priors=priors, markets=MarketSnapshot(),
        dominant_team_id=AWAY_ID,
    )
    assert out.score.dominant_team_id == AWAY_ID
