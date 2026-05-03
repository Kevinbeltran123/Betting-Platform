---
phase: 03-pick-engine-delivery-account-protection
plan: 0
status: complete
completed: 2026-05-02
duration: ~12min
tasks_total: 3
tasks_done: 3
commits: 3
requirements_addressed:
  - PICK-01
  - PICK-02
  - PICK-03
  - PICK-04
  - PICK-05
  - CLAUDE-01
  - CORNERS-01
---

# Plan 03-00 Summary — Wave 0 RED test stubs + bootstrap

## What was built

Foundational scaffolding so every Phase 3 implementation task lands on a failing test that already encodes the contract.

- **17 stub files** across 5 new test subdirectories (`tests/picks/`, `tests/claude/`, `tests/telegram/`, `tests/scheduler/`, `tests/scripts/`) — every test name from `03-VALIDATION.md` is represented as a `NotImplementedError` raise behind a module-level `pytestmark = pytest.mark.skip`.
- **`tests/__init__.py`** documents the PATTERNS.md §16 layout shift; existing flat `tests/test_*.py` files (12 of them) still discover and pass.
- **`tests/conftest.py`** extended with `mock_anthropic_client` (AsyncMock-backed `messages.create` returning a canned tool_use Message — default verdict CONFIRM), `mock_telegram_bot` (AsyncMock `send_html`), and `_build_canned_message` helper. Existing `settings` fixture got 4 new env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID=-1001234567890`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL=claude-sonnet-4-6`).
- **`.env.example`** adds the Phase 3 block (5 vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID=-100`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `MAX_KELLY_FRACTION=0.25`).
- **`scripts/verify_migration_004.py`** skeleton mirrors `verify_migration_003.py` — `derive_db_url` copied verbatim per PATTERNS.md drift risk #12. Returns exit 1 unconditionally (Wave 0 stub pattern from 02.1 D-15) so accidental CI invocation cannot mark the migration verified. Future SQL queries (4 column probe, `picks_status_check` widening, `idx_picks_sport_market_created`, `picks_unique_prediction` UNIQUE) documented in comments for plan 03-01.

## Key files

### Created
- `tests/picks/__init__.py`, `tests/picks/test_account_longevity.py`, `tests/picks/test_engine.py`
- `tests/claude/__init__.py`, `tests/claude/test_validator.py`, `tests/claude/test_learnings_loader.py`
- `tests/telegram/__init__.py`, `tests/telegram/test_bot.py`, `tests/telegram/test_sender.py`
- `tests/scheduler/__init__.py`, `tests/scheduler/test_reconcile.py`, `tests/scheduler/test_orchestrator.py`
- `tests/scripts/__init__.py`, `tests/scripts/test_corners_gate_artifacts.py`, `tests/scripts/test_corners_gate_coverage.py`, `tests/scripts/test_corners_gate_descope.py`
- `scripts/verify_migration_004.py`

### Modified
- `tests/__init__.py` — layout-shift docstring (was empty)
- `tests/conftest.py` — 4 new env vars in `settings`, `_build_canned_message`, `mock_anthropic_client`, `mock_telegram_bot`
- `.env.example` — Phase 3 block appended; `TELEGRAM_BOT_TOKEN` comment updated from "Phase 1 optional" to "required for delivery"

## Verification results

```text
$ uv run pytest tests/picks/ tests/claude/ tests/telegram/ tests/scheduler/ tests/scripts/ --collect-only -q
46 tests collected in 0.02s     ← all 46 stubs discovered

$ uv run pytest tests/picks/test_account_longevity.py -v
8 skipped in 0.01s              ← module-level skip works

$ uv run python scripts/verify_migration_004.py; echo $?
1                               ← stub correctly fails

$ uv run pytest tests/test_clv_recorder.py tests/test_scheduler.py -x -q
12 passed in 0.39s              ← Warning #3 satisfied — flat tests unaffected

$ grep -E "^(TELEGRAM_BOT_TOKEN|TELEGRAM_CHANNEL_ID|ANTHROPIC_API_KEY|CLAUDE_MODEL|MAX_KELLY_FRACTION)=" .env.example | wc -l
5                               ← all Phase 3 vars present
```

## Commits

1. `1919f47` — `test(03-00): add Wave 0 RED test stubs for Phase 3 (PATTERNS.md §16 layout shift)` (17 files, 347 insertions)
2. `9540ad1` — `test(03-00): extend conftest.py with Phase 3 fixtures and env vars` (1 file, 59 insertions)
3. `1f86fae` — `feat(03-00): bootstrap .env template + verify_migration_004 skeleton` (2 files, 89 insertions, 1 deletion)

## Deviations

### Minor: acceptance criteria typo in plan

Plan acceptance for Task 1 stated:

> `grep -c "raise NotImplementedError" tests/picks/test_account_longevity.py` returns 7

But the plan's own action block defines **8** test methods in `test_account_longevity.py` (TestQuarterKelly: 2, TestDeterministicJitter: 2, TestSendAtVariance: 2, TestMarketCap: 2). Implemented 8 to match the action block (which is the contract source); flagged the acceptance text as a planning typo. Functionally identical — the 8th test (`test_market_cap_dormant_under_5_picks`) is required by D-09 and listed in 03-VALIDATION.md.

### Hook noise

VS Code's `PreToolUse:Edit` hook fired three reminder messages during execution (one for `tests/__init__.py`, one for `conftest.py`, one for `.env.example`). All three files had been Read earlier in the session before the edit; the hook is conservative. All edits applied successfully.

## What this enables

Every Phase 3 plan from 03-01 through 03-10 can now write GREEN code against an existing RED test:

- 03-01 → `verify_migration_004.py` body replaces the stub
- 03-03 → `test_account_longevity.py` (8 tests) drives `account_longevity.py`
- 03-04 → `test_learnings_loader.py` (3 tests) drives `learnings_loader.py`
- 03-05 → `test_validator.py` (5 tests) drives `validator.py`
- 03-06 → `test_bot.py` + `test_sender.py` (8 tests) drive `bot.py` + `sender.py` + `pick.html`
- 03-07 → `test_engine.py` (6 tests) drives `engine.py`
- 03-08 → `test_reconcile.py` + `test_orchestrator.py` (9 tests) drive scheduler extensions
- 03-09 → `test_corners_gate_artifacts.py` (2 tests) drives the manual probe markdown
- 03-10 → `test_corners_gate_coverage.py` + `test_corners_gate_descope.py` (5 tests) drive the Polars coverage + descope orchestration

Anthropic mocks (`mock_anthropic_client`, `_build_canned_message`) and the Telegram mock (`mock_telegram_bot`) are wired centrally so plans 03-05 / 03-06 / 03-07 don't each re-mock.
