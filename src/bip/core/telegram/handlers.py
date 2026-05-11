"""Callback + command handlers for Telegram Bot v2.

Registered by ``TelegramBot.enable_interactivity()``. All handlers are
**operator-only** — gated by ``filters.User(operator_user_id)``. Any
update from another user is silently ignored.

Callback data schema (compact, fits TG's 64-byte budget, versioned):
    ``v1:{verb}:{pick_id}[:{arg}]``

Verbs:
    place     PLACE button. arg = stake_pct (float, e.g. "1.5")
    skip      SKIP button.
    remind    REMIND button. arg = minutes (int)
    promote   Tier-3 to Tier-2 promotion (Diagnostic → Primary).
    dismiss   Tier-3 dismissed (no-op, records intent).

Persistence: every state change goes through ``TelegramState`` —
idempotent on callback_id, durable across watcher restarts.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from bip.evaluation.live.telegram_state import (
    Action,
    Role,
    TelegramState,
)


logger = logging.getLogger(__name__)


CALLBACK_VERSION = "v1"


# ── Callback-data codec ─────────────────────────────────────────────────────


def encode_callback(verb: str, pick_id: int, arg: Any | None = None) -> str:
    parts = [CALLBACK_VERSION, verb, str(int(pick_id))]
    if arg is not None:
        parts.append(str(arg))
    data = ":".join(parts)
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data too long ({len(data)} bytes): {data}")
    return data


def decode_callback(data: str) -> tuple[str, int, str | None]:
    """Returns (verb, pick_id, arg). Raises ValueError on malformed input."""
    parts = data.split(":", 3)
    if len(parts) < 3 or parts[0] != CALLBACK_VERSION:
        raise ValueError(f"unrecognized callback_data: {data!r}")
    verb = parts[1]
    pick_id = int(parts[2])
    arg = parts[3] if len(parts) == 4 else None
    return verb, pick_id, arg


# ── Bot-data accessors ──────────────────────────────────────────────────────


def _state(ctx: ContextTypes.DEFAULT_TYPE) -> TelegramState:
    return ctx.application.bot_data["state"]


def _db_path(ctx: ContextTypes.DEFAULT_TYPE) -> Path:
    return ctx.application.bot_data["db_path"]


def _connect(ctx: ContextTypes.DEFAULT_TYPE) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(ctx))
    conn.row_factory = sqlite3.Row
    return conn


# ── Callback-query handler (inline buttons) ─────────────────────────────────


async def on_callback_query(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Dispatch all inline-button callbacks. Idempotent per callback_id."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        verb, pick_id, arg = decode_callback(query.data)
    except ValueError:
        await query.answer("Unrecognized button (bot version mismatch?)")
        return

    state = _state(ctx)
    user_id = query.from_user.id if query.from_user else 0

    try:
        if verb == "place":
            stake_pct = float(arg) if arg else 0.0
            was_new, prior = state.record_action(
                pick_id=pick_id, action=Action.PLACED,
                operator_user_id=user_id, callback_id=query.id,
                stake_pct=stake_pct,
            )
            if was_new:
                _mark_placed_in_picks_db(ctx, pick_id, stake_pct)
                await query.answer(f"Placed {stake_pct:.2f}%")
                await _edit_pick_footer(
                    ctx, query, f"Placed {stake_pct:.2f}% @ "
                    f"{datetime.now(timezone.utc).strftime('%H:%M')} UTC",
                )
            else:
                msg = "Already placed"
                if prior and prior.stake_pct is not None:
                    msg = f"Already placed ({prior.stake_pct:.2f}%)"
                await query.answer(msg)

        elif verb == "skip":
            was_new, _ = state.record_action(
                pick_id=pick_id, action=Action.SKIPPED,
                operator_user_id=user_id, callback_id=query.id,
            )
            await query.answer("Skipped" if was_new else "Already skipped")
            if was_new:
                await _edit_pick_footer(ctx, query, "Skipped")

        elif verb == "remind":
            minutes = int(arg) if arg else 5
            was_new, _ = state.record_action(
                pick_id=pick_id, action=Action.REMINDED,
                operator_user_id=user_id, callback_id=query.id,
                stake_pct=float(minutes),  # reuse slot for minutes
            )
            if was_new:
                _enqueue_reminder(state, pick_id=pick_id, minutes=minutes)
                await query.answer(f"Will remind in {minutes}m")
            else:
                await query.answer("Reminder already set")

        elif verb == "promote":
            was_new, _ = state.record_action(
                pick_id=pick_id, action=Action.PROMOTED,
                operator_user_id=user_id, callback_id=query.id,
            )
            await query.answer("Promoted" if was_new else "Already promoted")

        elif verb == "dismiss":
            was_new, _ = state.record_action(
                pick_id=pick_id, action=Action.DISMISSED,
                operator_user_id=user_id, callback_id=query.id,
            )
            await query.answer("Dismissed" if was_new else "Already dismissed")

        else:
            await query.answer(f"Unknown verb: {verb}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "callback_handler_failed verb=%s pick_id=%s err=%s",
            verb, pick_id, exc,
        )
        try:
            await query.answer("Internal error logged")
        except Exception:  # noqa: BLE001
            pass


# ── Footer edit + DB mutation helpers ───────────────────────────────────────


async def _edit_pick_footer(
    ctx: ContextTypes.DEFAULT_TYPE, query: Any, footer_note: str,
) -> None:
    """Append a footer line to the original message, preserving body text.

    Failure-safe: a failed edit is logged but never raised.
    """
    msg = query.message
    if msg is None:
        return
    original = msg.text_html or msg.text or ""
    if footer_note in original:
        return  # idempotent on repeat clicks
    new_text = f"{original}\n\n<i>[{footer_note}]</i>"
    try:
        await ctx.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=new_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=None,  # disable buttons after action
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("edit_pick_footer_failed err=%s", exc)


def _mark_placed_in_picks_db(
    ctx: ContextTypes.DEFAULT_TYPE, pick_id: int, stake_pct: float,
) -> None:
    """Mirror the placement to picks.placed_at_betano. Failure-safe."""
    try:
        with _connect(ctx) as conn:
            conn.execute(
                "UPDATE picks SET placed_at_betano = 1, "
                "actual_stake_units = ? WHERE id = ?",
                (stake_pct, pick_id),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("mark_placed_failed pick_id=%s err=%s", pick_id, exc)


def _enqueue_reminder(
    state: TelegramState, *, pick_id: int, minutes: int,
) -> None:
    """Persist a pending reminder. Drained by the watcher's periodic
    task (slice 5 — outcome_watcher will own this in v2.1).
    """
    fire_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    reminders = state.get_state("reminders", default=[])
    reminders.append({"pick_id": pick_id, "fire_at": fire_at.isoformat()})
    state.set_state("reminders", reminders)


# ── Command handlers ────────────────────────────────────────────────────────


async def cmd_status(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Live snapshot: today's emit count, P/L, mute state, pending count."""
    state = _state(ctx)
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect(ctx) as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS n_emit,
              SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS n_pending,
              SUM(CASE WHEN status='won'     THEN 1 ELSE 0 END) AS n_won,
              SUM(CASE WHEN status='lost'    THEN 1 ELSE 0 END) AS n_lost,
              COALESCE(SUM(CASE WHEN status IN ('won','lost')
                                THEN profit_units END), 0) AS pl_units
            FROM picks
            WHERE DATE(emitted_at) = ?
            """,
            (today,),
        ).fetchone()
    mute_until = state.get_state("mute_until")
    mute_line = ""
    if mute_until:
        mute_line = f"\nMute until <code>{mute_until}</code>"
    text = (
        f"<b>STATUS</b> · {today}\n"
        "\n"
        f"Picks emit today <b>{row['n_emit']}</b>\n"
        f"Pending <b>{row['n_pending'] or 0}</b> · "
        f"Won <b>{row['n_won'] or 0}</b> · Lost <b>{row['n_lost'] or 0}</b>\n"
        f"P/L today <b>{(row['pl_units'] or 0):+.2f}u</b>"
        f"{mute_line}"
    )
    await update.message.reply_html(text)


async def cmd_top(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Top-5 pending picks today by edge_pct."""
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect(ctx) as conn:
        rows = conn.execute(
            """
            SELECT id, home_team, away_team, market, selection,
                   bookmaker_odd, edge_pct, logical_score
            FROM picks
            WHERE DATE(emitted_at) = ? AND status = 'pending'
              AND placed_at_betano = 0
            ORDER BY edge_pct DESC
            LIMIT 5
            """,
            (today,),
        ).fetchall()
    if not rows:
        await update.message.reply_html("<i>No pending picks right now.</i>")
        return
    lines = [f"<b>TOP {len(rows)}</b> · pending picks"]
    lines.append("")
    for r in rows:
        lines.append(
            f"#{r['id']} <b>{r['home_team']}</b> vs <b>{r['away_team']}</b>\n"
            f"   <code>{r['market']}</code> <b>{r['selection']}</b> "
            f"@ {r['bookmaker_odd']:.2f} · "
            f"+{r['edge_pct']:.1f}% · L={r['logical_score']:.2f}"
        )
    await update.message.reply_html("\n".join(lines))


