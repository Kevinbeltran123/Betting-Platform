"""Wave 0 RED stubs for PICK-02, PICK-03 (D-09, D-10, D-11).

Implementation lands in plan 03-03 (account_longevity.py).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-03")


class TestQuarterKelly:
    def test_quarter_kelly(self):
        """PICK-02: kelly_fraction = (edge / (odds - 1)) × 0.25."""
        raise NotImplementedError("plan 03-03")

    def test_round_half_unit(self):
        """PICK-02: stake rounded to nearest 0.5 unit (anti-fingerprinting)."""
        raise NotImplementedError("plan 03-03")


class TestDeterministicJitter:
    def test_jitter_stable_across_processes(self):
        """D-10 + Pitfall 1: md5-seeded jitter must be stable across PYTHONHASHSEED variations.

        Spawn two subprocesses with PYTHONHASHSEED=0 and PYTHONHASHSEED=random,
        compare deterministic_jitter(12345, "1X2") output.
        """
        raise NotImplementedError("plan 03-03")

    def test_jitter_bounds(self):
        """D-10: jitter_pct ∈ [-0.10, +0.10]."""
        raise NotImplementedError("plan 03-03")


class TestSendAtVariance:
    def test_send_at_stable(self):
        """D-11: deterministic_send_at(t, fixture_id) is identical for same fixture_id."""
        raise NotImplementedError("plan 03-03")

    def test_send_at_within_30min_window(self):
        """D-11: send_at - prediction_completed_at ∈ [0, 1800]s."""
        raise NotImplementedError("plan 03-03")


class TestMarketCap:
    def test_market_cap_drop(self):
        """D-09: drop on bind when adding pick would push market past 60% in 168h window."""
        raise NotImplementedError("plan 03-03")

    def test_market_cap_dormant_under_5_picks(self):
        """D-09: tiny sample (<5 sent picks) does NOT gate."""
        raise NotImplementedError("plan 03-03")
