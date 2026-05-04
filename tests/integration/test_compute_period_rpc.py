"""compute_performance_period RPC integration tests (CLV-04, D-02, Pitfall 3).

Wave 0 stub — implemented in Wave 3 (04-03).
Hits the live Supabase project (migration 005). Covers: LEFT JOIN keeps
picks without clv_records (Pitfall 3 + D-02), status filter excludes
filtered/rejected/pending, won/lost/void counts match seed data.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 3")


def test_left_join_picks_without_clv_present_in_count():
    pass


def test_status_filter_excludes_filtered_rejected_pending():
    pass


def test_won_lost_void_counts_match_seed_data():
    pass
