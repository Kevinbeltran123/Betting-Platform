"""Telegram alerts for the Sportmonks live-edge spike.

Separate from `bip.core.telegram.sender` because the v1.0 sender is
coupled to the `Pick` schema (with Claude validation, 1X2 markets, etc.),
while the spike uses `LivePick` from `value_detector` with different
fields (calibrated probability, raw probability, logical components,
commentary events, etc.).

Two main outputs:

1. Per-pick alert (real-time when a LivePick is emitted):
   Compact HTML message with fixture, score, market/selection, odds,
   edge, stake, calibrated vs raw probability, and key flags.

2. Per-jornada summary (post-grading):
   Roll-up of emit universe + Top-N performance + drop_reason
   breakdown + calibrator health metrics.

Reuses the existing `TelegramBot` wrapper for actual sending. This
module owns only formatting.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from bip.evaluation.live.value_detector import LivePick


def _e(s: Any) -> str:
    """HTML-escape a value for Telegram (Telegram parse_mode='HTML')."""
    return html.escape(str(s), quote=False)


def format_pick_alert(
    pick: LivePick,
    *,
    home_score: int | None = None,
    away_score: int | None = None,
    league_name: str | None = None,
) -> str:
    """Return an HTML-formatted Telegram alert for a single emitted LivePick.

    `home_score` and `away_score` should reflect the score AT THE PICK'S
    minute (caller responsibility — usually from the LiveMatchState).
    `league_name` is optional context for the operator.

    Telegram HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a>.
    No emojis added to the message body — only in headers — per operator
    style preference (file-level commenting allows the existing prefix
    pattern).
    """
    fixture_line = f"{_e(pick.home_team)} vs {_e(pick.away_team)}"
    if league_name:
        fixture_line = f"{_e(league_name)} — {fixture_line}"

    score_str = ""
    if home_score is not None and away_score is not None:
        score_str = f" · Score <b>{home_score}-{away_score}</b>"

    cal_prob = pick.our_probability
    raw_prob = pick.model_probability_raw
    if raw_prob and abs(raw_prob - cal_prob) > 1e-4:
        prob_line = (
            f"Cal prob: <b>{cal_prob:.3f}</b> "
            f"(raw {raw_prob:.3f})"
        )
    else:
        prob_line = f"Prob: <b>{cal_prob:.3f}</b>"

    # Flag annotation (one of the cascade's soft-flag reasons)
    flag_line = ""
    if pick.flagged_reason:
        flag_line = (
            f"\n⚠️ <b>FLAGGED:</b> <code>{_e(pick.flagged_reason)}</code>"
        )

    # Compact logical-component fingerprint when available
    ls_extra = ""
    if pick.logical_components:
        # Top 2 components by magnitude for at-a-glance signal
        comps = sorted(
            pick.logical_components.items(),
            key=lambda kv: -abs(kv[1]),
        )[:2]
        ls_extra = " · " + " ".join(
            f"<i>{_e(k)}</i>={v:.2f}" for k, v in comps
        )

    lines = [
        f"<b>🎯 LIVE PICK</b> · <i>{fixture_line}</i>",
        "",
        f"Min <b>{pick.minute}'</b>{score_str}",
        f"Market: <code>{_e(pick.market)}</code> · "
        f"Selection: <b>{_e(pick.selection)}</b>",
        f"Odds: <b>{pick.bookmaker_odd:.2f}</b> · "
        f"Edge: <b>+{pick.edge_pct:.2f}%</b>",
        "",
        f"Stake: <b>{pick.suggested_stake_pct:.2f}%</b> bankroll "
        f"(¼ Kelly, full = {pick.kelly_fraction_full:.3f})",
        prob_line,
        f"Logical score: <b>{pick.logical_score:.2f}</b>{ls_extra}",
    ]
    if flag_line:
        lines.append(flag_line)
    return "\n".join(lines)


def format_jornada_summary(
    *,
    jornada_date: str,
    n_emit_total: int,
    n_emit_settled: int,
    n_won: int,
    profit_units: float,
    stake_pct_total: float,
    drops_by_reason: dict[str, int] | None = None,
    top_n_stats: dict[str, Any] | None = None,
    calibrator_ece_cv: float | None = None,
    calibrator_n_markets_own_fit: int | None = None,
    best_market: tuple[str, int, int, float] | None = None,
) -> str:
    """Return an HTML-formatted post-jornada summary message.

    Arguments:
        jornada_date: ISO date string for the header
        n_emit_total: picks emitted (before grading filter)
        n_emit_settled: picks that resolved won or lost (not void/pending)
        n_won, profit_units, stake_pct_total: ROI components
        drops_by_reason: drop_reason -> count from decisions table
        top_n_stats: optional dict {'n', 'won', 'profit', 'roi'} for Top-25
        calibrator_ece_cv: 5-fold CV ECE from latest fit (or None)
        calibrator_n_markets_own_fit: per-market count (or None)
        best_market: optional (market_name, n_picks, n_won, roi_pct) tuple
    """
    win_rate = (n_won / n_emit_settled * 100) if n_emit_settled else 0.0
    roi = (profit_units / stake_pct_total * 100) if stake_pct_total > 0 else 0.0

    lines = [
        f"<b>📊 JORNADA SUMMARY</b> · {_e(jornada_date)}",
        "",
        "<b>Emit universe:</b>",
        f"• Picks emitidos: <b>{n_emit_total}</b> "
        f"(settled: {n_emit_settled})",
        f"• Won: <b>{n_won}</b> ({win_rate:.1f}%)",
        f"• Profit: <b>{profit_units:+.2f} u</b>",
        f"• ROI: <b>{roi:+.2f}%</b>",
    ]

    if top_n_stats:
        n = top_n_stats.get("n", 0)
        w = top_n_stats.get("won", 0)
        pr = top_n_stats.get("profit", 0.0)
        r = top_n_stats.get("roi", 0.0)
        lines.extend([
            "",
            "<b>Top-N (placeable):</b>",
            f"• Picks: <b>{n}</b> · Won: <b>{w}</b> "
            f"({w/n*100 if n else 0:.1f}%)",
            f"• P/L: <b>{pr:+.2f} u</b> · ROI: <b>{r:+.2f}%</b>",
        ])

    if best_market:
        mkt, mn, mw, mroi = best_market
        lines.extend([
            "",
            f"<b>Best market:</b> <code>{_e(mkt)}</code> — "
            f"{mw}/{mn} ({mw/mn*100 if mn else 0:.0f}%) · "
            f"ROI <b>{mroi:+.1f}%</b>",
        ])

    if drops_by_reason:
        # Show top 5 drop reasons by count (skip noisy `below_min_edge`
        # which is the natural cascade gate, not a Tier 1+ filter)
        interesting = {
            k: v for k, v in drops_by_reason.items()
            if k != "below_min_edge"
        }
        top_drops = sorted(
            interesting.items(), key=lambda kv: -kv[1],
        )[:6]
        if top_drops:
            lines.extend([
                "",
                "<b>Drops by gate (excl. below_min_edge):</b>",
            ])
            for reason, count in top_drops:
                lines.append(
                    f"• <code>{_e(reason)}</code>: <b>{count}</b>"
                )

    if calibrator_ece_cv is not None or calibrator_n_markets_own_fit is not None:
        lines.append("")
        lines.append("<b>Calibrator:</b>")
        if calibrator_ece_cv is not None:
            lines.append(f"• ECE (5-fold CV): <b>{calibrator_ece_cv:.4f}</b>")
        if calibrator_n_markets_own_fit is not None:
            lines.append(
                f"• Markets with own fit: <b>{calibrator_n_markets_own_fit}</b>"
            )

    return "\n".join(lines)


def format_pre_jornada_brief(
    *,
    jornada_date: str,
    n_fixtures: int,
    calibrator_fitted_at: str | None = None,
    expected_roi_band: str | None = None,
    profile_name: str | None = None,
) -> str:
    """Pre-kickoff briefing (operator sanity check before watch session)."""
    lines = [
        f"<b>🚦 PRE-JORNADA BRIEF</b> · {_e(jornada_date)}",
        "",
        f"Fixtures to monitor: <b>{n_fixtures}</b>",
    ]
    if profile_name:
        lines.append(f"Stack profile: <code>{_e(profile_name)}</code>")
    if calibrator_fitted_at:
        lines.append(
            f"Calibrator fitted: <code>{_e(calibrator_fitted_at)}</code>"
        )
    if expected_roi_band:
        lines.append(f"Expected ROI band: <b>{_e(expected_roi_band)}</b>")
    return "\n".join(lines)


# ── Send helpers (async, wrap TelegramBot) ──────────────────────────────────


async def send_pick_alert(
    bot: Any,
    pick: LivePick,
    *,
    home_score: int | None = None,
    away_score: int | None = None,
    league_name: str | None = None,
) -> None:
    """Send a formatted pick alert via the supplied TelegramBot instance."""
    text = format_pick_alert(
        pick, home_score=home_score, away_score=away_score,
        league_name=league_name,
    )
    await bot.send_html(text)


async def send_jornada_summary(bot: Any, **kwargs: Any) -> None:
    """Send a post-jornada summary via the supplied TelegramBot instance.

    All keyword arguments are forwarded to ``format_jornada_summary``.
    """
    text = format_jornada_summary(**kwargs)
    await bot.send_html(text)


async def send_pre_jornada_brief(bot: Any, **kwargs: Any) -> None:
    """Send a pre-jornada briefing via the supplied TelegramBot instance."""
    text = format_pre_jornada_brief(**kwargs)
    await bot.send_html(text)
