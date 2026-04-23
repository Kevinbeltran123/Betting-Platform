"""One-off historical data seed — D-01.

Pulls fixtures + stats + lineups + H2H across 5 leagues × 3 seasons
(2023-2024, 2024-2025, 2025-2026) via the Phase 1 ApiFootballClient,
writing features to the same Hive-partitioned Parquet store as live
ingestion. Checkpoint-resumable.

NOT invoked by the scheduler. Run manually:
    uv run python scripts/seed_historical.py

Rate-limited to 300 req/min (API-Football Pro plan).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from bip.core.settings import Settings
from bip.core.storage.parquet_store import ParquetStore
from bip.sports import FixtureData
from bip.sports.football.client import ApiFootballClient
from bip.sports.football.config.league_registry import LeagueRegistry
from bip.sports.football.features import FeatureEngineer

logger = structlog.get_logger(__name__)

CHECKPOINT_PATH = Path("data/seed_checkpoint.json")
SEASONS = ["2023-2024", "2024-2025", "2025-2026"]
RATE_LIMIT_RPM = 300               # Pro plan
INTER_REQUEST_DELAY_S = 60.0 / RATE_LIMIT_RPM  # ~0.2s → ~300 req/min
_LEAGUES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "bip"
    / "sports"
    / "football"
    / "config"
    / "leagues"
)


# ----------------------------------------------------------------------
# Checkpoint helpers — atomic write (rename pattern)
# ----------------------------------------------------------------------

def load_checkpoint() -> set[int]:
    """Return the set of completed fixture IDs from data/seed_checkpoint.json.

    Returns an empty set if the file does not exist.
    """
    if CHECKPOINT_PATH.exists():
        data = json.loads(CHECKPOINT_PATH.read_text())
        return set(data.get("completed_fixture_ids", []))
    return set()


def save_checkpoint(completed_ids: set[int]) -> None:
    """Atomic write: JSON to .tmp, then Path.replace() onto target."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {
                "completed_fixture_ids": sorted(completed_ids),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    )
    tmp.replace(CHECKPOINT_PATH)


# ----------------------------------------------------------------------
# Season → date range (API-Football uses YYYY-MM-DD per-day queries)
# ----------------------------------------------------------------------

def season_date_range(season: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a season string like '2024-2025'.

    Football season window: Aug 1 YYYY → May 31 YYYY+1.
    """
    y1, y2 = season.split("-")
    start = datetime(int(y1), 8, 1, tzinfo=UTC)
    end = datetime(int(y2), 5, 31, 23, 59, 59, tzinfo=UTC)
    return start, end


def _parse_fixture(item: dict, league_slug: str) -> FixtureData | None:
    """Parse API-Football fixture item into FixtureData. Skip malformed."""
    try:
        return FixtureData(
            fixture_id=item["fixture"]["id"],
            league=league_slug,
            sport="football",
            home_team=item["teams"]["home"]["name"],
            away_team=item["teams"]["away"]["name"],
            kickoff_utc=datetime.fromisoformat(item["fixture"]["date"]),
        )
    except (KeyError, ValueError) as exc:
        logger.warning("fixture_parse_failed", error=str(exc))
        return None


def _parse_matchday(item: dict) -> int:
    """Parse 'Regular Season - 12' → 12. Returns 0 on any parse failure."""
    try:
        round_str = item["league"]["round"]
        # Examples: 'Regular Season - 12', 'Quarter-finals'
        tail = round_str.rsplit("-", 1)[-1].strip()
        return int(tail)
    except (KeyError, ValueError, AttributeError):
        return 0


# ----------------------------------------------------------------------
# Main seed loop
# ----------------------------------------------------------------------

async def seed_one_league(
    client: ApiFootballClient,
    engineer: FeatureEngineer,
    store: ParquetStore,
    league_cfg,
    season: str,
    completed: set[int],
) -> int:
    """Fetch fixtures for one (league, season) and write feature rows.

    Returns: count of NEW fixtures processed in this call.
    """
    processed = 0
    start, end = season_date_range(season)
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        try:
            raw = await client.get_fixtures(
                league_id=league_cfg.api_mappings.api_football_league_id,
                date=date_str,
            )
        except Exception as exc:
            logger.warning(
                "seed_get_fixtures_failed",
                league=league_cfg.slug,
                date=date_str,
                error=str(exc),
            )
            current += timedelta(days=1)
            await asyncio.sleep(INTER_REQUEST_DELAY_S)
            continue

        await asyncio.sleep(INTER_REQUEST_DELAY_S)

        for item in raw.get("response", []):
            fixture = _parse_fixture(item, league_cfg.slug)
            if fixture is None:
                continue
            if fixture.fixture_id in completed:
                continue

            matchday = _parse_matchday(item)

            # Pull per-fixture stats + lineups. Errors skip the fixture.
            try:
                raw_stats = await client.get_statistics(fixture_id=fixture.fixture_id)
                await asyncio.sleep(INTER_REQUEST_DELAY_S)
                raw_lineups = await client.get_lineups(fixture_id=fixture.fixture_id)
                await asyncio.sleep(INTER_REQUEST_DELAY_S)
            except Exception as exc:
                logger.warning(
                    "seed_fixture_failed",
                    fixture_id=fixture.fixture_id,
                    error=str(exc),
                )
                continue

            # computed_at is kickoff_utc itself (historical: we treat pre-kickoff
            # as the point-in-time boundary for this fixture).
            fm = engineer.build_features_for_fixture(
                fixture=fixture,
                raw_stats=raw_stats,
                raw_lineups=raw_lineups,
                computed_at=fixture.kickoff_utc,
            )
            parquet_row = engineer.to_parquet_row(fm, matchday=matchday, season=season)
            store.write_features(parquet_row)

            completed.add(fixture.fixture_id)
            processed += 1

            # Persist checkpoint every 25 fixtures
            if processed % 25 == 0:
                save_checkpoint(completed)

        current += timedelta(days=1)

    return processed


async def main(seasons: list[str] | None = None) -> None:
    settings = Settings()
    registry = LeagueRegistry(_LEAGUES_DIR)
    engineer = FeatureEngineer()
    store = ParquetStore(base_path=Path(settings.parquet_base_path))
    completed = load_checkpoint()
    logger.info("seed_start", resumed=len(completed), seasons=seasons or SEASONS)

    total_new = 0
    async with ApiFootballClient(api_key=settings.api_football_key) as client:
        for league_cfg in registry.all_leagues():
            for season in (seasons or SEASONS):
                try:
                    n = await seed_one_league(
                        client=client,
                        engineer=engineer,
                        store=store,
                        league_cfg=league_cfg,
                        season=season,
                        completed=completed,
                    )
                    total_new += n
                    save_checkpoint(completed)
                    logger.info(
                        "seed_league_season_done",
                        league=league_cfg.slug,
                        season=season,
                        new=n,
                        total=len(completed),
                    )
                except Exception as exc:
                    logger.warning(
                        "seed_league_failed",
                        league=league_cfg.slug,
                        season=season,
                        error=str(exc),
                    )

    save_checkpoint(completed)
    logger.info("seed_done", new=total_new, total=len(completed))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical data seed for Phase 2 ML training."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=None,
        help="Subset of seasons to seed (default: all 3). Example: --seasons 2024-2025",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(seasons=args.seasons))
