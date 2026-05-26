"""Pilot ingestion — Argentina (Scaloni since 2018, era >= 2023-01-01).

Validates the full TSV pipeline against real API-Football data for a
single team. Steps:
  1. Verify team_id=26 returns Argentina via /teams.
  2. Pull fixtures (team=26, from=2023-01-01, to=today).
  3. Filter to FT/AET matches only (finished).
  4. For each fixture: pull /statistics + /events.
  5. Build MatchFeatures via extract_match_features.
  6. Compute TSV via compute_tsv.
  7. Print summary + save JSON.

Expected cost: ~50-80 calls (1 team lookup + 1 fixtures list + 2 calls
per fixture for ~25 fixtures). At 450 req/min that's ~10 seconds.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    EventsResponse,
    FixturesResponse,
    StatsResponse,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    get_current_coach,
    get_effective_filter_date,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_calculator import (
    compute_tsv,
    extract_match_features,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import CoachInfo


# Hard-coded confederation lookup for opponents we may see — enough for pilot.
# Production version will use coach_history.teams_by_confederation().
CONF_BY_ID: dict[int, str] = {
    # Will be filled in lazily when we see an opponent. Default to UNK.
}


def _conf_lookup(team_id: int) -> str:
    return CONF_BY_ID.get(team_id, "UNK")


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API key")
        return 1

    team_id = 26  # Argentina per coach_history
    record = get_current_coach("Argentina")
    if record is None:
        print("ERROR: Argentina not in coach_history")
        return 1
    filter_date = get_effective_filter_date("Argentina")
    today = date.today()
    print(
        f"\nProfile target: Argentina (id={team_id})\n"
        f"Coach: {record.coach_name} since {record.coach_start_date.isoformat()}\n"
        f"Effective filter window: {filter_date} -> {today}\n"
    )

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        # ── Step 1: pull fixtures (loop over seasons; API requires it) ──
        print("[1/3] Pulling fixtures across seasons...")
        t0 = time.time()
        all_fixtures = []
        seasons_to_pull = list(range(filter_date.year, today.year + 1))
        for season in seasons_to_pull:
            r = await client.get(
                "/fixtures", params={"team": team_id, "season": season}
            )
            r.raise_for_status()
            seasonal = FixturesResponse.model_validate(r.json()).response
            all_fixtures.extend(seasonal)
            print(f"    season={season}: {len(seasonal)} fixtures")
        # Filter to >= filter_date and finished
        finished = [
            f for f in all_fixtures
            if f.is_finished and f.fixture.date.date() >= filter_date
        ]
        print(
            f"  ✓ {len(all_fixtures)} fixtures total, {len(finished)} finished. "
            f"({time.time() - t0:.1f}s)"
        )

        if not finished:
            print("  No finished fixtures; aborting.")
            return 0

        # ── Step 2: per-fixture stats + events ──
        print(f"\n[2/3] Pulling stats + events for {len(finished)} fixtures...")
        t0 = time.time()
        match_features = []
        api_calls_used = 1  # the fixtures list call
        for i, fix in enumerate(finished, 1):
            fid = fix.fixture_id
            # Stats
            r_stats = await client.get(
                "/fixtures/statistics", params={"fixture": fid}
            )
            r_stats.raise_for_status()
            stats_resp = StatsResponse.model_validate(r_stats.json())
            team_stats = stats_resp.for_team(team_id)
            opp_id = (
                fix.teams.away.id if team_id == fix.teams.home.id
                else fix.teams.home.id
            )
            opp_stats = stats_resp.for_team(opp_id)

            # Events
            r_events = await client.get(
                "/fixtures/events", params={"fixture": fid}
            )
            r_events.raise_for_status()
            events_resp = EventsResponse.model_validate(r_events.json())

            api_calls_used += 2

            mf = extract_match_features(
                fixture=fix,
                team_id=team_id,
                team_stats=team_stats,
                opponent_stats=opp_stats,
                events=events_resp.response,
                opponent_confederation_lookup=_conf_lookup,
            )
            match_features.append(mf)

            if i % 5 == 0 or i == len(finished):
                opp_name = fix.teams.away.name if team_id == fix.teams.home.id else fix.teams.home.name
                print(
                    f"  [{i}/{len(finished)}] {fix.fixture.date.date()} vs {opp_name} "
                    f"({mf.goals_for}-{mf.goals_against})"
                )

        elapsed = time.time() - t0
        print(
            f"  ✓ {api_calls_used} API calls in {elapsed:.1f}s "
            f"({api_calls_used / max(elapsed/60, 1/60):.0f} req/min effective)"
        )

        # ── Step 3: compute TSV ──
        print(f"\n[3/3] Computing TSV...")
        tsv = compute_tsv(
            team_name="Argentina",
            api_football_team_id=team_id,
            confederation="CONMEBOL",
            coach=CoachInfo(
                coach_name=record.coach_name,
                start_date=record.coach_start_date,
            ),
            matches=match_features,
            last_updated=datetime.now(),
        )

        # ── Report ──
        print(f"\n{'=' * 60}")
        print(f"ARGENTINA TSV (Scaloni era, {filter_date}+)")
        print(f"{'=' * 60}")
        print(f"  n_matches: {tsv.n_matches}")
        print(f"  flag: {tsv.flag}")
        print(f"  is_bettable: {tsv.is_bettable}")
        print(f"\n  Offensive:")
        print(f"    goals_for/match:  {tsv.goals_for_per_match.mean:.2f} "
              f"[{tsv.goals_for_per_match.ci_low:.2f}, "
              f"{tsv.goals_for_per_match.ci_high:.2f}] n={tsv.goals_for_per_match.n}")
        print(f"    shots/match:      {tsv.shots_per_match.mean:.2f} "
              f"(n={tsv.shots_per_match.n})")
        print(f"    SoT/match:        {tsv.shots_on_target_per_match.mean:.2f} "
              f"(n={tsv.shots_on_target_per_match.n})")
        print(f"    SoT ratio:        {tsv.shots_on_target_ratio.mean:.3f}")
        print(f"    corners_for:      {tsv.corners_for_per_match.mean:.2f}")
        print(f"    possession:       {tsv.possession_avg.mean:.1f}%")
        print(f"\n  Defensive:")
        print(f"    goals_against:    {tsv.goals_against_per_match.mean:.2f} "
              f"[{tsv.goals_against_per_match.ci_low:.2f}, "
              f"{tsv.goals_against_per_match.ci_high:.2f}]")
        print(f"    clean_sheet rate: {tsv.clean_sheet_rate.mean:.1%}")
        print(f"    corners_against:  {tsv.corners_against_per_match.mean:.2f}")
        print(f"\n  Character:")
        print(f"    BTTS rate:        {tsv.btts_rate.mean:.1%}")
        print(f"    O2.5 rate:        {tsv.over_25_rate.mean:.1%}")
        print(f"    O3.5 rate:        {tsv.over_35_rate.mean:.1%}")
        print(f"    mean total goals: {tsv.mean_total_goals.mean:.2f}")
        print(f"    yellow_cards:     {tsv.yellow_cards_per_match.mean:.2f}")
        print(f"    fouls:            {tsv.fouls_per_match.mean:.2f}")
        print(f"\n  Goals-per-15min distribution (offensive):")
        g15 = tsv.goals_for_per_15min
        for bucket_label, bucket_attr in [
            ("0-14", g15.bucket_0_14), ("15-29", g15.bucket_15_29),
            ("30-44", g15.bucket_30_44), ("45-59", g15.bucket_45_59),
            ("60-74", g15.bucket_60_74), ("75-90", g15.bucket_75_90),
        ]:
            print(f"    {bucket_label}min: {bucket_attr.mean:.3f}")

        # Save JSON
        out_path = (
            Path(__file__).resolve().parents[4]
            / "data" / "cache" / "tsp" / "argentina_tsv.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(tsv.model_dump_json(indent=2))
        print(f"\n  Saved TSV: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
