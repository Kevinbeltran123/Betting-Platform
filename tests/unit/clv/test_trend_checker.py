"""ClvTrendChecker tests (CLV-03, D-09–D-12).

Wave 0 stub — implemented in Wave 2 (04-02).
Covers: rolling-50 threshold, sample-size guard, 12h cooldown, per-market
sample gate (D-10), per-market alert tag (D-12).
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 2")


def test_alert_fires_below_threshold():
    pass


def test_no_alert_when_above_threshold():
    pass


def test_skip_insufficient_sample():
    pass


def test_cooldown_suppresses_repeat_alert():
    pass


def test_per_market_skipped_below_50():
    pass


def test_per_market_alert_appends_market_tag():
    pass
