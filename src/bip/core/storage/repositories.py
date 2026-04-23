"""Repository classes for Supabase CRUD operations.

Each repository wraps one table and provides typed methods for
insert, select, update, and upsert operations. Domain logic never
constructs Supabase queries directly — it goes through these repositories.

All operations are wrapped in error handling that converts Supabase
exceptions to StorageError with context (table name, operation).
"""

from __future__ import annotations

from dataclasses import dataclass

from bip.core.errors import StorageError
from bip.core.storage.models import (
    ClvRecord,
    OddsSnapshot,
    PerformanceMetric,
    Pick,
    Prediction,
    Result,
)
from supabase import Client


@dataclass
class PredictionRepository:
    """Repository for the predictions table."""

    client: Client

    def insert(self, prediction: Prediction) -> dict:
        """Insert a prediction and return the created record."""
        try:
            response = (
                self.client.table("predictions")
                .insert(prediction.to_supabase_dict())
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into predictions: {e}") from e

    def get_by_fixture(
        self, fixture_id: int, market: str | None = None, sport: str | None = None
    ) -> list[dict]:
        """Get predictions for a fixture, optionally filtered by market and sport."""
        try:
            query = (
                self.client.table("predictions").select("*").eq("fixture_id", fixture_id)
            )
            if market is not None:
                query = query.eq("market", market)
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from predictions: {e}") from e

    def get_latest(self, fixture_id: int, market: str) -> dict | None:
        """Get the most recent prediction for a fixture/market combo."""
        try:
            data = (
                self.client.table("predictions")
                .select("*")
                .eq("fixture_id", fixture_id)
                .eq("market", market)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ).data
            return data[0] if data else None
        except Exception as e:
            raise StorageError(f"Failed to select from predictions: {e}") from e

    def get_production(
        self, fixture_id: int, market: str | None = None
    ) -> list[dict]:
        """Get non-shadow predictions for a fixture (Phase 3 pick engine reads these) — ML-05."""
        try:
            query = (
                self.client.table("predictions")
                .select("*")
                .eq("fixture_id", fixture_id)
                .eq("is_shadow", False)
            )
            if market is not None:
                query = query.eq("market", market)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from predictions: {e}") from e


@dataclass
class PickRepository:
    """Repository for the picks table."""

    client: Client

    def insert(self, pick: Pick) -> dict:
        """Insert a pick and return the created record."""
        try:
            response = (
                self.client.table("picks").insert(pick.to_supabase_dict()).execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into picks: {e}") from e

    def get_by_fixture(self, fixture_id: int) -> list[dict]:
        """Get all picks for a fixture."""
        try:
            return (
                self.client.table("picks")
                .select("*")
                .eq("fixture_id", fixture_id)
                .execute()
            ).data
        except Exception as e:
            raise StorageError(f"Failed to select from picks: {e}") from e

    def get_by_status(self, status: str, sport: str | None = None) -> list[dict]:
        """Get all picks with a given status, optionally filtered by sport."""
        try:
            query = self.client.table("picks").select("*").eq("status", status)
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from picks: {e}") from e

    def update_status(self, pick_id: int, status: str) -> dict:
        """Update the status of a pick."""
        try:
            response = (
                self.client.table("picks")
                .update({"status": status})
                .eq("id", pick_id)
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to update picks: {e}") from e


@dataclass
class OddsSnapshotRepository:
    """Repository for the odds_snapshots table."""

    client: Client

    def insert(self, snapshot: OddsSnapshot) -> dict:
        """Insert an odds snapshot and return the created record."""
        try:
            response = (
                self.client.table("odds_snapshots")
                .insert(snapshot.to_supabase_dict())
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into odds_snapshots: {e}") from e

    def get_by_fixture(
        self, fixture_id: int, market: str | None = None, sport: str | None = None
    ) -> list[dict]:
        """Get odds snapshots for a fixture, optionally filtered by market and sport."""
        try:
            query = (
                self.client.table("odds_snapshots").select("*").eq("fixture_id", fixture_id)
            )
            if market is not None:
                query = query.eq("market", market)
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from odds_snapshots: {e}") from e

    def get_closing(self, fixture_id: int, market: str) -> dict | None:
        """Get the closing odds snapshot for a fixture/market."""
        try:
            data = (
                self.client.table("odds_snapshots")
                .select("*")
                .eq("fixture_id", fixture_id)
                .eq("market", market)
                .eq("is_closing", True)
                .execute()
            ).data
            return data[0] if data else None
        except Exception as e:
            raise StorageError(f"Failed to select from odds_snapshots: {e}") from e


@dataclass
class ResultRepository:
    """Repository for the results table."""

    client: Client

    def insert(self, result: Result) -> dict:
        """Insert a result and return the created record."""
        try:
            response = (
                self.client.table("results").insert(result.to_supabase_dict()).execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into results: {e}") from e

    def get_by_fixture(self, fixture_id: int) -> dict | None:
        """Get the result for a fixture (unique per fixture)."""
        try:
            data = (
                self.client.table("results")
                .select("*")
                .eq("fixture_id", fixture_id)
                .execute()
            ).data
            return data[0] if data else None
        except Exception as e:
            raise StorageError(f"Failed to select from results: {e}") from e

    def get_by_league(
        self, league: str, sport: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Get results for a league with optional sport filter and limit."""
        try:
            query = (
                self.client.table("results").select("*").eq("league", league).limit(limit)
            )
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from results: {e}") from e


@dataclass
class ClvRecordRepository:
    """Repository for the clv_records table."""

    client: Client

    def insert(self, record: ClvRecord) -> dict:
        """Insert a CLV record and return the created record."""
        try:
            response = (
                self.client.table("clv_records")
                .insert(record.to_supabase_dict())
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into clv_records: {e}") from e

    def get_by_pick(self, pick_id: int) -> dict | None:
        """Get the CLV record for a pick (unique per pick)."""
        try:
            data = (
                self.client.table("clv_records")
                .select("*")
                .eq("pick_id", pick_id)
                .execute()
            ).data
            return data[0] if data else None
        except Exception as e:
            raise StorageError(f"Failed to select from clv_records: {e}") from e

    def get_by_market(
        self, market: str, sport: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Get CLV records for a market with optional sport filter and limit."""
        try:
            query = (
                self.client.table("clv_records").select("*").eq("market", market).limit(limit)
            )
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from clv_records: {e}") from e


@dataclass
class PerformanceMetricRepository:
    """Repository for the performance_metrics table."""

    client: Client

    def upsert(self, metric: PerformanceMetric) -> dict:
        """Upsert a performance metric (insert or update on conflict)."""
        try:
            response = (
                self.client.table("performance_metrics")
                .upsert(
                    metric.to_supabase_dict(),
                    on_conflict="league,market,period,period_start",
                )
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to upsert into performance_metrics: {e}") from e

    def get_by_league_market(
        self, league: str, market: str, sport: str | None = None
    ) -> list[dict]:
        """Get performance metrics for a league/market combination."""
        try:
            query = (
                self.client.table("performance_metrics")
                .select("*")
                .eq("league", league)
                .eq("market", market)
            )
            if sport is not None:
                query = query.eq("sport", sport)
            return query.execute().data
        except Exception as e:
            raise StorageError(f"Failed to select from performance_metrics: {e}") from e
