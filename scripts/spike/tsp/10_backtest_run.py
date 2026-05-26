"""Backtest run — score AFCON23 / Copa24 / Euro24 fixtures with TSP, report metrics.

For each tournament:
  1. Load all profiles_backtest/{tournament}/*_tsv.json
  2. Build confederation cohorts (CAF, CONMEBOL, etc.)
  3. For each fixture:
       - Build home_profile + away_profile (own or cohort fallback)
       - If both available → predict_markets + record outcome
  4. run_backtest → metrics + Brier per market

Final output: combined + per-tournament reports.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.backtest.runner import (
    HistoricalFixture,
    render_markdown_report,
    run_backtest,
)
from bip.evaluation.tournaments.team_style_profiler.bettable_profile import (
    BettableProfile,
    from_confederation_cohort,
    from_tsv,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    CURRENT_COACHES,
    get_current_coach,
)
from bip.evaluation.tournaments.team_style_profiler.confederation_cohort import (
    MIN_COHORT_SIZE,
    build_confederation_cohort,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import (
    TeamStyleVector,
)


ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
TOURNAMENTS_DIR = ROOT / "data" / "cache" / "tsp" / "tournaments"
PROFILES_BT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_backtest"
REPORTS_DIR = ROOT / "data" / "cache" / "tsp" / "backtest_reports"

TOURNAMENTS = ["AFCON_2023", "Copa_2024", "Euro_2024"]


def load_profiles(tournament: str) -> dict[str, TeamStyleVector]:
    """team_name → TSV for the backtest folder."""
    out: dict[str, TeamStyleVector] = {}
    folder = PROFILES_BT_DIR / tournament
    if not folder.exists():
        return out
    for f in folder.glob("*_tsv.json"):
        try:
            tsv = TeamStyleVector.model_validate_json(f.read_text())
            out[tsv.team_name] = tsv
        except Exception:
            continue
    return out


def confederation_of_team(team_id: int, team_ids_by_id: dict[int, str]) -> str | None:
    name = team_ids_by_id.get(team_id)
    if name is None:
        return None
    rec = get_current_coach(name)
    return rec.confederation if rec else None


def build_profile_for_team(
    team_name: str | None,
    team_id: int,
    tsv_by_name: dict[str, TeamStyleVector],
    cohorts: dict[str, BettableProfile],
    team_ids_by_id: dict[int, str],
) -> BettableProfile | None:
    """Returns the best available BettableProfile for the team, or None."""
    # Case 1: own TSV (green/yellow)
    if team_name in tsv_by_name:
        tsv = tsv_by_name[team_name]
        if tsv.flag in ("green", "yellow"):
            return from_tsv(tsv)
    # Case 2: cohort fallback (CAF/CONMEBOL/UEFA/etc.)
    conf = confederation_of_team(team_id, team_ids_by_id)
    if conf and conf in cohorts:
        return cohorts[conf]
    return None


def backtest_one_tournament(
    tournament: str,
    team_ids_by_id: dict[int, str],
) -> tuple[list[HistoricalFixture], dict[str, int], int]:
    """Returns (fixtures_list, skip_reasons, total_fixtures)."""
    tsv_by_name = load_profiles(tournament)
    # Build cohorts per confederation
    all_tsvs = list(tsv_by_name.values())
    cohorts: dict[str, BettableProfile] = {}
    for conf in {t.confederation for t in all_tsvs}:
        cohort = build_confederation_cohort(conf, all_tsvs)
        if cohort:
            cohorts[conf] = from_confederation_cohort(cohort)

    print(f"\n  Cohorts built: {sorted(cohorts.keys())}")
    for conf, p in cohorts.items():
        # number of contributors comes from CohortProfile, but we have BettableProfile here
        n = sum(1 for t in all_tsvs if t.confederation == conf and t.flag == "green")
        print(f"    {conf}: from {n} green TSVs")

    # Load tournament fixtures
    fixtures_path = TOURNAMENTS_DIR / f"{tournament}_fixtures.json"
    fixtures_data = json.loads(fixtures_path.read_text())

    historical_fixtures: list[HistoricalFixture] = []
    skip_reasons: dict[str, int] = {}

    for fx in fixtures_data:
        if not fx["is_finished"]:
            continue
        home_id = fx["home_team_id"]
        away_id = fx["away_team_id"]
        home_name = team_ids_by_id.get(home_id)
        away_name = team_ids_by_id.get(away_id)

        home_profile = build_profile_for_team(
            home_name, home_id, tsv_by_name, cohorts, team_ids_by_id,
        )
        away_profile = build_profile_for_team(
            away_name, away_id, tsv_by_name, cohorts, team_ids_by_id,
        )

        if home_profile is None or away_profile is None:
            reason = "missing_both" if (home_profile is None and away_profile is None) \
                else ("missing_home" if home_profile is None else "missing_away")
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        historical_fixtures.append(HistoricalFixture(
            fixture_id=fx["fixture_id"],
            home_profile=home_profile,
            away_profile=away_profile,
            home_goals=fx["home_goals"] or 0,
            away_goals=fx["away_goals"] or 0,
            total_yellow_cards=None,  # outcome not parsed here
            total_corners=None,
        ))

    total = sum(1 for f in fixtures_data if f["is_finished"])
    return historical_fixtures, skip_reasons, total


def main() -> int:
    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("TSP Backtest — AFCON23 + Copa24 + Euro24")
    print("=" * 70)

    all_fixtures_combined: list[HistoricalFixture] = []
    for t in TOURNAMENTS:
        print(f"\n=== {t} ===")
        fixtures, skip_reasons, total = backtest_one_tournament(t, team_ids_by_id)
        print(f"\n  Scoreable: {len(fixtures)}/{total} fixtures ({100*len(fixtures)/total:.0f}% coverage)")
        if skip_reasons:
            print(f"  Skips: {skip_reasons}")

        if fixtures:
            metrics = run_backtest(fixtures)
            report = render_markdown_report(metrics, title=f"{t} Backtest")
            (REPORTS_DIR / f"{t}_report.md").write_text(report)
            print()
            for line in metrics.summary_lines():
                print(f"  {line}")
        all_fixtures_combined.extend(fixtures)

    # Combined report
    print("\n" + "=" * 70)
    print("Combined backtest")
    print("=" * 70)
    if all_fixtures_combined:
        combined = run_backtest(all_fixtures_combined)
        combined_report = render_markdown_report(combined, title="TSP Combined Backtest (3 tournaments)")
        (REPORTS_DIR / "combined_report.md").write_text(combined_report)
        for line in combined.summary_lines():
            print(f"  {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
