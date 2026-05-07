"""Lock pre-tournament predictions for FIFA World Cup 2026.

Operator-run before kickoff (2026-06-11). Deadline: 2026-06-08 (3-day buffer).

Usage::

    uv run python -m scripts.spike.lock_world_cup_2026 --confirm

Prerequisites (will refuse to run if any are missing):
1. .env with API_FOOTBALL_KEY populated.
2. configs/world_cup_2026.yaml — `groups` list filled with team_ids from
   the official FIFA draw (currently empty per .planning/spikes/SPIKE-...md
   §2 R-01: do not fabricate).
3. configs/_qualifying_leagues.yaml — every TODO marker resolved with the
   real league_id (verified against /leagues live).
4. league_strength.yaml — operator-reviewed (defaults are placeholders).

What it does:
1. For each WC2026 group-stage fixture (104 matches: 72 group + 32 knockout
   placeholders for top-2 + best-3rd advancement):
   - Pull squad via /players/squads
   - Pull team baseline (cached from qualifying ingestion)
   - Pull club form for each squad member (last-N matches)
   - Predict lineup heuristically (no live confirmed lineups yet)
   - Run BivariatePoissonModel(rho=0.04) — primary lock model
   - Emit JSON to src/bip/evaluation/locked_predictions/world_cup_2026/<match_id>.json
   - Emit Markdown to src/bip/evaluation/locked_predictions/world_cup_2026/<match_id>.md
2. Write a manifest.json summarizing run metadata (predicted_at, model
   version, alpha, rho, fixtures covered).

The locked JSONs are git-committed by the operator immediately after the
script finishes — that establishes the prospective test record. Any later
modification (post-kickoff lineup confirmation, model tuning) lives on
separate file paths to preserve the lock.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

import structlog

from bip.core.settings import Settings
from bip.evaluation.tournaments.baselines.team_rates import adjust_team_baselines
from bip.evaluation.tournaments.data.club_form_loader import ClubFormLoader
from bip.evaluation.tournaments.data.league_strength import load_league_strength
from bip.evaluation.tournaments.data.qualifying_loader import QualifyingLoader
from bip.evaluation.tournaments.loader import (
    load_qualifying_leagues,
    load_tournament,
)
from bip.evaluation.tournaments.models import Player, Position
from bip.evaluation.tournaments.players.lineup_predictor import (
    predict_from_squad_only,
)
from bip.evaluation.tournaments.players.recent_form import normalize_player_rates
from bip.evaluation.tournaments.predict.match_runner import (
    MatchPredictionRunner,
    TeamMatchInputs,
    synthesize_lineup_form_for,
)
from bip.evaluation.tournaments.predict.output import (
    write_json,
    write_markdown,
)
from bip.evaluation.tournaments.predictors.bivariate_poisson import (
    BivariatePoissonModel,
)
from bip.sports.football.client import ApiFootballClient

logger = structlog.get_logger(__name__)

LOCKED_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "bip" / "evaluation" / "locked_predictions" / "world_cup_2026"
)
TOURNAMENT_SLUG = "world_cup_2026"
PRIMARY_MODEL_RHO = 0.04
PRIMARY_ALPHA = 0.35


async def main(*, confirm: bool, output_dir: Path | None = None) -> int:
    if not confirm:
        print("ERROR: re-run with --confirm to acknowledge this generates LOCKED predictions.")
        return 2

    target_dir = output_dir or LOCKED_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Pre-flight: validate every dependency.
    settings = Settings()  # type: ignore[call-arg]  # pydantic-settings loads from env
    if not settings.api_football_key:
        print("ERROR: API_FOOTBALL_KEY missing from .env")
        return 2

    tournament = load_tournament(TOURNAMENT_SLUG)
    if not tournament.groups:
        print(
            f"ERROR: {TOURNAMENT_SLUG}.yaml has empty `groups` — fill team_ids "
            "from the FIFA draw before locking predictions."
        )
        return 2

    qualifying_leagues = load_qualifying_leagues()
    strength_table = load_league_strength()

    logger.info(
        "lock_run_started",
        tournament=TOURNAMENT_SLUG,
        n_fixtures=len(tournament.matches),
        n_groups=len(tournament.groups),
    )

    async with ApiFootballClient(api_key=settings.api_football_key) as client:
        qual_loader = QualifyingLoader(client=client)
        form_loader = ClubFormLoader(client=client)

        # 1. Build team baselines for every WC2026 participant.
        all_team_ids = {tid for g in tournament.groups for tid in g.team_ids}
        baselines = {}
        for team_id in all_team_ids:
            # Choose the qualifier confederation by inspection — the operator
            # YAML is expected to be 1 league per confed; we naively try them
            # all and use whichever returns matches first.
            for league in qualifying_leagues:
                df = await qual_loader.load_team_baseline(
                    team_id=team_id,
                    league_id=league.api_football_league_id,
                    season=league.season,
                    tournament_slug=TOURNAMENT_SLUG,
                )
                if df["matches_played"][0] > 0:
                    baselines[team_id] = df
                    break

        # Apply opponent-adjustment cohort-wide.
        import polars as pl

        cohort = pl.concat(list(baselines.values()))
        adjusted = adjust_team_baselines(cohort)
        adjusted_by_team: dict[int, pl.DataFrame] = {}
        for tid in baselines:
            row = adjusted.filter(pl.col("team_id") == tid)
            if row.height == 1:
                adjusted_by_team[tid] = row

        # Cache squad pulls so we don't re-pull per fixture.
        squad_cache: dict[int, list[Player]] = {}
        form_cache: dict[int, pl.DataFrame] = {}

        # 2. For each group-stage fixture, build inputs + emit prediction.
        runner = MatchPredictionRunner(
            BivariatePoissonModel(rho=PRIMARY_MODEL_RHO),
            alpha=PRIMARY_ALPHA,
        )
        manifest_entries: list[dict] = []

        for match in tournament.matches:
            if not match.stage.startswith("group:"):
                # Knockout fixtures depend on group standings; post-group lock.
                continue

            home_baseline = adjusted_by_team.get(match.home_team_id)
            away_baseline = adjusted_by_team.get(match.away_team_id)
            if home_baseline is None or away_baseline is None:
                logger.warning(
                    "lock_skipping_no_baseline",
                    match_id=match.match_id,
                    home_team=match.home_team_id,
                    away_team=match.away_team_id,
                )
                continue

            home_squad = await _get_or_pull_squad(
                client, match.home_team_id, squad_cache
            )
            away_squad = await _get_or_pull_squad(
                client, match.away_team_id, squad_cache
            )

            home_form_full = await _get_or_pull_form(
                client, form_loader, match.home_team_id, home_squad, strength_table, form_cache
            )
            away_form_full = await _get_or_pull_form(
                client, form_loader, match.away_team_id, away_squad, strength_table, form_cache
            )

            # Heuristic XI from squad (4-3-3 fallback). Operator can rerun
            # closer to kickoff with confirmed lineups.
            home_lineup = predict_from_squad_only(home_squad)
            away_lineup = predict_from_squad_only(away_squad)

            home_form = synthesize_lineup_form_for(home_lineup, home_form_full)
            away_form = synthesize_lineup_form_for(away_lineup, away_form_full)

            home_inputs = TeamMatchInputs(
                team_id=match.home_team_id,
                team_name=str(match.home_team_id),
                fifa_code="???",  # operator may enrich via /teams lookup
                baseline_row=home_baseline,
                lineup=home_lineup,
                lineup_form=home_form,
            )
            away_inputs = TeamMatchInputs(
                team_id=match.away_team_id,
                team_name=str(match.away_team_id),
                fifa_code="???",
                baseline_row=away_baseline,
                lineup=away_lineup,
                lineup_form=away_form,
            )

            pred = runner.predict(
                match_id=match.match_id,
                tournament_slug=TOURNAMENT_SLUG,
                kickoff=match.kickoff,
                home=home_inputs,
                away=away_inputs,
            )

            json_path = target_dir / f"{match.match_id}.json"
            md_path = target_dir / f"{match.match_id}.md"
            write_json(pred, json_path)
            write_markdown(pred, md_path)
            manifest_entries.append(
                {
                    "match_id": match.match_id,
                    "home_team_id": match.home_team_id,
                    "away_team_id": match.away_team_id,
                    "kickoff": match.kickoff.isoformat(),
                    "json": json_path.name,
                    "markdown": md_path.name,
                }
            )
            print(f"Locked {match.match_id} -> {json_path.name}")

        manifest = {
            "tournament": TOURNAMENT_SLUG,
            "predicted_at": datetime.now().isoformat(),
            "model": "bivariate_poisson",
            "rho": PRIMARY_MODEL_RHO,
            "alpha": PRIMARY_ALPHA,
            "fixtures_locked": manifest_entries,
        }
        manifest_path = target_dir / "manifest.json"
        import json

        with manifest_path.open("w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Manifest written to {manifest_path}")

    return 0


_API_POSITION_TO_ENUM = {
    "Goalkeeper": Position.GOALKEEPER,
    "Defender": Position.DEFENDER,
    "Midfielder": Position.MIDFIELDER,
    "Attacker": Position.FORWARD,
}


async def _get_or_pull_squad(
    client: ApiFootballClient,
    team_id: int,
    cache: dict[int, list[Player]],
) -> list[Player]:
    """Cache-first squad pull. Maps API-Football position strings to Position."""
    if team_id in cache:
        return cache[team_id]

    payload = await client.get_squad(team_id=team_id)
    response = payload.get("response", [])
    if not response:
        cache[team_id] = []
        return []

    players: list[Player] = []
    for p in response[0].get("players", []):
        pid = p.get("id")
        if pid is None:
            continue
        pos_str = (p.get("position") or "Midfielder").strip()
        pos = _API_POSITION_TO_ENUM.get(pos_str, Position.MIDFIELDER)
        players.append(
            Player.from_api_football(
                af_player_id=int(pid),
                name=p.get("name") or f"player-{pid}",
                position=pos,
                national_team_id=team_id,
            )
        )
    cache[team_id] = players
    return players


async def _get_or_pull_form(
    client: ApiFootballClient,
    form_loader: ClubFormLoader,
    team_id: int,
    squad: list[Player],
    strength_table,
    cache: "dict[int, pl.DataFrame]",  # noqa: F821 — forward ref
) -> "pl.DataFrame":  # noqa: F821
    """Cache-first per-team aggregated lineup form.

    Returns the full squad form (>11 rows) — the runner filters down to the
    predicted XI via synthesize_lineup_form_for().
    """
    import polars as pl

    if team_id in cache:
        return cache[team_id]

    if not squad:
        empty = pl.DataFrame({"canonical_id": []}, schema={"canonical_id": pl.Utf8})
        cache[team_id] = empty
        return empty

    rows = []
    for player in squad:
        form = await form_loader.load_player_form(
            player_id=player.api_football_id,
            season=2025,  # current club season — operator may override
            tournament_slug=TOURNAMENT_SLUG,
        )
        rows.append(form)

    raw = pl.concat(rows)
    normalized = normalize_player_rates(raw, strength_table)
    cache[team_id] = normalized
    return normalized


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Lock WC2026 predictions.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgment that predictions are LOCKED on disk.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override the default locked_predictions/world_cup_2026 path.",
    )
    args = parser.parse_args()
    return asyncio.run(main(confirm=args.confirm, output_dir=args.output_dir))


if __name__ == "__main__":
    sys.exit(_cli())
