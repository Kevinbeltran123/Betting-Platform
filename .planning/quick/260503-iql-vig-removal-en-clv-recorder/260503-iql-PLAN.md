---
quick_id: 260503-iql
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/bip/clv/odds_math.py
  - src/bip/clv/recorder.py
  - tests/test_clv_recorder.py
autonomous: true
requirements:
  - PITFALL-7-VIG-REMOVAL
user_setup: []

must_haves:
  truths:
    - "remove_vig() returns fair odds whose implicit probabilities sum to 1.0 (no bookmaker margin)"
    - "calculate_clv_percentage() compares odds_at_pick against the vig-removed (fair) closing price for the picked selection"
    - "ClvRecord.pinnacle_closing_odds persists the RAW Pinnacle closing odd for the selection (audit trail preserved)"
    - "ClvRecord.clv_percentage reflects the vig-removed math (lower magnitude than raw, unbiased upward)"
    - "remove_vig() raises ValueError on empty dict or any odd <= 1.0 (defensive against decoded h2h payloads)"
    - "All existing CLV tests still pass after recorder.record() signature change (dict + selection)"
  artifacts:
    - path: "src/bip/clv/odds_math.py"
      provides: "remove_vig() pure function for proportional vig removal"
      exports: ["remove_vig"]
    - path: "src/bip/clv/recorder.py"
      provides: "calculate_clv_percentage(odds_at_pick, closing_odds_dict, selection) + ClvRecorder.record() with dict+selection signature"
      contains: "remove_vig"
    - path: "tests/test_clv_recorder.py"
      provides: "Vig-removal correctness tests + updated record() call sites"
      contains: "test_remove_vig_proportional"
  key_links:
    - from: "src/bip/clv/recorder.py"
      to: "src/bip/clv/odds_math.py"
      via: "from bip.clv.odds_math import remove_vig"
      pattern: "from bip.clv.odds_math import remove_vig"
    - from: "src/bip/clv/recorder.py::calculate_clv_percentage"
      to: "src/bip/clv/odds_math.py::remove_vig"
      via: "fair = remove_vig(closing_odds_dict); compare odds_at_pick vs fair[selection]"
      pattern: "remove_vig\\(.*\\)\\[.*selection"
    - from: "src/bip/clv/recorder.py::ClvRecorder.record"
      to: "src/bip/core/storage/models.py::ClvRecord.pinnacle_closing_odds"
      via: "persist closing_odds_dict[selection] (raw, not fair) — schema unchanged"
      pattern: "pinnacle_closing_odds=closing_odds_dict\\[selection\\]"
---

<objective>
Fix CLV bias by removing the bookmaker vig (~2-4% margin) from Pinnacle closing odds before computing CLV percentage.
PITFALLS.md Pitfall 7 documents this as Error #1 of CLV: comparing raw odds inflates CLV systematically and biases the project's primary success metric (CLV > +3%) downward.

Purpose: Honest CLV measurement is the project's north star — every Phase-3 pick filter, alert threshold, and rolling-average decision depends on it being right.
Output: New `src/bip/clv/odds_math.py` with `remove_vig()`; updated `recorder.py` with dict+selection signature; updated `test_clv_recorder.py` with vig-removal cases and migrated existing call sites.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/research/PITFALLS.md
@src/bip/clv/recorder.py
@src/bip/clv/client.py
@src/bip/core/storage/models.py
@tests/test_clv_recorder.py

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->
<!-- Use these directly — no codebase exploration needed. -->

From src/bip/core/storage/models.py (ClvRecord — schema is unchanged by this plan):
```python
class ClvRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pick_id: int
    fixture_id: int
    sport: str = "football"
    market: str
    odds_at_pick: float
    pinnacle_closing_odds: float | None = None   # <-- stays float; persist RAW odd for selection
    implied_prob_at_pick: float
    implied_prob_closing: float | None = None    # <-- stays float; 1/raw_closing_odd (audit consistency)
    clv_percentage: float | None = None          # <-- now reflects VIG-REMOVED math
    odds_fetched_at: datetime | None = None
```

From src/bip/core/errors (existing):
```python
class ClvError(Exception): ...
```

