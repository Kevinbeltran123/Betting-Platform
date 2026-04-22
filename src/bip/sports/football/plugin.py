"""Football sport plugin -- implements SportPlugin ABC.

Phase 1: get_fixtures() and build_features() wired to real ApiFootballClient,
FeatureEngineer, and ParquetStore. predict() is still a stub (Phase 2).
build_claude_context() is still a stub (Phase 3).

T-05-03: computed_at captured BEFORE API calls to establish point-in-time boundary.
T-05-01: _parse_fixture() wraps KeyError/ValueError to skip malformed API responses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from bip.core.settings import Settings
from bip.core.storage.parquet_store import ParquetStore
from bip.sports import (
    ClaudeContext,
    FeatureMatrix,
    FixtureData,
    ProbabilityMap,
    SportPlugin,
)
from bip.sports.football.client import ApiFootballClient
from bip.sports.football.config.league_registry import LeagueRegistry
from bip.sports.football.config.market_config import load_markets
from bip.sports.football.features import FeatureEngineer

logger = structlog.get_logger(__name__)

_LEAGUES_DIR = Path(__file__).parent / "config" / "leagues"


class FootballPlugin(SportPlugin):
    """Football sport plugin -- full SportPlugin implementation.

    Phase 1 wires get_fixtures() and build_features() to real clients.
    Phase 2 replaces the predict() stub with the ML ensemble.
    Phase 3 replaces the build_claude_context() stub.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._markets = load_markets()
        self._registry = LeagueRegistry(_LEAGUES_DIR)
        self._store = ParquetStore(base_path=Path(settings.parquet_base_path))
        self._engineer = FeatureEngineer()

    def get_available_markets(self) -> list[str]:
        """Return market keys from markets.yaml -- CORE-05."""
        return [m["key"] for m in self._markets]

    async def get_fixtures(self, date: datetime) -> list[FixtureData]:
        """Fetch today's football fixtures from API-Football for all 5 leagues.

        Calls ApiFootballClient.get_fixtures() for each configured league.
        Malformed fixture responses are skipped (T-05-01).
        League fetch failures are logged and skipped (not crash-inducing).
        """
        date_str = date.strftime("%Y-%m-%d")
        fixtures: list[FixtureData] = []

        async with ApiFootballClient(api_key=self._settings.api_football_key) as client:
            for league_cfg in self._registry.all_leagues():
                try:
                    raw = await client.get_fixtures(
                        league_id=league_cfg.api_mappings.api_football_league_id,
                        date=date_str,
                    )
                    for item in raw.get("response", []):
                        fixture = self._parse_fixture(item, league_cfg.slug)
                        if fixture:
                            fixtures.append(fixture)
                except Exception as exc:
                    logger.warning(
                        "get_fixtures_failed",
                        league=league_cfg.slug,
                        error=str(exc),
                    )

        logger.info("fixtures_fetched", count=len(fixtures), date=date_str)
        return fixtures

    def _parse_fixture(self, item: dict, league_slug: str) -> FixtureData | None:
        """Parse one API-Football fixture response item into FixtureData.

        T-05-01: Malformed items (KeyError / ValueError) are logged and skipped,
        not crash-inducing. Pydantic validates the final FixtureData model.
        """
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
            logger.warning(
                "fixture_parse_failed",
                error=str(exc),
                item=str(item)[:200],
            )
            return None

    async def build_features(self, fixture: FixtureData) -> FeatureMatrix:
        """Build point-in-time feature matrix and write to ParquetStore.

        T-05-03: computed_at captured BEFORE API calls to enforce DATA-05
        point-in-time correctness. Features must not use data from after
        computed_at.
        """
        # Capture point-in-time timestamp BEFORE any API calls (T-05-03, DATA-05)
        computed_at = datetime.now(UTC)

        async with ApiFootballClient(api_key=self._settings.api_football_key) as client:
            raw_stats = await client.get_statistics(fixture_id=fixture.fixture_id)
            raw_lineups = await client.get_lineups(fixture_id=fixture.fixture_id)

        fm = self._engineer.build_features_for_fixture(
            fixture=fixture,
            raw_stats=raw_stats,
            raw_lineups=raw_lineups,
            computed_at=computed_at,
        )

        # Write to Parquet cache (DATA-02)
        # Season derived from kickoff year; matchday placeholder (Phase 2 will use API)
        season = f"{fixture.kickoff_utc.year}-{fixture.kickoff_utc.year + 1}"
        matchday = 1  # placeholder; real matchday from API in Phase 2

        parquet_row = self._engineer.to_parquet_row(fm, matchday=matchday, season=season)
        self._store.write_features(parquet_row)

        return fm

    async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap:
        """Run ML model -- stub in Phase 1, real ensemble added in Phase 2."""
        return ProbabilityMap(
            fixture_id=features.fixture_id,
            market=market,
            probabilities={"1": 0.333, "X": 0.333, "2": 0.334},
            model_version="stub-v0",
            computed_at=datetime.now(UTC),
        )

    async def build_claude_context(self, fixture: FixtureData) -> ClaudeContext:
        """Claude context -- stub in Phase 1, wired in Phase 3."""
        return ClaudeContext(
            fixture_id=fixture.fixture_id,
            sport=fixture.sport,
            summary="",
        )