async def cmd_mute(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """`/mute [minutes]` — suppress non-Tier-1 alerts. Default 30m."""
    minutes = 30
    if ctx.args:
        try:
            minutes = int(ctx.args[0])
        except (ValueError, TypeError):
            await update.message.reply_html(
                "<i>Usage: /mute &lt;minutes&gt;</i>"
            )
            return
    if minutes <= 0:
        _state(ctx).clear_mute()
        await update.message.reply_html("<b>Mute cleared.</b>")
        return
    state = _state(ctx)
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    state.set_mute_until(until)
    await update.message.reply_html(
        f"<b>Muted</b> for {minutes}m (until "
        f"{until.strftime('%H:%M')} UTC)."
    )


async def cmd_resume(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    _state(ctx).clear_mute()
    await update.message.reply_html("<b>Resumed.</b>")


async def cmd_bankroll(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Current vs baseline. Baseline stored in tg_state['bankroll_baseline']."""
    state = _state(ctx)
    baseline = state.get_state("bankroll_baseline", default=None)
    with _connect(ctx) as conn:
        # All-time P/L on emit universe.
        row_total = conn.execute(
            """
            SELECT COALESCE(SUM(profit_units), 0) AS pl
            FROM picks WHERE status IN ('won', 'lost')
            """,
        ).fetchone()
        today = datetime.now(timezone.utc).date().isoformat()
        row_today = conn.execute(
            """
            SELECT COALESCE(SUM(profit_units), 0) AS pl
            FROM picks
            WHERE status IN ('won', 'lost') AND DATE(emitted_at) = ?
            """,
            (today,),
        ).fetchone()
    pl_total = float(row_total["pl"] or 0)
    pl_today = float(row_today["pl"] or 0)
    baseline_line = ""
    if baseline is not None:
        try:
            base = float(baseline)
            current = base + pl_total
            pct = (current - base) / base * 100 if base else 0
            baseline_line = (
                f"\nBaseline <b>{base:.1f}u</b> → "
                f"Current <b>{current:.1f}u</b> ({pct:+.2f}%)"
            )
        except (TypeError, ValueError):
            pass
    text = (
        "<b>BANKROLL</b>\n"
        "\n"
        f"All-time P/L (emit) <b>{pl_total:+.2f}u</b>\n"
        f"Today P/L (emit) <b>{pl_today:+.2f}u</b>"
        f"{baseline_line}"
    )
    await update.message.reply_html(text)


async def cmd_placed(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """`/placed <pick_id> <stake_pct> [betano_odd]` — manual reconciliation."""
    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_html(
            "<i>Usage: /placed &lt;pick_id&gt; &lt;stake_pct&gt; "
            "[betano_odd]</i>"
        )
        return
    try:
        pick_id = int(args[0])
        stake_pct = float(args[1])
        betano_odd = float(args[2]) if len(args) >= 3 else None
    except (ValueError, TypeError):
        await update.message.reply_html(
            "<i>Bad arguments. Stake and odd must be numbers.</i>"
        )
        return

    state = _state(ctx)
    user_id = update.effective_user.id if update.effective_user else 0
    callback_id = f"manual-{pick_id}-{datetime.now(timezone.utc).timestamp()}"
    was_new, prior = state.record_action(
        pick_id=pick_id, action=Action.PLACED,
        operator_user_id=user_id, callback_id=callback_id,
        stake_pct=stake_pct,
    )
    if not was_new:
        prior_stake = prior.stake_pct if prior else None
        await update.message.reply_html(
            f"<i>Pick #{pick_id} already placed "
            f"({prior_stake:.2f}% — use /undo_place to revert).</i>"
        )
        return

    with _connect(ctx) as conn:
        if betano_odd is not None:
            conn.execute(
                "UPDATE picks SET placed_at_betano=1, "
                "actual_stake_units=?, betano_odd=? WHERE id=?",
                (stake_pct, betano_odd, pick_id),
            )
        else:
            conn.execute(
                "UPDATE picks SET placed_at_betano=1, "
                "actual_stake_units=? WHERE id=?",
                (stake_pct, pick_id),
            )
    await update.message.reply_html(
        f"<b>Placed</b> pick #{pick_id} · {stake_pct:.2f}%"
        + (f" @ {betano_odd:.2f}" if betano_odd else "")
    )


# ── Registration entry point ────────────────────────────────────────────────


def register_handlers(
    app: Application,
    *,
    state: TelegramState,
    db_path: Path,
    operator_user_id: int,
) -> None:
    """Wire all handlers onto the bot, gated by operator user-id."""
    app.bot_data["state"] = state
    app.bot_data["db_path"] = db_path
    app.bot_data["operator_user_id"] = operator_user_id

    user_filter = filters.User(user_id=operator_user_id)

    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(CommandHandler("status", cmd_status, filters=user_filter))
    app.add_handler(CommandHandler("top", cmd_top, filters=user_filter))
    app.add_handler(CommandHandler("mute", cmd_mute, filters=user_filter))
    app.add_handler(CommandHandler("resume", cmd_resume, filters=user_filter))
    app.add_handler(CommandHandler("bankroll", cmd_bankroll, filters=user_filter))
    app.add_handler(CommandHandler("placed", cmd_placed, filters=user_filter))