From src/bip/clv/client.py (shape of Pinnacle h2h payload — informs dict keys):
```python
# OddsApiClient.fetch_pinnacle_closing_odds returns the Pinnacle bookmaker dict.
# Markets contain outcomes like:
#   {"name": "Home", "price": 1.95}, {"name": "Away", "price": 4.20}, {"name": "Draw", "price": 3.40}
# Caller is responsible for projecting that into a {selection_key: odd} dict before calling record().
# This plan does NOT change client.py — the dict shape is the recorder's input contract.
# Selection keys are caller-defined (e.g., "1" / "X" / "2", or "home" / "draw" / "away", or "over" / "under").
# remove_vig() is key-agnostic — it operates on dict values only.
```

Existing call sites of `calculate_clv_percentage` and `recorder.record()`:
  - Production: ONLY `src/bip/clv/recorder.py` itself (internal call inside `record()`).
  - Tests: ONLY `tests/test_clv_recorder.py` (one call site at line 37-46).
  - Orchestrator's `_record_clv` is a STUB (will be wired in Step 4 of parent plan, not now).
  - `tests/test_clv_client.py` references `fetch_pinnacle_closing_odds` (the client method) — UNRELATED, do not touch.
</interfaces>

# Persistence decision (frozen — do NOT revisit during execution)

