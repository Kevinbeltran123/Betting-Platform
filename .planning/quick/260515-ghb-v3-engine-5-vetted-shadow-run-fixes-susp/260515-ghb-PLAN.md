---
phase: 260515-ghb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/bip/evaluation/live/engine_v3/runtime/dual_write.py
  - src/bip/evaluation/live/engine_v3/no_bet_gate.py
  - src/bip/evaluation/live/engine_v3/ood_detector.py
  - src/bip/evaluation/live/engine_v3/mes.py
  - src/bip/evaluation/live/engine_v3/gsv_builder.py
  - src/bip/evaluation/live/engine_v3/gsv.py
  - src/bip/evaluation/live/engine_v3/shadow_logger.py
  - tests/evaluation/live/engine_v3/
autonomous: true
requirements:
  - V3-FORENSIC-20260514
must_haves:
  truths:
    - "market_snapshot_from_odds skips any odd where suspended or stopped is True"
    - "market_snapshot_from_odds emits NO MarketLine for a market_id that had both a non-suspended and a suspended/stopped quote in the same payload (drop-ambiguous)"
    - "A new enforced no-bet rule denies cruise_mode + GOALS candidates when 2.5 <= mes.score < 4.0, and allows them at mes.score 2.49 and 4.0"
    - "OOD FEATURE_NAMES no longer contains total_goals, xg_total, goal_diff (forward-looking refit schema)"
    - "Loading the existing data/cache/ood_detector_v2_real.pkl and scoring a GSV does NOT raise (legacy 17-dim scoring path preserved for the shadow computation)"
    - "rule_9 OOD is shadow-only: a GSV the legacy detector would deny PASSES the gate and a shadow denial row is recorded; a GSV with total_goals outside [0,15] is a REAL enforced deny"
    - "Enforced MES score math is byte-for-byte unchanged (conditional_variance enforced return value is the original raw formula; the squashed variant is used ONLY inside rule_8's shadow decision)"
    - "rule_8 is shadow-only when raw would deny but squashed (minute>=40, GOALS) would pass: candidate PASSES and a shadow denial row is recorded; otherwise rule_8 enforces unchanged"
    - "_MARKET_DOM_MIN_PROB_GAP stays 0.04 enforced; a shadow dominant_team_id computed at 0.025 is attached to the GSV and appears in gsv_log.parquet"
    - "rule_11_calibration_drift returns OK early for Archetype.DOMINANT_LOSING_NAPOLI regardless of drift status, with a revoke-first code comment"
    - "engine_v3 test suite and the anti-Napoli regression suite pass before every commit"
    - "Five atomic commits exist, one per change, in the specified order"
  artifacts:
    - path: "src/bip/evaluation/live/engine_v3/runtime/dual_write.py"
      provides: "market_snapshot_from_odds with suspended-skip + drop-ambiguous dedup"
    - path: "src/bip/evaluation/live/engine_v3/no_bet_gate.py"
      provides: "new cruise_mode/goals MES dead-zone rule (enforced); rule_8/rule_9 shadow-tag; rule_11 napoli exemption"
    - path: "src/bip/evaluation/live/engine_v3/ood_detector.py"
      provides: "trimmed forward FEATURE_NAMES + preserved legacy scoring path"
    - path: "src/bip/evaluation/live/engine_v3/mes.py"
      provides: "squashed-GOALS-cvar helper used by rule_8 shadow path; enforced cvar unchanged"
    - path: "src/bip/evaluation/live/engine_v3/gsv.py"
      provides: "shadow_dominant_team_id field on the GSV model"
    - path: "tests/evaluation/live/engine_v3/"
      provides: "tests for suspended-skip/drop-ambiguous, MES dead-zone boundaries, shadow-tag pass-through, napoli rule-11 exemption"
  key_links:
    - from: "no_bet_gate.run_gate"
      to: "the new MES dead-zone rule"
      via: "per-candidate rule sequence (immediately after rule_5 thesis/market mismatch)"
      pattern: "dead.?zone|CRUISE_MODE"
    - from: "rule_9_ood_detector"
      to: "shadow_logger denial recording"
      via: "shadow verdict (is_shadow=True) instead of enforced deny"
      pattern: "is_shadow|shadow"
    - from: "gsv_builder.build"
      to: "gsv.shadow_dominant_team_id"
      via: "second dominant-team computation at _MARKET_DOM_MIN_PROB_GAP_SHADOW=0.025"
      pattern: "shadow_dominant_team_id|_SHADOW"
