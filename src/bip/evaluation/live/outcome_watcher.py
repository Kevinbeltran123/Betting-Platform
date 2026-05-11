"""Periodic outcome-reply + scoreboard maintenance task.

Decoupling rationale (per design memo §F): the grader writes only
``picks.status`` + ``picks.profit_units``. This watcher polls
``picks.db`` for newly-settled picks, replies to the original Telegram
message, and refreshes the pinned scoreboard.

Lives in the watch loop's asyncio task — failure-safe: any exception
in ``tick()`` is logged but never raised. Outage of Telegram does not
prevent the next tick from trying again on the same pick set (the
outcome-reply row only gets written on a successful send).

Pinned scoreboard: derived from ``picks.db`` on every render — no
persistent state beyond ``tg_state['scoreboard_msg_id']``. Cannot drift.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bip.evaluation.live.telegram_alerts import (
    format_outcome_reply,
    format_scoreboard,
)
from bip.evaluation.live.telegram_state import (
    Action,
    Role,
    TelegramState,
)


logger = logging.getLogger(__name__)


class OutcomeWatcher:
    """Periodic task: outcome replies + scoreboard maintenance.

    Usage::

        watcher = OutcomeWatcher(
            bot=alert_sender._bot, state=state, db_path=picks_db,
            primary_channel_id=os.environ["TELEGRAM_CHANNEL_ID"],
        )
        task = asyncio.create_task(watcher.run_forever(period_seconds=60))
        # ... watcher.cancel() on shutdown

    Or, when integrated with the watch loop's own scheduling, call
    ``await watcher.tick()`` once per period.
    """

    def __init__(
        self,
        *,
        bot: Any,
        state: TelegramState,
        db_path: Path,
        primary_channel_id: str,
        scoreboard_enabled: bool = True,
    ) -> None:
        self._bot = bot
        self._state = state
        self._db_path = Path(db_path)
        self._primary_channel_id = str(primary_channel_id)
        self._scoreboard_enabled = scoreboard_enabled
        self.n_outcome_replies_sent = 0
        self.n_scoreboard_updates = 0
        self.n_failures = 0
        self._stopped = False

    # ── one-tick API ────────────────────────────────────────────────────

    async def tick(self) -> int:
        """Run one cycle. Returns the number of outcome replies sent.

        Failure-safe. The scoreboard update is best-effort; an edit
        failure (e.g. message-too-old) triggers a fresh pin on the next
        tick.
        """
        try:
            n = await self._send_outcome_replies()
        except Exception as exc:  # noqa: BLE001
            self.n_failures += 1
            logger.warning("outcome_replies_failed err=%s", exc)
            n = 0
        if self._scoreboard_enabled:
            try:
                await self.update_scoreboard()
            except Exception as exc:  # noqa: BLE001
                self.n_failures += 1
                logger.warning("scoreboard_update_failed err=%s", exc)
        return n

    async def run_forever(self, *, period_seconds: float = 60.0) -> None:
        """Blocking infinite loop. Cancel via the caller's task object."""
        while not self._stopped:
            await self.tick()
            try:
                await asyncio.sleep(period_seconds)
            except asyncio.CancelledError:
                self._stopped = True
                return

    def stop(self) -> None:
        self._stopped = True

    # ── outcome replies ─────────────────────────────────────────────────

    async def _send_outcome_replies(self) -> int:
        """Send one reply per pick that settled but has no outcome yet."""
        rows = self._fetch_pending_outcome_rows()
        n_sent = 0
        for row in rows:
            try:
                await self._send_one_outcome_reply(row)
                n_sent += 1
                self.n_outcome_replies_sent += 1
            except Exception as exc:  # noqa: BLE001
                self.n_failures += 1
                logger.warning(
                    "outcome_reply_send_failed pick_id=%s err=%s",
                    row["pick_id"], exc,
                )
        return n_sent

    def _fetch_pending_outcome_rows(self) -> list[sqlite3.Row]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  p.id              AS pick_id,
                  p.status          AS status,
                  p.profit_units    AS profit_units,
                  p.market          AS market,
                  p.selection       AS selection,
                  p.bookmaker_odd   AS bookmaker_odd,
                  p.actual_stake_units AS actual_stake_units,
                  p.betano_odd      AS betano_odd,
                  m.channel_id      AS channel_id,
                  m.message_id      AS message_id,
                  a.stake_pct       AS placed_stake_pct
                FROM picks p
                JOIN tg_messages m
                  ON m.pick_id = p.id AND m.role = ?
                LEFT JOIN tg_messages r
                  ON r.pick_id = p.id AND r.role = ?
                LEFT JOIN tg_actions a
                  ON a.pick_id = p.id AND a.action = ?
                WHERE p.status IN ('won', 'lost', 'void')
                  AND r.pick_id IS NULL
                ORDER BY p.settled_at
                LIMIT 100
                """,
                (Role.PICK, Role.OUTCOME, Action.PLACED),
            ).fetchall()
        return list(rows)

    async def _send_one_outcome_reply(self, row: sqlite3.Row) -> None:
        placed_stake_pct = row["placed_stake_pct"]
        placed_odd = row["betano_odd"]
        actual_pl = None
        if (
            placed_stake_pct is not None
            and placed_odd is not None
            and row["status"] in ("won", "lost")
        ):
            actual_pl = _actual_profit_units(
                status=row["status"],
                stake_pct=float(placed_stake_pct),
                odd=float(placed_odd),
            )

        text = format_outcome_reply(
            status=row["status"],
            market=row["market"],
            selection=row["selection"],
            bookmaker_odd=float(row["bookmaker_odd"]),
            profit_units=float(row["profit_units"] or 0.0),
            placed_stake_pct=(
                float(placed_stake_pct)
                if placed_stake_pct is not None else None
            ),
            placed_odd=(
                float(placed_odd) if placed_odd is not None else None
            ),
            actual_profit_units=actual_pl,
        )

        reply_message_id = await self._bot.send_html(
            text,
            chat_id=row["channel_id"],
            reply_to_message_id=row["message_id"],
            disable_notification=True,
        )
        self._state.record_message(
            pick_id=row["pick_id"],
            channel_id=row["channel_id"],
            message_id=reply_message_id,
            role=Role.OUTCOME,
        )

    # ── scoreboard ──────────────────────────────────────────────────────

    async def update_scoreboard(self) -> None:
        """Refresh (or create) the pinned scoreboard for today."""
        snapshot = self._compute_scoreboard_snapshot()
        text = format_scoreboard(
            date=snapshot["date"],
            n_emit=snapshot["n_emit"],
            n_placed=snapshot["n_placed"],
            n_pending=snapshot["n_pending"],
            n_settled=snapshot["n_settled"],
            n_won=snapshot["n_won"],
            pl_emit_units=snapshot["pl_emit"],
            pl_placed_units=snapshot["pl_placed"],
            drawdown_pct=snapshot["drawdown_pct"],
            updated_at=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        )

        existing_id = self._state.get_state("scoreboard_msg_id")
        if existing_id:
            try:
                await self._bot.edit_html(
                    chat_id=self._primary_channel_id,
                    message_id=int(existing_id),
                    text=text,
                )
                self.n_scoreboard_updates += 1
                return
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "scoreboard_edit_failed_reposting err=%s", exc,
                )
                # Fall through to repost.

        message_id = await self._bot.send_html(
            text, chat_id=self._primary_channel_id,
            disable_notification=True,
        )
        self._state.set_state("scoreboard_msg_id", message_id)
        self._state.set_state(
            "scoreboard_date", datetime.now(timezone.utc).date().isoformat(),
        )
        self.n_scoreboard_updates += 1

    def _compute_scoreboard_snapshot(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                  COUNT(*)                                            AS n_emit,
                  SUM(CASE WHEN placed_at_betano=1 THEN 1 ELSE 0 END) AS n_placed,
                  SUM(CASE WHEN status='pending'   THEN 1 ELSE 0 END) AS n_pending,
                  SUM(CASE WHEN status IN ('won','lost')
                           THEN 1 ELSE 0 END)                         AS n_settled,
                  SUM(CASE WHEN status='won'       THEN 1 ELSE 0 END) AS n_won,
                  COALESCE(SUM(CASE WHEN status IN ('won','lost')
                                    THEN profit_units END), 0)        AS pl_emit
                FROM picks
                WHERE DATE(emitted_at) = ?
                """,
                (today,),
            ).fetchone()
            placed_row = conn.execute(
                """
                SELECT COALESCE(SUM(
                    CASE
                      WHEN p.status='won'  AND p.placed_at_betano=1
                        THEN p.actual_stake_units * (p.betano_odd - 1)
                      WHEN p.status='lost' AND p.placed_at_betano=1
                        THEN -p.actual_stake_units
                      ELSE 0
                    END
                ), 0) AS pl_placed
                FROM picks p
                WHERE DATE(p.emitted_at) = ?
                """,
                (today,),
            ).fetchone()

        # Drawdown computed against today's peak P/L.
        peak_pl = self._state.get_state("today_peak_pl", default=0.0) or 0.0
        pl_emit = float(row["pl_emit"] or 0.0)
        if pl_emit > peak_pl:
            self._state.set_state("today_peak_pl", pl_emit)
            peak_pl = pl_emit
        drawdown_pct = (peak_pl - pl_emit) if peak_pl > 0 else 0.0

        return {
            "date": today,
            "n_emit": int(row["n_emit"] or 0),
            "n_placed": int(row["n_placed"] or 0),
            "n_pending": int(row["n_pending"] or 0),
            "n_settled": int(row["n_settled"] or 0),
            "n_won": int(row["n_won"] or 0),
            "pl_emit": pl_emit,
            "pl_placed": float(placed_row["pl_placed"] or 0.0),
            "drawdown_pct": drawdown_pct,
        }


# ── helpers ─────────────────────────────────────────────────────────────────


def _actual_profit_units(*, status: str, stake_pct: float, odd: float) -> float:
    """Operator's actual P/L in stake-percent units.

    Mirrors how ``picks.profit_units`` is computed in the grader:
    won → stake_pct * (odd - 1); lost → -stake_pct; void → 0.
    """
    if status == "won":
        return stake_pct * (odd - 1.0)
    if status == "lost":
        return -stake_pct
    return 0.0
