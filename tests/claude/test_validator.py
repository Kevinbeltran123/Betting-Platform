"""Wave 0 RED stubs for CLAUDE-01 (D-06 strict tool_use, D-07 double-retry).

Implementation lands in plan 03-05 (claude/validator.py).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-05")


class TestToolSchema:
    def test_tool_schema_strict(self):
        """D-06: tool definition has strict=True + additionalProperties=false; tool_choice forces validate_pick."""
        raise NotImplementedError("plan 03-05")

    def test_verdict_enum(self):
        """D-06: verdict ∈ {CONFIRM, FLAG, REJECT}; pydantic regex ^(CONFIRM|FLAG|REJECT)$."""
        raise NotImplementedError("plan 03-05")

    def test_summary_max_120_chars(self):
        """D-06: summary field max_length=120."""
        raise NotImplementedError("plan 03-05")


class TestRetry:
    @pytest.mark.asyncio
    async def test_failure_double_retry(self):
        """D-07: APIError twice → asyncio.sleep(60) called once → returns None."""
        raise NotImplementedError("plan 03-05")

    @pytest.mark.asyncio
    async def test_first_attempt_success_no_sleep(self):
        """D-07: success on attempt 0 → no sleep, returns ClaudeVerdict."""
        raise NotImplementedError("plan 03-05")
