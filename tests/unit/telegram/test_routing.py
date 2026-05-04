"""Telegram channel routing tests (D-03).

Wave 0 stub — implemented in Wave 4 (04-04).
Covers: picks alerts route to TELEGRAM_CHANNEL_ID, ops alerts route to
TELEGRAM_OPS_CHANNEL_ID, two distinct TelegramBot instances are constructed.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 4")


def test_picks_alert_routes_to_picks_channel():
    pass


def test_ops_alert_routes_to_ops_channel():
    pass


def test_two_separate_TelegramBot_instances_constructed():
    pass
