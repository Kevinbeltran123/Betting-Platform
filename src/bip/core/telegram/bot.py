"""Send-only Telegram bot wrapper.

D-13: Lives in the same asyncio loop as PipelineOrchestrator (in-process). NO polling —
single private channel, outbound alerts only. AIORateLimiter handles flood control
(Pitfall 2 + Risks 2 — requires the [rate-limiter] extra in pyproject.toml).
"""

from __future__ import annotations

import structlog
from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import AIORateLimiter, Application, ApplicationBuilder

from bip.core.errors import TelegramError

logger = structlog.get_logger(__name__)


class TelegramBot:
    """Outbound-only Telegram bot owned by PipelineOrchestrator for the process lifetime."""

    def __init__(self, token: str, channel_id: str) -> None:
        if not token:
            raise TelegramError("telegram_bot_token is empty — set TELEGRAM_BOT_TOKEN in .env")
        if not channel_id:
            raise TelegramError("telegram_channel_id is empty — set TELEGRAM_CHANNEL_ID in .env")

        self._channel_id = channel_id
        self._app: Application = (
            ApplicationBuilder()
            .token(token)
            .rate_limiter(AIORateLimiter(max_retries=3))
            .build()
        )

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        logger.info("telegram_bot_started", channel_id=self._channel_id)

    async def shutdown(self) -> None:
        await self._app.stop()
        await self._app.shutdown()
        logger.info("telegram_bot_stopped")

    @property
    def bot(self) -> Bot:
        return self._app.bot

    async def send_html(self, text: str) -> None:
        await self.bot.send_message(
            chat_id=int(self._channel_id),
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("telegram_send_success", channel_id=self._channel_id, length=len(text))
