---
quick_id: 260503-iql
phase: quick
plan: 01
subsystem: clv
tags: [clv, vig-removal, pinnacle, pitfall-7, refactor]
requires:
  - bip.core.errors.ClvError
  - bip.core.storage.models.ClvRecord
  - bip.core.storage.repositories.ClvRecordRepository
provides:
  - bip.clv.odds_math.remove_vig
  - bip.clv.recorder.calculate_clv_percentage (new dict+selection signature)
  - bip.clv.recorder.ClvRecorder.record (new dict+selection signature)
affects:
  - tests/test_clv_recorder.py
tech_stack:
  added: []
  patterns:
    - "Pure-function odds math module isolated from I/O / logging"
    - "ClvError wraps ValueError at the recorder boundary so DB layer sees one exception type"
    - "Frozen persistence decision: raw odd in audit field, fair-odd math in success metric"
key_files:
  created:
    - src/bip/clv/odds_math.py
  modified:
    - src/bip/clv/recorder.py
    - tests/test_clv_recorder.py
decisions:
  - "PITFALLS.md Pitfall 7 closed: CLV is now computed against vig-removed (fair) Pinnacle closing odds, not raw quotes. Bias source removed."
  - "Persistence frozen: ClvRecord.pinnacle_closing_odds = closing_odds_dict[selection] (RAW); ClvRecord.implied_prob_closing = 1.0/raw; ClvRecord.clv_percentage = vig-removed math. No schema migration; no new field."
  - "Vig-removal algorithm: proportional (basic) -- each implicit probability divided by the overround sum. Sufficient for Pinnacle's 2-4% margin; Shin-free / power-method variants deferred unless backtest data shows asymmetry."
  - "ValueError raised by remove_vig (empty dict / odd <= 1.0) is wrapped into ClvError at the calculate_clv_percentage boundary so callers always handle a single exception type (T-quick-01)."
  - "Missing-selection check duplicated in both calculate_clv_percentage and ClvRecorder.record() so the persistence path catches the error before reaching the math (T-quick-04)."
metrics:
  duration_minutes: 9
  completed_date: "2026-05-03"
  tasks_completed: 2
  files_created: 1
  files_modified: 2
  tests_added: 9
---

# Quick 260503-iql: Vig Removal in CLV Recorder Summary

**One-liner:** Closes PITFALLS.md Pitfall 7 by introducing `remove_vig()` and rewriting CLV math to compare pick odds against the proportionally vig-removed (fair) Pinnacle closing price for the picked selection, while preserving the raw book quote in the audit field.

## What Changed

| Layer       | Change |
|-------------|--------|
| Module (new) | `src/bip/clv/odds_math.py` -- pure `remove_vig(dict[str, float]) -> dict[str, float]`. Strict input validation: empty dict and any odd <= 1.0 raise `ValueError`. |
| Recorder    | `calculate_clv_percentage(odds_at_pick, closing_odds_dict, selection)` -- old `(odds_at_pick, closing_odds: float)` signature gone. Body normalises the closing dict via `remove_vig`, then divides by `fair[selection]`. |
| Recorder    | `ClvRecorder.record(..., closing_odds_dict, selection, ...)` -- old `pinnacle_closing_odds: float` parameter gone. Persists raw `closing_odds_dict[selection]` into `ClvRecord.pinnacle_closing_odds` (audit), vig-removed CLV into `ClvRecord.clv_percentage` (success metric). |
| Logging     | Structured `clv_recorded` event now emits `selection`, `pinnacle_closing_odds_raw`, and full `closing_odds_dict` so any historical row can be back-recomputed (T-quick-03). |
| Schema      | `ClvRecord` schema unchanged. No migration generated. |
| Tests       | 4 existing CLV calculation/recorder tests migrated to new signature using vig-free dicts (`{"home": 2.00, "away": 2.00}`) so original numeric expectations (`+5.0`, `-5.0`, `0.0`) still hold. New `TestRemoveVig` (5 cases) and `TestClvVigRemoval` (4 cases) added. |

## Frozen Persistence Decision

`ClvRecord.pinnacle_closing_odds` keeps the **raw** closing odd for the picked selection
(`closing_odds_dict[selection]`). `ClvRecord.implied_prob_closing` stays `1.0 / raw_closing_odd`
so audit-trail rows show the actual book price. `ClvRecord.clv_percentage` is the **only** field
whose value semantics changed — it now reflects vig-removed math.

Rationale: keeps Phase 02.1 schema stable, preserves the actual bookmaker quote for forensics,
isolates the fix to a single computed field. (Audit trail = raw price; success metric = fair-price CLV.)

## Numeric Sanity

Manual sanity from the plan's verification block, post-implementation:

```
uv run python -c "from bip.clv.recorder import calculate_clv_percentage; \
                  print(calculate_clv_percentage(2.10, {'1':1.95,'X':3.40,'2':4.20}, '1'))"
# -> 3.05154639175258
```