---

<objective>
Apply five vetted changes to Live Engine v3, diagnosed from the 2026-05-14 shadow-run forensic
analysis. Two are ENFORCED behavior changes (suspended-line dedup; cruise_mode/goals MES dead-zone
gate). Three are SHADOW-TAGGED — they compute a verdict and record it to the denial log with an
is_shadow marker but do NOT change whether a candidate passes the gate, so a week of data accrues
with zero risk to the freshly-promoted live Telegram path. One sub-change (napoli rule-11 exemption)
is enforced because the gate is currently strangling the system's most profitable archetype.

Each change is exactly ONE atomic commit, applied in order 1→5. The engine_v3 test suite AND the
anti-Napoli regression suite (a CI gate) must pass before every commit.

Output: 5 atomic commits + tests; no change to enforced MES scoring; live gate behavior changes
ONLY for the two enforced items.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@src/bip/evaluation/live/engine_v3/runtime/dual_write.py
@src/bip/evaluation/live/engine_v3/no_bet_gate.py
@src/bip/evaluation/live/engine_v3/ood_detector.py
@src/bip/evaluation/live/engine_v3/mes.py
@src/bip/evaluation/live/engine_v3/gsv_builder.py
@src/bip/evaluation/live/engine_v3/gsv.py
@src/bip/evaluation/live/engine_v3/shadow_logger.py

<diagnostic_provenance>
Source: forensic analysis of data/cache/v3_shadow/dt=2026-05-14/{picks,gate_denials,gsv_log}.parquet
and logs/v3_day3_replay_graded.parquet + logs/v3_day4_regraded_dedup.parquet.
- Rule-4 was 81/138 denials on 2026-05-14; root cause = frozen suspended quotes shadowing fresh
  live ones via first-wins dedup in market_snapshot_from_odds (active odds refresh every 3-25s;
  staleness is confined to suspended/stopped quotes). User explicitly chose the CONSERVATIVE
  drop-ambiguous policy over freshest-wins.
- MES bin [3,4) is a replicated dead zone: Day-3 n=31 WR 38.7% -13.78u; Day-4 n=5 WR 40% -2.50u;
  almost entirely cruise_mode/goals.
- Rule-9 OOD (31 denials) = distribution shift: detector fit on the quiet 2026-05-12 GSV log
  (p99 total_goals=5); high-scoring MLS/Swiss states are 10-20σ out on total_goals/xg_total/goal_diff.
- Rule-8 (20 denials): GOALS cvar = λ_total·horizon/90 is structurally un-passable for a normal-λ
  GOALS thesis before ~min 50 with a rest-of-match horizon.
- dominant_losing_napoli: +96u/14 (Day-3, WR 1.0) and +6.75u/2 (Day-4) — the system's best
  archetype, priced as a long-shot (fair_prob 0.12-0.32), now denied by rule_11 on a 0.67 WR prior
  it never claimed.
</diagnostic_provenance>

<known_correctness_constraints>
These are subtle and MUST be honored — they are why this is a precise plan, not freeform:

