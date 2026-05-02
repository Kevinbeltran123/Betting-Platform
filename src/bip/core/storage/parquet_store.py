"""Hive-partitioned Parquet storage for feature + results + odds data.

Uses Polars for all Parquet I/O with Hive-style partitioning.

Features use 4-level partitioning (sport/league/season/matchday) — unchanged.
Results and odds use 3-level partitioning (sport/league/season) — research
finding 3 / Pitfall 4: matchday is not a natural partition key for post-match
facts and forcing it creates tiny-file pathology.

CRITICAL: Uses pyarrow_options={partition_cols: ...} NOT partition_by= argument.
Polars 1.x has a string partition bug with partition_by= on some platforms.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
import structlog

from bip.core.errors import StorageError

logger = structlog.get_logger(__name__)


class ParquetStore:
    """Read/write Hive-partitioned Parquet files.

    Directory layout::

        base_path/
            features/
                sport=football/
                    league=premier_league/
                        season=2025-2026/
                            matchday=10/
                                *.parquet
            results/
                sport=football/
                    league=premier_league/
                        season=2024-2025/
                            *.parquet
            odds/
                sport=football/
                    league=premier_league/
                        season=2024-2025/
                            *.parquet
    """

    PARTITION_COLS = ["sport", "league", "season", "matchday"]       # features (4-level)
    RESULTS_PARTITION_COLS = ["sport", "league", "season"]           # D-04 + Pitfall 4
    ODDS_PARTITION_COLS = ["sport", "league", "season"]              # D-04 + Pitfall 4

    def __init__(self, base_path: Path | str) -> None:
        self.base_path = Path(base_path)

    # ------------------------------------------------------------------
    # Public API — features (unchanged)
    # ------------------------------------------------------------------

    def write_features(self, df: pl.DataFrame) -> None:
        """Write feature data with 4-level Hive partitioning."""
        self._write(df, "features")

    def read_features(
        self,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
        matchday: str | None = None,
    ) -> pl.DataFrame:
        """Read feature data, optionally filtering by partition keys.

        D-08: emits a structlog warning when feature_schema_version column is
        absent on a non-empty result (Phase 1 Parquet files predate the column
        and are treated as implicit v1).
        """
        df = self._read(
            "features", sport=sport, league=league, season=season, matchday=matchday,
        )
        if not df.is_empty() and "feature_schema_version" not in df.columns:
            logger.warning(
                "feature_schema_version_missing",
                note="Phase 1 data lacks feature_schema_version — treating as v1",
                league=league,
                sport=sport,
            )
        return df

    # ------------------------------------------------------------------
    # Public API — matches (legacy compatibility, unchanged)
    # ------------------------------------------------------------------

    def write_matches(self, df: pl.DataFrame) -> None:
        """Write match data with Hive partitioning."""
        self._write(df, "matches")

    def read_matches(
        self,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
        matchday: str | None = None,
    ) -> pl.DataFrame:
        """Read match data, optionally filtering by partition keys."""
        return self._read(
            "matches", sport=sport, league=league, season=season, matchday=matchday,
        )

    # ------------------------------------------------------------------
    # Public API — results (NEW, 3-level)
    # ------------------------------------------------------------------

    def write_results(self, df: pl.DataFrame) -> None:
        """Write match results with 3-level Hive partitioning (sport/league/season).

        D-04: fixture_id, home_goals, away_goals, status.
        """
        self._write(df, "results", partition_cols=self.RESULTS_PARTITION_COLS)

    def read_results(
        self,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
    ) -> pl.DataFrame:
        """Read results data, optionally filtering by partition keys."""
        return self._read("results", sport=sport, league=league, season=season)

    # ------------------------------------------------------------------
    # Public API — odds (NEW, 3-level)
    # ------------------------------------------------------------------

    def write_odds(self, df: pl.DataFrame) -> None:
        """Write bookmaker odds with 3-level Hive partitioning.

        D-04: fixture_id, bookmaker, opening_home/draw/away, closing_home/draw/away,
        pinnacle_close_home/draw/away (nullable).
        """
        self._write(df, "odds", partition_cols=self.ODDS_PARTITION_COLS)

    def read_odds(
        self,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
    ) -> pl.DataFrame:
        """Read odds data, optionally filtering by partition keys."""
        return self._read("odds", sport=sport, league=league, season=season)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write(
        self,
        df: pl.DataFrame,
        subdir: str,
        partition_cols: list[str] | None = None,
    ) -> None:
        """Write a DataFrame as Hive-partitioned Parquet files.

        Removes existing partition directories that overlap with the incoming
        data before writing to ensure overwrite semantics.

        Args:
            df: Data to write; must contain every column listed in partition_cols.
            subdir: Top-level directory under base_path (e.g., "features", "results").
            partition_cols: Partition columns; defaults to self.PARTITION_COLS
                (4-level features layout). Pass self.RESULTS_PARTITION_COLS /
                self.ODDS_PARTITION_COLS for 3-level stores (D-04 / Pitfall 4).
        """
        if df.is_empty():
            return

        partition_cols = partition_cols or self.PARTITION_COLS
        missing = [c for c in partition_cols if c not in df.columns]
        if missing:
            raise StorageError(
                f"DataFrame missing required partition columns: {missing}"
            )

        target_dir = self.base_path / subdir

        partitions = df.select(partition_cols).unique()
        for row in partitions.iter_rows(named=True):
            partition_path = target_dir
            for col in partition_cols:
                partition_path = partition_path / f"{col}={row[col]}"
            if partition_path.exists():
                shutil.rmtree(partition_path)

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            df.write_parquet(
                target_dir,
                use_pyarrow=True,
                pyarrow_options={"partition_cols": partition_cols},
            )
        except Exception as exc:
            raise StorageError(
                f"Failed to write Parquet to {target_dir}: {exc}"
            ) from exc

    def _read(
        self,
        subdir: str,
        *,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
        matchday: str | None = None,
    ) -> pl.DataFrame:
        """Read Hive-partitioned Parquet files with optional partition filters.

        Returns an empty DataFrame if the directory does not exist or
        contains no .parquet files.
        """
        target_dir = self.base_path / subdir

        if not target_dir.exists() or not list(target_dir.rglob("*.parquet")):
            return pl.DataFrame()

        try:
            lf = pl.scan_parquet(
                target_dir / "**/*.parquet",
                hive_partitioning=True,
            )

            if sport is not None:
                lf = lf.filter(pl.col("sport") == sport)
            if league is not None:
                lf = lf.filter(pl.col("league") == league)
            if season is not None:
                lf = lf.filter(pl.col("season") == season)
            if matchday is not None:
                lf = lf.filter(pl.col("matchday") == matchday)

            return lf.collect()
        except Exception as exc:
            raise StorageError(
                f"Failed to read Parquet from {target_dir}: {exc}"
            ) from exc
