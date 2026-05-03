"""Wave 0 RED stubs for PICK-04 init.

Implementation lands in plan 03-06 (telegram/bot.py).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-06")


class TestBotInit:
    def test_init_no_polling(self):
        """D-13: bot does NOT call updater.start_polling — outbound only."""
        raise NotImplementedError("plan 03-06")

    def test_aiorate_limiter_attached(self):
        """Pitfall 2: app._rate_limiter is not None (AIORateLimiter wired)."""
        raise NotImplementedError("plan 03-06")

    def test_channel_id_validator_rejects_positive_int(self):
        """Pitfall 8: TELEGRAM_CHANNEL_ID without -100 prefix raises ValidationError."""
        raise NotImplementedError("plan 03-06")