1. OOD pkl dimension trap (Task 3): the persisted ood_detector_v2_real.pkl was fit with the FULL
   17-feature vector (mean/cov_inv are 17-dim). If you trim vectorize_gsv to 14 dims, scoring the
   legacy detector will raise on a shape mismatch. Required approach: the shadow computation in
   rule_9 MUST score the legacy detector with the SAME 17-feature vector it was fit on. Trim the
   module-level FEATURE_NAMES (forward-looking, consumed by the refit script) but preserve a
   legacy/full vectorization path for the loaded detector. If OODDetector persists its own feature
   list, score using the detector's persisted schema; if it does not, keep a `vectorize_gsv_legacy`
   (full 17) used by rule_9's shadow path and point the trimmed FEATURE_NAMES only at future fits.
   Verify by loading the real pkl and scoring a GSV without exception.

2. Enforced MES must not move (Task 4): conditional_variance's RETURN VALUE feeding mes.score
   (score = base_edge·clarity·slowness·liq / cvar) MUST stay the original raw formula. Do NOT make
   conditional_variance return the squashed value — that would silently change pick selection.
   Add the squash as a separate pure helper (e.g. `_squashed_goals_cvar(raw)` → raw/(1+raw)) used
   ONLY inside rule_8's shadow comparison. Add a regression test asserting an unrelated GOALS
   candidate's mes.score is identical before/after this commit.

3. Shadow rows must not be enforced (Tasks 3 & 4): a shadow verdict means GateResult.verdict is
   ALLOWED (candidate passes) AND a denial-style row is recorded with an is_shadow=True (or
   shadow_rule) marker. Extend the shadow_logger denial row schema with an is_shadow boolean
   (default False so existing/real denials are unaffected and the parquet stays diagonal-relaxed
   compatible). Do not break the existing _denial_row columns.

4. GSV model field (Task 5a): shadow_dominant_team_id must be an Optional field on the GSV/score
   model with a safe default (None) so gsv.model_dump_json() (written to gsv_log.parquet) carries
   it without breaking existing readers. Enforced dominant_team_id selection is UNCHANGED.

5. Rule numbering (Task 2): the gate already defines rules 1-11. The new dead-zone rule takes the
   next free number (12). Wire it into run_gate's per-candidate sequence immediately AFTER
   rule_5_thesis_market_mismatch (it is a sibling MES-based precision filter) and BEFORE rule_6.
</known_correctness_constraints>

<test_conventions>
- Boundary tests are parametrized at line±1 per project convention (memory: feedback_test_boundary_cases;
  canonical pattern tests/evaluation/live/test_grading.py::TestOuGoals::test_total_goals).
- For the MES dead-zone rule, parametrize mes.score at exactly: 2.49 (allow), 2.5 (deny), 3.99
  (deny), 4.0 (allow) — for cruise_mode/GOALS; PLUS a control: cruise_mode/CORNERS at 3.0 (allow)
  and a non-cruise archetype/GOALS at 3.0 (allow), proving the rule is correctly scoped.
- Shadow-tag tests assert BOTH: (a) GateResult for the candidate is allowed, AND (b) a shadow
  denial row with is_shadow=True was recorded.
- Anti-Napoli regression suite is a CI gate — locate it (grep -ri "napoli" tests/) and run it
  before EVERY commit alongside the engine_v3 suite.
</test_conventions>
</context>

<tasks>

<task id="1" type="execute">
**COMMIT 1 (ENFORCED) — suspended-skip + drop-ambiguous dedup**

files: src/bip/evaluation/live/engine_v3/runtime/dual_write.py, tests/evaluation/live/engine_v3/

action: In `market_snapshot_from_odds` (~L198-237): (a) skip any odd where
`getattr(o,"suspended",False) or getattr(o,"stopped",False)` is True; (b) replace the first-wins
`if market_id in lines: continue` with DROP-AMBIGUOUS — first pass over odds collects the set of
market_ids that had ANY suspended/stopped quote; second pass builds MarketLine ONLY from
non-suspended quotes whose market_id is NOT in that suspended set. Preserve all existing skip
conditions (empty desc, value is None, decimal parse failure, decimal <= 1.0) and the existing
`last_update = getattr(o,"latest_bookmaker_update",None) or captured_at` line. Add tests: a
suspended quote is dropped; a market with only live quotes is kept; a market with both a live and
a suspended quote in the same payload yields NO line.

