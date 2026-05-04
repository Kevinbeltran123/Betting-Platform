"""MetricsAggregator idempotency integration tests (CLV-04, D-13, D-16).

Wave 0 stub — implemented in Wave 3 (04-03).
Covers: repeat-run upserts the same row (D-13), one RPC call per
(sport, league, market) per period (D-16 round-trip count).
Hits the live Supabase project via the test client.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 3")


def test_repeat_run_upserts_same_row():
    pass


def test_compute_period_called_once_per_triple_per_period():
    pass
