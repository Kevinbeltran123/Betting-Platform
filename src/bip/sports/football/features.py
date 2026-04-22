"""Football feature engineering -- Polars-based.

CRITICAL (DATA-05): computed_at must be set to the time features are computed,
NOT the fixture kickoff time. Features must only use data available at prediction_time.

T-05-03: computed_at is always datetime.now(timezone.utc) captured BEFORE API calls.
This establishes the point-in-time boundary and prevents future data leakage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import structlog

from bip.sports import FeatureMatrix, FixtureData

logger = structlog.get_logger(__name__)


class FeatureEngineer:
    """Builds point-in-time correct feature matrices from API-Football data.

    Phase 1: Basic availability features (stats present, lineups confirmed).
    Phase 2 (ML Core): Expands to form, H2H, Dixon-Coles ratings, etc.
    """

    def build_features_for_fixture(
        self,
        fixture: FixtureData,
        raw_stats: dict,
        raw_lineups: dict,
        computed_at: datetime | None = None,
    ) -> FeatureMatrix:
        """Build feature matrix from raw API responses.

        Args:
            fixture: The fixture being analyzed.
            raw_stats: Response from GET /fixtures/statistics.
            raw_lineups: Response from GET /fixtures/lineups.
            computed_at: Point-in-time timestamp. Defaults to now (UTC).
                         MUST be <= fixture.kickoff_utc to prevent leakage.
                         Never set to kickoff time or fixture date.

        Returns:
            FeatureMatrix with computed_at set to the passed-in (or current) time.
        """
        if computed_at is None:
            computed_at = datetime.now(UTC)

        features = self._extract_features(fixture, raw_stats, raw_lineups)

        logger.info(
            "features_built",
            fixture_id=fixture.fixture_id,
            feature_count=len(features),
            computed_at=computed_at.isoformat(),
        )

        return FeatureMatrix(
            fixture_id=fixture.fixture_id,
            sport=fixture.sport,
            league=fixture.league,
            computed_at=computed_at,
            features=features,
        )

    def _extract_features(
        self,
        fixture: FixtureData,
        raw_stats: dict,
        raw_lineups: dict,
    ) -> dict[str, float]:
        """Extract numeric features from raw API responses.

        Phase 1: Returns basic structural features.
        Phase 2 (ML Core) will expand this significantly with form,
        H2H, corner stats, injuries, and Dixon-Coles ratings.
        """
        features: dict[str, float] = {}

        # Basic availability indicators (1.0 if data present, 0.0 if not)
        stats_available = len(raw_stats.get("response", [])) > 0
        lineups_confirmed = len(raw_lineups.get("response", [])) == 2
        features["stats_available"] = 1.0 if stats_available else 0.0
        features["lineups_confirmed"] = 1.0 if lineups_confirmed else 0.0

        return features

    def to_parquet_row(
        self,
        fm: FeatureMatrix,
        matchday: int,
        season: str,
    ) -> pl.DataFrame:
        """Convert FeatureMatrix to a Polars DataFrame row for ParquetStore.

        Includes all 4 partition columns required by ParquetStore:
        sport, league, season, matchday.

        Args:
            fm: Computed feature matrix.
            matchday: Matchday number for Hive partition key.
            season: Season string (e.g., "2025-2026") for Hive partition key.

        Returns:
            Single-row Polars DataFrame ready for ParquetStore.write_features().
        """
        row: dict[str, list] = {
            "fixture_id": [fm.fixture_id],
            "sport": [fm.sport],
            "league": [fm.league],
            "season": [season],
            "matchday": [matchday],
            "computed_at": [fm.computed_at.isoformat()],
        }
        for key, val in fm.features.items():
            row[key] = [val]
        return pl.DataFrame(row)
