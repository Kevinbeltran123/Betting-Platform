"""Grade the Day-3 replay picks against the in-shadow-log outcomes.

The Day-3 silence diagnostic + Phase-2 ship means v3 never persisted
picks.parquet for Day-3 (it emitted zero). The replay generates picks
in memory. To answer "if we had taken these 207 picks, how many would
have won?" we need to:

1. Generate the picks (same path as scripts/spike/v3/replay_today_with_committed_fixes.py).
2. Reconstruct each fixture's FinalOutcome from the GSV log — the last
   GSV per fixture carries final score/corners/cards. Goal events are
   reconstructed by walking the GSV history and detecting score changes.
3. Grade each pick via the existing v3 grader (``grade_v3_pick``).
4. Compute profit per pick using the bookmaker odd at the time of the
   pick (we have ``line.side_a_decimal`` from the GSV snapshot).

Caveats:
- Some Day-3 fixtures (Winterthur vs Grasshopper, etc.) only logged up
  to minute 81 — the watch loop was stopped before FT. Picks for those
  fixtures whose outcome depends on remaining minutes are flagged as
  "pending" rather than graded.
- We use the closing line as the book odd (side_a_decimal at the time
  the pick fires). Real production uses CLV against Pinnacle; this is
  a defensible approximation for a single-day backtest.

Usage:
    uv run python scripts/spike/v3/grade_day3_replay.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.archetypes import generate_theses  # noqa: E402
from bip.evaluation.live.engine_v3.calibrator import IsotonicCalibrator  # noqa: E402
from bip.evaluation.live.engine_v3.conditional_predictor import (  # noqa: E402
    ConditionalPredictor,
    make_fair_prob_provider,
)
from bip.evaluation.live.engine_v3.drift_monitor import (  # noqa: E402
    CalibrationDriftMonitor,
)
from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.market_selector import select_markets  # noqa: E402
from bip.evaluation.live.engine_v3.no_bet_gate import run_gate  # noqa: E402
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402
from bip.evaluation.live.engine_v3.runtime.v3_grader import (  # noqa: E402
    grade_v3_pick,
    profit_units_for,
    status_for,
)
from bip.evaluation.live.grading import FinalOutcome  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Outcome reconstruction from the GSV log
# ──────────────────────────────────────────────────────────────────────


def reconstruct_outcome(gsvs_for_fixture: list[GameStateVector]) -> FinalOutcome:
    """Build a FinalOutcome from the (chronologically sorted) GSV log of
    one fixture.

    - The FINAL state is taken from the highest-state_version GSV.
    - The goal_events timeline is reconstructed by detecting transitions
      in score across GSV rows: when home_goals or away_goals increments
      between consecutive GSVs, we emit (minute, team_id).
    - is_finished is True if the last GSV's minute >= 90 OR period in
      {FT, ET2, AET, PEN} (typical Sportmonks final markers).
    """
    sorted_gsvs = sorted(gsvs_for_fixture, key=lambda g: g.state_version)
    if not sorted_gsvs:
        raise ValueError("empty GSV list")
    final = sorted_gsvs[-1]
    home_id = final.home_team_id
    away_id = final.away_team_id

    # Goal events from score transitions
    goal_events: list[tuple[int, int]] = []
    prev_h, prev_a = 0, 0
    for g in sorted_gsvs:
        h, a = g.score.home_goals, g.score.away_goals
        if h > prev_h:
            for _ in range(h - prev_h):
                goal_events.append((g.time.minute, home_id))
        if a > prev_a:
            for _ in range(a - prev_a):
                goal_events.append((g.time.minute, away_id))
        prev_h, prev_a = h, a

    # First-half goals: count events with minute <= 45 (HT inclusive)
    h_1h = sum(1 for (m, t) in goal_events if m <= 45 and t == home_id)
    a_1h = sum(1 for (m, t) in goal_events if m <= 45 and t == away_id)

    total_corners = final.corners.corners_home + final.corners.corners_away
    total_cards = sum(final.cards.yellows) + sum(final.cards.reds)
    is_finished = final.time.minute >= 90 or final.time.period in {
        "FT",
        "ET2",
        "AET",
        "PEN",
        "ET1",  # extra-time first half is also a "we got there" signal
    }

    return FinalOutcome(
        fixture_id=final.fixture_id,
        league_id=None,
        home_goals=final.score.home_goals,
        away_goals=final.score.away_goals,
        home_goals_first_half=h_1h,
        away_goals_first_half=a_1h,
        total_cards=total_cards,
        total_corners=total_corners,
        is_finished=is_finished,
        goal_events=tuple(goal_events),
        home_team_id=home_id,
        away_team_id=away_id,
    )


# ──────────────────────────────────────────────────────────────────────
# Pick generation (mirrors replay_today_with_committed_fixes.py)
# ──────────────────────────────────────────────────────────────────────


def generate_picks(gsvs: list[GameStateVector]) -> list[dict[str, Any]]:
    """Run the full v3 pipeline frame-by-frame and emit one row per
    allowed pick. Each row carries everything needed to grade it
    later, including the side_a_decimal at the time of the pick.
    """
    ood = OODDetector.load("data/cache/ood_detector_v2_real.pkl")
    calibrator = IsotonicCalibrator.load("data/cache/isotonic_calibrator_v1.pkl")
    drift = CalibrationDriftMonitor()
    drift.warm_up_from_v2_history(
        Path("reports/sportmonks_live/exports/picks_graded.parquet")
    )
    predictor = ConditionalPredictor.default(calibrator=calibrator)
    provider = make_fair_prob_provider(predictor)

    picks: list[dict[str, Any]] = []
    for g in gsvs:
        theses = generate_theses(g)
        if not theses:
            continue
        cands = select_markets(
            theses, g, provider, top_k=3, target_stake=100.0, mes_threshold=0.6
        )
        if not cands:
            continue
        gate_results = run_gate(
            theses,
            cands,
            g,
            mes_threshold=0.6,
            line_max_age_sec=None,  # family-specific
            ood_detector=ood,
            drift_monitor=drift,
        )
        for r in gate_results:
            if not r.verdict.allowed:
                continue
            c = r.candidate
            line = g.markets.lines.get(c.market_id)
            book_odd = line.side_a_decimal if line else None
            picks.append(
                {
                    "fixture_id": g.fixture_id,
                    "minute": g.time.minute,
                    "score": f"{g.score.home_goals}-{g.score.away_goals}",
                    "dominant_losing": g.score.dominant_losing,
                    "archetype": c.thesis.archetype.value,
                    "family": c.family.value,
                    "market_id": c.market_id,
                    "direction": c.thesis.prediction.direction,
                    "mes": c.mes.score,
                    "base_edge": c.mes.base_edge,
                    "fair_prob": c.fair_prob,
                    "book_odd": book_odd,
                    "line_value": line.line_value if line else None,
                    "activated_at_minute": c.thesis.activated_at_minute,
                }
            )
    return picks


# ──────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    src = Path("data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet")
    df = pl.read_parquet(src)
    gsvs = [GameStateVector.model_validate_json(s) for s in df["gsv_json"]]
    print(f"Loaded {len(gsvs)} GSVs from {len({g.fixture_id for g in gsvs})} fixtures")

    # 1) generate picks
    print("Generating v3 picks…")
    picks = generate_picks(gsvs)
    print(f"  Generated {len(picks)} picks")

    # 2) per-fixture outcomes
    print("Reconstructing fixture outcomes from GSV log…")
    by_fid: dict[int, list[GameStateVector]] = defaultdict(list)
    for g in gsvs:
        by_fid[g.fixture_id].append(g)
    outcomes: dict[int, FinalOutcome] = {
        fid: reconstruct_outcome(g_list) for fid, g_list in by_fid.items()
    }
    finished_count = sum(1 for o in outcomes.values() if o.is_finished)
    pending_count = len(outcomes) - finished_count
    print(f"  {finished_count} fixtures finished, {pending_count} truncated/pending")

    # 3) grade picks
    print("Grading picks…")
    graded: list[dict[str, Any]] = []
    ungradable_reasons: Counter[str] = Counter()
    for p in picks:
        fid = p["fixture_id"]
        outcome = outcomes.get(fid)
        if outcome is None or not outcome.is_finished:
            graded.append({**p, "status": "pending", "won": None, "profit_units": 0.0})
            ungradable_reasons["fixture_not_finished"] += 1
            continue
        reason, won = grade_v3_pick(p, outcome)
        if reason == "ungradable" or won is None:
            graded.append({**p, "status": "void", "won": None, "profit_units": 0.0})
            ungradable_reasons[reason] += 1
            continue
        profit = profit_units_for(won, p.get("book_odd"))
        graded.append(
            {**p, "status": status_for(won), "won": won, "profit_units": profit}
        )

    # 4) Aggregate report
    print()
    print("=" * 80)
    print("DAY-3 REPLAY GRADING REPORT")
    print("=" * 80)
    settled = [g for g in graded if g["status"] in ("won", "lost")]
    n_won = sum(1 for g in settled if g["status"] == "won")
    n_lost = sum(1 for g in settled if g["status"] == "lost")
    n_pending = sum(1 for g in graded if g["status"] == "pending")
    n_void = sum(1 for g in graded if g["status"] == "void")
    pl_total = sum(g["profit_units"] for g in graded)
    pl_settled = sum(g["profit_units"] for g in settled)
    avg_odd = sum(g["book_odd"] for g in graded if g["book_odd"]) / max(
        sum(1 for g in graded if g["book_odd"]), 1
    )

    print(f"  total picks generated:  {len(graded)}")
    print(f"  settled (won + lost):    {len(settled)}  ({100*len(settled)/max(len(graded),1):.1f}%)")
    print(f"    won:                   {n_won}")
    print(f"    lost:                  {n_lost}")
    print(f"  pending (fixture cut):   {n_pending}")
    print(f"  void / ungradable:       {n_void}")
    print()
    print(f"  Win rate (settled):      {100*n_won/max(n_won+n_lost,1):.1f}%")
    print(f"  Total P/L (settled):     {pl_settled:+.2f}u")
    print(f"  ROI (settled):           {100*pl_settled/max(len(settled),1):+.2f}%")
    print(f"  Avg book odd:            {avg_odd:.2f}")

    # By archetype
    print()
    print("=== By archetype (settled only) ===")
    print(f"  {'archetype':<28} {'n':>4} {'won':>4} {'lost':>4} {'wr':>6} {'pl':>8} {'roi':>7}")
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for g in settled:
        by_arch[g["archetype"]].append(g)
    for arch, items in sorted(by_arch.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        lost = len(items) - won
        pl_value = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        roi = 100 * pl_value / max(len(items), 1)
        print(f"  {arch:<28} {len(items):>4} {won:>4} {lost:>4} {wr:>5.1f}% {pl_value:>+7.2f}u {roi:>+6.2f}%")

    # By family
    print()
    print("=== By family (settled only) ===")
    print(f"  {'family':<14} {'n':>4} {'wr':>6} {'pl':>8} {'roi':>7}")
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for g in settled:
        by_fam[g["family"]].append(g)
    for fam, items in sorted(by_fam.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_value = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        roi = 100 * pl_value / max(len(items), 1)
        print(f"  {fam:<14} {len(items):>4} {wr:>5.1f}% {pl_value:>+7.2f}u {roi:>+6.2f}%")

    # By fixture
    print()
    print("=== By fixture (settled only) ===")
    print(f"  {'fid':>10} {'fixture':<55} {'n':>4} {'wr':>6} {'pl':>8}")
    by_fix: dict[int, list[dict]] = defaultdict(list)
    fix_names: dict[int, str] = {}
    for g in gsvs:
        fix_names[g.fixture_id] = f"{g.home_team_name} vs {g.away_team_name}"
    for g in settled:
        by_fix[g["fixture_id"]].append(g)
    for fid, items in sorted(by_fix.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_value = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        name = fix_names.get(fid, "?")
        print(f"  {fid:>10} {name[:53]:<55} {len(items):>4} {wr:>5.1f}% {pl_value:>+7.2f}u")

    # Top winning & losing picks
    print()
    print("=== Top 10 winning picks ===")
    winners = sorted([g for g in settled if g["status"] == "won"],
                     key=lambda g: -g["profit_units"])[:10]
    for w in winners:
        print(f"  {w['fixture_id']} {fix_names.get(w['fixture_id'], '?')[:30]:<30}  "
              f"min={w['minute']:>3} {w['score']:<5} {w['archetype']:<28} "
              f"{w['market_id'][:38]:<38} odd={w['book_odd']:.2f} pl=+{w['profit_units']:.2f}u")
    print()
    print("=== Top 10 losing picks ===")
    losers = sorted([g for g in settled if g["status"] == "lost"],
                    key=lambda g: g["profit_units"])[:10]
    for l in losers:
        print(f"  {l['fixture_id']} {fix_names.get(l['fixture_id'], '?')[:30]:<30}  "
              f"min={l['minute']:>3} {l['score']:<5} {l['archetype']:<28} "
              f"{l['market_id'][:38]:<38} odd={l['book_odd']:.2f} pl={l['profit_units']:.2f}u")

    # Persist for analysis
    out_path = Path("logs/v3_day3_replay_graded.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(graded).write_parquet(out_path)
    print(f"\nPersisted full graded picks to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
