"""GREEN tests for PICK-02, PICK-03 (D-09, D-10, D-11).

Implementation: src/bip/core/picks/account_longevity.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


class TestQuarterKelly:
    def test_quarter_kelly(self):
        from bip.core.picks.account_longevity import quarter_kelly_units
        # PICK-02 math: edge=0.05, odds=2.10 → (0.05/1.10) * 0.25 ≈ 0.01136
        result = quarter_kelly_units(0.05, 2.10)
        assert abs(result - (0.05 / 1.10 * 0.25)) < 1e-9
        # Edge clamping: negative edge → 0
        assert quarter_kelly_units(-0.01, 2.0) == 0.0
        # Avoid div-by-zero on odds ≤ 1.0
        assert quarter_kelly_units(0.05, 1.0) == 0.0
        assert quarter_kelly_units(0.05, 0.5) == 0.0

    def test_round_half_unit(self):
        from bip.core.picks.account_longevity import round_to_nearest_half_unit
        assert round_to_nearest_half_unit(1.7) == 1.5
        assert round_to_nearest_half_unit(1.8) == 2.0
        assert round_to_nearest_half_unit(0.0) == 0.0
        assert round_to_nearest_half_unit(0.24) == 0.0
        assert round_to_nearest_half_unit(0.26) == 0.5


class TestDeterministicJitter:
    def test_jitter_stable_across_processes(self):
        """D-10 + Pitfall 1: md5 seeding survives PYTHONHASHSEED variation."""
        # Spawn two subprocesses with different PYTHONHASHSEED, compare jitter for same input.
        script = (
            "from bip.core.picks.account_longevity import deterministic_jitter; "
            "print(deterministic_jitter(12345, '1X2'))"
        )
        env_a = {**os.environ, "PYTHONHASHSEED": "0"}
        env_b = {**os.environ, "PYTHONHASHSEED": "random"}
        r_a = subprocess.run([sys.executable, "-c", script], env=env_a, capture_output=True, text=True, check=True)
        r_b = subprocess.run([sys.executable, "-c", script], env=env_b, capture_output=True, text=True, check=True)
        assert r_a.stdout.strip() == r_b.stdout.strip(), (
            f"Jitter NOT stable across PYTHONHASHSEED: {r_a.stdout!r} vs {r_b.stdout!r} — "
            "implementation likely uses Python hash() instead of hashlib.md5."
        )

    def test_jitter_bounds(self):
        from bip.core.picks.account_longevity import deterministic_jitter
        for fid in range(100, 200):
            j = deterministic_jitter(fid, "1X2")
            assert -0.10 <= j <= 0.10, f"jitter out of bounds for fixture {fid}: {j}"
            # Must be one of the 21 discrete values
            assert round(j * 100) in range(-10, 11), f"non-discrete jitter for fixture {fid}: {j}"


class TestSendAtVariance:
    def test_send_at_stable(self):
        from bip.core.picks.account_longevity import deterministic_send_at
        t = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        assert deterministic_send_at(t, 999) == deterministic_send_at(t, 999)

    def test_send_at_within_30min_window(self):
        from bip.core.picks.account_longevity import deterministic_send_at
        t = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        for fid in range(100, 200):
            send_at = deterministic_send_at(t, fid)
            delta = (send_at - t).total_seconds()
            assert 0 <= delta <= 1800, f"send_at - t = {delta}s out of [0, 1800]"


class TestMarketCap:
    def test_market_cap_drop(self):
        from bip.core.picks.account_longevity import exceeds_60pct_cap
        # 10 prior picks: 6 in 1X2, 4 in BTTS. Adding another 1X2 → 7/11 = 63.6% > 60%.
        repo = MagicMock()
        repo.get_window_picks.return_value = [
            *[{"market": "1X2"}] * 6,
            *[{"market": "BTTS"}] * 4,
        ]
        assert exceeds_60pct_cap(repo, market="1X2", sport="football") is True
        # Adding a BTTS instead → 5/11 = 45.5% (no cap)
        assert exceeds_60pct_cap(repo, market="BTTS", sport="football") is False

    def test_market_cap_dormant_under_5_picks(self):
        from bip.core.picks.account_longevity import exceeds_60pct_cap
        repo = MagicMock()
        repo.get_window_picks.return_value = [{"market": "1X2"}] * 4
        # Sample too small → cap dormant
        assert exceeds_60pct_cap(repo, market="1X2", sport="football") is False
