"""CLI entry point for the v3 cohort accountant.

Operator-runnable. Reads the v3 shadow log, joins with outcomes (if
present), evaluates the cohort against the frozen kill criteria, and
emits a daily report. Engages the filesystem kill switch on hard stop.

Usage::

    uv run python -m scripts.spike.v3.run_cohort_eval

    # Override paths
    uv run python -m scripts.spike.v3.run_cohort_eval \\
        --shadow-root data/cache/v3_shadow \\
        --report-root reports/v3/cohort_evals \\
        --kill-switch  data/cache/v3_shadow/v3_kill_switch.flag

    # Wire Telegram alerting (optional; needs TELEGRAM_BOT_TOKEN +
    # TELEGRAM_CHANNEL_ID in environment)
    uv run python -m scripts.spike.v3.run_cohort_eval --telegram

The exit code reflects the verdict:
- 0  : ok / soft warning / greenlight
- 10 : hard stop (kill switch engaged)
- 1  : runtime error (loading failed, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from bip.evaluation.live.engine_v3.runtime.cohort_accountant import (
    DEFAULT_REPORT_ROOT,
    AlertSink,
    run_cohort_eval,
)
from bip.evaluation.live.engine_v3.runtime.dual_write import (
    DEFAULT_KILL_SWITCH_PATH,
)
from bip.evaluation.live.engine_v3.shadow_logger import DEFAULT_SHADOW_ROOT


def _build_telegram_sink() -> AlertSink | None:
    """Lazy-build TelegramBot from environment. Returns None if env
    is missing — operator can still run the CLI without alerts.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not channel_id:
        return None
    try:
        from bip.core.telegram import TelegramBot
    except Exception:  # noqa: BLE001
        return None
    try:
        return TelegramBot(token=token, channel_id=channel_id)
    except Exception:  # noqa: BLE001
        return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v3 cohort accountant CLI")
    p.add_argument(
        "--shadow-root",
        type=Path,
        default=DEFAULT_SHADOW_ROOT,
        help="Root of v3 shadow log partitions",
    )
    p.add_argument(
        "--report-root",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Where to write the daily markdown report",
    )
    p.add_argument(
        "--kill-switch",
        type=Path,
        default=DEFAULT_KILL_SWITCH_PATH,
        help="Path to the kill switch flag file (engaged on hard stop)",
    )
    p.add_argument(
        "--telegram",
        action="store_true",
        help="Wire Telegram alerts (requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID env)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout (still writes report file + structured logs)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sink = _build_telegram_sink() if args.telegram else None

    try:
        result = asyncio.run(
            run_cohort_eval(
                shadow_root=args.shadow_root,
                report_root=args.report_root,
                kill_switch_path=args.kill_switch,
                alert_sink=sink,
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cohort eval failed: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        v = result.verdict
        kind = (
            "HARD_STOP" if v.is_hard_stop
            else "SOFT_WARN" if v.is_soft_warning
            else "GREENLIGHT" if v.is_greenlight_ready
            else "OK"
        )
        print(f"verdict={kind} stage={result.metrics.stage.value} "
              f"n_settled={result.metrics.n_settled} "
              f"WR={result.metrics.wr:.3f} "
              f"ROI={result.metrics.roi_flat:.3f}")
        if v.rule_triggered:
            print(f"rule={v.rule_triggered} reason={v.reason}")
        print(f"report={result.report_path}")
        if result.kill_switch_engaged:
            print(f"kill_switch_engaged at={args.kill_switch}")

    return 10 if result.verdict.is_hard_stop else 0


if __name__ == "__main__":
    sys.exit(main())
