---
quick_id: 260503-txj
description: Reschedule cadence + max_retries a Settings (G-MAINT-10)
status: complete
date: 2026-05-03
gap_closed: G-MAINT-10
commit: 6cc30ca
tests:
  baseline: 292
  final: 295
  delta: +3
---

# Quick Task 260503-txj — Reconcile Knobs to Settings (G-MAINT-10)

## Outcome

Closed audit gap **G-MAINT-10**: `_RECONCILE_MAX_RETRIES = 4` (class
constant) and the hardcoded `+30 min` reschedule backoff are now configurable
via `Settings.reconcile_max_retries` and `Settings.reconcile_retry_minutes`.
Ops can tune the reconciliation cadence per deployment without code changes.

## Decision: backwards-compat preserved

Defaults remain `4 retries × 30 minutes` to preserve all existing test
expectations and historical orchestrator behavior. The orchestrator falls
back to class-level `_RECONCILE_MAX_RETRIES_DEFAULT` and
`_RECONCILE_RETRY_MINUTES_DEFAULT` when `self.settings is None` (test
fixtures that construct PipelineOrchestrator without a Settings object).

## Changes

### `src/bip/core/settings.py`
Added two int fields with defaults under "Orchestrator reconciliation tuning":
```python
reconcile_max_retries: int = 4
reconcile_retry_minutes: int = 30
```

Loadable via env vars `RECONCILE_MAX_RETRIES` and `RECONCILE_RETRY_MINUTES`.

### `src/bip/core/scheduler/orchestrator.py`
- Renamed `_RECONCILE_MAX_RETRIES = 4` → `_RECONCILE_MAX_RETRIES_DEFAULT = 4`.
- Added `_RECONCILE_RETRY_MINUTES_DEFAULT = 30`.
- In `_reconcile_results`, the IN_PLAY/NOT_STARTED branch now reads
  `self.settings.reconcile_max_retries` and `self.settings.reconcile_retry_minutes`
  with a fallback to the class defaults.
- Added `max_retries` to the `reconcile_abandoned` log event (so ops can
  trace which limit was hit when tuning).
- Updated the abandoned-message note from "max 4 reschedule attempts" to
  "max reschedule attempts" (no longer hardcodes the literal 4).

### `tests/test_settings_phase3.py`
Added `TestReconcileTuning` class with 3 tests:
- `test_reconcile_defaults_match_historical_behavior` — defaults are 4 / 30.
- `test_reconcile_max_retries_overridable_via_env` — `RECONCILE_MAX_RETRIES=8` works.
- `test_reconcile_retry_minutes_overridable_via_env` — `RECONCILE_RETRY_MINUTES=15` works.

## Verification

- `uv run pytest tests/test_settings_phase3.py -v` → 15 passed (12 baseline + 3 new).
- `uv run pytest -q` → 295 passed, 0 failed (baseline 292 → +3).
- All existing scheduler/reconcile tests still pass without modification because
  the defaults preserve historical behavior.

## Why this matters (audit context)

Per AUDIT-GAPS.md G-MAINT-10: "Hardcoded reschedule cadence (`+30 min`
retry in orchestrator.py:307) and max retries (`_RECONCILE_MAX_RETRIES = 4`)
are class constants; not configurable per league or via Settings." This was
P3 / Moderate severity. With the move to Settings, ops can now extend the
reconciliation window for high-overtime sports (later phases) or shorten
it for fast-settling fixtures without touching code.

## What this does NOT do

- Per-league overrides (still global). Per-league tuning would require a
  new `LeagueConfig.reconcile_*` field — not in scope for this gap.
- Adaptive backoff (still flat 30-min). Exponential / jittered retry would
  be a future improvement if reconciliation patterns demand it.
