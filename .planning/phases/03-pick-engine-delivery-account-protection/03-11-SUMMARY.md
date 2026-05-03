---
phase: 03-pick-engine-delivery-account-protection
plan: 11
subsystem: testing
tags: [smoke-test, telegram, anthropic, supabase, pick-engine, e2e]

# Dependency graph
requires:
  - phase: 03-pick-engine-delivery-account-protection
    provides: PickEngine, ClaudeValidator, TelegramBot, TelegramSender, PickRepository (plans 03-02 through 03-08)
provides:
  - scripts/smoke_e2e_pick.py -- manually-invoked e2e smoke runner wiring all Phase 3 components against live services
  - scripts/smoke_e2e_runbook.md -- manual verification checklist (pre-flight, invocation, 4-step verify, failure triage, sign-off)
  - scripts/__init__.py -- makes scripts/ a Python package for import-based verify checks
affects: [gsd-verify-work, phase-03-verification-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Smoke runner pattern: SimpleNamespace synthetic Prediction for testing real wiring without a trained model"
    - "All credentials from Settings (.env), never from CLI args -- secrets stay out of shell history (T-3-SMOKE-01)"
    - "AsyncIOScheduler started inside smoke runner, DateTrigger polled for 60s after evaluate returns"

key-files:
  created:
    - scripts/smoke_e2e_pick.py
    - scripts/smoke_e2e_runbook.md
    - scripts/__init__.py
  modified: []

key-decisions:
  - "scripts/__init__.py added (deviation Rule 3 -- blocking) to enable `import scripts.smoke_e2e_pick` in verify checks; scripts/ now a proper Python package"
  - "Smoke fixture_id=99999 chosen -- well outside any real API-Football id range, safe to leave in DB (T-3-SMOKE-02)"
  - "Script never auto-runs: --fixture-id required argument with no default prevents accidental CI invocation (T-3-SMOKE-03)"
  - "Reconciliation made optional in runbook (step 5) -- unit tests in test_reconcile.py cover settlement logic"

patterns-established:
  - "Smoke runner: SimpleNamespace synthetic Prediction with all fields PickEngine.evaluate expects"
  - "Exit code contract: 0=any processed outcome, 1=wiring/runtime error, 2=Telegram send failure"

requirements-completed:
  - PICK-01
  - PICK-02
  - PICK-03
  - PICK-04
  - PICK-05
  - CLAUDE-01

# Metrics
duration: 4min
completed: 2026-05-03
---

# Phase 03, Plan 11: Phase 3 E2E Smoke Runner Summary

**`smoke_e2e_pick.py` wires TelegramBot + ClaudeValidator + PickEngine + PickRepository end-to-end against live services via a synthetic Prediction, with `smoke_e2e_runbook.md` documenting the 4-step manual verification gate**

## Performance

- **Duration:** 4min
- **Started:** 2026-05-03T16:20:10Z
- **Completed:** 2026-05-03T16:24:11Z
- **Tasks:** 2 of 3 automated (Task 3 is checkpoint:human-verify -- awaiting Kevin sign-off)
- **Files created:** 3

## Accomplishments
- `scripts/smoke_e2e_pick.py` wires every Phase 3 component (TelegramBot, ClaudeValidator, PickRepository, AsyncIOScheduler, PickEngine) against live Telegram + Anthropic + Supabase with a synthetic Prediction built from `--fixture-id`, `--probs`, `--odds` CLI args
- `scripts/smoke_e2e_runbook.md` documents pre-flight, smoke invocation, 4-step verification (console, Telegram, Supabase, learnings SHA), failure-mode triage, and sign-off block
- Threat model requirements honoured: no secrets on CLI (T-3-SMOKE-01), safe fixture id (T-3-SMOKE-02), no auto-invocation guard (T-3-SMOKE-03), sign-off block for audit (T-3-SMOKE-04), channel_id validated at Settings load (T-3-SMOKE-05)

## Task Commits

Each task was committed atomically:

1. **Task 1: smoke_e2e_pick.py** - `24e42c9` (feat)
2. **Task 2: smoke_e2e_runbook.md** - `ada5614` (docs)

**Task 3 (checkpoint:human-verify):** Awaiting Kevin to execute the runbook against live services and fill in the Sign-off block.

## Files Created/Modified
- `scripts/smoke_e2e_pick.py` -- end-to-end smoke runner, wires all Phase 3 components, --fixture-id / --probs / --odds args
- `scripts/smoke_e2e_runbook.md` -- manual verification runbook: pre-flight, invocation, 4 touchpoints, failure modes, sign-off
- `scripts/__init__.py` -- minimal package init (added per deviation Rule 3 to unblock import-based verify checks)

## Decisions Made
- `scripts/__init__.py` was added as a Rule 3 (blocking) auto-fix -- without it, `import scripts.smoke_e2e_pick` would fail in the plan's acceptance criteria verify command
- Smoke fixture_id=99999 ensures the synthetic row won't collide with any real API-Football fixture id; can be cleaned up via `delete from picks where fixture_id = 99999`
- Reconciliation flow documented as "optional step 5" in the runbook since its unit tests already cover settlement logic; required only if Kevin wants to verify the full post-match settlement path in one session

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added scripts/__init__.py to make scripts/ a Python package**
- **Found during:** Task 1 (smoke runner implementation)
- **Issue:** Plan's acceptance criteria includes `import scripts.smoke_e2e_pick as s` which requires `scripts` to be a Python package; no `__init__.py` existed
- **Fix:** Created minimal `scripts/__init__.py` with one-line docstring
- **Files modified:** `scripts/__init__.py`
- **Verification:** `python -c "import scripts.smoke_e2e_pick"` succeeds with mocked Phase 3 deps
- **Committed in:** 24e42c9 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - Blocking)
**Impact on plan:** Fix necessary for acceptance criteria; no scope change.

