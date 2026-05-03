"""Wave 0 RED stubs for D-16 result reconciliation.

Implementation lands in plan 03-08 (orchestrator extension).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-08")


class TestReconcile:
    @pytest.mark.asyncio
    async def test_status_to_settlement(self):
        """D-16: FT/AET → won/lost from goals; PST/CANC/ABD → void; PEN settles regulation+ET."""
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_reschedule_on_in_play(self):
        """Pitfall 7 + Risk 9: status in {2H, ET, SUSP, INT} → reschedule +30min, max 4 retries."""
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_pen_status_settles_on_regulation_plus_et(self):
        """D-16 + Betano standard: 1X2 settles on 90+ET draw → push (not on penalty winner)."""
        raise NotImplementedError("plan 03-08")

    @pytest.mark.asyncio
    async def test_reconcile_abandoned_after_4_retries(self):
        """RESEARCH §Open Questions Q3 (RESOLVED): after 4 reschedule attempts on INT/SUSP,
        log structlog ERROR event=reconcile_abandoned and leave pick status=pending
        (do NOT void — suspension can resume; FA decisions can settle weeks later)."""
        raise NotImplementedError("plan 03-08")
