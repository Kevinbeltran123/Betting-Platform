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

import dataclasses  # noqa: E402

from bip.evaluation.live import (  # noqa: E402
    LiveMatchPredictor,
    LiveMatchState,
    ValueDetector,
)
from bip.evaluation.live.pick_tracker import (  # noqa: E402
    DEFAULT_DB_PATH,
    PickTracker,
)
from bip.evaluation.live.team_form import (  # noqa: E402
    DEFAULT_FORM_DB_PATH,
    TeamFormCache,
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
    leagues_allowlist: frozenset[int] | None = None,
    leagues_blocklist: frozenset[int] | None = None,
    form_cache: TeamFormCache | None = None,
) -> tuple[int, int]:
    """One full scan round. Returns (picks_emitted, picks_new).

    League quality filter (B-21): when ``leagues_allowlist`` is set, only
    fixtures whose ``league_id`` is in the allowlist proceed. When
    ``leagues_blocklist`` is set, fixtures from those leagues are skipped.
    Both default to None (no filtering — preserves prior behaviour). The
    allowlist takes precedence: if both are set, fixtures must pass
    allowlist AND not appear in blocklist.

    Filter is applied BEFORE the get_fixture call to save API quota on
    leagues we never want picks from.
    """
    n_emitted = 0
    n_new = 0
    async with sportmonks_client_from_env() as client:
        live = await client.list_inplay_fixtures(includes=["state", "participants"])
        relevant = [
            f for f in live
            if f.state and f.state.id in LIVE_STATE_IDS
        ]
        # League filter — skip fixtures outside the operator's quality tier
        if leagues_allowlist is not None:
            relevant = [f for f in relevant if f.league_id in leagues_allowlist]
        if leagues_blocklist is not None:
            relevant = [f for f in relevant if f.league_id not in leagues_blocklist]

        for f in relevant:
            try:
                full = await client.get_fixture(f.id, includes=INCLUDES)
                snapshot_taken_at = datetime.now(timezone.utc)
                state = LiveMatchState.from_fixture(
                    full, snapshot_taken_at=snapshot_taken_at,
                )
                if not (state.is_live or state.is_half_time):
                    # Save fixture-only snapshot for non-live so the
                    # final-state snapshot is preserved for backtest grading.
                    cache.save_snapshot(
                        f.id, {"data": full.model_dump(mode="json")},
                    )
                    continue

                # Resolve team form (cache hit is instant; miss triggers
                # a single API call per team per ~18h). Failures degrade
                # gracefully — predictor falls back to Sportmonks priors.
                if form_cache is not None and state.season_id is not None:
                    home_form = await form_cache.get_or_fetch(
                        client, state.home_team_id, state.season_id,
                    )
                    away_form = await form_cache.get_or_fetch(
                        client, state.away_team_id, state.season_id,
                    )
                    state = dataclasses.replace(
                        state,
                        home_team_form=home_form,
                        away_team_form=away_form,
                    )

                probs = predictor.predict(state)
                odds = await client.get_inplay_odds_for_fixture(f.id)
                # Persist BOTH fixture + odds in one snapshot so backtest
                # replay can grade picks against the actual odds visible
                # at capture time. Previously snapshots had only fixture
                # data → backtest never saw odds → all replay picks empty.
                cache.save_snapshot(f.id, {
                    "data": full.model_dump(mode="json"),
                    "odds_snapshot": [o.model_dump(mode="json") for o in odds],
                    "snapshot_taken_at": snapshot_taken_at.isoformat(),
                })

                # Per-snapshot drop logger — feeds pick_decisions table so
                # gate_rejection_rates() has data. Emits/flags continue to
                # be recorded by the watcher post-loop (with pick_id).
                def _on_decision(*, snapshot_at=snapshot_taken_at, **kwargs):
                    tracker.record_decision(
                        snapshot_taken_at=snapshot_at, **kwargs,
                    )

                picks = detector.evaluate(
                    probs, odds,
                    home_team_name=state.home_team_name,
                    away_team_name=state.away_team_name,
                    state=state,  # enables sanity filters
                    on_decision=_on_decision,
                )

                # Note: detector already enforces min_edge_pct; no re-filter.
                for pick in picks:
                    n_emitted += 1
                    pick_id, is_new = tracker.record(pick)
                    decision = "flag" if pick.flagged_reason else "emit"
                    tracker.record_decision(
                        fixture_id=pick.fixture_id, minute=pick.minute,
                        market=pick.market, selection=pick.selection,
                        decision=decision,
                        bookmaker_id=pick.bookmaker_id,
                        bookmaker_odd=pick.bookmaker_odd,
                        our_probability=pick.our_probability,
                        edge_pct=pick.edge_pct,
                        drop_reason=pick.flagged_reason,
                        informational_density=state.informational_density,
                        logical_score=pick.logical_score,
                        logical_components=pick.logical_components,
                        confidence_half_width=pick.confidence_half_width,
                        pick_id=pick_id,
                        snapshot_taken_at=snapshot_taken_at,
                    )
                    if not is_new:
                        continue
                    n_new += 1

                    title, body = render_pick_alert(pick)
                    flag_str = f"  ⚠ FLAGGED: {pick.flagged_reason}" if pick.flagged_reason else ""
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
                            f"L={pick.logical_score:.2f}  "
                            f"id={pick_id}{flag_str}\n"
                        )
                    icon = "⚠️" if pick.flagged_reason else "🚨"
                    print(
                        f"\n{icon} NEW PICK: +{pick.edge_pct:5.2f}%  "
                        f"{state.home_team_name} vs {state.away_team_name} "
                        f"(min {pick.minute})  "
                        f"{pick.market}/{pick.selection} @ {pick.bookmaker_odd:.2f}  "
                        f"stake={pick.suggested_stake_pct:.2f}%  "
                        f"L={pick.logical_score:.2f}  id={pick_id}{flag_str}"
                    )
                    # Only send proactive notifications for clean picks; flagged
                    # picks log silently — operator must check the report.
                    if not pick.flagged_reason:
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
    leagues_allowlist: frozenset[int] | None = None,
    leagues_blocklist: frozenset[int] | None = None,
    form_db_path: Path | None = None,
    form_cache_enabled: bool = True,
) -> None:
    cache = SportmonksCache(root=cache_root)
    tracker = PickTracker(db_path=db_path)
    predictor = LiveMatchPredictor()
    detector = ValueDetector(min_edge_pct=min_edge, **detector_kwargs)
    form_cache: TeamFormCache | None = None
    if form_cache_enabled:
        form_cache = TeamFormCache(
            db_path=form_db_path or DEFAULT_FORM_DB_PATH,
        )

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
                leagues_allowlist=leagues_allowlist,
                leagues_blocklist=leagues_blocklist,
                form_cache=form_cache,
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
    p.add_argument("--sanity-edge-cap", type=float, default=50.0,
                   help="Above this %% EV picks are treated as stale-odd "
                        "artefacts (default 50)")
    p.add_argument("--no-drop-extreme", action="store_true",
                   help="Disable hard-drop of critical-flag picks "
                        "(default: hard-drop enabled)")
    p.add_argument("--no-coherence", action="store_true",
                   help="Disable bookmaker self-coherence gate")
    p.add_argument("--no-blackout", action="store_true",
                   help="Disable post-event / late-minute blackouts")
    p.add_argument("--no-stale-check", action="store_true",
                   help="Disable stale-odd timestamp gate")
    p.add_argument("--no-ci-gate", action="store_true",
                   help="Disable per-pick credibility-interval gate")
    p.add_argument("--no-bundle-dedup", action="store_true",
                   help="Disable correlated cross-market deduplication")
    p.add_argument("--info-density-floor", type=float, default=0.20,
                   help="Hard floor for live-pick informational density "
                        "(default 0.20)")
    p.add_argument("--min-logical-emit", type=float, default=0.70,
                   help="Logical-score threshold for clean emit (default 0.70)")
    p.add_argument("--min-logical-flag", type=float, default=0.40,
                   help="Logical-score threshold below which picks are "
                        "dropped entirely (default 0.40)")
    p.add_argument(
        "--leagues-allowlist", type=str, default="",
        help="Comma-separated Sportmonks league_ids to whitelist (others "
             "skipped before any per-fixture API call). Example: '8,564,82,"
             "384,301' for top-5 European. Default: empty (no allowlist).",
    )
    p.add_argument(
        "--leagues-blocklist", type=str, default="",
        help="Comma-separated Sportmonks league_ids to blacklist. Applied "
             "AFTER allowlist. Default: empty (no blocklist).",
    )
    p.add_argument(
        "--no-form-cache", action="store_true",
        help="Disable team-form cache (predictor falls back to Sportmonks "
             "priors). Default: enabled — pulls each team's last ~90 days "
             "of fixtures on first sight, refreshes every 18h.",
    )
    p.add_argument(
        "--form-db-path", type=Path, default=DEFAULT_FORM_DB_PATH,
        help="SQLite path for team-form cache",
    )
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
        sanity_edge_cap=args.sanity_edge_cap,
        drop_extreme=not args.no_drop_extreme,
        enforce_coherence=not args.no_coherence,
        enforce_blackout=not args.no_blackout,
        enforce_stale_odd_check=not args.no_stale_check,
        enforce_ci_gate=not args.no_ci_gate,
        bundle_dedup=not args.no_bundle_dedup,
        info_density_floor=args.info_density_floor,
        min_logical_score_emit=args.min_logical_emit,
        min_logical_score_flag=args.min_logical_flag,
    )

    def _parse_league_ids(s: str) -> frozenset[int] | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return frozenset(int(x.strip()) for x in s.split(",") if x.strip())
        except ValueError:
            print(f"⚠ invalid league id list: {s!r} — ignoring", file=sys.stderr)
            return None

    leagues_allowlist = _parse_league_ids(args.leagues_allowlist)
    leagues_blocklist = _parse_league_ids(args.leagues_blocklist)

    print(f"🟢 Watching live matches.  edge ≥ {args.min_edge:.1f}%   "
          f"interval={args.interval}s   "
          f"DB: {args.db_path}   log: {args.log_path}")
    if leagues_allowlist:
        print(f"   League allowlist: {sorted(leagues_allowlist)}")
    if leagues_blocklist:
        print(f"   League blocklist: {sorted(leagues_blocklist)}")
    if not args.no_form_cache:
        print(f"   Team-form cache: ON  ({args.form_db_path})")
    else:
        print("   Team-form cache: OFF")
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
        leagues_allowlist=leagues_allowlist,
        leagues_blocklist=leagues_blocklist,
        form_db_path=args.form_db_path,
        form_cache_enabled=not args.no_form_cache,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
