"""Wave 0 RED stubs for PICK-05 (all-paths persist) and CLAUDE-01 D-07 fall-through.

Implementation lands in plan 03-07 (PickEngine.evaluate orchestration).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-07")


class TestEvaluateAllPaths:
    def test_all_paths_persist(self):
        """D-04: filtered, rejected, pending all hit picks table; sent path persists pending then schedules send."""
        raise NotImplementedError("plan 03-07")

    def test_no_edge_persists_filtered_no_edge(self):
        """D-02 + D-04: simulate_pick returns None → status=filtered, reason_code=no_edge."""
        raise NotImplementedError("plan 03-07")

    def test_market_cap_persists_filtered_market_cap(self):
        """D-09: cap exceeded → status=filtered, reason_code=market_cap."""
        raise NotImplementedError("plan 03-07")

    def test_claude_unavailable_filters(self):
        """D-07: validator returns None after 2 attempts → status=filtered, reason_code=claude_api_unavailable."""
        raise NotImplementedError("plan 03-07")

    def test_claude_reject_persists_rejected(self):
        """D-03 + D-14: REJECT verdict → status=rejected, never reaches Telegram."""
        raise NotImplementedError("plan 03-07")

    def test_idempotent_on_fixture_market_prediction(self):
        """specifics §195: re-running evaluate for same (fixture_id, market, prediction_id) does NOT duplicate."""
        raise NotImplementedError("plan 03-07")
