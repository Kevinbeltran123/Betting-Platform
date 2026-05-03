"""Wave 0 RED stubs for PICK-04 (D-12, D-14, D-15).

Implementation lands in plan 03-06 (telegram/sender.py + templates/pick.html).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-06")


class TestRender:
    def test_render_escapes_special_chars(self):
        """D-12 + Threat T-3-XSS: <script> in team name is HTML-escaped (Jinja2 autoescape)."""
        raise NotImplementedError("plan 03-06")

    def test_flag_warning_marker(self):
        """D-14: claude_validation='FLAG' → leading WARNING emoji + 'Claude flagged: <reason_code>' line."""
        raise NotImplementedError("plan 03-06")

    def test_confirm_clean(self):
        """D-14: claude_validation='CONFIRM' → no WARNING marker."""
        raise NotImplementedError("plan 03-06")

    def test_summary_bullets_max_3(self):
        """D-15: claude_summary split on ' * ' separator; max 3 bullets."""
        raise NotImplementedError("plan 03-06")

    def test_message_length_under_600_chars(self):
        """specifics §194: total length under ~600 chars for mobile rendering."""
        raise NotImplementedError("plan 03-06")
