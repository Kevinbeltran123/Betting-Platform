"""Polars drift parsing tests for Supabase ISO8601 date strings (CLV-04, WARNING 4).

Wave 0 stub — implemented in Wave 3 (04-03).
Supabase REST returns settled_at as ISO8601 strings; the drift compute path
uses Polars datetime arithmetic. Covers: ISO8601 string parsing, native
datetime backwards compatibility.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implemented in Wave 3")


def test_compute_weekly_drift_parses_supabase_iso8601_strings():
    pass


def test_compute_weekly_drift_handles_native_datetime_objects():
    pass
