---
phase: 03-pick-engine-delivery-account-protection
plan: 7
status: complete
completed: 2026-05-03
duration: ~10min (executed by orchestrator)
tasks_total: 2
tasks_done: 2
commits: 2
requirements_addressed:
  - PICK-01
  - PICK-02
  - PICK-03
  - PICK-04
  - PICK-05
  - CLAUDE-01
---

# Plan 03-07 Summary — PickEngine orchestration heart

## What was built

The single async entry point that wires together all Phase 3 plans into the 5-step filter chain.

- **`src/bip/core/picks/engine.py`** — `PickEngine.evaluate(prediction, opening_odds) → Pick | None`:
  - Step 1: `simulate_pick` + `EDGE_THRESHOLD_PCT` from `bip.train.backtest` (D-02)
  - Step 2: `quarter_kelly_units` + `deterministic_jitter` + `round_to_nearest_half_unit` (D-10)
  - Step 3: `exceeds_60pct_cap` (D-09 — dormant in 1X2-only)
  - Step 4: `ClaudeValidator.validate` — None → filtered, REJECT → rejected (D-07, D-14)
  - Step 5: CONFIRM/FLAG → pending + `DateTrigger` send job at `deterministic_send_at` (D-11)
- Three persistence helpers (`_persist_filtered`, `_persist_rejected`, `_persist_pending`) — every branch hits `pick_repo.insert` (D-04)
- Send job uses deterministic id `send_pick_<fixture>_<market>`, `replace_existing=True` (specifics §195), `misfire_grace_time=300` (Pitfall 6)
- **`src/bip/core/picks/__init__.py`** — re-exports `PickEngine`

## Tests

13 GREEN total (5 PickRepository extension + 8 PickEngine):
- TestEvaluateAllPaths: no_edge / market_cap / claude_unavailable / REJECT / CONFIRM / FLAG / all_paths_persist / idempotent

## Commits

- `80f9905`: feat(03-07): PickEngine.evaluate orchestration heart
- `100acb2`: test(03-07): GREEN engine tests covering all 5 outcome paths + idempotency

## Notes

Wires all upstream Phase 3 work together: account_longevity (03-03), claude.validator (03-05), telegram.sender (03-06), Pick model + repo extensions (03-02, 03-03). 03-08 will integrate this engine into PipelineOrchestrator (T-2h, T-30min triggers + reconcile).
