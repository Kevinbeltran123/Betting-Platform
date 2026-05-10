"""Replay cached snapshots through the live predictor + value detector.

Purpose: estimate the predictor's true edge against bookmaker odds we
captured DURING matches, then score against the FINAL outcome of each
match. No live API calls — pure offline replay.

Each snapshot was captured with::

    {
      "data": <Fixture model_dump>,
      "odds_snapshot": <list of Odd model_dump>
    }

So the replay loop is:
  for fixture in cached_fixtures:
      snapshots = sorted(snapshots[fixture])
      final_outcome = derive_from_last_snapshot(snapshots[-1])
      for snap in snapshots:
          state = LiveMatchState.from_fixture(snap.data)
          probs = predictor.predict(state)
          odds  = parse_odds_snapshot(snap.odds_snapshot)
          picks = detector.evaluate(probs, odds, ...)
          for pick in picks:
              record_outcome(pick, final_outcome)

Then aggregate: ROI / hit rate / Brier / coverage per market.

Run::

    uv run python -m scripts.spike.sportmonks.backtest \\
        --cache-root data/cache/sportmonks \\
        --output reports/sportmonks_backtest

NOT invoked by the scheduler.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live import (  # noqa: E402
    LiveMatchPredictor,
    LiveMatchState,
    ValueDetector,
)
from bip.evaluation.live.value_detector import LivePick  # noqa: E402
from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)
from bip.sports.football.sportmonks.schemas import Fixture, Odd  # noqa: E402

logger = logging.getLogger(__name__)


# ── Outcome derivation ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FinalOutcome:
    home_goals: int
    away_goals: int
    home_goals_first_half: int
    away_goals_first_half: int
    is_finished: bool

    @property
    def fulltime_result(self) -> str:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals == self.away_goals:
            return "draw"
        return "away"

    @property
    def first_half_result(self) -> str:
        if self.home_goals_first_half > self.away_goals_first_half:
            return "home"
        if self.home_goals_first_half == self.away_goals_first_half:
            return "draw"
        return "away"

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def total_goals_first_half(self) -> int:
        return self.home_goals_first_half + self.away_goals_first_half

    @property
    def btts(self) -> bool:
        return self.home_goals > 0 and self.away_goals > 0


def _derive_final_outcome(last_snapshot: Fixture) -> FinalOutcome | None:
    """Pull final score + first-half score from the LAST snapshot of a match.

    Returns None when the match isn't actually finished (still in play
    when capture stopped).
    """
    state = LiveMatchState.from_fixture(last_snapshot)
    if not state.is_finished:
        return None

    # First-half goals: count goal_events with minute ≤ 45
    home_1h = sum(
        1 for minute, team in state.goal_events
        if minute <= 45 and team == state.home_team_id
    )
    away_1h = sum(
        1 for minute, team in state.goal_events
        if minute <= 45 and team == state.away_team_id
    )

    return FinalOutcome(
        home_goals=state.home_goals,
        away_goals=state.away_goals,
        home_goals_first_half=home_1h,
        away_goals_first_half=away_1h,
        is_finished=True,
    )


def _outcome_for_pick(pick: LivePick, outcome: FinalOutcome) -> bool | None:
    """Did the pick win? Returns None when we can't grade it."""
    market = pick.market
    selection = pick.selection

    if market == "fulltime_result":
        return selection == outcome.fulltime_result
    if market == "first_half_result":
        return selection == outcome.first_half_result
    if market == "double_chance":
        ft = outcome.fulltime_result
        return (
            (selection == "1x" and ft in ("home", "draw")) or
            (selection == "x2" and ft in ("draw", "away")) or
            (selection == "12" and ft in ("home", "away"))
        )
    if market == "btts":
        return (selection == "yes") == outcome.btts
    if market == "btts_first_half":
        return (selection == "yes") == (
            outcome.home_goals_first_half > 0
            and outcome.away_goals_first_half > 0
        )
    if market.startswith("ou_"):
        # ou_2_5 → line 2.5
        line = float(market.split("_")[1] + "." + market.split("_")[2])
        if selection == "over":
            return outcome.total_goals > line
        if selection == "under":
            return outcome.total_goals < line + 1  # under means ≤ floor(line)
        return None
    if market.startswith("first_half_ou_"):
        line = float(market.split("_")[3] + "." + market.split("_")[4])
        if selection == "over":
            return outcome.total_goals_first_half > line
        if selection == "under":
            return outcome.total_goals_first_half < line + 1
        return None
    if market in ("home_ou_1_5", "away_ou_1_5"):
        team_goals = (
            outcome.home_goals if market == "home_ou_1_5"
            else outcome.away_goals
        )
        if selection == "over":
            return team_goals > 1.5
        if selection == "under":
            return team_goals < 1.5
        return None
    return None


# ── Replay engine ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GradedPick:
    """A pick that survived backtest grading."""

    pick: LivePick
    won: bool | None  # None = ungraded
    profit_units: float  # +odds-1 if won; -1 if lost; 0 if void/ungraded


