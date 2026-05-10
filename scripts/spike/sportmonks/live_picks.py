"""Live picks scanner — sweep all in-play matches, find value picks.

Runs once or in a loop. For each in-play fixture:
1. Pull fixture with all relevant includes
2. Build LiveMatchState
3. Run LiveMatchPredictor
4. Pull in-play odds
5. Run ValueDetector
6. Persist snapshot to cache, emit pick rows to a markdown report

Run::

    # one-shot scan
    uv run python -m scripts.spike.sportmonks.live_picks

    # loop every 60s for an hour
    uv run python -m scripts.spike.sportmonks.live_picks --interval 60 --duration 3600

    # with custom edge threshold
    uv run python -m scripts.spike.sportmonks.live_picks --min-edge 5.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow `python -m scripts.spike.sportmonks.live_picks` from repo root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live import (  # noqa: E402
    LiveMatchPredictor,
    LiveMatchState,
    LivePick,
    ValueDetector,
)
from bip.sports.football.sportmonks.cache import SportmonksCache  # noqa: E402
from bip.sports.football.sportmonks.client import (  # noqa: E402
    SportmonksClient,
    sportmonks_client_from_env,
)

logger = logging.getLogger(__name__)


REPORTS_DIR = Path("reports/sportmonks_live")

INCLUDES_LIVE = [
    "participants", "state", "periods", "scores",
    "statistics", "predictions", "events", "trends", "pressure",
]


# ── Pipeline ────────────────────────────────────────────────────────────────


async def scan_one_fixture(
    client: SportmonksClient,
    fixture_id: int,
    *,
    cache: SportmonksCache,
    detector: ValueDetector,
    predictor: LiveMatchPredictor,
) -> list[LivePick]:
    """Pipeline for one in-play fixture: pull → state → predict → odds → value."""
    f = await client.get_fixture(fixture_id, includes=INCLUDES_LIVE)

    # Persist raw payload (snapshot)
    raw = f.model_dump(mode="json")
    cache.save_snapshot(fixture_id, {"data": raw})

    state = LiveMatchState.from_fixture(f)
    if not (state.is_live or state.is_half_time):
        return []

    probs = predictor.predict(state)
    odds = await client.get_inplay_odds_for_fixture(fixture_id)
    picks = detector.evaluate(
        probs, odds,
        home_team_name=state.home_team_name,
        away_team_name=state.away_team_name,
    )
    return picks


async def scan_all_inplay(
    client: SportmonksClient,
    *,
    cache: SportmonksCache,
    detector: ValueDetector,
    predictor: LiveMatchPredictor,
) -> tuple[list[LivePick], dict[int, str]]:
    """Run the pipeline over every in-play fixture currently exposed.

    Returns ``(all_picks, fixture_label_map)``. The label map carries
    "Home vs Away (state)" strings for the report.
    """
    inplay = await client.list_inplay_fixtures(includes=["state", "participants"])
    all_picks: list[LivePick] = []
    labels: dict[int, str] = {}

    for f in inplay:
        teams = " vs ".join((p.name for p in f.participants or [])) if f.participants else "?"
        state_dev = f.state.developer_name if f.state else "?"
        labels[f.id] = f"{teams} ({state_dev})"
        try:
            picks = await scan_one_fixture(
                client, f.id, cache=cache, detector=detector, predictor=predictor,
            )
            all_picks.extend(picks)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan_failed fixture=%d err=%s", f.id, exc)
            continue

    return all_picks, labels


# ── Reporting ───────────────────────────────────────────────────────────────


def render_markdown_report(
    picks: list[LivePick],
    *,
    labels: dict[int, str],
    scan_time: datetime,
    config: dict[str, float],
) -> str:
    lines: list[str] = []
    lines.append(f"# Live picks — {scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("")
    lines.append(f"**Edge threshold:** ≥ {config['min_edge_pct']:.1f}%   "
                 f"**Kelly fraction:** {config['kelly_fraction']:.2f}   "
                 f"**Stake cap:** {config['max_stake_pct']:.1f}%")
    lines.append(f"**Odd range:** {config['min_odd']:.2f} – {config['max_odd']:.2f}")
    lines.append("")

    if not picks:
        lines.append("_No value picks found in current scan._")
        return "\n".join(lines)

    lines.append(f"## {len(picks)} value picks (sorted by edge)")
    lines.append("")
    lines.append("| EV%   | Match | Min | Market | Selection | Odd | Fair | P(model) | Stake% |")
    lines.append("|-------|-------|-----|--------|-----------|-----|------|----------|--------|")
    for p in picks:
        match_label = labels.get(p.fixture_id, f"{p.home_team} vs {p.away_team}")
        lines.append(
            f"| {p.edge_pct:+5.2f} | {match_label} | {p.minute} | "
            f"{p.market} | {p.selection} | {p.bookmaker_odd:.2f} | "
            f"{p.fair_odd:.2f} | {p.our_probability:.3f} | "
            f"{p.suggested_stake_pct:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(
    picks: list[LivePick],
    labels: dict[int, str],
    *,
    scan_time: datetime,
    output_dir: Path,
    config: dict[str, float],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = scan_time.strftime("%Y%m%dT%H%M%SZ")

    md_path = output_dir / f"picks_{ts}.md"
    md_path.write_text(render_markdown_report(
        picks, labels=labels, scan_time=scan_time, config=config,
    ))

    json_path = output_dir / f"picks_{ts}.json"
    json_path.write_text(json.dumps({
        "scan_time": scan_time.isoformat(),
        "config": config,
        "n_picks": len(picks),
        "fixtures_scanned": list(labels.keys()),
        "picks": [
            {
                "fixture_id": p.fixture_id,
                "minute": p.minute,
                "home_team": p.home_team,
                "away_team": p.away_team,
                "market": p.market,
                "selection": p.selection,
                "bookmaker_odd": p.bookmaker_odd,
                "our_probability": p.our_probability,
                "fair_odd": p.fair_odd,
                "edge_pct": p.edge_pct,
                "kelly_fraction_full": p.kelly_fraction_full,
                "suggested_stake_pct": p.suggested_stake_pct,
                "market_description": p.market_description,
                "snapshot_kind": p.snapshot_kind,
            }
            for p in picks
        ],
    }, indent=2, default=str))
    return md_path, json_path


# ── CLI ─────────────────────────────────────────────────────────────────────


async def run_once(
    *,
    min_edge_pct: float,
    max_stake_pct: float,
    kelly_fraction: float,
    min_odd: float,
    max_odd: float,
    cache_root: Path,
    output_dir: Path,
) -> tuple[list[LivePick], dict[int, str], Path | None]:
    cache = SportmonksCache(root=cache_root)
    detector = ValueDetector(
        min_edge_pct=min_edge_pct,
        max_stake_pct=max_stake_pct,
        kelly_fraction=kelly_fraction,
        min_odd=min_odd,
        max_odd=max_odd,
    )
    predictor = LiveMatchPredictor()

    async with sportmonks_client_from_env() as client:
        picks, labels = await scan_all_inplay(
            client, cache=cache, detector=detector, predictor=predictor,
        )

    scan_time = datetime.now(timezone.utc)
    config = {
        "min_edge_pct": min_edge_pct,
        "max_stake_pct": max_stake_pct,
        "kelly_fraction": kelly_fraction,
        "min_odd": min_odd,
        "max_odd": max_odd,
    }
    md_path, json_path = write_reports(
        picks, labels, scan_time=scan_time, output_dir=output_dir, config=config,
    )
    print(f"\n[scan] {scan_time.isoformat()}  fixtures={len(labels)}  picks={len(picks)}")
    print(f"[scan] reports: {md_path}  &  {json_path}")
    if picks:
        print()
        print("TOP PICKS:")
        for p in picks[:5]:
            label = labels.get(p.fixture_id, "?")
            print(
                f"  EV={p.edge_pct:+5.2f}%  {label[:40]:40} "
                f"min={p.minute:3} {p.market:25} {p.selection:6} "
                f"@ {p.bookmaker_odd:.2f}  Kelly={p.suggested_stake_pct:.2f}%"
            )
    return picks, labels, md_path


async def run_loop(
    *,
    interval: int,
    duration: int,
    **kwargs,
) -> None:
    end = time.monotonic() + duration
    iteration = 0
    while time.monotonic() < end:
        iteration += 1
        print(f"\n{'='*72}\nITERATION {iteration}\n{'='*72}")
        try:
            await run_once(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("loop_iteration_failed err=%s", exc)
        next_wake = time.monotonic() + interval
        sleep_for = max(0.0, next_wake - time.monotonic())
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min-edge", type=float, default=3.0,
                   help="Minimum edge%% to emit a pick (default 3.0)")
    p.add_argument("--max-stake", type=float, default=1.5,
                   help="Max stake %% per pick (Kelly cap, default 1.5)")
    p.add_argument("--kelly", type=float, default=0.25,
                   help="Kelly fraction (default ¼)")
    p.add_argument("--min-odd", type=float, default=1.20)
    p.add_argument("--max-odd", type=float, default=8.0)
    p.add_argument("--interval", type=int, default=0,
                   help="Loop interval seconds; 0 = single run (default)")
    p.add_argument("--duration", type=int, default=3600,
                   help="Loop duration seconds (default 1h)")
    p.add_argument("--cache-root", type=Path,
                   default=Path("data/cache/sportmonks"))
    p.add_argument("--output-dir", type=Path, default=REPORTS_DIR)
    p.add_argument("--log-level", type=str, default="WARNING")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    kwargs = dict(
        min_edge_pct=args.min_edge,
        max_stake_pct=args.max_stake,
        kelly_fraction=args.kelly,
        min_odd=args.min_odd,
        max_odd=args.max_odd,
        cache_root=args.cache_root,
        output_dir=args.output_dir,
    )
    if args.interval > 0:
        asyncio.run(run_loop(
            interval=args.interval, duration=args.duration, **kwargs,
        ))
    else:
        asyncio.run(run_once(**kwargs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
