"""GREEN tests for orchestrator extension (Pitfall 6 auto-recover + D-01 dup-alert guard
+ G-CODE-01/02/03 + G-MAINT-04 ABC compliance + full-Prediction build + sync repo guard).
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from bip.core.storage.models import Prediction
from bip.core.storage.repositories import PickRepository
from bip.sports import FeatureMatrix, FixtureData, ProbabilityMap, SportPlugin


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


# ---------------------------------------------------------------------
# Helpers for ABC-compliant orchestrator builds (used by Task-2 tests)
# ---------------------------------------------------------------------

def _abc_plugin(
    *,
    league: str = "premier_league",
    model_version: str = "ensemble-v3",
    odds: dict | None = None,
) -> AsyncMock:
    """Build an AsyncMock(spec=SportPlugin) with sensible return values for the pipeline."""
    plugin = AsyncMock(spec=SportPlugin)

    fm = MagicMock(spec=FeatureMatrix)
    fm.fixture_id = 999
    fm.sport = "football"
    fm.league = league
    fm.kickoff_utc = datetime(2026, 5, 1, 15, 0, tzinfo=UTC)
    fm.home_team = "Home FC"
    fm.away_team = "Away FC"
    plugin.build_features.return_value = fm

    pm = MagicMock(spec=ProbabilityMap)
    pm.fixture_id = 999
    pm.market = "1X2"
    pm.probabilities = {"1": 0.5, "X": 0.3, "2": 0.2}
    pm.model_version = model_version
    plugin.predict.return_value = pm

    plugin.get_opening_odds.return_value = (
        odds if odds is not None else {"1": 2.0, "X": 3.0, "2": 4.0}
    )
    return plugin


def _make_fixture(
    *,
    fixture_id: int = 999,
    home_team: str = "Arsenal",
    away_team: str = "Chelsea",
    league: str = "premier_league",
    kickoff: datetime | None = None,
) -> FixtureData:
    return FixtureData(
        fixture_id=fixture_id,
        league=league,
        sport="football",
        home_team=home_team,
        away_team=away_team,
        kickoff_utc=kickoff or datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
    )


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
    """D-01 dup-alert guard tests (Blocker #1 fix) -- now with sync repo + dict access."""

    @pytest.mark.asyncio
    async def test_t30_skipped_when_t2h_pending(self, capsys):
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin()
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        # SYNC, returns list[dict] (matches PickRepository.get_pending_for_fixture real shape)
        pick_repo = Mock(spec=PickRepository)
        pick_repo.get_pending_for_fixture = Mock(
            return_value=[{"id": 42, "market": "1X2", "status": "pending"}]
        )

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = _make_fixture()
        await orch._run_pipeline(fixture, stage="t_minus_30m")

        pick_engine.evaluate.assert_not_called()
        plugin.predict.assert_not_called()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "t30_skipped_pending_already" in combined, (
            f"expected 't30_skipped_pending_already' in stdout; got:\n{combined}"
        )

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_rejected(self):
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin()
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = Mock(spec=PickRepository)
        pick_repo.get_pending_for_fixture = Mock(
            return_value=[{"id": 43, "market": "1X2", "status": "rejected"}]
        )

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = _make_fixture()
        await orch._run_pipeline(fixture, stage="t_minus_30m")
        pick_engine.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_filtered(self):
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin()
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = Mock(spec=PickRepository)
        pick_repo.get_pending_for_fixture = Mock(return_value=[])

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = _make_fixture()
        await orch._run_pipeline(fixture, stage="t_minus_30m")
        pick_engine.evaluate.assert_awaited_once()


class TestPipelineABCCompliance:
    """G-CODE-01/02/03 + G-MAINT-04 — wiring contracts."""

    @pytest.mark.asyncio
    async def test_pipeline_invokes_only_plugin_abc_methods(self):
        """No AttributeError when plugin is strictly spec'd to SportPlugin ABC."""
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin()
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=None,
        )

        fixture = _make_fixture()
        await orch._run_pipeline(fixture, stage="t_minus_2h")

        plugin.build_features.assert_awaited_once()
        plugin.predict.assert_awaited_once()
        plugin.get_opening_odds.assert_awaited_once_with(fixture.fixture_id)

    @pytest.mark.asyncio
    async def test_pipeline_builds_full_prediction(self):
        """Orchestrator constructs a typed Prediction from fixture+features+prob_map."""
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin(
            league="premier_league",
            model_version="ensemble-v3",
            odds={"1": 2.0, "X": 3.0, "2": 4.0},
        )
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = Mock(spec=PickRepository)
        pick_repo.get_pending_for_fixture = Mock(return_value=[])

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        kickoff = datetime(2026, 5, 1, 15, 0, tzinfo=UTC)
        fixture = _make_fixture(
            fixture_id=999,
            home_team="Arsenal",
            away_team="Chelsea",
            league="premier_league",
            kickoff=kickoff,
        )

        await orch._run_pipeline(fixture, stage="t_minus_30m")

        pick_engine.evaluate.assert_awaited_once()
        prediction = pick_engine.evaluate.call_args.args[0]
        opening_odds = pick_engine.evaluate.call_args.args[1]

        assert isinstance(prediction, Prediction)
        assert prediction.fixture_id == 999
        assert prediction.home_team == "Arsenal"
        assert prediction.away_team == "Chelsea"
        assert prediction.league == "premier_league"
        assert prediction.sport == "football"
        assert prediction.kickoff_utc == kickoff
        assert prediction.market == "1X2"
        assert prediction.model_version == "ensemble-v3"
        assert prediction.probabilities == {"1": 0.5, "X": 0.3, "2": 0.2}
        assert prediction.is_lineup_adjusted is True

        assert opening_odds == {"1": 2.0, "X": 3.0, "2": 4.0}

    @pytest.mark.asyncio
    async def test_dup_alert_guard_uses_sync_repo_and_dict_access(self):
        """G-CODE-02 — sync call (no await) + dict access via p['market']."""
        from bip.scheduler.orchestrator import PipelineOrchestrator

        plugin = _abc_plugin()
        pick_engine = MagicMock()
        pick_engine.evaluate = AsyncMock()

        pick_repo = Mock(spec=PickRepository)
        pick_repo.get_pending_for_fixture = Mock(
            return_value=[{"id": 42, "market": "1X2", "status": "pending"}]
        )

        orch = PipelineOrchestrator(
            plugin=plugin,
            pick_engine=pick_engine,
            pick_repo=pick_repo,
        )

        fixture = _make_fixture()
        await orch._run_pipeline(fixture, stage="t_minus_30m")

        pick_repo.get_pending_for_fixture.assert_called_once_with(fixture.fixture_id)
        pick_engine.evaluate.assert_not_called()
        plugin.predict.assert_not_called()
