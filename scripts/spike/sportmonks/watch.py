"""Live streaming watcher — dedup picks, alert on new ones.

Use for actual live betting workflow:
  1. Loop forever (until Ctrl+C), polling every N seconds
  2. For each new pick (not seen in last N minutes), notify via:
     - macOS notification (osascript)
     - Terminal beep
     - Append to a tail-friendly log file
  3. Persist every emitted pick to SQLite for backtest grading
  4. Don't re-alert duplicates within the dedup window

Usage::

    # Standard run with notifications
    uv run python -m scripts.spike.sportmonks.watch

    # Loud — beep on every new pick, edge ≥ 4%
    uv run python -m scripts.spike.sportmonks.watch --min-edge 4 --beep

    # Silent (logs only, useful when you can't have notifications popping)
    uv run python -m scripts.spike.sportmonks.watch --no-notify

Output:
- ``data/cache/sportmonks/picks.db`` — SQLite with every pick
- ``reports/sportmonks_live/watch.log`` — tail-friendly log
- macOS notifications + optional terminal beep
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live import (  # noqa: E402
    LiveMatchPredictor,
    LiveMatchState,
    ValueDetector,
)
from bip.evaluation.live.pick_tracker import (  # noqa: E402
    DEFAULT_DB_PATH,
    PickTracker,
)
from bip.evaluation.live.value_detector import LivePick  # noqa: E402
from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)
from bip.sports.football.sportmonks.client import (  # noqa: E402
    sportmonks_client_from_env,
)
from bip.sports.football.sportmonks.types import LIVE_STATE_IDS  # noqa: E402

logger = logging.getLogger(__name__)


INCLUDES = [
    "participants", "state", "periods", "scores",
    "statistics", "predictions", "events", "trends", "pressure",
]


_stop_requested = False


def _on_signal(signum, frame):
    global _stop_requested
    _stop_requested = True


# ── Notification primitives ─────────────────────────────────────────────────


def macos_notify(title: str, message: str) -> None:
    """Send a macOS notification via osascript. No-op on other platforms."""
    if platform.system() != "Darwin":
        return
    osascript = shutil.which("osascript")
    if not osascript:
        return
    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")
    subprocess.run(
        [
            osascript, "-e",
            f'display notification "{safe_msg}" with title "{safe_title}"',
        ],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def terminal_beep() -> None:
    """Print BEL — most terminals will beep or flash."""
    sys.stdout.write("\a")
    sys.stdout.flush()


def render_pick_alert(pick: LivePick) -> tuple[str, str]:
    """Build (title, body) for a notification."""
    title = f"⚽ +{pick.edge_pct:.1f}% EV — {pick.market}"
    body = (
        f"{pick.home_team} vs {pick.away_team} (min {pick.minute})\n"
        f"{pick.market} {pick.selection} @ {pick.bookmaker_odd:.2f}  "
        f"P={pick.our_probability:.2f}  Stake={pick.suggested_stake_pct:.2f}%"
    )
    return title, body


# ── Pipeline ────────────────────────────────────────────────────────────────


async def scan_round(
    *,
    cache: SportmonksCache,
    tracker: PickTracker,
    predictor: LiveMatchPredictor,
    detector: ValueDetector,
    log_path: Path,
    notify: bool,
    beep: bool,
    min_edge: float,
) -> tuple[int, int]:
    """One full scan round. Returns (picks_emitted, picks_new)."""
    n_emitted = 0
    n_new = 0
    async with sportmonks_client_from_env() as client:
        live = await client.list_inplay_fixtures(includes=["state", "participants"])
        relevant = [
            f for f in live
            if f.state and f.state.id in LIVE_STATE_IDS
        ]

        for f in relevant:
            try:
                full = await client.get_fixture(f.id, includes=INCLUDES)
                cache.save_snapshot(f.id, {"data": full.model_dump(mode="json")})

                state = LiveMatchState.from_fixture(full)
                if not (state.is_live or state.is_half_time):
                    continue

                probs = predictor.predict(state)
                odds = await client.get_inplay_odds_for_fixture(f.id)
                picks = detector.evaluate(
                    probs, odds,
                    home_team_name=state.home_team_name,
                    away_team_name=state.away_team_name,
                )

                for pick in picks:
                    if pick.edge_pct < min_edge:
                        continue
                    n_emitted += 1
                    pick_id, is_new = tracker.record(pick)
                    if not is_new:
                        continue
                    n_new += 1

                    title, body = render_pick_alert(pick)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with log_path.open("a") as f_log:
                        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        f_log.write(
                            f"[{ts}] +{pick.edge_pct:5.2f}%  "
                            f"{state.home_team_name} vs {state.away_team_name} "
                            f"(min {pick.minute})  "
                            f"{pick.market}/{pick.selection} @ {pick.bookmaker_odd:.2f}  "
                            f"P={pick.our_probability:.3f}  "
                            f"stake={pick.suggested_stake_pct:.2f}%  "
                            f"id={pick_id}\n"
                        )
                    print(
                        f"\n🚨 NEW PICK: +{pick.edge_pct:5.2f}%  "
                        f"{state.home_team_name} vs {state.away_team_name} "
                        f"(min {pick.minute})  "
                        f"{pick.market}/{pick.selection} @ {pick.bookmaker_odd:.2f}  "
                        f"stake={pick.suggested_stake_pct:.2f}%  id={pick_id}"
                    )
                    if notify:
                        macos_notify(title, body)
                    if beep:
                        terminal_beep()

            except Exception as exc:  # noqa: BLE001
                logger.warning("scan_failed fixture=%d err=%s", f.id, exc)
                continue

    return n_emitted, n_new


async def watch_loop(
    *,
    interval: int,
    duration: int,
    min_edge: float,
    cache_root: Path,
    db_path: Path,
    log_path: Path,
    notify: bool,
    beep: bool,
    detector_kwargs: dict,
) -> None:
    cache = SportmonksCache(root=cache_root)
    tracker = PickTracker(db_path=db_path)
    predictor = LiveMatchPredictor()
    detector = ValueDetector(min_edge_pct=min_edge, **detector_kwargs)

    end = (datetime.now(timezone.utc).timestamp() + duration) if duration > 0 else None
    iteration = 0

    while True:
        if _stop_requested:
            print("\nStop requested — exiting cleanly.")
            break
        if end is not None and datetime.now(timezone.utc).timestamp() >= end:
            print("\nDuration reached — exiting.")
            break

        iteration += 1
        t0 = datetime.now(timezone.utc).timestamp()
        try:
            n_emit, n_new = await scan_round(
                cache=cache, tracker=tracker, predictor=predictor,
                detector=detector, log_path=log_path,
                notify=notify, beep=beep, min_edge=min_edge,
            )
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            elapsed = datetime.now(timezone.utc).timestamp() - t0
            print(
                f"[{now}] round={iteration:4} emitted={n_emit:3} "
                f"new={n_new:3} elapsed={elapsed:.1f}s"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"round_error iteration={iteration} err={exc}")

        sleep_for = max(0.0, interval - (datetime.now(timezone.utc).timestamp() - t0))
        if sleep_for > 0:
            try:
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                break


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval", type=int, default=45,
                   help="Seconds between rounds (default 45)")
    p.add_argument("--duration", type=int, default=0,
                   help="Total seconds (0 = until Ctrl+C; default)")
    p.add_argument("--min-edge", type=float, default=4.0,
                   help="Minimum edge%% to emit + alert (default 4.0)")
    p.add_argument("--max-stake", type=float, default=1.5)
    p.add_argument("--kelly", type=float, default=0.25)
    p.add_argument("--min-odd", type=float, default=1.20)
    p.add_argument("--max-odd", type=float, default=8.0)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--log-path", type=Path,
                   default=Path("reports/sportmonks_live/watch.log"))
    p.add_argument("--no-notify", action="store_true",
                   help="Disable macOS notifications")
    p.add_argument("--beep", action="store_true",
                   help="Terminal BEL on each new pick")
    p.add_argument("--log-level", type=str, default="WARNING")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    detector_kwargs = dict(
        max_stake_pct=args.max_stake,
        kelly_fraction=args.kelly,
        min_odd=args.min_odd,
        max_odd=args.max_odd,
    )

    print(f"🟢 Watching live matches.  edge ≥ {args.min_edge:.1f}%   "
          f"interval={args.interval}s   "
          f"DB: {args.db_path}   log: {args.log_path}")
    if not args.no_notify and platform.system() == "Darwin":
        print("   macOS notifications: ON")
    if args.beep:
        print("   Terminal beep: ON")
    print()

    asyncio.run(watch_loop(
        interval=args.interval, duration=args.duration,
        min_edge=args.min_edge,
        cache_root=args.cache_root, db_path=args.db_path,
        log_path=args.log_path,
        notify=not args.no_notify, beep=args.beep,
        detector_kwargs=detector_kwargs,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
