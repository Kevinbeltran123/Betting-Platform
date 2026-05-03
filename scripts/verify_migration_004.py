"""Verify migration 004 (claude_* columns + status CHECK widening + index + unique idempotency constraint) on live Supabase.

Wave 0 SKELETON — returns exit 1 even when SUPABASE_DB_PASSWORD is set.
Mirrors the 02.1 D-15 pattern: a stub that cannot accidentally mark the gate complete.
Real implementation lands in plan 03-01 (after migration SQL exists).

Security (T-02.1-02, T-02.1-03):
  - Never log or print the DB password or the full connection string.
  - All SQL queries use parameterized placeholders (%s), never f-strings.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote

import structlog

from bip.core.settings import Settings

logger = structlog.get_logger(__name__)


# Copied verbatim from verify_migration_003.py — DO NOT diverge.
def derive_db_url(supabase_url: str, db_password: str) -> str:
    subdomain = supabase_url.removeprefix("https://").removesuffix(".supabase.co")
    return (
        f"postgresql://postgres:{quote(db_password, safe='')}"
        f"@db.{subdomain}.supabase.co:5432/postgres"
    )


def main() -> int:
    # Wave 0 stub: returns 1 always so accidental run cannot mark the migration complete.
    # Plan 03-01 replaces this body with the real psycopg verification.
    settings = Settings()  # noqa: F841 — exercised in plan 03-01
    db_password = os.environ.get("SUPABASE_DB_PASSWORD")
    if db_password:
        logger.warning(
            "verify_migration_004_stub_invoked",
            note="Wave 0 stub — implementation lands in plan 03-01",
        )
    print("STUB: migration 004 verification not yet implemented — implement in plan 03-01")
    return 1


# Once plan 03-01 lands, replace the stub return with:
# 1. Query information_schema.columns for the 4 new columns:
#    cur.execute("SELECT column_name, data_type FROM information_schema.columns "
#                "WHERE table_name=%s AND column_name = ANY(%s)",
#                ("picks", ["claude_validation", "claude_reasoning",
#                          "claude_summary", "claude_validated_at"]))
#    Expect 4 rows.
# 2. Query pg_get_constraintdef for picks_status_check:
#    cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
#                "WHERE conname = %s", ("picks_status_check",))
#    Expect output containing "'filtered'" and "'rejected'".
# 3. Query pg_indexes for idx_picks_sport_market_created:
#    cur.execute("SELECT indexname FROM pg_indexes "
#                "WHERE tablename=%s AND indexname=%s",
#                ("picks", "idx_picks_sport_market_created"))
#    Expect 1 row.
# 4. Query pg_constraint for the picks_unique_prediction UNIQUE constraint
#    (idempotency guard for evaluate() — Warning #2 fix in plan 03-01):
#    cur.execute("SELECT conname FROM pg_constraint WHERE conname = %s",
#                ("picks_unique_prediction",))
#    Expect 1 row.


if __name__ == "__main__":
    sys.exit(main())
