"""Verify migration 003 (is_shadow column + index) is applied to live Supabase.

Phase 02.1 Wave 0 stub — plan 02.1-01 fills in the psycopg verification body.

Exit criterion for Phase 02.1 (D-15). Returns exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    """Stub — real implementation lands in plan 02.1-01."""
    if not os.environ.get("SUPABASE_DB_PASSWORD"):
        print("FAIL: SUPABASE_DB_PASSWORD not set in environment")
        return 1
    print(
        "STUB: Phase 02.1 Wave 0 — plan 02.1-01 will implement the real "
        "information_schema and pg_indexes queries here."
    )
    return 1  # Stub never claims success


if __name__ == "__main__":
    sys.exit(main())
