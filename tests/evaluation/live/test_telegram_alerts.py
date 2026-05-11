"""Tests for telegram_alerts formatters."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bip.evaluation.live.telegram_alerts import (
    format_jornada_summary,
    format_pick_alert,
    format_pre_jornada_brief,
    send_jornada_summary,
    send_pick_alert,
)
from bip.evaluation.live.value_detector import LivePick


def _make_pick(
    *,
    home="Real Madrid", away="Barcelona", market="ou_3_5", selection="under",
    minute=25, odd=1.85, our_prob=0.78, raw_prob=0.71,
    edge_pct=18.5, stake=1.05, kelly_full=0.42,
    logical_score=0.85, components=None, flagged=None,
) -> LivePick:
    return LivePick(
        fixture_id=1, minute=minute,
        home_team=home, away_team=away,
        market=market, selection=selection,
        bookmaker_id=2, bookmaker_odd=odd,
        our_probability=our_prob,
        fair_odd=1.0 / our_prob,
        edge_pct=edge_pct,
        kelly_fraction_full=kelly_full,
        suggested_stake_pct=stake,
        snapshot_kind="live",
        flagged_reason=flagged,
        logical_score=logical_score,
        logical_components=components or {},
        confidence_half_width=0.05,
        model_probability_raw=raw_prob,
    )


class TestFormatPickAlert:
    def test_basic_fields_in_output(self):
        pick = _make_pick()
        out = format_pick_alert(pick)
        assert "Real Madrid" in out
        assert "Barcelona" in out
        assert "ou_3_5" in out
        assert "under" in out
        assert "1.85" in out
        assert "18.5" in out  # edge

    def test_score_included_when_provided(self):
        pick = _make_pick(minute=42)
        out = format_pick_alert(pick, home_score=1, away_score=0)
        assert "1-0" in out
        assert "42'" in out

    def test_score_omitted_when_not_provided(self):
        pick = _make_pick()
        out = format_pick_alert(pick)
        # No score block when not passed
        assert "Score" not in out

    def test_league_included(self):
        pick = _make_pick()
        out = format_pick_alert(pick, league_name="La Liga")
        assert "La Liga" in out

    def test_calibrated_vs_raw_shown_when_differ(self):
        pick = _make_pick(our_prob=0.78, raw_prob=0.71)
        out = format_pick_alert(pick)
        assert "Cal prob" in out
        assert "0.780" in out
        assert "0.710" in out

    def test_single_prob_when_equal(self):
        pick = _make_pick(our_prob=0.71, raw_prob=0.71)
        out = format_pick_alert(pick)
        assert "Cal prob" not in out
        assert "Prob" in out

    def test_flagged_reason_shown(self):
        pick = _make_pick(flagged="extreme_edge_no_sm_confirmation")
        out = format_pick_alert(pick)
        assert "FLAGGED" in out
        assert "extreme_edge_no_sm_confirmation" in out

    def test_no_flag_block_when_clean(self):
        pick = _make_pick(flagged=None)
        out = format_pick_alert(pick)
        assert "FLAGGED" not in out

    def test_logical_components_top2_shown(self):
        pick = _make_pick(
            components={"a": 0.9, "b": 0.7, "c": 0.5, "d": 0.3},
        )
        out = format_pick_alert(pick)
        # Top 2 by abs value should appear
        assert "a" in out
        assert "b" in out

    def test_html_escapes_special_chars_in_names(self):
        # Defensive: team names should be escaped to prevent injection
        pick = _make_pick(home="<script>alert(1)</script>", away="B")
        out = format_pick_alert(pick)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_kelly_diagnostic_field_shown(self):
        pick = _make_pick(kelly_full=0.42)
        out = format_pick_alert(pick)
        assert "0.42" in out


class TestFormatJornadaSummary:
    def test_basic_summary(self):
        out = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=487,
            n_emit_settled=425,
            n_won=270,
            profit_units=123.5,
            stake_pct_total=420.3,
        )
        assert "2026-05-13" in out
        assert "487" in out
        assert "270" in out
        # Win rate 270/425 = 63.5%
        assert "63.5" in out
        # ROI 123.5/420.3 = 29.4%
        assert "29.38" in out or "29.4" in out

    def test_top_n_block_included_when_provided(self):
        out = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=487, n_emit_settled=425, n_won=270,
            profit_units=123.5, stake_pct_total=420.3,
            top_n_stats={"n": 25, "won": 20, "profit": 15.8, "roi": 63.2},
        )
        assert "Top-N" in out
        assert "63.2" in out
        assert "15.8" in out

    def test_drops_by_reason_excludes_below_min_edge(self):
        out = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=487, n_emit_settled=425, n_won=270,
            profit_units=123.5, stake_pct_total=420.3,
            drops_by_reason={
                "below_min_edge": 200,  # excluded (too noisy)
                "market_blacklist": 18,
                "positive_side_binary_ban": 23,
                "commentary_cooloff": 12,
            },
        )
        assert "market_blacklist" in out
        assert "positive_side_binary_ban" in out
        assert "commentary_cooloff" in out
        # below_min_edge is excluded from the displayed list (count 200
        # should NOT appear). The string itself may appear in the header
        # "(excl. below_min_edge)".
        assert "200" not in out

    def test_best_market_included(self):
        out = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=487, n_emit_settled=425, n_won=270,
            profit_units=123.5, stake_pct_total=420.3,
            best_market=("ou_3_5", 10, 9, 91.0),
        )
        assert "ou_3_5" in out
        assert "9/10" in out

    def test_calibrator_block_optional(self):
        # Without calibrator metadata
        out_no_cal = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=10, n_emit_settled=8, n_won=5,
            profit_units=2.0, stake_pct_total=10.0,
        )
        assert "Calibrator" not in out_no_cal

        # With calibrator metadata
        out_cal = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=10, n_emit_settled=8, n_won=5,
            profit_units=2.0, stake_pct_total=10.0,
            calibrator_ece_cv=0.052,
            calibrator_n_markets_own_fit=11,
        )
        assert "Calibrator" in out_cal
        assert "0.052" in out_cal
        assert "11" in out_cal


class TestPreJornadaBrief:
    def test_basic(self):
        out = format_pre_jornada_brief(
            jornada_date="2026-05-13", n_fixtures=42,
        )
        assert "2026-05-13" in out
        assert "42" in out

    def test_with_profile_and_band(self):
        out = format_pre_jornada_brief(
            jornada_date="2026-05-13", n_fixtures=42,
            profile_name="aggressive",
            expected_roi_band="+40% to +60%",
        )
        assert "aggressive" in out
        assert "+40% to +60%" in out


class TestSendHelpers:
    @pytest.mark.asyncio
    async def test_send_pick_alert_invokes_bot(self):
        bot = AsyncMock()
        bot.send_html = AsyncMock()
        pick = _make_pick()
        await send_pick_alert(bot, pick, home_score=1, away_score=0)
        bot.send_html.assert_awaited_once()
        sent = bot.send_html.await_args.args[0]
        assert "Real Madrid" in sent
        assert "1-0" in sent

    @pytest.mark.asyncio
    async def test_send_jornada_summary_invokes_bot(self):
        bot = AsyncMock()
        bot.send_html = AsyncMock()
        await send_jornada_summary(
            bot,
            jornada_date="2026-05-13",
            n_emit_total=487, n_emit_settled=425, n_won=270,
            profit_units=123.5, stake_pct_total=420.3,
        )
        bot.send_html.assert_awaited_once()
