"""Diagnostic report — read all TSV profiles + print summary tables.

Outputs:
  - Per-team summary (n, flag, GF, GA, BTTS%, O2.5%)
  - Per-confederation aggregate
  - Top scorers / top defenses by confederation
  - Most-data and least-data teams (with DT info)
"""
from __future__ import annotations

import json
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.tsv_schema import TeamStyleVector


ROOT = Path(__file__).resolve().parents[3]
PROFILES_DIR = ROOT / "data" / "cache" / "tsp" / "profiles"


def main() -> int:
    profiles: list[TeamStyleVector] = []
    for f in sorted(PROFILES_DIR.glob("*_tsv.json")):
        try:
            tsv = TeamStyleVector.model_validate_json(f.read_text())
            profiles.append(tsv)
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")

    print(f"\n=== {len(profiles)} TSV profiles loaded ===\n")

    # By confederation
    by_conf: dict[str, list[TeamStyleVector]] = {}
    for p in profiles:
        by_conf.setdefault(p.confederation, []).append(p)

    print(f"{'Team':<22} {'Conf':<10} {'n':>4} {'Flag':<7} "
          f"{'GF':>5} {'GA':>5} {'BTTS%':>6} {'O2.5%':>6} {'CS%':>5} {'Coach':<30}")
    print("─" * 110)
    for p in sorted(profiles, key=lambda x: (x.confederation, -x.n_matches)):
        print(
            f"{p.team_name:<22} {p.confederation:<10} {p.n_matches:>4} "
            f"{p.flag:<7} {p.goals_for_per_match.mean:>5.2f} "
            f"{p.goals_against_per_match.mean:>5.2f} "
            f"{p.btts_rate.mean * 100:>5.1f}% "
            f"{p.over_25_rate.mean * 100:>5.1f}% "
            f"{p.clean_sheet_rate.mean * 100:>4.1f}% "
            f"{p.coach.coach_name:<30}"
        )

    # Top scorers by conf (≥10 matches, sorted by GF)
    print("\n" + "=" * 60)
    print("Top scorers per confederation (n≥10)")
    print("=" * 60)
    for conf in sorted(by_conf.keys()):
        green = [p for p in by_conf[conf] if p.flag == "green"]
        top = sorted(green, key=lambda x: -x.goals_for_per_match.mean)[:3]
        for p in top:
            print(f"  {conf:<10} {p.team_name:<22} GF={p.goals_for_per_match.mean:.2f}")

    # Top defenses by conf (lowest GA among green ≥10)
    print("\n" + "=" * 60)
    print("Best defenses per confederation (n≥10, lowest GA)")
    print("=" * 60)
    for conf in sorted(by_conf.keys()):
        green = [p for p in by_conf[conf] if p.flag == "green"]
        top = sorted(green, key=lambda x: x.goals_against_per_match.mean)[:3]
        for p in top:
            print(
                f"  {conf:<10} {p.team_name:<22} GA={p.goals_against_per_match.mean:.2f}, "
                f"CS={p.clean_sheet_rate.mean*100:.0f}%"
            )

    # Stats summary
    print("\n" + "=" * 60)
    print("Cohort stats per confederation (greens only)")
    print("=" * 60)
    print(f"{'Conf':<10} {'n_teams':>8} {'avg_n':>6} "
          f"{'mean GF':>8} {'mean GA':>8} {'mean BTTS%':>11} {'mean O2.5%':>11}")
    for conf in sorted(by_conf.keys()):
        green = [p for p in by_conf[conf] if p.flag == "green"]
        if not green:
            continue
        avg_n = sum(p.n_matches for p in green) / len(green)
        mean_gf = sum(p.goals_for_per_match.mean for p in green) / len(green)
        mean_ga = sum(p.goals_against_per_match.mean for p in green) / len(green)
        mean_btts = sum(p.btts_rate.mean for p in green) / len(green) * 100
        mean_o25 = sum(p.over_25_rate.mean for p in green) / len(green) * 100
        print(f"{conf:<10} {len(green):>8} {avg_n:>6.1f} "
              f"{mean_gf:>8.2f} {mean_ga:>8.2f} {mean_btts:>10.1f}% {mean_o25:>10.1f}%")

    # Most/least data
    print("\n" + "=" * 60)
    print("Top-5 most data / Bottom-5 least data")
    print("=" * 60)
    by_n = sorted(profiles, key=lambda x: -x.n_matches)
    for p in by_n[:5]:
        print(f"  TOP {p.team_name:<22} n={p.n_matches} ({p.coach.coach_name} since {p.coach.start_date})")
    print("  ...")
    for p in by_n[-5:]:
        print(f"  BOT {p.team_name:<22} n={p.n_matches} ({p.coach.coach_name} since {p.coach.start_date})")

    return 0


if __name__ == "__main__":
    main()
