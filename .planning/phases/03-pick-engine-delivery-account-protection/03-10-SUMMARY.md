---
phase: 03-pick-engine-delivery-account-protection
plan: 10
subsystem: corners-gate
tags: [corners, gate, coverage, descope, polars, scripts]
dependency_graph:
  requires:
    - "Phase 02.1 P05: ParquetStore.read_results (3-level Hive partitioning)"
  provides:
    - "scripts/corners_gate_coverage.py: CORNERS-01 D-17b automated Polars coverage query"
    - "scripts/corners_gate_descope.py: CORNERS-01 D-18 conditional descope orchestration"
  affects:
    - ".planning/ROADMAP.md (Phase 6 Conditional entry -- when descope_flow runs on FAIL)"
    - ".planning/STATE.md (Blockers/Concerns -- when descope_flow runs on FAIL)"
tech_stack:
  added: []
  patterns:
    - "Atomic write via .md.tmp + Path.replace (PATTERNS.md §7)"
    - "Settings graceful fallback: CLI arg > env var > Settings() best-effort > default"
    - "subprocess mock via monkeypatch -- zero real git/gsd-sdk calls in tests"
key_files:
  created:
    - scripts/corners_gate_coverage.py
    - scripts/corners_gate_descope.py
  modified:
    - tests/scripts/test_corners_gate_coverage.py
    - tests/scripts/test_corners_gate_descope.py
decisions:
  - "Settings graceful fallback added to main() -- coverage script only reads Parquet, API/DB credentials not needed; ValidationError on missing .env should not block the gate check"
  - "descope_flow commit_descope uses --no-verify to match parallel executor convention"
metrics:
  duration: "4 minutes"
  completed_date: "2026-05-03"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
---

# Phase 03 Plan 10: CORNERS-01 Gate Automation Summary

**One-liner:** Polars coverage gate (D-17b) + conditional descope orchestrator (D-18) — both scripts implementation-ready; gate FAILS as expected per A5 (corner columns absent from 02.1 results).

## What Was Built

### Task 1: scripts/corners_gate_coverage.py (D-17b)

Automated coverage gate that reads from the Phase 02.1 results Parquet store via `ParquetStore.read_results`, filters `status='FT'` (specifics §199 — PST/CANC/ABD excluded from denominator), and aggregates per-league per-season coverage of `home_corners`/`away_corners`.

Key behaviors:
- **A5 fast path:** When `home_corners`/`away_corners` are absent from the Parquet schema (expected outcome), `coverage_pct=0` for all rows → gate FAILS with `SystemExit(1)`
- **Threshold logic:** Every league must have ≥3 seasons with ≥95% coverage to PASS
- **Atomic report:** Writes `scripts/corners_gate_coverage.md` via `.md.tmp + Path.replace` (PATTERNS.md §7)
- **PASS path:** Also writes `scripts/corners_gate_pass.md` marker when gate passes
- **Settings resilience:** `main()` resolves `parquet_base_path` via CLI arg → env var → `Settings()` best-effort → default `data/cache`; does not crash when `.env` is absent

End-to-end smoke run: exits 1 (FAIL) and writes `scripts/corners_gate_coverage.md` — correct per A5.

### Task 2: scripts/corners_gate_descope.py (D-18)

Conditional descope orchestrator. On FAIL produces three D-18 artifacts:

1. **(a) ROADMAP.md edit:** Calls `gsd-sdk query roadmap.move-phase --phase 6 --from Conditional --to v2-deferred`; falls back to in-file text replacement if CLI is absent or returns non-zero (A7 fallback)
2. **(b) STATE.md Blockers/Concerns entry:** Appended via atomic write with date + `--reason` text
3. **(c) git commit:** `docs(03): CORNERS-01 gate failed -- Phase 6 descoped`

On PASS (triggered with `--pass`): writes `scripts/corners_gate_pass.md` only; no ROADMAP/STATE mutation.

Both paths are idempotent and manually triggered (PATTERNS.md drift risk #20 — never a CI step).

## Tests

| File | Tests | Result |
|------|-------|--------|
| tests/scripts/test_corners_gate_coverage.py | 7 | GREEN |
| tests/scripts/test_corners_gate_descope.py | 4 | GREEN |
| **Total** | **11** | **GREEN** |

Coverage test breakdown: pass threshold, fail on 2/5 leagues, fail below 95%, fail on missing columns (A5), fail on empty table, FT-only filter (PST excluded), missing columns → zero coverage.

Descope test breakdown: three-artifact FAIL flow (ROADMAP+STATE+commit), PASS marker written, non-zero return on missing ROADMAP, main() --pass dispatch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Settings.ValidationError crashed main() without .env**
- **Found during:** Overall verification (`uv run python scripts/corners_gate_coverage.py`)
- **Issue:** `Settings()` requires `supabase_url`, `supabase_key`, `api_football_key`, `odds_api_key` — none present in the worktree; coverage script only reads Parquet and needs none of them
- **Fix:** `main()` now resolves `parquet_base_path` via: CLI `--parquet-base-path` arg > `PARQUET_BASE_PATH` env var > `Settings()` best-effort with try/except > default `"data/cache"`. Structured warning logged on fallback.
- **Files modified:** `scripts/corners_gate_coverage.py`
- **Commit:** `18fa780`

## Gate Outcome (End-to-End)

Script run: `uv run python scripts/corners_gate_coverage.py` → **exit 1 (FAIL)**

This is the **correct and expected outcome** per A5: Phase 02.1 P09 (`seed_historical.py`) seeds `home_goals`/`away_goals`/`status` but NOT `home_corners`/`away_corners`. The gate surfaces this deficit before Phase 6 engineering begins.

Generated artifact: `scripts/corners_gate_coverage.md` (5-league FAIL report).

## Known Stubs

None — both scripts are fully implementation-ready per Risk 6.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. Both scripts are local filesystem + subprocess only. STRIDE mitigations T-3-COV-01 through T-3-DESCOPE-04 all addressed in implementation (FT filter, atomic writes, step-gated descope_flow, gsd-sdk fallback, monkeypatched tests).

## Self-Check: PASSED

- `scripts/corners_gate_coverage.py` exists: YES
- `scripts/corners_gate_descope.py` exists: YES
- `tests/scripts/test_corners_gate_coverage.py` updated (Wave 0 skip removed): YES
- `tests/scripts/test_corners_gate_descope.py` updated (Wave 0 skip removed): YES
- Commit `6b897ab` (Task 1) exists: YES
- Commit `8f6f91b` (Task 2) exists: YES
- Commit `18fa780` (Rule 3 fix) exists: YES
- 11/11 tests GREEN: YES
- `scripts/corners_gate_coverage.md` written by smoke run: YES
