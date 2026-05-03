"""Wave 0 RED stubs for orchestrator extension (Pitfall 6 auto-recover + D-01 dup-alert guard).

Implementation lands in plan 03-08.
Existing scheduler tests live at tests/test_scheduler.py and stay there;
this new file holds ONLY Phase 3-specific scheduler tests.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-08")


class TestAutoRecover:
    @pytest.mark.asyncio
    async def test_recover_pending_sends(self):
        """Pitfall 6: pending picks <30min old without scheduled send_pick_* job → re-queued via DateTrigger(now)."""
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_recover_skips_picks_older_than_30min(self):
        """Pitfall 6: pending picks >30min old are NOT re-queued (likely a real failure, not a restart)."""
        raise NotImplementedError("plan 03-08")


class TestT30DupAlertGuard:
    @pytest.mark.asyncio
    async def test_t30_skipped_when_t2h_pending(self):
        """D-01: T-30min must NOT call pick_engine.evaluate when a T-2h pick for the
        same (fixture_id, market='1X2') already has status=PickStatus.pending.
        (T-2h is the primary send moment; T-30min only retries on REJECT or no-edge.)
        Verify orchestrator emits structlog event 't30_skipped_pending_already' with
        the t2h_pick_id and does NOT invoke pick_engine.evaluate.
        """
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_rejected(self):
        """D-01: T-30min DOES proceed if the T-2h pick was rejected by Claude
        (status=PickStatus.rejected) — Claude may have rejected on stale lineup data."""
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_t30_proceeds_when_t2h_filtered(self):
        """D-01: T-30min DOES proceed if T-2h had no qualifying edge (status=filtered, no row
        with PickStatus.pending) — lineup-adjusted features may surface a new edge."""
        raise NotImplementedError("plan 03-08")