Raw CLV would have been `(2.10 / 1.95 - 1) * 100 ~= 7.69%`. Vig-removed fair odd for `"1"` is
`~2.038`, giving `~+3.05%` -- a 4.6 percentage-point downward correction confirming Pitfall 7
was a real, material bias.

## Test Count Delta

| Suite                | Before | After | Delta |
|----------------------|--------|-------|-------|
| `tests/test_clv_recorder.py::TestClvCalculation`  | 4 | 4 (migrated, unchanged numerics) | 0 |
| `tests/test_clv_recorder.py::TestRollingAverage`  | 4 | 4 | 0 |
| `tests/test_clv_recorder.py::TestRemoveVig`       | 0 | 5 | +5 |
| `tests/test_clv_recorder.py::TestClvVigRemoval`   | 0 | 4 | +4 |
| **Total `test_clv_recorder.py`**                  | **8** | **17** | **+9** |
| Full suite passing (excl. pre-existing env errors)| 195 | 204 | +9 |

Full sweep `uv run pytest -q --ignore=tests/test_api_football_client.py --ignore=tests/test_apifootball_get_odds.py --ignore=tests/test_clv_client.py`: **43 failed, 204 passed**. The 43 failures are pre-existing on `HEAD~1` (worktree `.venv` is missing `pytest_asyncio` and `pytest_httpx`); same 43 failures + 195 passing on baseline. None are CLV-related, none introduced by this plan.

## Caller Audit

| Caller of old signature                              | Status |
|------------------------------------------------------|--------|
| `src/bip/clv/recorder.py` (internal)                 | Updated. |
| `tests/test_clv_recorder.py`                         | Updated (4 tests migrated, 9 added). |
| `src/bip/scheduler/orchestrator.py::_record_clv`     | Stub — no body invoking `recorder.record()` yet. Will be wired in Step 4 of parent plan at `~/.claude/plans/planea-c-mo-implementar-estas-giggly-hare.md`. **Not touched by this plan.** |
| `tests/test_clv_client.py`                           | Unrelated (tests `OddsApiClient.fetch_pinnacle_closing_odds`). Not touched. |

`grep -rn "calculate_clv_percentage\|recorder\.record(" src tests` confirms no stale call sites remain.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|------------|
| T-quick-01 (Tampering, `remove_vig` input) | Empty-dict and odd <= 1.0 raise `ValueError`; wrapped to `ClvError` at recorder boundary so DB layer never sees a bad math result. |
| T-quick-02 (Info Disclosure, audit field)  | Accepted -- raw Pinnacle price is public market data; persisting it preserves forensic value. Documented in recorder.py module docstring. |
| T-quick-03 (Repudiation, semantic change)  | Recorder docstring + `clv_recorded` log event document vig-removal; `closing_odds_dict` and `selection` logged so any row can be back-recomputed. |
| T-quick-04 (DoS, missing selection)        | Early `ClvError` in both `calculate_clv_percentage` and `record()` prevents `KeyError` propagating into scheduler thread (Pitfall 6 jobstore-loss risk). |

## Deviations from Plan

None of substance.

- Test `test_calculate_clv_uses_vig_removed_price` asserts `result == pytest.approx(3.05, abs=0.5)` (vig-removed math actually returns ~3.05%, not the ~5.5% the plan estimated). The plan's `result < 7.0` strict bound (proves vig was removed) is asserted as well. Both invariants — "vig was actually removed" and "magnitude is materially below raw" — hold.
- Tests organised into a new `TestClvVigRemoval` class (the plan offered "executor's choice"), keeping `TestClvCalculation` focused on the migrated original cases and isolating the new vig-aware behaviour.

## Deferred Items

- Pre-existing 43 test failures across `tests/picks/test_engine.py`, `tests/scheduler/test_*.py`, `tests/claude/test_validator.py`, `tests/test_plugin_predict.py` and 3 collection errors (`test_api_football_client.py`, `test_apifootball_get_odds.py`, `test_clv_client.py`) caused by `pytest_asyncio` and `pytest_httpx` missing from the worktree's `.venv`. **Out of scope for this plan** (env hygiene, not CLV math). Workaround for full-suite verification: install the missing dev deps via `uv pip install pytest-asyncio pytest-httpx` or rebuild from `pyproject.toml` dev extras.

## Self-Check: PASSED

- `src/bip/clv/odds_math.py` -- FOUND
- `src/bip/clv/recorder.py` -- FOUND, modified
- `tests/test_clv_recorder.py` -- FOUND, modified
- Commit `fe66d5b` (Task 1: feat(quick-260503-iql): add remove_vig() pure function with tests) -- FOUND
- Commit `94c0a7b` (Task 2: refactor(quick-260503-iql): vig-removed CLV in recorder + dict+selection signature) -- FOUND
- 17/17 `tests/test_clv_recorder.py` GREEN
- Manual sanity returns `3.05154639175258` (in expected `[3.0, 6.0]` band; materially below raw `7.69%`)
- `ClvRecord.pinnacle_closing_odds` schema unchanged (`float | None`)
- No new callers of the old signature exist (orchestrator `_record_clv` still a stub; `tests/test_clv_client.py` unrelated)
