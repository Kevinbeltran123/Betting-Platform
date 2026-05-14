"""Re-grade Day-4 (2026-05-13) v3 picks from the raw Sportmonks cache.

WHY a re-grade is necessary:
    The home/away identification bug (fixed in commit abb4a16) corrupted
    9 of 31 Day-4 fixtures — most visibly Crystal Palace vs Man City,
    where we displayed "Palace 3-0 City" for what was actually a 3-0
    City win. The previous grade run (logs/v3_day4_graded.parquet)
    treated picks against the wrong home/away assignment and therefore
    graded the wrong outcomes for those 9 fixtures.

WHAT this script does:
    1. Walk every raw Sportmonks snapshot for each Day-4 fixture
       (data/cache/sportmonks/snapshots/<fixture_id>/*.json).
    2. Re-parse each frame with the fixed parser (home/away derived
       from scores cross-reference, not array order).
    3. Run V3Pipeline.run() against each frame so dedup is applied
       just like production.
    4. Reconstruct outcomes from the last frame per fixture.
    5. Grade the dedup'd pick set.

Compare with the (contaminated) previous report to see what flipped.

Usage:
    uv run python scripts/spike/v3/regrade_day4_from_raw.py
    uv run python scripts/spike/v3/regrade_day4_from_raw.py --date 2026-05-13
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.calibrator import IsotonicCalibrator  # noqa: E402
from bip.evaluation.live.engine_v3.conditional_predictor import (  # noqa: E402
    ConditionalPredictor,
)
from bip.evaluation.live.engine_v3.drift_monitor import (  # noqa: E402
    CalibrationDriftMonitor,
)
from bip.evaluation.live.engine_v3.mispricing_window import (  # noqa: E402
    MispricingWindowConfig,
)
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402
from bip.evaluation.live.engine_v3.pipeline import V3Pipeline  # noqa: E402
from bip.evaluation.live.engine_v3.runtime.dual_write import (  # noqa: E402
    derive_priors_from_fixture,
    market_snapshot_from_odds,
)
from bip.evaluation.live.engine_v3.shadow_logger import _pick_row  # noqa: E402
from bip.evaluation.live.engine_v3.runtime.v3_grader import (  # noqa: E402
    grade_v3_pick,
    profit_units_for,
    status_for,
)
from bip.evaluation.live.grading import FinalOutcome  # noqa: E402
from bip.evaluation.live.match_state import LiveMatchState  # noqa: E402
from bip.sports.football.sportmonks.schemas import Fixture, Odd  # noqa: E402


_FNAME_TS = re.compile(r"^(\d{8})T(\d{6})Z\.json$")


def _ts_from_fname(fname: str) -> datetime | None:
    """Parse the snapshot timestamp from its filename."""
    m = _FNAME_TS.match(fname)
    if not m:
        return None
    d, t = m.group(1), m.group(2)
    return datetime(
        int(d[:4]), int(d[4:6]), int(d[6:8]),
        int(t[:2]), int(t[2:4]), int(t[4:6]),
        tzinfo=timezone.utc,
    )


def _snapshots_for_date(snapshots_root: Path, date: str) -> dict[int, list[Path]]:
    """Map fixture_id → ordered list of snapshot paths for the date."""
    date_prefix = date.replace("-", "")
    out: dict[int, list[Path]] = {}
    for fix_dir in snapshots_root.iterdir():
        if not fix_dir.is_dir() or not fix_dir.name.isdigit():
            continue
        files = sorted(fix_dir.glob(f"{date_prefix}T*.json"))
        if files:
            out[int(fix_dir.name)] = files
    return out


def _reconstruct_outcome(final_state: LiveMatchState) -> FinalOutcome:
    """Build a FinalOutcome from the last LiveMatchState we observed.

    Goal events are taken directly from the state — they preserve the
    per-team scorer attribution we need for next_goal grading.
    """
    h_1h = sum(1 for (m, t) in final_state.goal_events
               if m <= 45 and t == final_state.home_team_id)
    a_1h = sum(1 for (m, t) in final_state.goal_events
               if m <= 45 and t == final_state.away_team_id)
    total_cards = 0  # approximated downstream — cards aren't graded here
    # corner / card totals from raw stats if present
    from bip.sports.football.sportmonks.types import StatType
    total_corners = int(final_state.home_stats.get(StatType.CORNERS, 0)) \
        + int(final_state.away_stats.get(StatType.CORNERS, 0))
    total_yellows = int(final_state.home_stats.get(StatType.YELLOW_CARDS, 0)) \
        + int(final_state.away_stats.get(StatType.YELLOW_CARDS, 0))
    total_reds = sum(1 for _m, _t in final_state.red_card_events)
    return FinalOutcome(
        fixture_id=final_state.fixture_id,
        league_id=final_state.league_id,
        home_goals=final_state.home_goals,
        away_goals=final_state.away_goals,
        home_goals_first_half=h_1h,
        away_goals_first_half=a_1h,
        total_cards=total_yellows + total_reds,
        total_corners=total_corners,
        is_finished=final_state.is_finished or final_state.minute >= 90,
        goal_events=tuple(final_state.goal_events),
        home_team_id=final_state.home_team_id,
        away_team_id=final_state.away_team_id,
    )


def _build_pipeline() -> V3Pipeline:
    """Wire the pipeline with the same detectors production uses."""
    ood_path = Path("data/cache/ood_detector_v2_real.pkl")
    cal_path = Path("data/cache/isotonic_calibrator_v1.pkl")
    v2_picks_path = Path("reports/sportmonks_live/exports/picks_graded.parquet")

    ood = OODDetector.load(ood_path) if ood_path.exists() else None
    calibrator = IsotonicCalibrator.load(cal_path) if cal_path.exists() else None
    predictor = ConditionalPredictor.default(calibrator=calibrator)

    drift_monitor = None
    if v2_picks_path.exists():
        drift_monitor = CalibrationDriftMonitor()
        drift_monitor.warm_up_from_v2_history(v2_picks_path)

    return V3Pipeline(
        conditional_predictor=predictor,
        ood_detector=ood,
        drift_monitor=drift_monitor,
        mispricing_window_cfg=MispricingWindowConfig(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-05-13")
    parser.add_argument("--snapshots-root", type=Path,
                        default=Path("data/cache/sportmonks/snapshots"))
    args = parser.parse_args()

    fixtures = _snapshots_for_date(args.snapshots_root, args.date)
    print(f"📥 Found {len(fixtures)} fixtures with raw snapshots for {args.date}")
    if not fixtures:
        print("Nothing to regrade.")
        return 1

    pipeline = _build_pipeline()
    all_picks: list[dict[str, Any]] = []
    outcomes: dict[int, FinalOutcome] = {}
    fix_names: dict[int, str] = {}
    home_away_flips = 0
    parse_errors = 0

    for fix_id, files in sorted(fixtures.items()):
        last_state: LiveMatchState | None = None
        for path in files:
            try:
                raw = json.loads(path.read_text())
            except Exception:
                parse_errors += 1
                continue
            fx_data = raw.get("data", raw)
            try:
                fx = Fixture.model_validate(fx_data)
                state = LiveMatchState.from_fixture(fx)
            except Exception:
                parse_errors += 1
                continue
            ts = _ts_from_fname(path.name) or datetime.now(timezone.utc)
            priors = derive_priors_from_fixture(fx)
            # Odds are persisted alongside the fixture, not inside it.
            odds_raw = raw.get("odds_snapshot") or []
            odds: list[Odd] = []
            for o in odds_raw:
                try:
                    odds.append(Odd.model_validate(o))
                except Exception:
                    continue
            markets = market_snapshot_from_odds(odds, captured_at=ts)
            if not markets.lines:
                last_state = state
                continue
            out = pipeline.run(
                state,
                priors=priors,
                markets=markets,
                now_utc=ts,
            )
            # Use ShadowLogger's exact row builder so the regrade has
            # the same schema as production picks.parquet (including
            # derived bookmaker_odd / line_value from market lines).
            for pick in out.allowed_picks:
                all_picks.append(_pick_row(pick, fix_id, ts, out.gsv))
            last_state = state
        if last_state is not None:
            outcomes[fix_id] = _reconstruct_outcome(last_state)
            fix_names[fix_id] = (
                f"{last_state.home_team_name} vs {last_state.away_team_name}"
            )

    # Compare home/away with the old gsv_log to count flips.
    old_gsv_path = Path(f"data/cache/v3_shadow/dt={args.date}/gsv_log.parquet")
    if old_gsv_path.exists():
        from bip.evaluation.live.engine_v3.gsv import GameStateVector
        old_g = pl.read_parquet(old_gsv_path)
        old_last = (old_g.sort(["fixture_id", "state_version"])
                    .group_by("fixture_id", maintain_order=True).last())
        for row in old_last.iter_rows(named=True):
            old_gsv = GameStateVector.model_validate_json(row["gsv_json"])
            new_state = None
            for fx_id, _ in fixtures.items():
                if fx_id == old_gsv.fixture_id:
                    pass
            # Just compare home_team_id between old and new
            if old_gsv.fixture_id in fix_names:
                new_name = fix_names[old_gsv.fixture_id]
                old_name = f"{old_gsv.home_team_name} vs {old_gsv.away_team_name}"
                if new_name != old_name:
                    home_away_flips += 1

    print(f"📋 Fixtures processed: {len(outcomes)}  "
          f"home/away flipped vs old run: {home_away_flips}  "
          f"parse errors: {parse_errors}")

    # ── Dedup picks before grading ──────────────────────────────────────
    dedup_picks: dict[tuple, dict] = {}
    for p in all_picks:
        key = (p["fixture_id"], p["archetype"], p["market_id"])
        if (key not in dedup_picks
                or p.get("activated_at_minute", 999)
                < dedup_picks[key].get("activated_at_minute", 999)):
            dedup_picks[key] = p
    dedup_list = list(dedup_picks.values())

    # Grade each pick
    graded: list[dict[str, Any]] = []
    for p in dedup_list:
        pick_row = {
            "family": p["family"],
            "market_id": p["market_id"],
            "direction": p["direction"],
            "line_value": p.get("line_value"),
            "activated_at_minute": p.get("activated_at_minute"),
        }
        outcome = outcomes.get(p["fixture_id"])
        if outcome is None or not outcome.is_finished:
            graded.append({**p, "status": "pending", "won": None,
                           "profit_units": 0.0, "grade_reason": "fixture_unfinished"})
            continue
        reason, won = grade_v3_pick(pick_row, outcome)
        if reason == "ungradable" or won is None:
            graded.append({**p, "status": "void", "won": None,
                           "profit_units": 0.0, "grade_reason": reason})
            continue
        profit = profit_units_for(won, p.get("bookmaker_odd"))
        graded.append({**p, "status": status_for(won), "won": won,
                       "profit_units": profit, "grade_reason": reason})

    settled = [g for g in graded if g["status"] in ("won", "lost")]
    n_won = sum(1 for g in settled if g["status"] == "won")
    n_lost = len(settled) - n_won
    pl_settled = sum(g["profit_units"] for g in settled)

    # ── Headline report ─────────────────────────────────────────────────
    print()
    print("=" * 80)
    print(f"DAY-4 ({args.date}) RE-GRADE FROM RAW (with home/away fix)")
    print("=" * 80)
    print(f"  Raw stream emissions:          {len(all_picks)}")
    print(f"  Unique trios (dedup'd):        {len(dedup_list)}")
    print(f"  Settled (won/lost):            {len(settled)}")
    print(f"    Won / Lost:                  {n_won} / {n_lost}")
    print(f"  Pending (truncated):           "
          f"{sum(1 for g in graded if g['status'] == 'pending')}")
    print(f"  Void / ungradable:             "
          f"{sum(1 for g in graded if g['status'] == 'void')}")
    print()
    print(f"  Win rate (settled):    {100 * n_won / max(n_won + n_lost, 1):.1f}%")
    print(f"  P/L (settled):         {pl_settled:+.2f}u")
    print(f"  ROI (settled):         "
          f"{100 * pl_settled / max(len(settled), 1):+.2f}%")

    # By archetype
    print("\n=== By archetype (settled only) ===")
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for g in settled:
        by_arch[g["archetype"]].append(g)
    for arch, items in sorted(by_arch.items(),
                              key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_arch = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        roi = 100 * pl_arch / max(len(items), 1)
        print(f"  {arch:<28} n={len(items):>3}  wr={wr:>5.1f}%  "
              f"P/L={pl_arch:>+7.2f}u  ROI={roi:>+6.2f}%")

    # By fixture
    print("\n=== By fixture (settled only) ===")
    by_fix: dict[int, list[dict]] = defaultdict(list)
    for g in settled:
        by_fix[g["fixture_id"]].append(g)
    for fid, items in sorted(by_fix.items(),
                             key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_fix = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        print(f"  {fid:>10}  {fix_names.get(fid, '?')[:48]:<48}  "
              f"n={len(items):>2}  wr={wr:>5.1f}%  P/L={pl_fix:>+7.2f}u")

    # Persist
    out_path = Path("logs/v3_day4_regraded_dedup.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(graded).write_parquet(out_path)
    print(f"\nPersisted: {out_path}")

    # Side-by-side with old (contaminated) numbers
    old_graded_path = Path("logs/v3_day4_graded_dedup.parquet")
    if old_graded_path.exists():
        old = pl.read_parquet(old_graded_path)
        old_settled = old.filter(pl.col("status").is_in(["won", "lost"]))
        old_won = old_settled.filter(pl.col("status") == "won").height
        old_pl = old_settled["profit_units"].sum()
        print()
        print("=" * 80)
        print("DELTA vs OLD CONTAMINATED RUN")
        print("=" * 80)
        print(f"  Picks (dedup'd):    {old.height} → {len(dedup_list)}  "
              f"({len(dedup_list) - old.height:+d})")
        print(f"  Won:                {old_won} → {n_won}  "
              f"({n_won - old_won:+d})")
        print(f"  P/L:                {old_pl:+.2f}u → {pl_settled:+.2f}u  "
              f"({pl_settled - old_pl:+.2f}u)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
