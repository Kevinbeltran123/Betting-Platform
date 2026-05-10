"""CLI for inspecting + grading the picks SQLite DB.

Subcommands:
  list             List recent picks (default 30)
  pending          List pending (ungraded) picks
  fixture <id>     List all picks for one fixture
  grade <id>       Mark a pick won/lost/void
  place <id>       Mark pick as placed at Betano (bookmaker, stake, notes)
  stats            Aggregate ROI / win rate / by-market breakdown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.pick_tracker import (  # noqa: E402
    DEFAULT_DB_PATH,
    PickTracker,
    TrackedPick,
)


def _format_table(picks: list[TrackedPick]) -> str:
    if not picks:
        return "(no picks)"
    lines = []
    lines.append(
        f"{'ID':>5} {'EDGE%':>6} {'STATUS':<8} {'TS (UTC)':<19} "
        f"{'MATCH':<40} {'MIN':>3} {'MARKET':<25} {'SEL':<6} "
        f"{'ODD':>5} {'P':>5} {'STAKE%':>6}"
    )
    lines.append("-" * 150)
    for p in picks:
        match = f"{p.home_team[:18]} vs {p.away_team[:18]}"
        ts = p.emitted_at.split(".")[0]
        lines.append(
            f"{p.id:>5} {p.edge_pct:>+5.2f} {p.status:<8} {ts:<19} "
            f"{match:<40} {p.minute:>3} {p.market:<25} {p.selection:<6} "
            f"{p.bookmaker_odd:>5.2f} {p.our_probability:>5.3f} "
            f"{p.suggested_stake_pct:>5.2f}"
        )
    return "\n".join(lines)


def cmd_list(args, tracker: PickTracker) -> int:
    picks = tracker.list_recent(limit=args.limit)
    print(_format_table(picks))
    return 0


def cmd_pending(args, tracker: PickTracker) -> int:
    picks = tracker.list_pending()
    print(_format_table(picks))
    return 0


def cmd_fixture(args, tracker: PickTracker) -> int:
    picks = tracker.list_for_fixture(args.fixture_id)
    print(_format_table(picks))
    return 0


def cmd_grade(args, tracker: PickTracker) -> int:
    if args.status == "won":
        # Compute profit_units from bookmaker_odd unless overridden
        with tracker._connect() as conn:
            row = conn.execute(
                "SELECT bookmaker_odd FROM picks WHERE id=?", (args.pick_id,)
            ).fetchone()
            if not row:
                print(f"Pick {args.pick_id} not found")
                return 1
            profit = float(args.profit) if args.profit is not None else (row["bookmaker_odd"] - 1.0)
    elif args.status == "lost":
        profit = float(args.profit) if args.profit is not None else -1.0
    else:
        profit = 0.0
    tracker.update_outcome(args.pick_id, status=args.status, profit_units=profit)
    print(f"Pick {args.pick_id} → {args.status}  profit={profit:+.2f} units")
    return 0


def cmd_place(args, tracker: PickTracker) -> int:
    tracker.mark_placed(
        args.pick_id, betano_odd=args.odd,
        stake_units=args.stake, notes=args.notes,
    )
    print(f"Pick {args.pick_id} marked placed at Betano @ {args.odd}, stake={args.stake} units")
    return 0


def cmd_stats(args, tracker: PickTracker) -> int:
    s = tracker.stats_summary()
    print("=" * 70)
    print("PICK TRACKER — AGGREGATE STATS")
    print("=" * 70)
    print(f"  Total picks:              {s['n_total']}")
    print(f"  Graded picks:             {s['n_graded']}")
    print(f"  Placed at Betano:         {s['n_placed_betano']}")
    print(f"  Wins:                     {s['n_won']}")
    if s['win_rate'] is not None:
        print(f"  Win rate:                 {s['win_rate']:.1%}")
        print(f"  Total P/L (units):        {s['total_profit_units']:+.2f}")
        print(f"  ROI per pick:             {s['roi_pct']:+.2f}%")
    if s['by_market']:
        print()
        print(f"  {'MARKET':<28} {'N':>4} {'WINS':>5} {'WIN%':>6} {'ROI%':>7}")
        print("  " + "-" * 60)
        for m in sorted(s['by_market'], key=lambda x: -x['roi_pct']):
            print(
                f"  {m['market']:<28} {m['n']:>4} {m['wins']:>5} "
                f"{m['win_rate']:>5.1%} {m['roi_pct']:>+6.2f}"
            )
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)

    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List recent picks")
    p_list.add_argument("--limit", type=int, default=30)

    sub.add_parser("pending", help="List pending (ungraded) picks")

    p_fx = sub.add_parser("fixture", help="List picks for a fixture")
    p_fx.add_argument("fixture_id", type=int)

    p_grade = sub.add_parser("grade", help="Mark pick won/lost/void")
    p_grade.add_argument("pick_id", type=int)
    p_grade.add_argument("status", choices=["won", "lost", "void", "unknown"])
    p_grade.add_argument("--profit", type=float, default=None,
                          help="Override profit_units (default: derived from odd)")

    p_place = sub.add_parser("place", help="Mark pick placed at Betano")
    p_place.add_argument("pick_id", type=int)
    p_place.add_argument("--odd", type=float, required=True)
    p_place.add_argument("--stake", type=float, required=True,
                          help="Actual stake in units")
    p_place.add_argument("--notes", type=str, default="")

    sub.add_parser("stats", help="Aggregate stats")

    return p.parse_args()


def main() -> int:
    args = _parse_args()
    tracker = PickTracker(db_path=args.db_path)
    handlers = {
        "list": cmd_list, "pending": cmd_pending, "fixture": cmd_fixture,
        "grade": cmd_grade, "place": cmd_place, "stats": cmd_stats,
    }
    return handlers[args.cmd](args, tracker)


if __name__ == "__main__":
    sys.exit(main())
