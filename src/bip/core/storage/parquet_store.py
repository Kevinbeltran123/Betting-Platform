"""Hive-partitioned Parquet storage for feature data.

Uses Polars for all Parquet I/O with 4-level Hive-style partitioning
(sport=X/league=Y/season=Z/matchday=W/).

CRITICAL: Uses pyarrow_options={partition_cols: ...} NOT partition_by= argument.
Polars 1.x has a string partition bug with partition_by= on some platforms.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl

from bip.core.errors import StorageError


class ParquetStore:
    """Read/write 4-level Hive-partitioned Parquet files.

    Directory layout::

        base_path/
            features/
                sport=football/
                    league=premier_league/
                        season=2025-2026/
                            matchday=10/
                                *.parquet
    """

    PARTITION_COLS = ["sport", "league", "season", "matchday"]

    def __init__(self, base_path: Path | str) -> None:
        self.base_path = Path(base_path)

    # ------------------------------------------------------------------
    # Public API — features
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
        """Read feature data, optionally filtering by partition keys."""
        return self._read("features", sport=sport, league=league, season=season, matchday=matchday)

    # ------------------------------------------------------------------
    # Public API — matches (legacy compatibility)
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
        return self._read("matches", sport=sport, league=league, season=season, matchday=matchday)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write(self, df: pl.DataFrame, subdir: str) -> None:
        """Write a DataFrame as 4-level Hive-partitioned Parquet files.

        Removes existing partition directories that overlap with the incoming
        data before writing to ensure overwrite semantics.
        """
        if df.is_empty():
            return

        missing = [c for c in self.PARTITION_COLS if c not in df.columns]
        if missing:
            raise StorageError(f"DataFrame missing required partition columns: {missing}")

        target_dir = self.base_path / subdir

        partitions = df.select(self.PARTITION_COLS).unique()
        for row in partitions.iter_rows(named=True):
            partition_path = target_dir
            for col in self.PARTITION_COLS:
                partition_path = partition_path / f"{col}={row[col]}"
            if partition_path.exists():
                shutil.rmtree(partition_path)

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            df.write_parquet(
                target_dir,
                use_pyarrow=True,
                pyarrow_options={"partition_cols": self.PARTITION_COLS},
            )
        except Exception as exc:
            raise StorageError(f"Failed to write Parquet to {target_dir}: {exc}") from exc

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
            raise StorageError(f"Failed to read Parquet from {target_dir}: {exc}") from exc
