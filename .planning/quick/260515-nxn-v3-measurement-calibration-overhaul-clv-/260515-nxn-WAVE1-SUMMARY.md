---
phase: 260515-nxn
plan: 01
wave: 1
subsystem: engine_v3/measurement
tags: [grading, observability, telegram, deliveries, canonical-path]
key-decisions:
  - "SendResult dataclass chosen over bare bool for send_pick_safe — backward-compat via __bool__, exposes message_id cleanly"
  - "delivery buffer in DualWriteRuntime (not ShadowLogger) — delivery is a runtime concern, not a shadow concern"
  - "grade_day4_real.py = the wave's grade_day3_replay.py analog — plan name mismatch documented"
metrics:
  duration: "~30 min"
  completed: "2026-05-15T22:49:00Z"
  tasks: 2
  files_modified: 7
key-files:
  modified:
    - src/bip/evaluation/live/engine_v3/runtime/v3_grader.py
    - src/bip/evaluation/live/telegram_integration.py
    - src/bip/evaluation/live/engine_v3/runtime/dual_write.py
    - scripts/spike/v3/grade_day4_real.py
    - scripts/spike/v3/regrade_day4_from_raw.py
    - tests/evaluation/live/engine_v3/test_v3_grader.py
    - tests/evaluation/live/engine_v3/runtime/test_dual_write_telegram.py
---

# Phase 260515-nxn Wave 1 Summary

## One-liner

Canonical grading path established (no-circularity, authoritative Sportmonks includes, Wave-2-reusable callable API) and deliveries.parquet delivery observability implemented (message_id threaded from bot through send_pick_safe to parquet sink).

## Tasks Executed

| Task | Commit | Description |
|------|--------|-------------|
| 1.1 #3 | fcdef5c | Canonical grading; deprecate circular replay scripts |
| 1.2 #2 | a1c62fd | deliveries.parquet trace with telegram_message_id |

## What Changed

### Task 1.1 — Canonical grading (fcdef5c)

**v3_grader.py:**
- Extended module docstring to declare the canonical grading contract: `grade_picks_for_date` reads `picks.parquet` + fetches from Sportmonks only — never reads `gsv_log.parquet`.
- Documented the authoritative includes set: `["participants", "state", "periods", "scores", "statistics", "events"]`.
- Added `run_grade_for_date(date_iso, *, shadow_root, client, dry_run=False)` callable API that wraps grade + write-to-disk for use by Wave-2 shadow-promotion report. Exported in `__all__`.

**grade_day4_real.py** (the wave-1 analog of `grade_day3_replay.py` from plan — see Deviations):
- Added deprecation docstring banner explaining the gsv_log circularity issue.
- Added `warnings.warn(DeprecationWarning)` at top of `main()` pointing to the canonical path.

**regrade_day4_from_raw.py:**
- Added deprecation docstring banner explaining the raw-snapshot pipeline-coupling issue.
- Added `warnings.warn(DeprecationWarning)` at top of `main()`.

**Tests added (test_v3_grader.py):**
- `test_canonical_grader_no_circularity_goals_btts_corners`: grades goals/btts/corners via mock client; plants a trap `gsv_log.parquet`; verifies canonical includes; asserts the client went to Sportmonks (not the GSV log). Goals over 2.5 with 3 total = won; btts yes with 2-1 = won; corners over 9.5 with 0 corners = lost.
- `test_run_grade_for_date_writes_parquet`: callable API writes picks_outcomes.parquet and returns the path.
- `test_run_grade_for_date_dry_run_no_write`: dry_run=True returns out_path=None and creates no parquet.

### Task 1.2 — deliveries.parquet (a1c62fd)

**telegram_integration.py:**
- Added `SendResult` frozen dataclass: `{ok: bool, message_id: int|None, status: str}`.
- `status` ∈ `{"sent", "skipped", "failed"}`.
- `__bool__` returns `ok` for full backward compatibility.
- `send_pick_safe` now returns `SendResult` instead of bare `bool`.
  - Sent path: `SendResult(ok=True, message_id=<from bot.send_html>, status="sent")`
  - Skipped paths (filter, bandwidth gate): `SendResult(ok=False, message_id=None, status="skipped")`
  - Failed path: `SendResult(ok=False, message_id=None, status="failed")`

