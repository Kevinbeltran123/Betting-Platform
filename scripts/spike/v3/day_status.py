"""One-shot Day-N status report.

Reads:
  - data/cache/v3_shadow/dt=YYYY-MM-DD/gsv_log.parquet  (live GSVs)
  - data/cache/v3_shadow/dt=YYYY-MM-DD/picks.parquet    (v3 picks, if any)
  - logs/watch_day{N}_stdout.log                         (watch loop stdout)

Prints a compact summary:
  - Fixtures captured and their latest state (min/score/dom_los)
  - v3 picks emitted today (count + breakdown)
  - v2 picks emitted today (distinct trios, edge, flagged)
  - For each fixture, the active v3 archetype hypothesis (or "none")

Usage:
  uv run python scripts/spike/v3/day_status.py
  uv run python scripts/spike/v3/day_status.py --date 2026-05-13
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.archetypes import generate_theses  # noqa: E402
from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402


PICK_LINE_RE = re.compile(
    r"NEW PICK:\s+\+([\d.]+)%\s+(.*?)\s+\(min (\d+)\)\s+(\S+?)\s+@ ([\d.]+).*?id=(\d+)(?:.*?FLAGGED:\s*(\S+))?"
)


def parse_v2_picks_from_log(log_path: Path) -> list[dict]:
    """Extract all "NEW PICK" lines from watch.py stdout."""
    if not log_path.exists():
        return []
    picks = []
    for line in log_path.read_text(errors="ignore").splitlines():
        m = PICK_LINE_RE.search(line)
        if not m:
            continue
        edge_pct, fixture, minute, market_sel, odd, pid, flagged = m.groups()
        market, selection = market_sel.split("/", 1) if "/" in market_sel else (market_sel, "")
        picks.append({
            "id": int(pid),
            "fixture": fixture,
            "minute": int(minute),
            "market": market,
            "selection": selection,
            "edge_pct": float(edge_pct),
            "odd": float(odd),
            "flagged": flagged or "",
        })
    return picks


def latest_gsv_per_fixture(df: pl.DataFrame) -> dict[int, GameStateVector]:
    latest_rows = (
        df.sort("state_version", descending=True)
        .group_by("fixture_id")
        .agg(pl.first("gsv_json"))
        .to_dicts()
    )
    return {r["fixture_id"]: GameStateVector.model_validate_json(r["gsv_json"]) for r in latest_rows}


def archetype_hint(g: GameStateVector) -> str:
    """One-line hint about why no thesis fires, or which one fires."""
    theses = generate_theses(g)
    if theses:
        return ", ".join(f"{t.archetype.value}({t.prediction.family.value}/{t.prediction.direction})" for t in theses)
    # Diagnose nearest missing condition
    if not g.score.dominant_losing:
        if g.score.goal_diff == 0:
            return "tied → no napoli; awaiting score change"
        return f"dominant winning (diff={g.score.goal_diff}) → no napoli; possible cruise after min 80"
    # dominant_losing=True — close to A2 maybe
    if g.time.minute > 45:
        return "dom_losing but past A2 window [25,45]; needs A10 (formation change) or A7 (late siege)"
    if abs(g.xg.xg_vs_score_divergence) < 0.3:
        return f"dom_losing but |xg_div|={g.xg.xg_vs_score_divergence:+.2f} below 0.3 threshold"
    return "near-A2 candidate; conditions converging"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--day-n", type=int, default=4, help="Day-N for log file naming (default 4)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"╔══════════════════════════════════════════════════════════════════════════════")
    print(f"║ Day-{args.day_n} status — {date_str}  (now {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC)")
    print(f"╚══════════════════════════════════════════════════════════════════════════════")

    # GSV log
    gsv_path = Path(f"data/cache/v3_shadow/dt={date_str}/gsv_log.parquet")
    if not gsv_path.exists():
        print(f"⚠️  No GSV log at {gsv_path}")
        return 1
    df = pl.read_parquet(gsv_path)
    fixtures = latest_gsv_per_fixture(df)
    print(f"\n📊 GSV log: {df.height} rows, {len(fixtures)} fixtures")

    # v3 picks (if any persisted)
    picks_path = Path(f"data/cache/v3_shadow/dt={date_str}/picks.parquet")
    if picks_path.exists():
        v3 = pl.read_parquet(picks_path)
        print(f"🎯 v3 picks emitted: {v3.height}")
        if v3.height:
            print(v3.select(["fixture_id", "archetype", "market_id", "direction", "fair_prob"]).head(10))
    else:
        print(f"🎯 v3 picks emitted: 0  (no picks.parquet yet)")

    # v2 picks from log (with trio dedup)
    log_path = Path(f"logs/watch_day{args.day_n}_stdout.log")
    v2 = parse_v2_picks_from_log(log_path)
    trios = defaultdict(list)
    for p in v2:
        trio = f"{p['fixture']}|{p['market']}|{p['selection']}"
        trios[trio].append(p)
    print(f"\n📈 v2 picks emitted: {len(v2)} total / {len(trios)} unique trios")
    for trio, items in trios.items():
        first = min(items, key=lambda x: x["id"])
        last = max(items, key=lambda x: x["id"])
        flag = " ⚠FLAG" if any(p["flagged"] for p in items) else ""
        print(f"  • {trio}  min={first['minute']}→{last['minute']}  edge_max={max(p['edge_pct'] for p in items):.1f}%  emissions={len(items)}{flag}")

    # Per-fixture analysis
    print("\n🎬 Live fixtures status:")
    for fid, g in sorted(fixtures.items(), key=lambda x: -x[1].time.minute):
        hint = archetype_hint(g)
        scoreline = f"{g.score.home_goals}-{g.score.away_goals}"
        dom = "🏆" if not g.score.dominant_losing else "⚠️"
        print(f"  {dom} fid={fid}  min={g.time.minute:>3}  {scoreline}  "
              f"{g.home_team_name[:18]:<18} vs {g.away_team_name[:18]:<18}  → {hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
