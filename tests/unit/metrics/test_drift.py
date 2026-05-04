"""Weekly model-CLV drift tests (D-14, RESEARCH §Drift Statistical Method).

Wave 0 stub — implemented in Wave 3 (04-03).
Covers: hard 2pp threshold, soft 1.5×stdev threshold, insufficient-sample None,
stdev floor (heavy-tail mitigation), stdev computed over daily means not per-pick.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 3")


def test_hard_threshold_2pp_drop_triggers():
    pass


def test_soft_threshold_15x_stdev_triggers():
    pass


def test_insufficient_sample_returns_None():
    pass


def test_stdev_floor_prevents_zero_stdev_tight_gate():
    pass


def test_drift_uses_stdev_of_daily_means_not_per_pick():
    pass
