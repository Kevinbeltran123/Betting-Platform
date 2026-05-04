"""MetricsAggregator tests (CLV-04, D-13).

Wave 0 stub — implemented in Wave 3 (04-03).
Covers: PerformanceMetric return shape, LEFT JOIN keeps clv-less picks (Pitfall 3),
idempotent upsert on rerun (D-13), all 4 periods in one run, completion log emitted.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 3")


def test_compute_period_returns_PerformanceMetric():
    pass


def test_left_join_keeps_picks_without_clv_record():
    pass


def test_idempotent_rerun_upserts_not_inserts():
    pass


def test_all_four_periods_computed_in_one_run():
    pass


def test_metrics_aggregation_complete_log_emitted():
    pass
