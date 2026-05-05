---
phase: 04
plan: 07
status: complete
completed: 2026-05-04
tasks_total: 3
tasks_done: 3
files_modified: 1
files_created: 1
checkpoint: human-action (deferred — operator runs SMOKE_TEST.md when staging VPS provisioned)
---

# Plan 04-07 — ROADMAP reconciliation + staging smoke runbook

## What was built

ROADMAP.md Phase 4 §Success Criteria #1 and #2 now reflect the locked CONTEXT.md `<reconciliations>` decisions: SC#1 is the weekly model-CLV drift check spec (with feature/odds drift deferred to v2); SC#2 is the `claude_failure_mode` feature flag spec. SC#3-#5 also enriched with implementation specifics (Type=notify, RPC migration 005, ops channel cooldown). `deploy/SMOKE_TEST.md` is the 137-line operator runbook with 8 numbered checks (each with explicit expected output) covering all 4 Wave 6 threat mitigations.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | Apply ROADMAP SC#1+SC#2 reconciliation patch | Imprecise wording removed; reconciled text matches CONTEXT.md verbatim. |
| 2 | Create deploy/SMOKE_TEST.md | 8 numbered checks; every threat (T-4-02/04/05/06) covered; auto-restart + host-reboot optional sections. 137 lines. |
| 3 | Operator runs smoke test on staging VPS | **DEFERRED** — operator-only action requires real Hetzner VPS provisioning. The runbook is shipped; the actual exercise is the operator's gate before `/gsd-verify-work`. |

## Key deviations

- **Task 3 marked deferred-not-failed**: this plan was `autonomous: false` because the staging exercise requires an operator. Per the orchestrator's "push straight through" choice, the SMOKE_TEST.md FILE is shipped now; the on-VPS run is logged in 04-VALIDATION.md as `4-07-03 ⬜ pending` for the operator to execute when staging is available.

## Verification

```
$ grep -c "weekly model-CLV drift" .planning/ROADMAP.md
1

$ grep -c "claude_failure_mode" .planning/ROADMAP.md
1

$ grep -c "Feature drift (KS test) and odds drift are explicitly deferred" .planning/ROADMAP.md
1

$ grep -c "instead of failing\|CLV recording is deferred" .planning/ROADMAP.md
0   # imprecise wording removed

$ grep -c "### Check [1-8]:" deploy/SMOKE_TEST.md
8

$ grep -cE "T-4-02|T-4-04|T-4-05|T-4-06" deploy/SMOKE_TEST.md
6
```

## Self-Check: PASSED

- [x] ROADMAP SC#1 + SC#2 wording matches CONTEXT.md `<reconciliations>` verbatim
- [x] SMOKE_TEST.md exists with 8 numbered checks + explicit expected output
- [x] All threat-model criteria represented in smoke test
- [x] Operator-staging task documented as deferred-pending in 04-VALIDATION.md row 4-07-03
