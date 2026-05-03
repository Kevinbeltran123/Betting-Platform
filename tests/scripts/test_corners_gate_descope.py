"""Wave 0 RED stubs for CORNERS-01 D-18 descope orchestration.

Implementation lands in plan 03-10.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-10")


class TestDescope:
    def test_descope_three_artifacts(self):
        """D-18: gate-fail produces (a) ROADMAP.md edit, (b) STATE.md Blockers entry, (c) single git commit."""
        raise NotImplementedError("plan 03-10")

    def test_pass_writes_corners_gate_pass_md(self):
        """D-18: gate-pass produces scripts/corners_gate_pass.md and skips ROADMAP edit."""
        raise NotImplementedError("plan 03-10")
