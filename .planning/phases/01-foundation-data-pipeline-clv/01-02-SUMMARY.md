---
phase: "01-foundation-data-pipeline-clv"
plan: 2
subsystem: test-infrastructure
tags: [tdd, wave-0, test-stubs, pytest, contracts]
dependency_graph:
  requires: []
  provides:
    - Wave 0 test stubs for all Phase 1 requirements
    - conftest.py shared fixtures (settings, league_registry, mock_client, sample_prediction)
    - pytest collection contract for RED phase
  affects:
    - Plans 03-07 (will make these tests GREEN)
    - Phase 1 Nyquist compliance (nyquist_compliant gate)
tech_stack:
  added: []
  patterns:
    - pytest class-based test organization
    - pytest-httpx HTTPXMock for async HTTP client tests
    - pytest.fixture with monkeypatch for settings isolation
    - setup_mock_chain helper for Supabase fluent API mock
key_files:
  created:
    - tests/conftest.py
    - tests/test_plugin_contract.py
    - tests/test_market_config.py
    - tests/test_league_registry.py
    - tests/test_repositories.py
    - tests/test_api_football_client.py
    - tests/test_parquet_store.py
    - tests/test_scheduler.py
    - tests/test_feature_pipeline.py
    - tests/test_clv_client.py
    - tests/test_clv_recorder.py
  modified: []
decisions:
  - "Test classes used (not standalone functions) per Football_analysis patterns from PATTERNS.md"
  - "conftest.py LEAGUES_DIR guarded with .exists() check so stubs work before Plan 01 creates the football config dir"
  - "sample_prediction fixture placed in conftest.py (not test_repositories.py) so it is accessible to test_market_config.py too"
  - "Threat T-02-01 mitigated: all env vars in conftest.py use placeholder strings, no real secrets"
metrics:
  duration: "12 minutes"
  completed: "2026-04-22"
  tasks_completed: 2
  files_created: 11
  test_functions: 53
---

# Phase 1 Plan 2: Wave 0 Test Stubs Summary

**One-liner:** 11 pytest stub files with 53 test functions covering every Phase 1 requirement (CORE-01 to CLV-04) in syntactically valid RED state before any implementation exists.

## What Was Built

Created the complete Wave 0 test contract for Phase 1. All 11 test files are syntactically valid Python. Tests will fail with `ImportError` until Plans 03-07 create the source modules — this is the expected RED state per TDD protocol.

### Test File Coverage

| File | Requirements | Test Functions |
|------|-------------|----------------|
| tests/conftest.py | shared fixtures | 4 fixtures + setup_mock_chain helper |
| tests/test_plugin_contract.py | CORE-01, CORE-04 | 9 |
| tests/test_market_config.py | CORE-05 | 5 |
| tests/test_league_registry.py | DATA-03 | 5 |
| tests/test_repositories.py | CLV-04 | 4 |
| tests/test_api_football_client.py | DATA-01 | 4 |
| tests/test_parquet_store.py | DATA-02 | 7 |
| tests/test_scheduler.py | DATA-04 | 4 |
| tests/test_feature_pipeline.py | DATA-05 | 3 |
| tests/test_clv_client.py | CLV-01 | 4 |
| tests/test_clv_recorder.py | CLV-02, CLV-03 | 8 |
| **Total** | **CORE-01 to CLV-04** | **53** |

Note: CORE-02 (no sport-specific imports in core/) is covered via test_market_config.py `test_core_types_has_no_market_enum` and will be verified by ruff check in later plans. CORE-03 (migration SQL) is manual-only per VALIDATION.md.

## Task Commits

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Core + repository test stubs (CORE-01 through CLV-04) | 9368f84 | conftest.py, test_plugin_contract.py, test_market_config.py, test_league_registry.py, test_repositories.py |
| 2 | Async client, scheduler, CLV, feature pipeline stubs | 5e8b16c | test_api_football_client.py, test_parquet_store.py, test_scheduler.py, test_feature_pipeline.py, test_clv_client.py, test_clv_recorder.py |

## Deviations from Plan

None — plan executed exactly as written.

One minor enhancement: the `tmp_leagues_dir` fixture in conftest.py uses `if LEAGUES_DIR.exists(): shutil.copytree(...)  else: leagues_dest.mkdir()` rather than the bare `shutil.copytree` from the plan's PATTERNS.md analog. This makes the stubs runnable even before Plan 01 creates the league config directory (Wave 1 parallel execution). This is a Rule 3 auto-fix (blocking issue: bare copytree would raise FileNotFoundError during pytest collection if Plan 01 hasn't merged yet).

## Security (Threat Model)

T-02-01 (Information Disclosure — test env vars): All env vars in conftest.py use placeholder strings ("test-supabase-key-12345", "test-api-football-key", "test-odds-api-key") — no real secrets committed.

T-02-02 (DoS — pytest-httpx): All HTTP tests use HTTPXMock; no real network calls made during test execution.

## Known Stubs

All 53 test functions are intentional stubs at this stage. They import source modules that do not exist yet — this is the expected Wave 0 RED state. Plans 03-07 will make them GREEN.

The following tests contain structural checks (inspect.getsource) that will only pass after source implementation exists:
- `test_clv_snapshot_job_registered_at_kickoff_plus_105min` — checks source for "105"
- `test_feature_matrix_has_computed_at` — checks FeatureMatrix.model_fields

## Threat Flags

No new security surface introduced. Test files only — no network endpoints, auth paths, or schema changes.

## Self-Check: PASSED

Files verified present:
- tests/conftest.py: FOUND
- tests/test_plugin_contract.py: FOUND
- tests/test_market_config.py: FOUND
- tests/test_league_registry.py: FOUND
- tests/test_repositories.py: FOUND
- tests/test_api_football_client.py: FOUND
- tests/test_parquet_store.py: FOUND
- tests/test_scheduler.py: FOUND
- tests/test_feature_pipeline.py: FOUND
- tests/test_clv_client.py: FOUND
- tests/test_clv_recorder.py: FOUND

Commits verified present:
- 9368f84: FOUND (test(01-02): add Wave 0 core and repository test stubs)
- 5e8b16c: FOUND (test(01-02): add Wave 0 async client, scheduler, CLV and feature pipeline test stubs)