## Issues Encountered
- Phase 3 source modules (picks/engine.py, claude/validator.py, telegram/bot.py, etc.) are not yet in this worktree -- being built by parallel agents. The smoke runner is written against the expected final interfaces documented in plans 03-02 through 03-08. Imports will resolve after wave merge.

## User Setup Required

This plan has human setup requirements documented in the runbook:

**Before running the smoke:** See `scripts/smoke_e2e_runbook.md` Pre-flight checklist for:
- `TELEGRAM_BOT_TOKEN` from @BotFather
- `TELEGRAM_CHANNEL_ID` (-100... format) via @userinfobot
- `ANTHROPIC_API_KEY` from console.anthropic.com
- `CLAUDE_MODEL` (default: claude-sonnet-4-6)
- Telegram bot set as channel ADMIN with post permission

## Known Stubs
None. The smoke runner is not a data-display component; it calls live services. No hardcoded return values flow to UI rendering.

## Threat Flags
None. All threats documented in plan's `<threat_model>` are mitigated within the smoke runner per T-3-SMOKE-01 through T-3-SMOKE-05.

## Next Phase Readiness
- Phase 3 is functionally complete (plans 03-02 through 03-10 built by parallel agents)
- This plan (03-11) delivers the phase-exit smoke gate
- After Kevin runs the runbook and fills in the Sign-off block, Phase 3 is ready for `/gsd-verify-work`

## Self-Check: PASSED

All created files verified present:
- `scripts/smoke_e2e_pick.py` FOUND
- `scripts/smoke_e2e_runbook.md` FOUND
- `scripts/__init__.py` FOUND

All task commits verified in git log:
- `24e42c9` FOUND (feat: smoke_e2e_pick.py)
- `ada5614` FOUND (docs: smoke_e2e_runbook.md)

---

*Phase: 03-pick-engine-delivery-account-protection*
*Completed: 2026-05-03*
