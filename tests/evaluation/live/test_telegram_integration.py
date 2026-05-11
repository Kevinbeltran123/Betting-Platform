"""Tests for LiveAlertSender failure-safe semantics."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from bip.evaluation.live.telegram_integration import LiveAlertSender
from bip.evaluation.live.value_detector import LivePick


def _make_pick(*, edge_pct: float = 10.0, flagged: str | None = None) -> LivePick:
    return LivePick(
        fixture_id=1, minute=30,
        home_team="A", away_team="B",
        market="ou_3_5", selection="under",
        bookmaker_id=2, bookmaker_odd=1.85,
        our_probability=0.7, fair_odd=1.43,
        edge_pct=edge_pct,
        kelly_fraction_full=0.2, suggested_stake_pct=1.0,
        snapshot_kind="live", flagged_reason=flagged,
        logical_score=0.8, logical_components={},
        confidence_half_width=0.05,
        model_probability_raw=0.7,
    )


def _make_sender(bot, **kwargs) -> LiveAlertSender:
    """LiveAlertSender with throttle disabled by default (snappy tests)."""
    defaults = {"min_interval_seconds": 0.0}
    defaults.update(kwargs)
    return LiveAlertSender(bot, **defaults)


class TestSendPickSafe:
    @pytest.mark.asyncio
    async def test_send_succeeds_above_threshold(self):
        bot = AsyncMock()
        sender = _make_sender(bot, min_edge_pct_for_alert=5.0)
        pick = _make_pick(edge_pct=10.0)
        result = await sender.send_pick_safe(pick)
        assert result is True
        assert sender.n_sent == 1
        assert sender.n_skipped == 0
        bot.send_html.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skip_below_threshold(self):
        bot = AsyncMock()
        sender = _make_sender(bot, min_edge_pct_for_alert=10.0)
        pick = _make_pick(edge_pct=5.0)
        result = await sender.send_pick_safe(pick)
        assert result is False
        assert sender.n_skipped == 1
        bot.send_html.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_flagged_when_enabled(self):
        bot = AsyncMock()
        sender = _make_sender(bot, skip_flagged=True)
        pick = _make_pick(edge_pct=10.0, flagged="extreme_edge_no_sm_confirmation")
        result = await sender.send_pick_safe(pick)
        assert result is False
        assert sender.n_skipped == 1

    @pytest.mark.asyncio
    async def test_send_flagged_when_disabled(self):
        bot = AsyncMock()
        sender = _make_sender(bot, skip_flagged=False)
        pick = _make_pick(edge_pct=10.0, flagged="some_flag")
        result = await sender.send_pick_safe(pick)
        assert result is True
        bot.send_html.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_swallows_exception_from_bot(self):
        bot = AsyncMock()
        bot.send_html.side_effect = RuntimeError("network down")
        sender = _make_sender(bot)
        pick = _make_pick(edge_pct=10.0)
        result = await sender.send_pick_safe(pick)
        assert result is False
        assert sender.n_failed == 1
        # NB: no exception propagated

    @pytest.mark.asyncio
    async def test_throttle_enforces_interval(self):
        bot = AsyncMock()
        sender = _make_sender(bot, min_interval_seconds=0.1)
        pick = _make_pick(edge_pct=10.0)
        t0 = asyncio.get_event_loop().time()
        await sender.send_pick_safe(pick)
        await sender.send_pick_safe(pick)
        elapsed = asyncio.get_event_loop().time() - t0
        # Second send should have waited at least the interval
        assert elapsed >= 0.1
        assert sender.n_sent == 2


class TestBriefAndSummary:
    @pytest.mark.asyncio
    async def test_send_brief_safe_success(self):
        bot = AsyncMock()
        sender = _make_sender(bot)
        ok = await sender.send_brief_safe(
            jornada_date="2026-05-13", n_fixtures=10,
        )
        assert ok is True
        bot.send_html.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_brief_safe_failure(self):
        bot = AsyncMock()
        bot.send_html.side_effect = RuntimeError("API timeout")
        sender = _make_sender(bot)
        ok = await sender.send_brief_safe(
            jornada_date="2026-05-13", n_fixtures=10,
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_send_summary_safe_success(self):
        bot = AsyncMock()
        sender = _make_sender(bot)
        ok = await sender.send_summary_safe(
            jornada_date="2026-05-13",
            n_emit_total=100, n_emit_settled=80, n_won=50,
            profit_units=10.0, stake_pct_total=50.0,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_send_summary_safe_failure(self):
        bot = AsyncMock()
        bot.send_html.side_effect = RuntimeError("502 bad gateway")
        sender = _make_sender(bot)
        ok = await sender.send_summary_safe(
            jornada_date="2026-05-13",
            n_emit_total=100, n_emit_settled=80, n_won=50,
            profit_units=10.0, stake_pct_total=50.0,
        )
        assert ok is False


class TestFromEnv:
    @pytest.mark.asyncio
    async def test_returns_none_when_token_missing(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-1001234567890")
        result = await LiveAlertSender.from_env()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_channel_missing(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.delenv("TELEGRAM_CHANNEL_ID", raising=False)
        result = await LiveAlertSender.from_env()
        assert result is None


class TestContextManager:
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        bot = AsyncMock()
        sender = _make_sender(bot)
        async with sender as s:
            assert s is sender

    @pytest.mark.asyncio
    async def test_aexit_shuts_down_bot(self):
        bot = AsyncMock()
        sender = _make_sender(bot)
        async with sender:
            pass
        bot.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_swallows_shutdown_errors(self):
        bot = AsyncMock()
        bot.shutdown.side_effect = RuntimeError("cleanup failed")
        sender = _make_sender(bot)
        # Should not raise
        async with sender:
            pass
