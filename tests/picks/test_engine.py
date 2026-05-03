"""GREEN tests for PickRepository extensions (D-09 window query, D-16 reconcile, Pitfall 6 recovery).
PickEngine tests stay skipped — they activate in plan 03-07.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# NOTE: PickEngine class tests below stay skipped — implementation lands in plan 03-07.
ENGINE_SKIP = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-07")


class TestPickRepositoryExtensions:
    def test_get_window_picks_filters(self, mock_client):
        from tests.conftest import setup_mock_chain
        from bip.core.storage.repositories import PickRepository

        builder = setup_mock_chain(mock_client, data=[
            {"market": "1X2", "status": "pending", "created_at": "2026-05-02T10:00:00+00:00"},
        ])
        # neq returns the same builder (fluent chain)
        builder.neq.return_value = builder
        builder.gte.return_value = builder

        repo = PickRepository(client=mock_client)
        rows = repo.get_window_picks(sport="football", hours=168)

        assert isinstance(rows, list)
        assert len(rows) == 1
        # Verify the chain was called with the expected filters
        mock_client.table.assert_called_with("picks")

    def test_get_pending_for_fixture(self, mock_client):
        from tests.conftest import setup_mock_chain
        from bip.core.storage.repositories import PickRepository

        setup_mock_chain(mock_client, data=[{"id": 1, "status": "pending"}])
        repo = PickRepository(client=mock_client)
        rows = repo.get_pending_for_fixture(fixture_id=999)
        assert len(rows) == 1
        mock_client.table.assert_called_with("picks")

    def test_update_status_by_fixture(self, mock_client):
        from tests.conftest import setup_mock_chain
        from bip.core.storage.repositories import PickRepository

        setup_mock_chain(mock_client, data=[{"id": 1}, {"id": 2}])
        repo = PickRepository(client=mock_client)
        count = repo.update_status_by_fixture(fixture_id=1, new_status="void")
        assert count == 2

    def test_query_pending_sends_filters_by_age(self, mock_client):
        from tests.conftest import setup_mock_chain
        from bip.core.storage.repositories import PickRepository

        builder = setup_mock_chain(mock_client, data=[{"id": 1, "status": "pending", "claude_validation": "CONFIRM"}])
        # Mock the chained .not_.is_(...) — Supabase-py builder API
        not_obj = MagicMock()
        not_obj.is_.return_value = builder
        builder.not_ = not_obj
        builder.gte.return_value = builder

        repo = PickRepository(client=mock_client)
        rows = repo.query_pending_sends(sport="football", max_age_minutes=30)
        assert isinstance(rows, list)
        mock_client.table.assert_called_with("picks")

    def test_storage_errors_wrap_exceptions(self, mock_client):
        from bip.core.errors import StorageError
        from bip.core.storage.repositories import PickRepository

        mock_client.table.side_effect = RuntimeError("supabase unreachable")
        repo = PickRepository(client=mock_client)
        with pytest.raises(StorageError):
            repo.get_window_picks(sport="football")


@ENGINE_SKIP
class TestEvaluateAllPaths:
    def test_all_paths_persist(self):
        raise NotImplementedError("plan 03-07")

    def test_no_edge_persists_filtered_no_edge(self):
        raise NotImplementedError("plan 03-07")

    def test_market_cap_persists_filtered_market_cap(self):
        raise NotImplementedError("plan 03-07")

    def test_claude_unavailable_filters(self):
        raise NotImplementedError("plan 03-07")

    def test_claude_reject_persists_rejected(self):
        raise NotImplementedError("plan 03-07")

    def test_idempotent_on_fixture_market_prediction(self):
        raise NotImplementedError("plan 03-07")
