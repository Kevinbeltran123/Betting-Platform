"""Repository tests — CLV-04 (sport field in PerformanceMetric)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from tests.conftest import setup_mock_chain


class TestPredictionRepository:
    """Prediction repository insert and select."""

    def test_insert_returns_dict(self, mock_client):
        """insert() must return the created record dict."""
        setup_mock_chain(mock_client, data=[{"id": 1, "fixture_id": 12345}])
        from bip.core.storage.repositories import PredictionRepository
        from bip.core.storage.models import Prediction
        repo = PredictionRepository(client=mock_client)
        pred = Prediction(
            fixture_id=12345,
            league="premier_league",
            sport="football",
            market="btts",
            home_team="Arsenal",
            away_team="Chelsea",
            kickoff_utc=datetime(2026, 4, 22, 15, 0, 0),
            probabilities={"yes": 0.65, "no": 0.35},
            model_version="v1.0",
        )
        result = repo.insert(pred)
        assert result["fixture_id"] == 12345

    def test_sport_filter_passed_to_query(self, mock_client):
        """get_by_fixture() with sport parameter must call .eq('sport', sport)."""
        builder = setup_mock_chain(mock_client, data=[])
        from bip.core.storage.repositories import PredictionRepository
        repo = PredictionRepository(client=mock_client)
        repo.get_by_fixture(fixture_id=12345, sport="football")
        builder.eq.assert_any_call("sport", "football")


class TestPerformanceMetricRepository:
    """CLV-04: PerformanceMetric.to_supabase_dict() includes sport field."""

    def test_performance_metric_dict_includes_sport(self):
        """to_supabase_dict() must include sport key — CLV-04."""
        from bip.core.storage.models import PerformanceMetric
        from bip.core.types import AggregationPeriod
        metric = PerformanceMetric(
            sport="football",
            league="premier_league",
            market="btts",
            period=AggregationPeriod.weekly,
            period_start=datetime(2026, 4, 14),
            roi=0.05,
            yield_pct=0.04,
            avg_clv=0.03,
            wins=3,
            losses=2,
            voids=0,
            total_picks=5,
        )
        d = metric.to_supabase_dict()
        assert "sport" in d
        assert d["sport"] == "football"

    def test_clv_record_has_odds_fetched_at(self):
        """ClvRecord model must have odds_fetched_at field — D-04c."""
        from bip.core.storage.models import ClvRecord
        import inspect
        fields = ClvRecord.model_fields
        assert "odds_fetched_at" in fields, (
            "ClvRecord missing odds_fetched_at — required by D-04c"
        )
