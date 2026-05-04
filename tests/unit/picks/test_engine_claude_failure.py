"""PickEngine Claude failure-mode tests (D-01).

Wave 0 stub — implemented in Wave 4 (04-04).
Covers: filter mode (default — pick persisted as 'filtered', never sent),
skip mode (opt-in — pick persisted as 'pending' with claude_validation='SKIPPED', sent).
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 4")


def test_filter_mode_persists_filtered_with_reason_code():
    pass


def test_skip_mode_persists_pending_with_SKIPPED_validation():
    pass


def test_skip_mode_schedules_send():
    pass
