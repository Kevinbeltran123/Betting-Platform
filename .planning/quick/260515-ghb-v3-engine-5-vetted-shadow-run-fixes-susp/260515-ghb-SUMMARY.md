---
phase: 260515-ghb
plan: "01"
subsystem: engine_v3
tags:
  - live-engine
  - shadow-logging
  - no-bet-gate
  - ood-detector
  - suspended-odds
  - napoli-exemption
dependency_graph:
  requires: []
  provides:
    - engine_v3/suspended-dedup
    - engine_v3/cruise-mode-mes-dead-zone
    - engine_v3/shadow-ood-rule9
    - engine_v3/shadow-rule8-goals-cvar
    - engine_v3/shadow-dominant-team-025
    - engine_v3/napoli-rule11-exemption
  affects:
    - src/bip/evaluation/live/engine_v3/runtime/dual_write.py
    - src/bip/evaluation/live/engine_v3/no_bet_gate.py
    - src/bip/evaluation/live/engine_v3/ood_detector.py
    - src/bip/evaluation/live/engine_v3/mes.py
    - src/bip/evaluation/live/engine_v3/gsv.py
    - src/bip/evaluation/live/engine_v3/gsv_builder.py
    - src/bip/evaluation/live/engine_v3/shadow_logger.py
tech_stack:
  added:
    - _squashed_goals_cvar helper (mes.py)
    - vectorize_gsv_legacy 17-dim path (ood_detector.py)
    - ShadowLogger.record_shadow_denial (shadow_logger.py)
  patterns:
    - shadow-and-pass (record denial, allow candidate)
    - drop-ambiguous suspended dedup
    - min_prob_gap dual computation for shadow analysis
key_files:
  created: []
  modified:
    - src/bip/evaluation/live/engine_v3/runtime/dual_write.py
    - src/bip/evaluation/live/engine_v3/no_bet_gate.py
    - src/bip/evaluation/live/engine_v3/ood_detector.py
    - src/bip/evaluation/live/engine_v3/mes.py
    - src/bip/evaluation/live/engine_v3/gsv.py
    - src/bip/evaluation/live/engine_v3/gsv_builder.py
    - src/bip/evaluation/live/engine_v3/shadow_logger.py
    - tests/evaluation/live/engine_v3/test_dual_write.py
    - tests/evaluation/live/engine_v3/test_no_bet_gate.py
    - tests/evaluation/live/engine_v3/test_ood_detector.py
    - tests/evaluation/live/engine_v3/test_next_goal_and_drift.py
decisions:
  - "Conservative drop-ambiguous suspended dedup chosen over freshest-wins: any market_id with both a suspended and live quote drops entirely"
  - "OOD rule_9 is shadow-only: Mahalanobis OOD records shadow row but candidate passes; total_goals outside [0,15] is still a real enforced deny"
  - "rule_8 shadow-only path scoped to GOALS + minute>=40: squashed cvar (raw/(1+raw)) used only for the shadow comparison, enforced cvar unchanged"
  - "DOMINANT_LOSING_NAPOLI exempt from rule_11 calibration drift: graded on P/L (+96u/14 Day-3) not WR, rule_11 prior of 0.67 was never the napoli claim"
  - "shadow_dominant_team_id computed at 0.025 gap (vs enforced 0.04) and stored as Optional field on GSV model; enforced dominant_team_id unchanged"
  - "OOD FEATURE_NAMES trimmed to 14 (removed total_goals, xg_total, goal_diff): legacy 17-dim path vectorize_gsv_legacy preserved for loaded pkl compatibility"
metrics:
  duration: "~120 min (resumed from previous session, 4 tasks already committed)"
  completed_date: "2026-05-15"
  tasks_completed: 5
  tasks_total: 5
  files_modified: 11
---

# Phase 260515-ghb Plan 01: V3 Engine 5 Vetted Shadow-Run Fixes Summary

Five forensic fixes to Live Engine v3 from the 2026-05-14 shadow-run analysis. Two enforced behavior changes; three shadow-tagged (record denial, candidate passes); one exemption that was strangling the most profitable archetype.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Suspended odds skip + drop-ambiguous dedup | a80d89b | dual_write.py, test_dual_write.py |
| 2 | cruise_mode/GOALS MES dead-zone rule_12 | b855104 | no_bet_gate.py, test_no_bet_gate.py |
| 3 | OOD trim 14-feat + shadow-only rule_9 | 3e80e0b | ood_detector.py, no_bet_gate.py, shadow_logger.py, test_ood_detector.py |
| 4 | GOALS cvar squash helper + shadow-only rule_8 | 7256bc2 | mes.py, no_bet_gate.py, test_no_bet_gate.py |
| 5 | Shadow dominant-team 0.025 + napoli rule_11 exemption | 3ddfc09 | gsv.py, gsv_builder.py, no_bet_gate.py, test_no_bet_gate.py, test_next_goal_and_drift.py |

## What Was Shipped

### Task 1 — Suspended-line drop-ambiguous dedup (ENFORCED)

Root cause of 81/138 Rule-4 denials on 2026-05-14: frozen suspended quotes were beating fresh live quotes in the first-wins dedup. Two-pass approach: first pass collects all `market_id`s that have ANY suspended/stopped quote; second pass builds MarketLine only from non-suspended quotes whose `market_id` is NOT in the suspended set. Conservative policy — drop the whole market rather than risk a stale line.

