"""Wave 0 RED stubs for CORNERS-01 D-17b Polars coverage script.

Implementation lands in plan 03-10.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-10")


class TestThresholdLogic:
    def test_threshold_logic(self):
        """D-17b: ≥95% coverage on ≥3 seasons per league → pass; otherwise fail."""
        raise NotImplementedError("plan 03-10")

    def test_ft_only_filter(self):
        """D-17b + specifics §199: PST/CANC/ABD rows excluded from coverage denominator."""
        raise NotImplementedError("plan 03-10")

    def test_missing_columns_fail_gate(self):
        """A5 + D-17b: home_corners/away_corners absent from Parquet → coverage_pct=0 → fail."""
        raise NotImplementedError("plan 03-10")
