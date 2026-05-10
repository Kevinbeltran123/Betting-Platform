"""Background capture loop — snapshots all live matches every N seconds.

Persists to ``data/cache/sportmonks/snapshots/{fixture_id}/{ts}.json``.
Used to build a historical replay corpus for backtesting the live
predictor without paying for repeated API calls.

Run::

    # Run for 4 hours, snapshot every 30 seconds
    uv run python -m scripts.spike.sportmonks.capture_loop \\
        --duration 14400 --interval 30

    # Run forever (until Ctrl+C), snapshot every 60s
    uv run python -m scripts.spike.sportmonks.capture_loop \\
        --duration 0 --interval 60

The loop is rate-limit aware: Sportmonks Pro allows ~3,000 calls/hour
per entity. Each capture round costs:
  1× /livescores/inplay (1 call)
  N× /fixtures/{id} with full include (1 call per live fixture)
  N× /odds/inplay/fixtures/{id} (1 call per live fixture)

So a 30-second cadence on 10 live matches → 21 calls/round × 120
rounds/hour = 2,520 calls/hour. Stays under the Pro limit.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)
from bip.sports.football.sportmonks.client import (  # noqa: E402
    SportmonksClient,
    sportmonks_client_from_env,
)
from bip.sports.football.sportmonks.types import LIVE_STATE_IDS  # noqa: E402

logger = logging.getLogger(__name__)

# Includes we want on every snapshot (everything we can use later)
SNAPSHOT_INCLUDES = [
    "participants", "state", "periods", "scores",
    "statistics", "predictions", "events", "trends", "pressure",
    "lineups",
]


_stop_requested = False


def _on_signal(signum, frame):
    global _stop_requested
    _stop_requested = True
    logger.warning("signal_received signum=%s — finishing current round", signum)


async def capture_round(
    client: SportmonksClient,
    *,
    cache: SportmonksCache,
    capture_odds: bool = True,
) -> tuple[int, int]:
    """One capture round. Returns (n_fixtures_seen, n_snapshots_written)."""
    inplay = await client.list_inplay_fixtures(includes=["state"])
    relevant = [
        f for f in inplay
        if f.state and f.state.id in LIVE_STATE_IDS
    ]
    n_written = 0

    for f in relevant:
        try:
            full = await client.get_fixture(f.id, includes=SNAPSHOT_INCLUDES)
            payload = {"data": full.model_dump(mode="json")}

            # Optional odds snapshot — Sportmonks keeps a separate URL,
            # so we attach the array under a 'odds_snapshot' field.
            if capture_odds:
                odds = await client.get_inplay_odds_for_fixture(f.id)
                payload["odds_snapshot"] = [
                    o.model_dump(mode="json") for o in odds
                ]

            cache.save_snapshot(f.id, payload)
            n_written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "capture_failed fixture=%d err=%s", f.id, exc,
            )
            continue

    return len(relevant), n_written


async def main_loop(
    *,
    interval: int,
    duration: int,
    cache_root: Path,
    capture_odds: bool,
) -> None:
    cache = SportmonksCache(root=cache_root)
    end = (time.monotonic() + duration) if duration > 0 else None

    iteration = 0
    async with sportmonks_client_from_env() as client:
        while True:
            if _stop_requested:
                print("\nStop requested — exiting cleanly.")
                break
            if end is not None and time.monotonic() >= end:
                print("\nDuration reached — exiting.")
                break

            iteration += 1
            t0 = time.monotonic()
            now = datetime.now(timezone.utc)
            try:
                n_seen, n_written = await capture_round(
                    client, cache=cache, capture_odds=capture_odds,
                )
                elapsed = time.monotonic() - t0
                print(
                    f"[{now.strftime('%H:%M:%S')}] "
                    f"round={iteration:4} live={n_seen:3} "
                    f"written={n_written:3} elapsed={elapsed:.1f}s"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[{now.strftime('%H:%M:%S')}] round={iteration} ERR {exc}")

            sleep_for = max(0.0, interval - (time.monotonic() - t0))
            if sleep_for > 0:
                try:
                    await asyncio.sleep(sleep_for)
                except asyncio.CancelledError:
                    break


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval", type=int, default=30,
                   help="Seconds between rounds (default 30)")
    p.add_argument("--duration", type=int, default=0,
                   help="Total seconds to run (0 = until Ctrl+C; default)")
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--no-odds", action="store_true",
                   help="Skip odds capture (saves ~50%% calls)")
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

    asyncio.run(main_loop(
        interval=args.interval,
        duration=args.duration,
        cache_root=args.cache_root,
        capture_odds=not args.no_odds,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
