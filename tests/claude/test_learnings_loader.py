"""Wave 0 RED stubs for learnings_loader (CLAUDE-01 audit + caching).

Implementation lands in plan 03-04 (claude/learnings_loader.py).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub — implementation lands in plan 03-04")


class TestLearningsLoader:
    def test_sha_stamp_and_cache_block(self):
        """Risks 5: load_learnings returns (text, git_sha); SHA is 40-char hex from git log -1."""
        raise NotImplementedError("plan 03-04")

    def test_falls_back_to_sha256_when_uncommitted(self):
        """Risks 5: when git log fails, falls back to hashlib.sha256(text).hexdigest()[:16]."""
        raise NotImplementedError("plan 03-04")

    def test_size_above_2048_tokens(self):
        """Pitfall 4: ported football-learnings.md must be ≥2048 tokens (cache minimum for sonnet-4-6)."""
        raise NotImplementedError("plan 03-04")
