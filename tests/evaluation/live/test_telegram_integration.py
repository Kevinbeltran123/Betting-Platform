"""Tests for LiveAlertSender failure-safe semantics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bip.evaluation.live.pick_tracker import PickTracker
from bip.evaluation.live.telegram_integration import LiveAlertSender
from bip.evaluation.live.telegram_state import Role, TelegramState
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


# ── V2: state-aware features ────────────────────────────────────────────────


def _bot_returning(message_id: int = 1000) -> AsyncMock:
    """Build a bot mock whose send_html returns a fake message_id."""
    bot = AsyncMock()
    bot.send_html = AsyncMock(return_value=message_id)
    bot.channel_id = "-100PRIMARY"
    return bot


@pytest.fixture
def state_and_db(tmp_path: Path):
    db_path = tmp_path / "picks.db"
    PickTracker(db_path=db_path)
    return TelegramState(db_path=db_path), db_path


def _make_tier1_pick() -> LivePick:
    return LivePick(
        fixture_id=1, minute=30,
        home_team="A", away_team="B",
        market="ou_3_5", selection="under",
        bookmaker_id=2, bookmaker_odd=1.85,
        our_probability=0.7, fair_odd=1.43,
        edge_pct=15.0,
        kelly_fraction_full=0.2, suggested_stake_pct=1.0,
        snapshot_kind="live", flagged_reason=None,
        logical_score=0.90, logical_components={},
        confidence_half_width=0.05,
        model_probability_raw=0.7,
    )


def _make_tier3_pick() -> LivePick:
    return LivePick(
        fixture_id=2, minute=30,
        home_team="C", away_team="D",
        market="btts", selection="yes",
        bookmaker_id=2, bookmaker_odd=2.10,
        our_probability=0.55, fair_odd=1.82,
        edge_pct=10.0,
        kelly_fraction_full=0.1, suggested_stake_pct=0.5,
        snapshot_kind="live", flagged_reason="extreme_edge_no_sm_confirmation",
        logical_score=0.65, logical_components={},
        confidence_half_width=0.05,
        model_probability_raw=0.55,
    )


class TestStateAware:
    @pytest.mark.asyncio
    async def test_message_id_recorded_when_pick_id_supplied(
        self, state_and_db,
    ):
        state, _ = state_and_db
        bot = _bot_returning(message_id=12345)
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            min_edge_pct_for_alert=5.0,
        )
        ok = await sender.send_pick_safe(
            _make_tier1_pick(), pick_id=42,
        )
        assert ok is True
        ref = state.find_message(pick_id=42, role=Role.PICK)
        assert ref is not None
        assert ref.message_id == 12345
        assert ref.tier == 1

    @pytest.mark.asyncio
    async def test_no_state_no_keyboard(self):
        """Backwards-compat: caller without state/pick_id gets v1 behavior."""
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0,
            min_edge_pct_for_alert=5.0,
        )
        await sender.send_pick_safe(_make_tier1_pick())
        # send_html called WITHOUT reply_markup
        call = bot.send_html.await_args
        assert call.kwargs.get("reply_markup") is None

    @pytest.mark.asyncio
    async def test_keyboard_attached_when_state_and_pick_id(
        self, state_and_db,
    ):
        state, _ = state_and_db
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            min_edge_pct_for_alert=5.0,
        )
        await sender.send_pick_safe(_make_tier1_pick(), pick_id=99)
        call = bot.send_html.await_args
        markup = call.kwargs.get("reply_markup")
        assert markup is not None
        # Decode the first PLACE button's callback_data
        buttons = markup.inline_keyboard[0]
        assert any(
            b.callback_data.startswith("v1:place:99")
            for b in buttons
        )


class TestTierRouting:
    @pytest.mark.asyncio
    async def test_tier3_routes_to_diag_when_configured(
        self, state_and_db,
    ):
        state, _ = state_and_db
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            skip_flagged=False,   # need to allow flagged through to test Tier 3
            min_edge_pct_for_alert=5.0,
            diag_channel_id="-100DIAG",
        )
        await sender.send_pick_safe(_make_tier3_pick(), pick_id=7)
        call = bot.send_html.await_args
        assert call.kwargs.get("chat_id") == "-100DIAG"
        assert call.kwargs.get("disable_notification") is True

    @pytest.mark.asyncio
    async def test_tier3_falls_back_to_primary_when_no_diag(
        self, state_and_db,
    ):
        state, _ = state_and_db
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            skip_flagged=False,
            min_edge_pct_for_alert=5.0,
            diag_channel_id=None,
        )
        await sender.send_pick_safe(_make_tier3_pick(), pick_id=7)
        call = bot.send_html.await_args
        # chat_id is None → bot routes to its primary channel
        assert call.kwargs.get("chat_id") is None

    @pytest.mark.asyncio
    async def test_tier1_uses_primary_with_notification(
        self, state_and_db,
    ):
        state, _ = state_and_db
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            diag_channel_id="-100DIAG",
        )
        await sender.send_pick_safe(_make_tier1_pick(), pick_id=1)
        call = bot.send_html.await_args
        assert call.kwargs.get("chat_id") is None  # primary
        assert call.kwargs.get("disable_notification") is False


class TestMuteRespect:
    @pytest.mark.asyncio
    async def test_tier2_suppressed_during_mute(self, state_and_db):
        state, _ = state_and_db
        state.set_mute_until(
            datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            min_edge_pct_for_alert=5.0,
        )
        # Tier 2 pick (clean, edge=15, L=0.80 — borderline T1)
        pick = LivePick(
            fixture_id=1, minute=30, home_team="A", away_team="B",
            market="ou", selection="o", bookmaker_id=2,
            bookmaker_odd=1.85, our_probability=0.7, fair_odd=1.43,
            edge_pct=7.0,  # below T1 edge floor
            kelly_fraction_full=0.1, suggested_stake_pct=1.0,
            snapshot_kind="live", flagged_reason=None,
            logical_score=0.85,  # T1 logical, but edge<8 → drops to T2
            confidence_half_width=0.05, model_probability_raw=0.7,
        )
        ok = await sender.send_pick_safe(pick, pick_id=100)
        assert ok is False
        assert sender.n_muted == 1
        bot.send_html.assert_not_called()

    @pytest.mark.asyncio
    async def test_tier1_bypasses_mute(self, state_and_db):
        state, _ = state_and_db
        state.set_mute_until(
            datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            min_edge_pct_for_alert=5.0,
        )
        # Tier 1: L=0.90, edge=15 → bypasses mute
        ok = await sender.send_pick_safe(_make_tier1_pick(), pick_id=200)
        assert ok is True
        assert sender.n_muted == 0
        bot.send_html.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_muted_pick_enqueued_to_burst_queue(self, state_and_db):
        state, _ = state_and_db
        state.set_mute_until(
            datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        bot = _bot_returning()
        sender = LiveAlertSender(
            bot, min_interval_seconds=0.0, state=state,
            min_edge_pct_for_alert=5.0,
        )
        pick = LivePick(
            fixture_id=1, minute=30, home_team="A", away_team="B",
            market="ou", selection="o", bookmaker_id=2,
            bookmaker_odd=1.85, our_probability=0.7, fair_odd=1.43,
            edge_pct=7.0, kelly_fraction_full=0.1,
            suggested_stake_pct=1.0, snapshot_kind="live",
            flagged_reason=None, logical_score=0.85,
            confidence_half_width=0.05, model_probability_raw=0.7,
        )
        await sender.send_pick_safe(pick, pick_id=42)
        assert state.burst_queue_size() == 1
        assert state.drain_burst_queue() == [42]


class TestBuildKeyboard:
    """Smoke-test the keyboard builder works for all tiers."""

    def test_tier1_has_two_rows(self):
        from bip.core.telegram.keyboards import build_pick_keyboard
        kb = build_pick_keyboard(42, tier=1)
        assert len(kb.inline_keyboard) == 2
        # Row 0: PLACE buttons (2 stake rungs)
        assert len(kb.inline_keyboard[0]) == 2
        # Row 1: SKIP + REMIND
        assert len(kb.inline_keyboard[1]) == 2

    def test_tier2_omits_remind(self):
        from bip.core.telegram.keyboards import build_pick_keyboard
        kb = build_pick_keyboard(42, tier=2)
        # Row 1: just SKIP (no REMIND for Tier 2)
        assert len(kb.inline_keyboard[1]) == 1

    def test_tier3_promote_dismiss(self):
        from bip.core.telegram.keyboards import build_pick_keyboard
        kb = build_pick_keyboard(42, tier=3)
        assert len(kb.inline_keyboard) == 1
        labels = [b.text for b in kb.inline_keyboard[0]]
        assert labels == ["PROMOTE", "DISMISS"]