### Task 2 — cruise_mode/GOALS MES dead-zone rule_12 (ENFORCED)

Replicated loss: Day-3 n=31 WR 38.7% −13.78u; Day-4 n=5 WR 40% −2.50u, both in MES bin [2.5, 4.0) for cruise_mode/GOALS. Rule_12 denies exactly this band. MES >= 4.0 (high-conviction cruise_mode/GOALS) and MES < 2.5 (below rule_5 threshold) are unaffected. Wired immediately after rule_5 in `run_gate`.

### Task 3 — OOD feature trim + shadow-only rule_9 with sanity bound (SHADOW-TAGGED)

The legacy `ood_detector_v2_real.pkl` was fit on 17 features including `total_goals`, `xg_total`, `goal_diff` — which made high-scoring MLS/Swiss states (total_goals=10-20) appear 20σ OOD. Forward FEATURE_NAMES trimmed to 14 (removed those 3). Legacy 17-dim path (`vectorize_gsv_legacy`) preserved for pkl compatibility via `_select_vectorizer()` auto-detection. Rule_9 is now shadow-only: Mahalanobis OOD records is_shadow=True and lets the candidate pass. Exception: `total_goals` outside [0, 15] is still a real enforced deny (broken GSV). Shadow_logger extended with `is_shadow` boolean + `record_shadow_denial()` method.

### Task 4 — GOALS cvar squash helper + shadow-only rule_8 (SHADOW-TAGGED)

`_squashed_goals_cvar(raw)` = raw/(1+raw) added as a pure helper in mes.py. The enforced `conditional_variance` return value (raw formula λ_total·horizon/90) is unchanged — the regression test confirms this. Rule_8's shadow path: when raw cvar > band AND family=GOALS AND minute >= 40 AND squashed <= band, candidate passes and shadow row is recorded. Pre-minute-40 GOALS and all non-GOALS still enforce normally.

### Task 5 — Shadow dominant-team gap + napoli rule_11 exemption (SHADOW + ENFORCED)

5a (shadow): `shadow_dominant_team_id` computed at `_MARKET_DOM_MIN_PROB_GAP_SHADOW=0.025` alongside the enforced 0.04 gap. Attached as Optional field on `GameStateVector` with `None` default (backward-compatible with existing gsv_log.parquet readers). Enforced `dominant_team_id` (score.dominant_team_id) unchanged.

5b (enforced): `rule_11_calibration_drift` returns `NoBetVerdict.ok()` early for `DOMINANT_LOSING_NAPOLI`. Rationale: archetype delivered +96u/14 picks (Day-3, WR 1.0) and +6.75u/2 (Day-4). Rule_11's WR drift gate uses a 0.67 prior the long-shot archetype (fair_prob 0.12-0.32) never claimed. Revoke comment embedded: "REVOKE THIS FIRST if live napoli P/L turns negative."

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_rule_11_denies_when_cell_drifted used DOMINANT_LOSING_NAPOLI incidentally**
- **Found during:** Task 5
- **Issue:** The existing test `test_next_goal_and_drift.py::test_rule_11_denies_when_cell_drifted` was using `ThesisArchetype.DOMINANT_LOSING_NAPOLI` as a generic archetype to test the general drift-denial path. After Task 5b made napoli exempt from rule_11, this test started asserting `v.allowed is False` when the new code returns True.
- **Fix:** Changed the test's archetype to `ThesisArchetype.OPEN_GAME_FORMATIONS` (a non-napoli archetype). The test now correctly covers the general drift path while the new `test_rule_11_napoli_exemption_with_drifted_monitor` test covers the napoli exemption.
- **Files modified:** tests/evaluation/live/engine_v3/test_next_goal_and_drift.py
- **Commit:** 3ddfc09

## Test Coverage

Final suite run: **499 passed, 2 skipped** (engine_v3 suite) + **53 passed** (anti-Napoli regression).

The 2 skipped tests require `data/cache/ood_detector_v2_real.pkl` which is not tracked in the worktree (by design — the pkl is a generated artifact).

## Known Stubs

None — all five changes are complete and wired end-to-end.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary schema changes introduced. Shadow logging extends existing parquet schema with an `is_shadow` boolean column (additive, diagonal-relaxed compatible).

## Self-Check: PASSED

Commits verified in git log:
- a80d89b: fix(engine_v3/dual_write): drop suspended odds + drop-ambiguous market dedup
- b855104: feat(engine_v3/gate): suppress cruise_mode/goals MES dead-zone [2.5,4.0)
- 3e80e0b: feat(engine_v3/ood): trim OOD features + shadow-only rule_9 with broken-GSV sanity bound
- 7256bc2: feat(engine_v3/gate): shadow-only horizon-squashed rule_8 for HT GOALS theses
- 3ddfc09: feat(engine_v3): shadow dominant-team gap 0.025 + exempt napoli from rule_11 drift

Key files confirmed present:
- src/bip/evaluation/live/engine_v3/no_bet_gate.py (rule_12 + shadow paths + napoli exemption)
- src/bip/evaluation/live/engine_v3/ood_detector.py (14-feat FEATURE_NAMES + legacy path)
- src/bip/evaluation/live/engine_v3/mes.py (_squashed_goals_cvar helper)
- src/bip/evaluation/live/engine_v3/gsv.py (shadow_dominant_team_id field)
- src/bip/evaluation/live/engine_v3/gsv_builder.py (_MARKET_DOM_MIN_PROB_GAP_SHADOW compute)