`ClvRecord.pinnacle_closing_odds` keeps the **raw** closing odd for the picked selection
(`closing_odds_dict[selection]`). `ClvRecord.implied_prob_closing` stays `1.0 / raw_closing_odd`
so audit-trail rows show the actual book price. `ClvRecord.clv_percentage` is the ONLY field
whose value changes — it now reflects vig-removed math. No new ClvRecord field, no schema migration.
Rationale: keeps Phase 02.1 schema stable, preserves the actual bookmaker quote for forensics,
isolates the fix to a single computed field. (Audit trail = raw price; success metric = fair-price CLV.)
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add remove_vig() pure function with tests</name>
  <files>src/bip/clv/odds_math.py, tests/test_clv_recorder.py</files>
  <behavior>
    - test_remove_vig_proportional: input {"1": 1.95, "X": 3.40, "2": 4.20} -> sum(1/fair_odds[k] for k in ...) == pytest.approx(1.0, abs=1e-6); fair_odds["1"] > 1.95 (vig pushes raw price below fair); same for "X", "2".
    - test_remove_vig_two_way: input {"over": 1.91, "under": 1.91} -> fair_odds["over"] == pytest.approx(2.0, abs=1e-6); fair_odds["under"] == pytest.approx(2.0, abs=1e-6).
    - test_remove_vig_rejects_empty_dict: remove_vig({}) raises ValueError with message mentioning "empty".
    - test_remove_vig_rejects_invalid_odds: remove_vig({"1": 1.0, "X": 3.0, "2": 4.0}) raises ValueError; remove_vig({"1": 0.5, "X": 3.0}) raises ValueError; both messages mention the offending key or value.
    - test_remove_vig_preserves_keys: set(remove_vig({"a": 2.0, "b": 2.1, "c": 2.2}).keys()) == {"a", "b", "c"}.
  </behavior>
  <action>
    1. Create `src/bip/clv/odds_math.py` with:
       - Module docstring explaining proportional vig removal and its role in CLV (cite PITFALLS.md Pitfall 7 in 1-2 lines).
       - `def remove_vig(odds: dict[str, float]) -> dict[str, float]:` — pure, no I/O, no logging.
       - Strict implementation:
         ```
         if not odds: raise ValueError("remove_vig: empty odds dict")
         for k, v in odds.items():
             if v <= 1.0: raise ValueError(f"remove_vig: invalid odd for {k!r}: {v} (must be > 1.0)")
         implicit = {k: 1.0 / v for k, v in odds.items()}
         total = sum(implicit.values())  # > 1.0 due to bookmaker overround
         fair_probs = {k: p / total for k, p in implicit.items()}
         return {k: 1.0 / p for k, p in fair_probs.items()}
         ```
       - Type hints strict (`dict[str, float]` both sides). No `Any`. No external deps beyond stdlib.
    2. Append the 5 RED tests above to `tests/test_clv_recorder.py` inside a new `class TestRemoveVig:` block. Each test imports inside the method (`from bip.clv.odds_math import remove_vig`) to match the file's existing import style.
    3. RED: run `uv run pytest tests/test_clv_recorder.py::TestRemoveVig -x` and confirm tests fail with `ModuleNotFoundError` (file doesn't exist yet) — then create the file. After file exists, all 5 tests must be GREEN.
    4. No emojis. No Co-Authored-By trailers when committing (CLAUDE.md convention).
  </action>
  <verify>
    <automated>uv run pytest tests/test_clv_recorder.py::TestRemoveVig -x -q</automated>
  </verify>
  <done>
    - `src/bip/clv/odds_math.py` exists, exports `remove_vig`, no I/O, no logging, type-hinted.
    - All 5 `TestRemoveVig` cases pass.
    - `python -c "from bip.clv.odds_math import remove_vig; print(remove_vig({'1':1.95,'X':3.40,'2':4.20}))"` runs without error and prints fair odds whose 1/odd values sum to ~1.0.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Refactor calculate_clv_percentage + ClvRecorder.record() to use vig-removed math</name>
  <files>src/bip/clv/recorder.py, tests/test_clv_recorder.py</files>
  <behavior>
    - test_calculate_clv_uses_vig_removed_price: odds_at_pick=2.10, closing_odds_dict={"1": 1.95, "X": 3.40, "2": 4.20}, selection="1" -> CLV is approximately +5.5% (vig-removed), NOT +7.7% (raw). Assert `pytest.approx(5.5, abs=0.5)` AND `result < 7.0` (proves vig was actually removed; raw math would give ~7.69).
    - test_calculate_clv_raises_on_missing_selection: selection="Z" not in dict -> raises ClvError or KeyError (executor's choice — wrap KeyError into ClvError for consistency with existing error style).
    - test_calculate_clv_raises_on_invalid_dict: empty dict -> ValueError (propagated from remove_vig); odds with 1.0 -> ValueError.
    - test_record_persists_raw_closing_odd_for_selection: after `recorder.record(..., closing_odds_dict={"1":1.95,"X":3.40,"2":4.20}, selection="1")`, the inserted ClvRecord has `pinnacle_closing_odds == 1.95` (RAW, not fair) AND `implied_prob_closing == pytest.approx(1.0/1.95, abs=1e-6)` AND `clv_percentage` is the vig-removed value (matches test_calculate_clv_uses_vig_removed_price).
    - Existing tests (test_clv_percentage_formula, test_clv_negative_when_odds_worse_than_closing, test_clv_zero_when_odds_equal_closing, test_clv_record_stored_with_odds_fetched_at) updated to use the new dict+selection signature and still pass with the same numeric expectations (use a synthetic 2-way dict where vig is 0, e.g., {"home": 2.00, "away": 2.00} which is already vig-free, so fair == raw and CLV math collapses to the original formula).
  </behavior>
  <action>
    1. Modify `src/bip/clv/recorder.py`:
       a. Add `from bip.clv.odds_math import remove_vig` at the top with the other imports.
       b. Change `calculate_clv_percentage` signature from `(odds_at_pick: float, closing_odds: float)` to `(odds_at_pick: float, closing_odds_dict: dict[str, float], selection: str) -> float`. New body:
          ```
          if odds_at_pick <= 0:
              raise ClvError(f"Invalid odds_at_pick={odds_at_pick} -- must be positive")
          try:
              fair = remove_vig(closing_odds_dict)
          except ValueError as exc:
              raise ClvError(f"Vig removal failed: {exc}") from exc
          if selection not in fair:
              raise ClvError(f"Selection {selection!r} not in closing_odds_dict (keys={sorted(fair.keys())})")
          fair_odd = fair[selection]
          return (odds_at_pick / fair_odd - 1.0) * 100.0
          ```
          Update docstring to reflect: "Compares odds_at_pick against the vig-removed (fair) closing price for `selection`. PITFALLS.md Pitfall 7." Drop the old `closing_odds <= 0` check (now handled inside remove_vig per-key with a clearer message).
       c. Change `ClvRecorder.record()` signature: replace `pinnacle_closing_odds: float` with `closing_odds_dict: dict[str, float]` and add a required `selection: str` parameter (no default; positional after `odds_at_pick`). Update the docstring's Args block accordingly.
       d. Inside `record()`:
          - Compute `clv_pct = calculate_clv_percentage(odds_at_pick, closing_odds_dict, selection)`.
          - Validate `selection in closing_odds_dict` early and raise `ClvError(f"selection {selection!r} not in closing_odds_dict")` if not (so the persistence path also gets a clean error before remove_vig is called twice).
          - Compute `raw_closing_odd = closing_odds_dict[selection]`.
          - Construct `ClvRecord` with `pinnacle_closing_odds=raw_closing_odd` and `implied_prob_closing=1.0 / raw_closing_odd` (RAW values — frozen persistence decision above).
          - Update the `logger.info("clv_recorded", ...)` call: replace `pinnacle_closing_odds=pinnacle_closing_odds` with `pinnacle_closing_odds_raw=raw_closing_odd, closing_odds_dict=closing_odds_dict`. Add `selection=selection`.
       e. Keep `compute_rolling_clv_average` untouched.
    2. Update `tests/test_clv_recorder.py`:
       a. Existing 3 calculation tests (`test_clv_percentage_formula`, `test_clv_negative_when_odds_worse_than_closing`, `test_clv_zero_when_odds_equal_closing`): replace each `closing_odds=X.XX` argument with `closing_odds_dict={"home": X.XX, "away": X.XX}, selection="home"` so the dict is exactly vig-free (sum 1/X.XX + 1/X.XX == 1.0 only if X.XX == 2.00). For the non-2.00 cases, switch to a 2-way vig-free dict like `{"home": 2.10, "away": 2.10}` does NOT sum to 1 — instead, use `{"home": 2.10, "away": 1.91}` which is roughly vig-free, OR (cleaner) switch the assertions to use `pytest.approx` with `abs=0.5` and document that the original raw-odd test invariants no longer hold post-vig-removal. **Preferred path:** rewrite each existing test as a vig-aware assertion: e.g., `result_for_(2.10 vs {"home":2.00,"away":2.00}) == pytest.approx(5.0, abs=0.01)` because that input is vig-free (1/2 + 1/2 = 1.0) so CLV math collapses to the original. Same for 1.90 vs 2.00/2.00 -> -5.0, and 2.00 vs 2.00/2.00 -> 0.0. **Use this preferred path** — it preserves the original numeric intent without introducing fuzz.
       b. Existing `test_clv_record_stored_with_odds_fetched_at`: change `pinnacle_closing_odds=2.00` to `closing_odds_dict={"home": 2.00, "away": 2.00}, selection="home"`. Assertion `clv.clv_percentage == pytest.approx(5.0, abs=0.01)` still holds. Also add `assert clv.pinnacle_closing_odds == pytest.approx(2.00, abs=1e-6)` to lock in the persistence-decision invariant.
       c. Add the 4 new tests from `<behavior>` (test_calculate_clv_uses_vig_removed_price, test_calculate_clv_raises_on_missing_selection, test_calculate_clv_raises_on_invalid_dict, test_record_persists_raw_closing_odd_for_selection) inside the existing `TestClvCalculation` class (or a new `TestClvVigRemoval` class — executor's choice for organization).
    3. RED then GREEN:
       - Run `uv run pytest tests/test_clv_recorder.py -x -q` — expect failures from existing tests (signature changed) and new tests (vig-removal not wired). Fix the recorder code in step 1, then re-run until all GREEN.
    4. Run the full suite to confirm no regressions in the other 120+ tests:
       - `uv run pytest -x -q --ignore=tests/test_clv_recorder.py` first (sanity: nothing else imports `calculate_clv_percentage` or calls `recorder.record()`).
       - Then `uv run pytest -q` for the full sweep.
    5. No emojis in code, docstrings, or commit messages. No Co-Authored-By trailers.
  </action>
  <verify>
    <automated>uv run pytest tests/test_clv_recorder.py -x -q && uv run pytest -q</automated>
  </verify>
  <done>
    - `calculate_clv_percentage(odds_at_pick, closing_odds_dict, selection)` signature live in recorder.py.
    - `ClvRecorder.record()` accepts `closing_odds_dict: dict[str, float]` + `selection: str` and persists raw closing odd into `ClvRecord.pinnacle_closing_odds`.
    - `ClvRecord.clv_percentage` reflects vig-removed math (verified by test_calculate_clv_uses_vig_removed_price showing ~+5.5% not +7.7%).
    - All `tests/test_clv_recorder.py` cases pass (existing + new).
    - Full `uv run pytest -q` passes with zero regressions (target: 126+ tests still GREEN).
    - No new callers of the old signature exist (grep confirms — orchestrator `_record_clv` is still a stub, untouched by this plan).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| The Odds API -> ClvRecorder | Pinnacle odds dict is decoded from external JSON; values could be malformed (0.0, negative, missing keys). |
| ClvRecorder -> Supabase | Persisted `pinnacle_closing_odds` and `clv_percentage` feed downstream rolling-average alerting (Phase 4). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Tampering | `remove_vig` input dict | mitigate | Reject empty dict and any odd <= 1.0 with `ValueError` (Task 1). Wrap into `ClvError` at recorder boundary so DB layer never sees a bad math result (Task 2). |
| T-quick-02 | Information Disclosure | `ClvRecord.pinnacle_closing_odds` audit field | accept | Persisting raw Pinnacle price preserves forensic value; not PII, public market data. Frozen persistence decision documented in plan + recorder docstring. |
| T-quick-03 | Repudiation | `clv_percentage` semantic change (raw -> vig-removed) | mitigate | Update recorder.py module docstring to call out vig-removal; log `closing_odds_dict` + `selection` in `clv_recorded` event so historical rows can be back-recomputed if needed. |
| T-quick-04 | Denial of Service | Selection key absent from dict | mitigate | Early `ClvError` in both `calculate_clv_percentage` and `record()` prevents `KeyError` propagating to scheduler thread (Pitfall 6 risk: jobstore loss on unhandled exception). |
</threat_model>

<verification>
1. `uv run pytest tests/test_clv_recorder.py -v` — all CLV tests GREEN, new vig-removal cases visible in output.
2. `uv run pytest -q` — full suite (126+ tests) GREEN, zero regressions.
3. Manual sanity: `uv run python -c "from bip.clv.recorder import calculate_clv_percentage; print(calculate_clv_percentage(2.10, {'1':1.95,'X':3.40,'2':4.20}, '1'))"` prints a value in [5.0, 6.0] — confirms vig-removed CLV is materially lower than the raw 7.69%.
4. `grep -rn "calculate_clv_percentage\|recorder.record(" src tests` — every call site uses the new signature (dict + selection); no stale `closing_odds=` float arguments remain.
5. `grep -n "pinnacle_closing_odds" src/bip/core/storage/models.py` — schema unchanged (still `float | None`); no migration generated.
</verification>

<success_criteria>
- `src/bip/clv/odds_math.py` exists with `remove_vig` (pure, type-hinted, ValueError on bad input).
- `calculate_clv_percentage(odds_at_pick, closing_odds_dict, selection)` uses vig-removed math; raw signature is gone.
- `ClvRecorder.record()` accepts `closing_odds_dict + selection`; persists raw closing odd into `pinnacle_closing_odds` and vig-removed CLV into `clv_percentage`.
- `tests/test_clv_recorder.py` covers proportional vig removal, invalid-input rejection, missing-selection error, and raw-vs-fair persistence invariant.
- Full `uv run pytest -q` GREEN (no regressions in the other 120+ tests).
- ClvRecord schema unchanged — no migration needed.
- No Co-Authored-By trailers in commits; no emojis anywhere.
</success_criteria>

<output>
After completion, create `.planning/quick/260503-iql-vig-removal-en-clv-recorder/260503-iql-SUMMARY.md` documenting:
- Files changed (odds_math.py created, recorder.py + test_clv_recorder.py modified).
- Persistence decision frozen: `pinnacle_closing_odds` = raw, `clv_percentage` = vig-removed.
- Test count delta (added vig-removal cases, migrated existing call sites).
- Confirmation no other callers needed updating (orchestrator `_record_clv` is still a stub, awaiting Step 4 of parent multi-step plan at `/Users/kevin_beltran/.claude/plans/planea-c-mo-implementar-estas-giggly-hare.md`).
</output>
