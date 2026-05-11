#!/usr/bin/env python3
"""Manual smoke test for Telegram alerts (run BEFORE first jornada with alerts ON).

Modes:

    # Print formatted message to stdout — no Telegram bot used
    uv run python scripts/spike/sportmonks/test_telegram_alert.py --dry-run

    # Actually send to the configured channel — REQUIRES .env Telegram secrets
    uv run python scripts/spike/sportmonks/test_telegram_alert.py --send

    # Send a sample post-jornada summary
    uv run python scripts/spike/sportmonks/test_telegram_alert.py --send --kind summary

Use `--dry-run` to verify formatting visually without spamming the channel.
Use `--send` once before a live jornada to confirm bot token + channel ID
are configured correctly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from bip.evaluation.live.telegram_alerts import (
    format_jornada_summary,
    format_pick_alert,
    format_pre_jornada_brief,
)
from bip.evaluation.live.value_detector import LivePick


def _sample_pick() -> LivePick:
    """A representative Day-1-style pick for visual inspection."""
    return LivePick(
        fixture_id=19425232,
        minute=27,
        home_team="FSV Mainz 05",
        away_team="FC Union Berlin",
        market="ou_3_5",
        selection="under",
        bookmaker_id=2,
        bookmaker_odd=1.61,
        our_probability=0.78,
        fair_odd=1.282,
        edge_pct=25.6,
        kelly_fraction_full=0.43,
        suggested_stake_pct=1.05,
        market_description="Total Goals — Under 3.5",
        snapshot_kind="live",
        flagged_reason=None,
        logical_score=0.85,
        logical_components={
            "edge_consilience": 0.92,
            "size_consistency": 0.88,
            "informational_density": 0.78,
            "odds_credibility": 0.85,
            "liquidity": 0.82,
        },
        confidence_half_width=0.04,
        model_probability_raw=0.71,
    )


def _sample_summary_args() -> dict:
    return dict(
        jornada_date="2026-05-13",
        n_emit_total=487,
        n_emit_settled=425,
        n_won=270,
        profit_units=123.5,
        stake_pct_total=420.3,
        top_n_stats={"n": 25, "won": 20, "profit": 15.8, "roi": 63.2},
        drops_by_reason={
            "below_min_edge": 215,
            "market_blacklist": 22,
            "positive_side_binary_ban": 34,
            "commentary_cooloff:var_check": 6,
            "commentary_cooloff:injury_delay": 9,
            "zero_zero_over_gate": 4,
        },
        calibrator_ece_cv=0.052,
        calibrator_n_markets_own_fit=11,
        best_market=("ou_3_5", 10, 9, 91.0),
    )


def _sample_pre_brief() -> str:
    return format_pre_jornada_brief(
        jornada_date="2026-05-13",
        n_fixtures=42,
        calibrator_fitted_at="2026-05-12T22:30:00Z",
        expected_roi_band="+40% to +60% (CV 5-fold, n=813)",
        profile_name="aggressive",
    )


async def _send_via_bot(text: str) -> int:
    from bip.core.telegram.bot import TelegramBot
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not channel:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHANNEL_ID not set "
            "in environment. Aborting send.",
            file=sys.stderr,
        )
        return 2
    bot = TelegramBot(token=token, channel_id=channel)
    await bot.start()
    try:
        await bot.send_html(text)
    finally:
        await bot.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--kind", choices=["pick", "summary", "brief"], default="pick",
        help="Which sample message to render",
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="Print to stdout only (default if neither given)")
    group.add_argument("--send", action="store_true",
                       help="Actually send to Telegram (requires .env secrets)")
    args = ap.parse_args(argv)

    if args.kind == "pick":
        text = format_pick_alert(
            _sample_pick(), home_score=1, away_score=0,
            league_name="Bundesliga",
        )
    elif args.kind == "summary":
        text = format_jornada_summary(**_sample_summary_args())
    else:  # brief
        text = _sample_pre_brief()

    if args.send:
        rc = asyncio.run(_send_via_bot(text))
        if rc == 0:
            print("Sent successfully to Telegram channel.")
        return rc

    # Default: dry-run
    print("─" * 70)
    print(f"Sample {args.kind!r} message (HTML body — Telegram parse_mode='HTML'):")
    print("─" * 70)
    print(text)
    print("─" * 70)
    print(
        f"To actually send: rerun with --send "
        f"(requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID in env)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