**dual_write.py:**
- Added `_delivery_row()` helper: builds delivery dict from a ShadowPick + send metadata, extracting `bookmaker_odd` from GSV market lines (same side_a/side_b logic as shadow_logger).
- Added `_delivery_buf: list[dict]` field to `DualWriteRuntime`.
- Updated `_send_alerts_for`: after every send attempt (including adapter-failures and adapter-skips), appends a delivery row. Handles both `SendResult` (new) and bare `bool` (legacy) from the sender.
- Added `_flush_deliveries()` method: partitions by row `timestamp_utc` → `data/cache/v3_shadow/dt=YYYY-MM-DD/deliveries.parquet`, diagonal_relaxed append.
- Updated `flush()` to call `_flush_deliveries()` alongside `ShadowLogger.flush()`.

**test_dual_write_telegram.py:**
- Fixed 4 pre-existing test failures (Rule 1 Bug): `@pytest.mark.asyncio` → `@pytest.mark.anyio("asyncio")`.
- Added 3 new delivery tests:
  - `test_delivery_row_written_with_message_id_on_sent`: sender returns `SendResult(ok=True, message_id=42)` → 1 row, id=42, status="sent", all schema fields present.
  - `test_delivery_row_skipped_pick_no_live_pick`: sender returns `False` (bare bool legacy) → row with status="skipped", message_id=None.
  - `test_existing_telegram_tests_still_pass_with_send_result`: asserts `bool()` truthiness contract.

## Test Counts

| Baseline | After Wave 1 | Delta |
|----------|-------------|-------|
| 475 passed | 485 passed | +10 |
| 4 failed (pre-existing asyncio mark bug) | 0 failed | -4 (fixed) |
| 1 skipped | 1 skipped | 0 |

**Root cause of baseline failures:** `test_dual_write_telegram.py` used `@pytest.mark.asyncio` (pytest-asyncio mark) instead of `@pytest.mark.anyio("asyncio")` (the project's anyio test pattern). This was a pre-existing bug on base commit 5886142. Fixed as Rule 1 deviation during Task 1.2 since dual_write.py was already in scope.

**Anti-Napoli regression:** 53 passed throughout.

## Deviations from Plan

### Auto-fixed — Rule 1 Bug: @pytest.mark.asyncio in test_dual_write_telegram.py

- **Found during:** Task 1.2
- **Issue:** 4 tests used `@pytest.mark.asyncio` (unknown to pytest-anyio) — all failed on base commit 5886142.
- **Fix:** Changed all 4 to `@pytest.mark.anyio("asyncio")`. Also added module-level `anyio_backend` fixture for completeness.
- **Files modified:** `tests/evaluation/live/engine_v3/runtime/test_dual_write_telegram.py`
- **Commit:** a1c62fd (bundled with Task 1.2 since it touches the same test file)

### Name mismatch: grade_day3_replay.py vs grade_day4_real.py

- **Plan says:** deprecate `grade_day3_replay.py` and `regrade_day4_from_raw.py`
- **Reality:** `grade_day3_replay.py` does not exist in the worktree. The equivalent historical circular script is `grade_day4_real.py` (derives outcomes from gsv_log, same circularity flaw). Deprecated `grade_day4_real.py` instead, with the same rationale. `regrade_day4_from_raw.py` exists and was deprecated as planned.

## Known Stubs

None — deliveries.parquet is wired end-to-end. `run_grade_for_date` is a complete callable, not a stub.

## Threat Flags

None — no new network endpoints, no new auth paths. deliveries.parquet is a local file write.

## Self-Check: PASSED

- fcdef5c exists: `git log --oneline | grep fcdef5c` ✓
- a1c62fd exists: `git log --oneline | grep a1c62fd` ✓
- `src/bip/evaluation/live/engine_v3/runtime/v3_grader.py` modified ✓
- `src/bip/evaluation/live/telegram_integration.py` contains `SendResult` ✓
- `src/bip/evaluation/live/engine_v3/runtime/dual_write.py` contains `_delivery_buf` ✓
- Final test count: 485 passed, 1 skipped, 0 failed ✓
