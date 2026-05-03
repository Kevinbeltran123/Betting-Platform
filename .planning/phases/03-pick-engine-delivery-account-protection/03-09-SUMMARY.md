---
phase: 03-pick-engine-delivery-account-protection
plan: 9
subsystem: corners-gate
tags: [corners, gate, manual-probe, documentation, d-17a]
dependency_graph:
  requires: [03-00]
  provides: [CORNERS-01-manual-half]
  affects: [03-10, phase-06]
tech_stack:
  added: []
  patterns: [plain-markdown-no-yaml]
key_files:
  created:
    - scripts/corners_gate_probe.md
    - scripts/corners_gate_findings.md
  modified:
    - tests/scripts/test_corners_gate_artifacts.py
decisions:
  - "Plain Markdown chosen over YAML front-matter for gate files (Open Question #5) — files are read by Kevin and coverage report; YAML adds no value"
metrics:
  duration: 2min
  completed: "2026-05-03"
  tasks_completed: 3
  files_changed: 3
---

# Phase 3 Plan 9: CORNERS-01 Manual Gate Probe Summary

**One-liner:** CORNERS-01 manual gate probe checklist and findings template delivered as plain Markdown co-located with the automated gate scripts in `scripts/`.

## What Was Built

Two plain Markdown files that form the manual half (D-17a) of the CORNERS-01 gate:

- `scripts/corners_gate_probe.md` — checklist Kevin executes against Betano live UI. Covers 5 leagues x 3-5 fixtures each; per-fixture capture items (markets, naming convention, odds range, min stake, screenshot); gate decision block referencing D-17 and D-18.

- `scripts/corners_gate_findings.md` — hand-fillable template paired with the probe. 5-league table layout with columns for all required data points; Part A Gate Decision block with PASS/FAIL checkboxes; next-step instructions routing to either `corners_gate_coverage.py` (PASS) or `corners_gate_descope.py --part a` (FAIL).

Wave 0 stub in `tests/scripts/test_corners_gate_artifacts.py` converted to 10 GREEN structural tests validating both artifact files.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write corners_gate_probe.md | 9d77c61 | scripts/corners_gate_probe.md |
| 2 | Write corners_gate_findings.md | c6104a4 | scripts/corners_gate_findings.md |
| 3 | Convert Wave 0 stub to GREEN tests | a99aaeb | tests/scripts/test_corners_gate_artifacts.py |

## Deviations from Plan

None — plan executed exactly as written.

Note: plan acceptance criteria cited 9 structural tests; implementation produced 10 (an extra `test_probe_md_exists` was present in the spec). All 10 pass.

## TDD Gate Compliance

Task 3 was marked `tdd="true"`. The Wave 0 stub with `NotImplementedError` and `pytest.mark.skip` served as the RED gate (committed in a prior wave). The GREEN gate commit is `a99aaeb`. No separate RED commit was needed in this plan since the RED artifact was pre-existing.

## Known Stubs

`corners_gate_findings.md` contains intentional fill-in placeholders (`_(fill)_`) throughout. These are not code stubs — they are the designed template structure Kevin fills during the manual probe. The file ships unfilled by design; filling it is the human action that resolves CORNERS-01.

## Threat Flags

No new threat surface introduced. Both files are static Markdown documentation with no network endpoints, auth paths, or schema changes.

The threat register from the plan (T-3-PROBE-01 through T-3-PROBE-03) was reviewed:
- T-3-PROBE-01 (Repudiation): mitigated — findings template includes Screenshot column per fixture and probe checklist includes screenshot step.
- T-3-PROBE-02 (Info Disclosure): accepted — manual discipline, not enforceable in code.
- T-3-PROBE-03 (Tampering): accepted — honour-system; structural test cannot verify semantic content.

## Self-Check: PASSED
