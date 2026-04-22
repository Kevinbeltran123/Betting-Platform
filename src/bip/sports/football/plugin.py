"""Football sport plugin -- implements SportPlugin ABC.

Phase 1: All 5 methods implemented with stubs where ML/feature engineering
is not yet built. Phase 2 replaces predict(). Phase 5 replaces build_features().
"""

from datetime import datetime, timezone

import structlog

from bip.core.settings import Settings
from bip.sports import (
    ClaudeContext,
    FeatureMatrix,
    FixtureData,
    ProbabilityMap,
    SportPlugin,
)
from bip.sports.football.config.market_config import load_markets

logger = structlog.get_logger(__name__)


class FootballPlugin(SportPlugin):
    """Football sport plugin."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._markets = load_markets()

    def get_available_markets(self) -> list[str]:
        """Return market keys from markets.yaml -- CORE-05."""
        return [m["key"] for m in self._markets]

    async def get_fixtures(self, date: datetime) -> list[FixtureData]:
        """Fetch today's football fixtures from API-Football.

        Phase 1: Returns empty list -- ApiFootballClient is added in Plan 05.
        """
        logger.info("get_fixtures_called", date=date.isoformat(), sport="football")
        return []

    async def build_features(self, fixture: FixtureData) -> FeatureMatrix:
        """Build point-in-time feature matrix for a fixture.

        Phase 1: Returns minimal feature matrix -- full feature engineering added in Plan 05.
        """
        return FeatureMatrix(
            fixture_id=fixture.fixture_id,
            sport=fixture.sport,
            league=fixture.league,
            computed_at=datetime.now(timezone.utc),
            features={},
        )

    async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap:
        """Run ML model and return probability map.

        Phase 1: Returns uniform prior -- real ensemble added in Phase 2.
        """
        return ProbabilityMap(
            fixture_id=features.fixture_id,
            market=market,
            probabilities={"1": 0.333, "X": 0.333, "2": 0.334},
            model_version="stub-v0",
            computed_at=datetime.now(timezone.utc),
        )

    async def build_claude_context(self, fixture: FixtureData) -> ClaudeContext:
        """Build context for Claude AI enrichment.

        Phase 1: Returns empty context -- Claude integration added in Phase 3.
        """
        return ClaudeContext(
            fixture_id=fixture.fixture_id,
            sport=fixture.sport,
            summary="",
        )