verify: new tests pass; engine_v3 suite + anti-Napoli suite green; `git show --stat` shows only
dual_write.py + test file.

done: Commit `fix(engine_v3/dual_write): drop suspended odds + drop-ambiguous market dedup`
with the diagnostic rationale (81/138 Rule-4 denials were frozen suspended quotes shadowing live
ones; conservative policy chosen to protect CLV measurement during freshly-promoted Telegram path)
in the body. No Co-Authored-By.
</task>

<task id="2" type="execute">
**COMMIT 2 (ENFORCED) — cruise_mode/goals MES dead-zone rule**

files: src/bip/evaluation/live/engine_v3/no_bet_gate.py, tests/evaluation/live/engine_v3/

action: Add `rule_12_mes_dead_zone(candidate)` (next free number after the existing 1-11) denying
when `candidate.thesis.archetype == Archetype.CRUISE_MODE and candidate.family ==
MarketFamily.GOALS and 2.5 <= candidate.mes.score < 4.0` with reason
`"cruise_mode/goals MES dead-zone [2.5,4.0)"`. Wire into `run_gate`'s per-candidate sequence
immediately AFTER `rule_5_thesis_market_mismatch` and before `rule_6`. Add parametrized boundary
tests (2.49 allow / 2.5 deny / 3.99 deny / 4.0 allow for cruise_mode+GOALS) plus scoped controls
(cruise_mode+CORNERS@3.0 allow; non-cruise+GOALS@3.0 allow).

verify: boundary + control tests pass; engine_v3 + anti-Napoli suites green.

done: Commit `feat(engine_v3/gate): suppress cruise_mode/goals MES dead-zone [2.5,4.0)` with the
replicated-loss rationale (Day-3 n=31 WR 38.7% -13.78u; Day-4 n=5 WR 40% -2.50u) in the body.
</task>

<task id="3" type="execute">
**COMMIT 3 (SHADOW-TAGGED) — OOD trim + shadow-only rule_9 + sanity bound**

files: src/bip/evaluation/live/engine_v3/ood_detector.py,
src/bip/evaluation/live/engine_v3/no_bet_gate.py,
src/bip/evaluation/live/engine_v3/shadow_logger.py, tests/evaluation/live/engine_v3/

action: Remove "total_goals","xg_total","goal_diff" from the module-level FEATURE_NAMES (forward
schema for refits). Honor known_correctness_constraint #1: preserve a full-17 legacy vectorization
path so the loaded pkl still scores without a shape mismatch (use the detector's persisted feature
schema if present, else a `vectorize_gsv_legacy`). Make `rule_9_ood_detector` SHADOW-ONLY: if the
legacy detector would deny, record a shadow denial row (is_shadow=True) and return OK (candidate
passes); EXCEPT add a REAL enforced deny when `total_goals` is outside [0,15] (genuinely broken
GSV). Extend shadow_logger `_denial_row` with an `is_shadow` boolean (default False; keep
diagonal-relaxed parquet compatibility). Add a commit-body note (do NOT run it) that
scripts/spike/v3/refit_ood_v2_real.py should be re-run with the trimmed, tempo-stratified feature
set to produce a new enforced detector later. Tests: a high-scoring GSV the legacy detector flags
→ candidate ALLOWED + shadow row recorded; total_goals=20 → real deny; loading the real pkl and
scoring a GSV does not raise.

