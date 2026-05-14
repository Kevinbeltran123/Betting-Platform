"""Grade the REAL Day-4 v3 picks against outcomes derived from the GSV log.

Differs from grade_day3_replay.py: reads the actual picks.parquet that
the live watch loop persisted today, instead of regenerating picks from
the pipeline. Reflects "what we actually emitted" rather than "what the
pipeline would emit re-replayed".

Outcomes are reconstructed from the GSV log:
- Final score / corner / card totals from the latest GSV per fixture.
- goal_events timeline from score-transition detection across frames.
- Fixtures truncated before min 90 → picks marked "pending".

Usage:
    uv run python scripts/spike/v3/grade_day4_real.py
    uv run python scripts/spike/v3/grade_day4_real.py --date 2026-05-13
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.runtime.v3_grader import (  # noqa: E402
    grade_v3_pick,
    profit_units_for,
    status_for,
)
from bip.evaluation.live.grading import FinalOutcome  # noqa: E402


def reconstruct_outcome(gsvs: list[GameStateVector]) -> FinalOutcome:
    sorted_gsvs = sorted(gsvs, key=lambda g: g.state_version)
    final = sorted_gsvs[-1]
    home_id, away_id = final.home_team_id, final.away_team_id
    goal_events: list[tuple[int, int]] = []
    ph, pa = 0, 0
    for g in sorted_gsvs:
        h, a = g.score.home_goals, g.score.away_goals
        for _ in range(max(0, h - ph)):
            goal_events.append((g.time.minute, home_id))
        for _ in range(max(0, a - pa)):
            goal_events.append((g.time.minute, away_id))
        ph, pa = h, a
    h_1h = sum(1 for (m, t) in goal_events if m <= 45 and t == home_id)
    a_1h = sum(1 for (m, t) in goal_events if m <= 45 and t == away_id)
    is_finished = final.time.minute >= 90 or final.time.period in {
        "FT", "ET1", "ET2", "AET", "PEN",
    }
    return FinalOutcome(
        fixture_id=final.fixture_id, league_id=None,
        home_goals=final.score.home_goals, away_goals=final.score.away_goals,
        home_goals_first_half=h_1h, away_goals_first_half=a_1h,
        total_cards=sum(final.cards.yellows) + sum(final.cards.reds),
        total_corners=final.corners.corners_home + final.corners.corners_away,
        is_finished=is_finished,
        goal_events=tuple(goal_events),
        home_team_id=home_id, away_team_id=away_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-05-13")
    args = parser.parse_args()

    date = args.date
    picks_path = Path(f"data/cache/v3_shadow/dt={date}/picks.parquet")
    gsv_path = Path(f"data/cache/v3_shadow/dt={date}/gsv_log.parquet")

    if not picks_path.exists() or not gsv_path.exists():
        print(f"❌ Missing inputs: {picks_path} / {gsv_path}")
        return 1

    picks = pl.read_parquet(picks_path).to_dicts()
    gsv_df = pl.read_parquet(gsv_path)
    print(f"📥 Loaded {len(picks)} v3 picks from {picks_path}")
    print(f"📥 Loaded {gsv_df.height} GSVs from {gsv_path}")

    # Build outcomes per fixture from GSV log
    by_fid: dict[int, list[GameStateVector]] = defaultdict(list)
    for s in gsv_df["gsv_json"]:
        g = GameStateVector.model_validate_json(s)
        by_fid[g.fixture_id].append(g)
    outcomes = {fid: reconstruct_outcome(g_list) for fid, g_list in by_fid.items()}
    fix_names = {
        fid: f"{g_list[-1].home_team_name} vs {g_list[-1].away_team_name}"
        for fid, g_list in by_fid.items()
    }
    finished = sum(1 for o in outcomes.values() if o.is_finished)
    print(f"📋 Fixtures: {len(outcomes)} captured, {finished} finished, {len(outcomes)-finished} truncated\n")

    # Grade each pick
    graded: list[dict[str, Any]] = []
    for p in picks:
        # Map picks.parquet columns to grader interface
        pick_row = {
            "family": p["family"],
            "market_id": p["market_id"],
            "direction": p["direction"],
            "line_value": p.get("line_value"),
            "activated_at_minute": p.get("activated_at_minute"),
        }
        fid = p["fixture_id"]
        outcome = outcomes.get(fid)
        if outcome is None or not outcome.is_finished:
            graded.append({**p, "status": "pending", "won": None, "profit_units": 0.0, "grade_reason": "fixture_unfinished"})
            continue
        reason, won = grade_v3_pick(pick_row, outcome)
        if reason == "ungradable" or won is None:
            graded.append({**p, "status": "void", "won": None, "profit_units": 0.0, "grade_reason": reason})
            continue
        profit = profit_units_for(won, p.get("bookmaker_odd"))
        graded.append({**p, "status": status_for(won), "won": won, "profit_units": profit, "grade_reason": reason})

    # ── Dedup: 1 pick per (fixture × archetype × market_id) ─────────────
    # The pipeline (post-T1 fix) emits at most once per trio. For
    # historical Day-4 picks captured pre-T1, we collapse re-emissions
    # to the earliest activation here. ALL HEADLINE METRICS use the
    # dedup'd view — this is what reflects operational reality (the
    # operator places 1 bet per trio, not 11).
    dedup_picks: dict[tuple, dict] = {}
    for g in graded:
        key = (g["fixture_id"], g["archetype"], g["market_id"])
        if (key not in dedup_picks
                or g.get("activated_at_minute", 999)
                < dedup_picks[key].get("activated_at_minute", 999)):
            dedup_picks[key] = g
    dedup_list = list(dedup_picks.values())
    dedup_settled = [g for g in dedup_list if g["status"] in ("won", "lost")]
    n_won = sum(1 for g in dedup_settled if g["status"] == "won")
    n_lost = len(dedup_settled) - n_won
    n_pending = sum(1 for g in dedup_list if g["status"] == "pending")
    n_void = sum(1 for g in dedup_list if g["status"] == "void")
    pl_settled = sum(g["profit_units"] for g in dedup_settled)
    bk_odds = [g["bookmaker_odd"] for g in dedup_list if g.get("bookmaker_odd")]
    avg_odd = sum(bk_odds) / max(len(bk_odds), 1)

    # Stream-count (raw) is informational only: it tells us how often
    # each trio was re-emitted before T1 dedup. Useful for diagnosing
    # whether the pipeline regression has actually shipped.
    raw_count = len(graded)

    # ── Aggregate report ────────────────────────────────────────────────
    print("=" * 80)
    print(f"DAY-4 ({date}) v3 PICKS — GRADING REPORT (DEDUP'D HEADLINE)")
    print("=" * 80)
    print(f"  Total picks (unique trios):    {len(dedup_list)}")
    print(f"    Settled (won/lost):          {len(dedup_settled)}  "
          f"({100*len(dedup_settled)/max(len(dedup_list),1):.1f}%)")
    print(f"      Won:                       {n_won}")
    print(f"      Lost:                      {n_lost}")
    print(f"    Pending (truncated):         {n_pending}")
    print(f"    Void / ungradable:           {n_void}")
    print()
    print(f"  Win rate (settled):    {100*n_won/max(n_won+n_lost,1):.1f}%")
    print(f"  P/L (settled):         {pl_settled:+.2f}u")
    print(f"  ROI (settled):         {100*pl_settled/max(len(dedup_settled),1):+.2f}%")
    print(f"  Avg book odd:          {avg_odd:.2f}")
    print()
    print(f"  ── Stream diagnostic (informational, not betting metrics) ──")
    print(f"  Raw emission rows:     {raw_count}  "
          f"(re-emission factor {raw_count/max(len(dedup_list),1):.1f}×)")
    print(f"  Post-T1 fix, this should drop to {len(dedup_list)} on Day-5+.")

    # By archetype — dedup'd
    print("\n=== By archetype (settled only, dedup'd) ===")
    print(f"  {'archetype':<28} {'n':>4} {'won':>4} {'lost':>4} {'wr':>6} {'pl':>8} {'roi':>7}")
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for g in dedup_settled:
        by_arch[g["archetype"]].append(g)
    for arch, items in sorted(by_arch.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        lost = len(items) - won
        pl_arch = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        roi = 100 * pl_arch / max(len(items), 1)
        print(f"  {arch:<28} {len(items):>4} {won:>4} {lost:>4} {wr:>5.1f}% {pl_arch:>+7.2f}u {roi:>+6.2f}%")

    # By family — dedup'd
    print("\n=== By family (settled only, dedup'd) ===")
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for g in dedup_settled:
        by_fam[g["family"]].append(g)
    for fam, items in sorted(by_fam.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_fam = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        roi = 100 * pl_fam / max(len(items), 1)
        print(f"  {fam:<14} {len(items):>4} {wr:>5.1f}% {pl_fam:>+7.2f}u {roi:>+6.2f}%")

    # By fixture — dedup'd
    print("\n=== By fixture (settled only, dedup'd) ===")
    by_fix: dict[int, list[dict]] = defaultdict(list)
    for g in dedup_settled:
        by_fix[g["fixture_id"]].append(g)
    for fid, items in sorted(by_fix.items(), key=lambda x: -sum(i["profit_units"] for i in x[1])):
        won = sum(1 for i in items if i["status"] == "won")
        pl_fix = sum(i["profit_units"] for i in items)
        wr = 100 * won / max(len(items), 1)
        print(f"  {fid:>10} {fix_names.get(fid,'?')[:48]:<48} {len(items):>4} {wr:>5.1f}% {pl_fix:>+7.2f}u")

    # Top winning + losing picks (dedup'd already by construction)
    print("\n=== Top 10 winning picks ===")
    winners = sorted([g for g in dedup_settled if g["status"] == "won"], key=lambda g: -g["profit_units"])[:10]
    for w in winners:
        print(f"  {w['fixture_id']} {fix_names.get(w['fixture_id'],'?')[:30]:<30} "
              f"min={w.get('activated_at_minute', '?'):>3} "
              f"{w['archetype'][:22]:<22} {w['market_id'][:38]:<38} odd={w['bookmaker_odd']:.2f} +{w['profit_units']:.2f}u")
    print("\n=== Top 10 losing picks ===")
    losers = sorted([g for g in dedup_settled if g["status"] == "lost"], key=lambda g: g["profit_units"])[:10]
    for l in losers:
        print(f"  {l['fixture_id']} {fix_names.get(l['fixture_id'],'?')[:30]:<30} "
              f"min={l.get('activated_at_minute', '?'):>3} "
              f"{l['archetype'][:22]:<22} {l['market_id'][:38]:<38} odd={l['bookmaker_odd']:.2f} {l['profit_units']:.2f}u")

    # Persist BOTH views: dedup'd (the headline) + raw (stream/diagnostic).
    out_dedup = Path(f"logs/v3_day4_graded_dedup.parquet")
    out_raw = Path(f"logs/v3_day4_graded.parquet")
    pl.DataFrame(dedup_list).write_parquet(out_dedup)
    pl.DataFrame(graded).write_parquet(out_raw)
    print(f"\nPersisted: {out_dedup}  (headline / dedup'd)")
    print(f"Persisted: {out_raw}  (raw stream — diagnostic only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
