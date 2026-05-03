---
phase: 03-pick-engine-delivery-account-protection
plan: 02
subsystem: core
tags: [pydantic, pydantic-settings, enums, domain-errors, settings, pick-model]

# Dependency graph
requires:
  - phase: 03-pick-engine-delivery-account-protection
    plan: 01
    provides: migration 004 applied (claude_* columns + extended PickStatus CHECK on picks table)

provides:
  - PickStatus enum with 7 members (filtered + rejected added, D-03)
  - Pick model with 4 optional claude_* fields + ISO datetime serialization in to_supabase_dict (D-08)
  - PickError, ClaudeError, TelegramError in core/errors.py (PATTERNS.md discretion #3)
  - Settings extended with telegram_channel_id, anthropic_api_key, claude_model, max_kelly_fraction (D-13)
  - telegram_channel_id @field_validator rejecting non-'-100*' values (Pitfall 8)

affects:
  - 03-03 (pick engine — imports PickStatus.filtered/rejected, Pick.claude_* fields)
  - 03-04 (Claude validator — imports ClaudeError, Settings.anthropic_api_key, Settings.claude_model)
  - 03-05 (Telegram delivery — imports TelegramError, Settings.telegram_channel_id)
  - 03-06 through 03-08 (all downstream plans importing from core/)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PATTERNS.md drift risk #3: flat field append to Settings, no per-feature settings classes"
    - "D-08: claude_validated_at serialized via .isoformat() in to_supabase_dict, not model_dump"
    - "Pitfall 8: telegram_channel_id validated as str (not int) with @field_validator; empty string allowed for CI"
    - "extra='ignore' on Settings prevents SUPABASE_DB_PASSWORD env var from raising ValidationError"

key-files:
  created:
    - tests/test_core_types_phase3.py
    - tests/test_settings_phase3.py
  modified:
    - src/bip/core/types.py
    - src/bip/core/storage/models.py
    - src/bip/core/errors.py
    - src/bip/core/settings.py

key-decisions:
  - "claude_validation is str | None, NOT a new enum — migration 004 CHECK constraint enforces values; no Python enum coupling"
  - "empty string default on telegram_channel_id allows CI and test environments to construct Settings before secrets are wired"
  - "extra='ignore' on Settings required because verify scripts set SUPABASE_DB_PASSWORD in env"
  - "PickError/ClaudeError/TelegramError appended at END of errors.py, never inserted mid-file (PATTERNS.md append-only convention)"

patterns-established:
  - "claude_* fields: all default None, ISO serialization explicitly handled in to_supabase_dict"
  - "Settings: phase additions are flat field appends only, no per-feature classes"
  - "errors.py: domain exception classes appended in declaration order, never alphabetically shuffled"

requirements-completed: [PICK-01, PICK-05, CLAUDE-01]

# Metrics
duration: 3min
completed: 2026-05-03
---

# Phase 3 Plan 02: Core Type Layer Summary

**PickStatus extended to 7 members (filtered/rejected), Pick model gains 4 claude_* fields with ISO serialization, Settings extended with 4 Phase 3 env vars + Pitfall 8 channel_id validator, 3 domain errors added to core/errors.py**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-03T16:18:24Z
- **Completed:** 2026-05-03T16:21:57Z
- **Tasks:** 2 (each with TDD RED/GREEN commits)
- **Files modified:** 4 source + 2 test files

## Accomplishments
- PickStatus enum gains `filtered` and `rejected` (D-03); downstream plans 03-03 through 03-08 can now import these statuses
- Pick storage model extended with `claude_validation`, `claude_reasoning`, `claude_summary`, `claude_validated_at` — all `None`-defaulted for Phase 1+2 backcompat; `to_supabase_dict` emits ISO string for datetime (D-08)
- Three domain errors (`PickError`, `ClaudeError`, `TelegramError`) exported from `core/errors.py` — all downstream consumer plans import from single canonical location
- Settings gains `telegram_channel_id`, `anthropic_api_key`, `claude_model` (default: `claude-sonnet-4-6`), `max_kelly_fraction` (default: 0.25); `@field_validator` rejects any channel_id not starting with `-100` (Pitfall 8 protection)

## Task Commits

Each task was committed atomically with TDD RED/GREEN gates:

1. **Task 1 RED: Failing tests for PickStatus + Pick claude_* + domain errors** - `0210b47` (test)
2. **Task 1 GREEN: Implement PickStatus + Pick + errors** - `176fc8c` (feat)
3. **Task 2 RED: Failing tests for Settings extensions** - `7434f50` (test)
4. **Task 2 GREEN: Implement Settings extensions + validator** - `d31e401` (feat)

**Plan metadata:** (committed below)

_TDD tasks have separate test and feat commits per gate._

## Files Created/Modified
- `src/bip/core/types.py` - PickStatus.filtered + PickStatus.rejected appended (D-03)
- `src/bip/core/storage/models.py` - Pick class extended with 4 claude_* fields; to_supabase_dict updated (D-08)
- `src/bip/core/errors.py` - PickError, ClaudeError, TelegramError appended (PATTERNS.md #3)
- `src/bip/core/settings.py` - Full rewrite: 4 new fields + field_validator + extra='ignore' (D-13)
- `tests/test_core_types_phase3.py` - 12 tests covering Task 1 behavior
- `tests/test_settings_phase3.py` - 12 tests covering Task 2 behavior

## Decisions Made
- `claude_validation` is `str | None` not a Python enum — migration 004 CHECK constraint enforces `CONFIRM | FLAG | REJECT | SKIPPED | NULL`; coupling to a Python enum would require synchronizing two sources of truth
- Empty string default for `telegram_channel_id` deliberately allows CI and test environments to construct `Settings` without secrets; the Telegram bot construction in plan 03-06 is the appropriate fail-fast point
- `extra="ignore"` added to `SettingsConfigDict` — Phase 02.1 verify scripts export `SUPABASE_DB_PASSWORD` to env; without this, any test importing Settings would raise `ValidationError` on unknown field
- No `TelegramSettings` or `ClaudeSettings` sub-classes created — PATTERNS.md drift risk #3 mandates flat field append to the single `Settings` class

## Deviations from Plan

None - plan executed exactly as written. All 4 modified files match the plan's specified final content.

## Issues Encountered
- `tests/test_clv_client.py` failed to collect due to missing `pytest_httpx` module — this is a pre-existing issue unrelated to plan 03-02 changes; `test_clv_recorder.py` passes cleanly. Logged to deferred items.

## User Setup Required
None - no external service configuration required in this plan. Secrets (`ANTHROPIC_API_KEY`, `TELEGRAM_CHANNEL_ID`) are loaded by Settings; wiring happens in the calling environment.

## Next Phase Readiness
- All downstream Phase 3 plans (03-03 through 03-08) can now import from the extended core layer
- `PickStatus.filtered` and `PickStatus.rejected` ready for pick engine (03-03)
- `ClaudeError` and Settings Claude fields ready for Role C validator (03-04)
- `TelegramError` and Settings Telegram fields ready for delivery (03-05/03-06)
- 39 tests pass; no regressions in existing test suite

## TDD Gate Compliance

- RED gate: `test(03-02)` commits `0210b47` (Task 1) and `7434f50` (Task 2) — tests failed as expected before implementation
- GREEN gate: `feat(03-02)` commits `176fc8c` (Task 1) and `d31e401` (Task 2) — all tests pass after implementation
- REFACTOR gate: Not needed — implementation was clean on first pass

---
*Phase: 03-pick-engine-delivery-account-protection*
*Completed: 2026-05-03*

## Self-Check: PASSED

Files verified:
- `src/bip/core/types.py` — FOUND, contains `filtered = "filtered"` and `rejected = "rejected"`
- `src/bip/core/storage/models.py` — FOUND, contains `claude_validation: str | None = None`
- `src/bip/core/errors.py` — FOUND, contains `PickError`, `ClaudeError`, `TelegramError`
- `src/bip/core/settings.py` — FOUND, contains `telegram_channel_id`, `field_validator`, `extra="ignore"`
- `tests/test_core_types_phase3.py` — FOUND, 12 tests
- `tests/test_settings_phase3.py` — FOUND, 12 tests

Commits verified:
- `0210b47` — FOUND (test RED Task 1)
- `176fc8c` — FOUND (feat GREEN Task 1)
- `7434f50` — FOUND (test RED Task 2)
- `d31e401` — FOUND (feat GREEN Task 2)