verify: pkl-load-and-score test passes (constraint #1); shadow pass-through test passes;
engine_v3 + anti-Napoli suites green.

done: Commit `feat(engine_v3/ood): trim OOD features + shadow-only rule_9 with broken-GSV sanity bound`
with the distribution-shift rationale (31 OOD denials on 2 high-scoring fixtures; detector fit on
quiet 2026-05-12 p99 total_goals=5) and the refit-script note in the body.
</task>

<task id="4" type="execute">
**COMMIT 4 (SHADOW-TAGGED) — GOALS cvar squash helper + shadow-only rule_8**

files: src/bip/evaluation/live/engine_v3/mes.py,
src/bip/evaluation/live/engine_v3/no_bet_gate.py, tests/evaluation/live/engine_v3/

action: Honor known_correctness_constraint #2: leave `conditional_variance`'s enforced return
value (the GOALS raw formula λ_total·horizon/90) UNCHANGED. Add a pure helper
`_squashed_goals_cvar(raw) -> raw/(1+raw)`. Make `rule_8_predictive_uncertainty` SHADOW-ONLY in
exactly one case: when raw cvar WOULD deny, the family is GOALS, and gsv minute >= 40, and the
squashed value would pass the band → record a shadow denial row (is_shadow=True) and return OK
(candidate passes). In every other case rule_8 enforces exactly as before. Tests: a GOALS
candidate at minute 48 with raw cvar > band but squashed <= band → ALLOWED + shadow row recorded;
a pre-min-40 GOALS candidate over band → still REAL deny; a regression test asserting an unrelated
GOALS candidate's `mes.score` is identical before/after this commit (enforced math unchanged).

verify: mes.score regression test passes (constraint #2); shadow pass-through + pre-40 still-deny
tests pass; engine_v3 + anti-Napoli suites green.

done: Commit `feat(engine_v3/gate): shadow-only horizon-squashed rule_8 for HT GOALS theses`
with the rationale (open_game/goals at HT auto-denied; squashed HT cvar ~0.57 not ~1.34) in the body.
</task>

<task id="5" type="execute">
**COMMIT 5 — shadow dominant-team gap (5a, shadow) + napoli rule-11 exemption (5b, enforced)**

files: src/bip/evaluation/live/engine_v3/gsv_builder.py,
src/bip/evaluation/live/engine_v3/gsv.py,
src/bip/evaluation/live/engine_v3/no_bet_gate.py, tests/evaluation/live/engine_v3/

action: (5a) Keep `_MARKET_DOM_MIN_PROB_GAP = 0.04` ENFORCED. Add
`_MARKET_DOM_MIN_PROB_GAP_SHADOW = 0.025`. In `gsv_builder.build`, additionally compute the
dominant_team_id at the 0.025 shadow gap and attach it to the GSV via a new
Optional `shadow_dominant_team_id` field (constraint #4: Optional, default None, so
gsv.model_dump_json() → gsv_log.parquet carries it without breaking readers). Enforced
dominant_team_id selection is UNCHANGED. (5b) In `rule_11_calibration_drift`, return
`NoBetVerdict.ok()` early when `candidate.thesis.archetype == Archetype.DOMINANT_LOSING_NAPOLI`,
with a comment: "REVOKE THIS FIRST if live napoli P/L turns negative — napoli is graded on P/L
not WR (+96u/14 Day-3); rule_11's WR-drift gate uses a 0.67 prior the long-shot archetype never
claimed." Tests: GSV exposes shadow_dominant_team_id and it appears in model_dump; a napoli
candidate with a drifted monitor → rule_11 returns OK (allowed); a non-napoli drifted candidate →
still denied by rule_11.

verify: shadow-field dump test + napoli-exempt test + non-napoli-still-denied test pass;
engine_v3 + anti-Napoli suites green.

done: Commit `feat(engine_v3): shadow dominant-team gap 0.025 + exempt napoli from rule_11 drift`
with both rationales in the body.
</task>

</tasks>

<sequence>
1 → 2 → 3 → 4 → 5. Strictly ordered, one atomic commit each. Run the engine_v3 test suite AND the
anti-Napoli regression suite before EVERY commit; if either fails, fix before committing (do not
proceed to the next task with a red suite). Do NOT commit docs artifacts (PLAN/SUMMARY/STATE) —
the orchestrator handles the docs commit.
</sequence>
