"""GREEN tests for orchestrator extension (Pitfall 6 auto-recover + D-01 dup-alert guard)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_orchestrator(pending_rows=None, existing_jobs=None):
    from bip.scheduler.orchestrator import PipelineOrchestrator

    plugin = MagicMock()
    pick_repo = MagicMock()
    pick_repo.query_pending_sends = MagicMock(return_value=pending_rows or [])

    pick_engine = MagicMock()
    pick_engine.evaluate = AsyncMock()

    orch = PipelineOrchestrator(plugin=plugin, pick_repo=pick_repo, pick_engine=pick_engine)

    fake_jobs = []
    for jid in (existing_jobs or []):
        j = MagicMock()
        j.id = jid
        fake_jobs.append(j)
    for jid in ("daily_orchestrator", "nightly_clv_reconciliation"):
        j = MagicMock()
        j.id = jid
        fake_jobs.append(j)

    orch.scheduler = MagicMock()
    orch.scheduler.get_jobs = MagicMock(return_value=fake_jobs)
    orch.scheduler.add_job = MagicMock()
    return orch, pick_repo


class TestAutoRecover:
    @pytest.mark.asyncio
    async def test_recover_pending_sends(self, monkeypatch):
        from datetime import UTC, datetime
        import bip.scheduler.orchestrator as mod

        class _Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(mod, "datetime", _Now)

        orch, _ = _make_orchestrator(
            pending_rows=[{"id": 1, "fixture_id": 999, "market": "1X2", "sport": "football",
                           "claude_validation": "CONFIRM"}],
            existing_jobs=["pipeline_999_t_minus_2h"],
        )
        await orch._auto_recover()

        send_calls = [c for c in orch.scheduler.add_job.call_args_list
                      if c.kwargs.get("id") == "send_pick_999_1X2"]
        assert len(send_calls) == 1
        assert send_calls[0].kwargs["replace_existing"] is True
        assert send_calls[0].kwargs["misfire_grace_time"] == 300

    @pytest.mark.asyncio
    async def test_recover_skips_already_scheduled(self, monkeypatch):
        from datetime import UTC, datetime
        import bip.scheduler.orchestrator as mod

        class _Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(mod, "datetime", _Now)

        orch, _ = _make_orchestrator(
            pending_rows=[{"id": 1, "fixture_id": 999, "market": "1X2", "sport": "football",
                           "claude_validation": "CONFIRM"}],
            existing_jobs=["pipeline_999_t_minus_2h", "send_pick_999_1X2"],
        )
        await orch._auto_recover()

        send_calls = [c for c in orch.scheduler.add_job.call_args_list
                      if c.kwargs.get("id") == "send_pick_999_1X2"]
        assert len(send_calls) == 0

    @pytest.mark.asyncio
    async def test_recover_handles_no_pending(self, monkeypatch):
        from datetime import UTC, datetime
        import bip.scheduler.orchestrator as mod

        class _Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(mod, "datetime", _Now)

        orch, _ = _make_orchestrator(pending_rows=[], existing_jobs=["pipeline_999_t_minus_2h"])
        await orch._auto_recover()
        send_calls = [c for c in orch.scheduler.add_job.call_args_list
                      if c.kwargs.get("id", "").startswith("send_pick_")]
        assert send_calls == []

    @pytest.mark.asyncio
    async def test_recover_skips_when_unwired(self, monkeypatch):
        from datetime import UTC, datetime
        import bip.scheduler.orchestrator as mod

        class _Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(mod, "datetime", _Now)

        from bip.scheduler.orchestrator import PipelineOrchestrator
        plugin = MagicMock()
        orch = PipelineOrchestrator(plugin=plugin)
        # Provide a non-default fixture job so daily_orchestrator path is skipped
        existing = MagicMock()
        existing.id = "pipeline_999_t_minus_2h"
        orch.scheduler = MagicMock()
        orch.scheduler.get_jobs = MagicMock(return_value=[existing])
        # Should not raise (pick_repo None → early return after fixture jobs check)
        await orch._auto_recover()


class TestT30DupAlertGuard:
    """D-01 dup-alert guard tests (Blocker #1 fix)."""

    @pytest.mark.asyncio
    async def test_t30_skipped_when_t2h_pending(self, capsys):
        from bip.scheduler.orchestrator import PipelineOrchestrator
        from bip.core.storage.models import PickStatus

        plugin = MagicMock()
        plugin.build_features = AsyncMock()
        plugin.predict = AsyncMock()
        plugin.get_opening_odds = AsyncMock()

        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = MagicMock()
        existing_pick = MagicMock()
        existing_pick.id = 42
        existing_pick.market = "1X2"
        existing_pick.status = PickStatus.pending
        pick_repo.get_pending_for_fixture = AsyncMock(return_value=[existing_pick])

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = MagicMock()
        fixture.fixture_id = 999

        await orch._run_pipeline(fixture, stage="t_minus_30m")

        pick_engine.evaluate.assert_not_called()
        plugin.predict.assert_not_called()
        # structlog writes to stdout — check captured output
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "t30_skipped_pending_already" in combined, \
            f"expected 't30_skipped_pending_already' in stdout; got:\n{combined}"

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_rejected(self):
        from bip.scheduler.orchestrator import PipelineOrchestrator
        from bip.core.storage.models import PickStatus

        plugin = MagicMock()
        plugin.build_features = AsyncMock()
        plugin.predict = AsyncMock(return_value=MagicMock())
        plugin.get_opening_odds = AsyncMock(return_value=MagicMock())

        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = MagicMock()
        rejected_pick = MagicMock()
        rejected_pick.id = 43
        rejected_pick.market = "1X2"
        rejected_pick.status = PickStatus.rejected
        pick_repo.get_pending_for_fixture = AsyncMock(return_value=[rejected_pick])

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = MagicMock()
        fixture.fixture_id = 999

        await orch._run_pipeline(fixture, stage="t_minus_30m")
        pick_engine.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_filtered(self):
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = MagicMock()
        plugin.build_features = AsyncMock()
        plugin.predict = AsyncMock(return_value=MagicMock())
        plugin.get_opening_odds = AsyncMock(return_value=MagicMock())

        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = MagicMock()
        pick_repo.get_pending_for_fixture = AsyncMock(return_value=[])

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = MagicMock()
        fixture.fixture_id = 999

        await orch._run_pipeline(fixture, stage="t_minus_30m")
        pick_engine.evaluate.assert_awaited_once()
