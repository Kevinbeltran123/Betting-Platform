"""Live-watch Telegram integration with failure-safe semantics.

Wraps `TelegramBot` with logic specific to the Sportmonks spike:

- Start/shutdown lifecycle managed by an async context manager.
- All sends are swallowed-on-failure: a Telegram outage must NEVER crash
  the watch loop. We log and continue.
- Throttling: optionally enforce a minimum interval between sends to
  avoid flooding the channel when the cascade emits many picks at once.
- Send filters: only emit Telegram alerts above an edge threshold, only
  for non-flagged picks, etc.

Used by `scripts/spike/sportmonks/watch.py` when the operator passes
`--telegram`. Falls back to stdout-only logging when bot init fails.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from bip.evaluation.live.telegram_alerts import (
    format_jornada_summary,
    format_pick_alert,
    format_pre_jornada_brief,
)
from bip.evaluation.live.value_detector import LivePick

logger = logging.getLogger(__name__)


class LiveAlertSender:
    """Failure-safe Telegram alert sender for the live watch loop.

    Use as an async context manager so start/shutdown are paired:

        async with LiveAlertSender.from_env() as sender:
            if sender:
                await sender.send_pick_safe(pick, home_score=1, away_score=0)
    """

    def __init__(
        self,
        bot: Any,
        *,
        min_edge_pct_for_alert: float = 5.0,
        skip_flagged: bool = True,
        min_interval_seconds: float = 2.0,
    ) -> None:
        self._bot = bot
        self.min_edge_pct_for_alert = min_edge_pct_for_alert
        self.skip_flagged = skip_flagged
        self.min_interval_seconds = min_interval_seconds
        self._last_send_ts: float = 0.0
        self.n_sent = 0
        self.n_skipped = 0
        self.n_failed = 0

    @classmethod
    async def from_env(
        cls,
        *,
        min_edge_pct_for_alert: float = 5.0,
        skip_flagged: bool = True,
        min_interval_seconds: float = 2.0,
    ) -> "LiveAlertSender | None":
        """Build from TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID env vars.

        Returns None when env vars are missing or bot init fails — caller
        proceeds without Telegram (the watch loop must remain operational).
        """
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
        if not token or not channel:
            logger.warning(
                "telegram_alerts_disabled "
                "(TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID missing)"
            )
            return None
        try:
            from bip.core.telegram.bot import TelegramBot
            bot = TelegramBot(token=token, channel_id=channel)
            await bot.start()
            return cls(
                bot,
                min_edge_pct_for_alert=min_edge_pct_for_alert,
                skip_flagged=skip_flagged,
                min_interval_seconds=min_interval_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_bot_init_failed err=%s", exc)
            return None

    async def __aenter__(self) -> "LiveAlertSender":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        try:
            await self._bot.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_bot_shutdown_failed err=%s", exc)

    def _should_send(self, pick: LivePick) -> bool:
        """Apply per-pick filters before attempting a send."""
        if self.skip_flagged and pick.flagged_reason:
            return False
        if pick.edge_pct < self.min_edge_pct_for_alert:
            return False
        return True

    async def _throttle(self) -> None:
        """Enforce minimum interval between sends to avoid flooding."""
        if self.min_interval_seconds <= 0:
            return
        now = datetime.now(timezone.utc).timestamp()
        elapsed = now - self._last_send_ts
        if elapsed < self.min_interval_seconds:
            wait = self.min_interval_seconds - elapsed
            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                pass
        self._last_send_ts = datetime.now(timezone.utc).timestamp()

    async def send_pick_safe(
        self,
        pick: LivePick,
        *,
        home_score: int | None = None,
        away_score: int | None = None,
        league_name: str | None = None,
    ) -> bool:
        """Send a pick alert. Returns True on success, False on skip/failure.

        Failure modes are logged but never raised — the watch loop must
        continue running even if Telegram is unreachable.
        """
        if not self._should_send(pick):
            self.n_skipped += 1
            return False
        await self._throttle()
        try:
            text = format_pick_alert(
                pick, home_score=home_score, away_score=away_score,
                league_name=league_name,
            )
            await self._bot.send_html(text)
            self.n_sent += 1
            return True
        except Exception as exc:  # noqa: BLE001
            self.n_failed += 1
            logger.warning(
                "telegram_send_failed pick=%s/%s err=%s",
                pick.market, pick.selection, exc,
            )
            return False

    async def send_brief_safe(self, **kwargs: Any) -> bool:
        """Send a pre-jornada brief. Failure-safe."""
        try:
            text = format_pre_jornada_brief(**kwargs)
            await self._bot.send_html(text)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_brief_failed err=%s", exc)
            return False

    async def send_summary_safe(self, **kwargs: Any) -> bool:
        """Send a post-jornada summary. Failure-safe."""
        try:
            text = format_jornada_summary(**kwargs)
            await self._bot.send_html(text)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_summary_failed err=%s", exc)
            return False
