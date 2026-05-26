"""Copa Oro 2025 dry-run — discovery + re-ingest + backtest in one shot.

Workflow:
  1. Search /leagues for "Gold Cup" → league_id, confirm season 2025
  2. Pull /fixtures for league+season → get participants + outcomes
  3. For each participant in our coach_history: re-ingest profile with
     cutoff = Copa Oro start - 1 day
  4. Score fixtures with predict_markets_shrunk(0.85)
  5. Compute Brier per market vs outcomes
  6. Compare against backtest tournament results

Output: data/cache/tsp/backtest_reports/copa_oro_2025_dryrun.md
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    EventsResponse,
    FixturesResponse,
    StatsResponse,
)
from bip.evaluation.tournaments.team_style_profiler.backtest.metrics import (
    MARKET_BRIER_GATES,
    brier_score,
    expected_calibration_error,
    hit_rate,
    market_passes_brier_gate,
)
from bip.evaluation.tournaments.team_style_profiler.backtest.runner import (
    HistoricalFixture,
    _market_outcome,
)
from bip.evaluation.tournaments.team_style_profiler.bettable_profile import (
    from_confederation_cohort,
    from_tsv,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    CURRENT_COACHES,
    get_current_coach,
    get_effective_filter_date,
)
from bip.evaluation.tournaments.team_style_profiler.confederation_cohort import (
    build_confederation_cohort,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_calculator import (
    compute_tsv,
    extract_match_features,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import (
    CoachInfo,
    TeamStyleVector,
)


# Import the shrunk predictor from the calibration script
sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module
calibrate_mod = import_module("11_calibrate_and_rerun")
predict_markets_shrunk = calibrate_mod.predict_markets_shrunk

ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
COPA_ORO_DIR = ROOT / "data" / "cache" / "tsp" / "copa_oro_2025"
PROFILES_DIR = COPA_ORO_DIR / "profiles"
REPORTS_DIR = ROOT / "data" / "cache" / "tsp" / "backtest_reports"

SHRINKAGE = 0.85


async def discover_league(client: httpx.AsyncClient) -> dict:
    """Find Gold Cup league_id with 2025 season."""
    r = await client.get("/leagues", params={"search": "Gold Cup"})
    r.raise_for_status()
    response = r.json().get("response", [])
    print("\nSearching 'Gold Cup'...")
    for item in response[:5]:
        league = item.get("league", {})
        country = item.get("country", {})
        seasons = [s.get("year") for s in item.get("seasons", [])]
        print(f"  id={league.get('id'):4} name={league.get('name'):30} "
              f"country={country.get('name'):20} seasons={seasons[-5:]}")
    # Pick the one matching "Gold Cup" and has 2025
    for item in response:
        league = item.get("league", {})
        lname = league.get("name", "").lower()
        seasons_years = [s.get("year") for s in item.get("seasons", [])]
        if "gold cup" in lname and "concacaf" in lname.lower() and 2025 in seasons_years:
            return {
                "id": league.get("id"),
                "name": league.get("name"),
                "season": 2025,
            }
        if "gold cup" in lname and 2025 in seasons_years:
            return {
                "id": league.get("id"),
                "name": league.get("name"),
                "season": 2025,
            }
    raise ValueError("Could not find CONCACAF Gold Cup 2025")


async def fetch_fixtures(client: httpx.AsyncClient, league_id: int, season: int) -> list[dict]:
    r = await client.get("/fixtures", params={"league": league_id, "season": season})
    r.raise_for_status()
    parsed = FixturesResponse.model_validate(r.json())
    return [
        {
            "fixture_id": f.fixture_id,
            "date": f.fixture.date.isoformat(),
            "home_team_id": f.teams.home.id,
            "home_team_name": f.teams.home.name,
            "away_team_id": f.teams.away.id,
            "away_team_name": f.teams.away.name,
            "home_goals": f.goals.home,
            "away_goals": f.goals.away,
            "is_finished": f.is_finished,
        }
        for f in parsed.response
    ]


async def reingest_for_dry_run(
    client: httpx.AsyncClient,
    participants: set[int],
    team_ids_by_id: dict[int, str],
    cutoff_date: date,
) -> dict[str, TeamStyleVector]:
    """Re-ingest profiles up to cutoff for participants in our coach_history."""
    coach_map_conf = {n: r.confederation for n, r in CURRENT_COACHES.items()}

    def conf_lookup(tid: int) -> str:
        n = team_ids_by_id.get(tid)
        return coach_map_conf.get(n, "UNK") if n else "UNK"

    profiles: dict[str, TeamStyleVector] = {}
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    for team_id in sorted(participants):
        team_name = team_ids_by_id.get(team_id)
        if team_name is None:
            print(f"  team_id={team_id}: not in coach_history — skip")
            continue
        coach_rec = get_current_coach(team_name)
        if coach_rec is None:
            continue
        fdate = get_effective_filter_date(team_name) or date(2023, 1, 1)
        if fdate >= cutoff_date:
            print(f"  {team_name}: DT post-cutoff — skip")
            continue
        # Pull seasons
        seasons = list(range(fdate.year, cutoff_date.year + 1))
        all_fixtures = []
        for season in seasons:
            r = await client.get("/fixtures", params={"team": team_id, "season": season})
            r.raise_for_status()
            all_fixtures.extend(FixturesResponse.model_validate(r.json()).response)
        finished = [
            f for f in all_fixtures
            if f.is_finished and fdate <= f.fixture.date.date() <= cutoff_date
        ]

        match_features = []
        for fix in finished:
            fid = fix.fixture_id
            r_stats = await client.get("/fixtures/statistics", params={"fixture": fid})
            r_stats.raise_for_status()
            stats_resp = StatsResponse.model_validate(r_stats.json())
            team_stats = stats_resp.for_team(team_id)
            opp_id = (
                fix.teams.away.id if team_id == fix.teams.home.id
                else fix.teams.home.id
            )
            opp_stats = stats_resp.for_team(opp_id)
            r_events = await client.get("/fixtures/events", params={"fixture": fid})
            r_events.raise_for_status()
            events_resp = EventsResponse.model_validate(r_events.json())
            mf = extract_match_features(
                fixture=fix, team_id=team_id,
                team_stats=team_stats, opponent_stats=opp_stats,
                events=events_resp.response,
                opponent_confederation_lookup=conf_lookup,
            )
            match_features.append(mf)

        tsv = compute_tsv(
            team_name=team_name,
            api_football_team_id=team_id,
            confederation=coach_rec.confederation,
            coach=CoachInfo(coach_name=coach_rec.coach_name, start_date=coach_rec.coach_start_date),
            matches=match_features,
            last_updated=datetime.now(),
        )
        profiles[team_name] = tsv
        safe = team_name.replace(" ", "_").replace("'", "").replace("ô", "o").lower()
        (PROFILES_DIR / f"{safe}_tsv.json").write_text(tsv.model_dump_json(indent=2))
        glyph = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(tsv.flag, "?")
        print(f"  {team_name:22} → n={tsv.n_matches:3} {glyph} {tsv.flag}")

    return profiles


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}

    COPA_ORO_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(120.0),
    ) as client:
        # 1) Discover league
        league_info = await discover_league(client)
        print(f"\n→ Using: id={league_info['id']} {league_info['name']} season={league_info['season']}")

        # 2) Fixtures
        fixtures = await fetch_fixtures(client, league_info["id"], league_info["season"])
        finished_fixtures = [f for f in fixtures if f["is_finished"]]
        print(f"\nFixtures: {len(fixtures)} total, {len(finished_fixtures)} finished")
        if not finished_fixtures:
            print("No finished fixtures in Copa Oro 2025; aborting.")
            return 0
        (COPA_ORO_DIR / "fixtures.json").write_text(json.dumps(fixtures, indent=2))

        participants = {f["home_team_id"] for f in fixtures} | {f["away_team_id"] for f in fixtures}
        tournament_start = min(date.fromisoformat(f["date"][:10]) for f in fixtures)
        cutoff = tournament_start - timedelta(days=1)
        print(f"\nTournament start: {tournament_start}")
        print(f"Cutoff for profiles: {cutoff}")
        print(f"Participants: {len(participants)}")
        print(f"Participants in coach_history: {sum(1 for p in participants if team_ids_by_id.get(p))}")

        # 3) Re-ingest profiles
        print("\nRe-ingesting profiles...")
        t0 = time.time()
        profiles = await reingest_for_dry_run(client, participants, team_ids_by_id, cutoff)
        print(f"\n  Re-ingest took {time.time() - t0:.1f}s")

    # 4) Build cohorts + score fixtures
    print("\n=== Scoring Copa Oro 2025 fixtures ===")
    all_tsvs = list(profiles.values())
    cohorts = {}
    for conf in {t.confederation for t in all_tsvs}:
        c = build_confederation_cohort(conf, all_tsvs)
        if c:
            cohorts[conf] = from_confederation_cohort(c)
    print(f"  Cohorts: {sorted(cohorts.keys())}")

    coach_map_conf = {n: r.confederation for n, r in CURRENT_COACHES.items()}

    def get_profile(team_id):
        name = team_ids_by_id.get(team_id)
        if name in profiles and profiles[name].flag in ("green", "yellow"):
            return from_tsv(profiles[name])
        conf = coach_map_conf.get(name)
        if conf and conf in cohorts:
            return cohorts[conf]
        return None

    historical = []
    skip_count = 0
    for f in finished_fixtures:
        hp = get_profile(f["home_team_id"])
        ap = get_profile(f["away_team_id"])
        if hp is None or ap is None:
            skip_count += 1
            continue
        historical.append(HistoricalFixture(
            fixture_id=f["fixture_id"], home_profile=hp, away_profile=ap,
            home_goals=f["home_goals"] or 0,
            away_goals=f["away_goals"] or 0,
        ))
    print(f"  Scoreable: {len(historical)}/{len(finished_fixtures)} ({100*len(historical)/len(finished_fixtures):.0f}%)")
    print(f"  Skipped: {skip_count}")

    # 5) Compute Brier with shrinkage 0.85
    market_data = {}
    for fix in historical:
        preds = predict_markets_shrunk(fix.home_profile, fix.away_profile, lambda_scale=SHRINKAGE)
        for mp in preds.all_markets:
            out = _market_outcome(mp.market, fix)
            if out is None:
                continue
            market_data.setdefault(mp.market, ([], []))
            market_data[mp.market][0].append(mp.probability)
            market_data[mp.market][1].append(out)

    print(f"\n=== Copa Oro 2025 Brier (shrinkage {SHRINKAGE}) ===")
    lines = ["# Copa Oro 2025 Dry-Run", "", f"Fixtures scored: {len(historical)}",
             f"Shrinkage applied: λ × {SHRINKAGE}", "", "| Market | n | Gate | Brier | E[p] | E[y] | Hit | Verdict |",
             "|--------|---|------|-------|------|------|-----|---------|"]
    for market in sorted(market_data.keys()):
        probs, outs = market_data[market]
        p, y = np.asarray(probs, dtype=float), np.asarray(outs, dtype=float)
        b = brier_score(p, y)
        h = hit_rate(p, y)
        ep, ey = float(p.mean()), float(y.mean())
        verdict = "✅ PASS" if market_passes_brier_gate(market, b) else "❌ FAIL"
        gate = MARKET_BRIER_GATES.get(market, "?")
        print(f"  {market:18}: n={len(p):3} Brier={b:.4f} (gate {gate}) "
              f"E[p]={ep:.3f} E[y]={ey:.3f} hit={h:.0%} → {verdict}")
        lines.append(f"| {market} | {len(p)} | {gate} | {b:.4f} | {ep:.3f} | {ey:.3f} | {h:.0%} | {verdict} |")

    out_path = REPORTS_DIR / "copa_oro_2025_dryrun.md"
    out_path.write_text("\n".join(lines))
    print(f"\nSaved: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