def _replay_fixture(
    fixture_id: int,
    cache: SportmonksCache,
    *,
    predictor: LiveMatchPredictor,
    detector: ValueDetector,
) -> list[GradedPick]:
    """Replay all snapshots for one fixture, grade picks against final outcome."""
    snap_paths = cache.list_snapshots(fixture_id)
    if len(snap_paths) < 2:
        return []  # Need at least 2 snapshots (one early + final)

    # Last snapshot's payload to derive final outcome
    last_payload = json.loads(snap_paths[-1].read_text())
    last_fixture = Fixture.model_validate(last_payload.get("data", last_payload))
    outcome = _derive_final_outcome(last_fixture)
    if outcome is None:
        # Match never finished in our captures
        return []

    graded: list[GradedPick] = []
    home_team_name = ""
    away_team_name = ""

    for path in snap_paths[:-1]:  # don't replay the final snapshot
        payload = json.loads(path.read_text())
        record = payload.get("data", payload)
        fixture = Fixture.model_validate(record)
        try:
            state = LiveMatchState.from_fixture(fixture)
        except ValueError:
            continue
        home_team_name = state.home_team_name
        away_team_name = state.away_team_name

        if not (state.is_live or state.is_half_time):
            continue

        probs = predictor.predict(state)

        # Reconstruct odds from the snapshot
        odds_records = payload.get("odds_snapshot", [])
        odds = []
        for r in odds_records:
            try:
                odds.append(Odd.model_validate(r))
            except Exception:  # noqa: BLE001
                continue

        if not odds:
            continue

        picks = detector.evaluate(
            probs, odds,
            home_team_name=state.home_team_name,
            away_team_name=state.away_team_name,
            state=state,
        )
        for p in picks:
            won = _outcome_for_pick(p, outcome)
            if won is None:
                profit = 0.0
            elif won:
                profit = p.bookmaker_odd - 1.0
            else:
                profit = -1.0
            graded.append(GradedPick(pick=p, won=won, profit_units=profit))

    return graded


# ── Aggregate metrics ───────────────────────────────────────────────────────


def aggregate(graded: list[GradedPick]) -> dict[str, Any]:
    if not graded:
        return {
            "n_picks": 0, "n_graded": 0, "win_rate": None, "roi_pct": None,
            "by_market": {},
        }
    n = len(graded)
    n_graded = sum(1 for g in graded if g.won is not None)
    n_won = sum(1 for g in graded if g.won is True)
    profit = sum(g.profit_units for g in graded)

    by_market: dict[str, dict[str, float]] = defaultdict(lambda: {
        "n": 0, "n_won": 0, "profit": 0.0, "stake": 0.0,
    })
    for g in graded:
        m = by_market[g.pick.market]
        m["n"] += 1
        m["stake"] += 1.0
        if g.won:
            m["n_won"] += 1
        m["profit"] += g.profit_units
    market_summary = {}
    for k, v in by_market.items():
        market_summary[k] = {
            "n": int(v["n"]),
            "n_won": int(v["n_won"]),
            "win_rate": v["n_won"] / v["n"] if v["n"] else 0,
            "roi_pct": (v["profit"] / v["stake"] * 100) if v["stake"] else 0,
        }

    return {
        "n_picks": n,
        "n_graded": n_graded,
        "n_won": n_won,
        "win_rate": n_won / n_graded if n_graded else None,
        "total_profit_units": profit,
        "roi_pct": (profit / n_graded * 100) if n_graded else None,
        "by_market": market_summary,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--output", type=Path,
                   default=Path("reports/sportmonks_backtest"))
    p.add_argument("--min-edge", type=float, default=3.0)
    p.add_argument("--kelly", type=float, default=0.25)
    p.add_argument("--max-stake", type=float, default=1.5)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cache = SportmonksCache(root=args.cache_root)
    detector = ValueDetector(
        min_edge_pct=args.min_edge,
        kelly_fraction=args.kelly,
        max_stake_pct=args.max_stake,
    )
    predictor = LiveMatchPredictor()

    fixtures = cache.list_fixtures()
    print(f"Replay over {len(fixtures)} cached fixtures")

    all_graded: list[GradedPick] = []
    for fid in fixtures:
        graded = _replay_fixture(
            fid, cache, predictor=predictor, detector=detector,
        )
        if graded:
            print(f"  fixture {fid}: {len(graded)} graded picks")
            all_graded.extend(graded)

    summary = aggregate(all_graded)

    args.output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    json_path = args.output / f"backtest_{ts}.json"
    json_path.write_text(json.dumps({
        "ran_at": ts,
        "config": {
            "min_edge_pct": args.min_edge,
            "kelly_fraction": args.kelly,
            "max_stake_pct": args.max_stake,
        },
        "summary": summary,
        "picks": [
            {
                "fixture_id": g.pick.fixture_id,
                "minute": g.pick.minute,
                "market": g.pick.market,
                "selection": g.pick.selection,
                "bookmaker_odd": g.pick.bookmaker_odd,
                "our_probability": g.pick.our_probability,
                "edge_pct": g.pick.edge_pct,
                "won": g.won,
                "profit_units": g.profit_units,
            }
            for g in all_graded
        ],
    }, indent=2, default=str))

    print(f"\n{'='*60}")
    print(f"BACKTEST SUMMARY  ({summary['n_picks']} picks, "
          f"{summary['n_graded']} graded)")
    print(f"{'='*60}")
    if summary["n_graded"]:
        print(f"  Win rate:    {summary['win_rate']:.1%}")
        print(f"  ROI:         {summary['roi_pct']:+.2f}%")
        print(f"  Total P/L:   {summary['total_profit_units']:+.2f} units")
        print(f"\nBy market:")
        for m, s in sorted(summary["by_market"].items()):
            print(f"  {m:30}  n={s['n']:3}  win={s['win_rate']:.1%}  ROI={s['roi_pct']:+.2f}%")
    print(f"\nReport: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
