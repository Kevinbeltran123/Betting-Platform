# Wave 0 Summary — 260515-nxn

**Phase:** 260515-nxn  **Wave:** 0  **Tasks:** 3/3 complete

---

## Commits

| Task | Hash | Subject |
|------|------|---------|
| 0.1 | `9a92dcd` | `feat(engine_v3/archetypes): suppress numerical_sustained (net-negative both days)` |
| 0.2 | `4405e1d` | `docs(engine_v3): dead-signal audit — A6/A9 non-firing, dead formation/elo branches` |
| 0.3 | `46992b3` | `fix(engine_v3): reconcile V3_TELEGRAM_ENABLED parser (watch.py vs dual_write)` |

---

## What Changed

### Task 0.1 — Suppress numerical_sustained (#5)

**Files:** `src/bip/evaluation/live/engine_v3/archetypes.py`, `tests/evaluation/live/engine_v3/test_archetypes.py`, `tests/evaluation/live/engine_v3/test_pipeline.py`

Removed `detect_numerical_sustained` from the `_ARCHETYPE_DETECTORS` tuple (archetypes.py line 829). The function definition and `__all__` export are retained for import stability. A one-line comment cites the net-negative evidence:

```
# D3: -5.79u wr=0.50 n=42; D4: -1.00u; MES anti-predictive on corners
```

Tests added:
- `test_a11_suppressed_from_generate_theses` (test_archetypes.py): asserts the raw detector still fires on a qualifying GSV (function intact) but `generate_theses` never yields `NUMERICAL_SUSTAINED`.
- `test_pipeline_on_numerical_advantage` (test_pipeline.py): updated from asserting `"numerical_sustained" in arch_ids` to `"numerical_sustained" not in arch_ids`.

### Task 0.2 — Dead-signal audit (#9)

**Files:** `docs/v3_dead_signal_audit.md` (new, 110 lines)

Written audit covering all 13 detectors. Key findings:

| Signal | Path | Status |
|--------|------|--------|
| `ref_card_rate_prior` | `cards.ref_card_rate_prior` | **DEAD** — defaults 0.0, predicate >= 5.0 never met, A6 never fires |
| `key_player_off` | `roster.key_player_off` | **DEAD** — defaults (False,False), no GSVBuilder path sets it, A9 never fires |
| `role_signal` | `roster.recent_subs_5min[].role_signal` | **DEAD** — defaults "unknown", A4 defensive-sub filter never satisfied |
| `formation_home/away` | `roster.formation_home/away` | **DEAD branch** — always "unknown" (0/31 Day-4 fixtures), only affects confidence_prior delta in A8/A10, not firing |
| `elo_diff` | `PreMatchPriors.elo_diff` | **DEAD tier** — defaults 0.0, threshold 25.0 never reached, ELO dominant-team resolver always falls through to market/lambda |

No code change — read-only deliverable.

### Task 0.3 — Reconcile V3_TELEGRAM_ENABLED parser (#2b)

**Files:** `scripts/spike/sportmonks/watch.py`, `tests/evaluation/live/engine_v3/test_dual_write.py`

watch.py previously parsed `V3_TELEGRAM_ENABLED` with a bespoke inline set `{"1","true","yes","on"}` (fail-closed). `DualWriteRuntime` used `is_v3_shadow_enabled` accepting `{"1","true","yes","on","y","t"}` with fail-open fallback. Two different parsers, different token sets.

Fix: watch.py now imports and calls `is_v3_shadow_enabled("V3_TELEGRAM_ENABLED")` — one parser. AND-gate semantics documented in an inline comment: Telegram promotion requires BOTH (1) `telegram_sender` wired AND (2) `V3_TELEGRAM_ENABLED` truthy.

Tests added:
- `test_v3_telegram_enabled_parser_unified`: parametrized over 7 values `{unset, "true", "y", "on", "false", "0", "garbage"}` asserting the unified parser decision matches expectations.

---

## Test Counts

| Baseline | After Wave 0 | Delta |
|----------|-------------|-------|
| 475 pass, 4 fail (pre-existing) | 483 pass, 4 fail (same pre-existing) | +8 tests |

Pre-existing failures (all in `test_dual_write_telegram.py`): 4 async tests that require `pytest-asyncio` which is not installed in the worktree. These are not caused by Wave 0 changes and are not regressions.

---

## Deviations

**Task 0.1 — test_pipeline.py also required updating (Rule 1 auto-fix)**

`tests/evaluation/live/engine_v3/test_pipeline.py::test_pipeline_on_numerical_advantage` asserted that `"numerical_sustained" in arch_ids` — it was testing the old behavior. After the suppression it failed immediately. Updated to assert the correct post-suppression behavior (`not in arch_ids`) and updated the docstring. This is an expected consequence of the code change and classified as a Rule 1 auto-fix (broken test behavior caused by the current task's change).

**No other deviations.** Wave 0 executed exactly as planned.

---

## Known Blockers for Wave 1+

None from Wave 0. The 4 pre-existing async test failures (`test_dual_write_telegram.py`) should be investigated before Wave 1 merges — they indicate `pytest-asyncio` is missing from the worktree environment, which may silently skip coverage for the Telegram delivery path added in Wave 1 task 1.2.
