---
phase: 1
slug: foundation-data-pipeline-clv
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` section |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~20 seconds |

**Required pyproject.toml config:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| CORE-01 | `SportPlugin` ABC has all required abstract methods | unit | `uv run pytest tests/test_plugin_contract.py -x` | ❌ W0 | ⬜ pending |
| CORE-02 | `core/` imports have zero sport-specific references | static/lint | `uv run ruff check src/bip/core/` | ❌ W0 | ⬜ pending |
| CORE-03 | Migration 002 SQL applies without error | manual | Manual — apply via Supabase dashboard/CLI | N/A | ⬜ pending |
| CORE-04 | `FootballPlugin` implements all `SportPlugin` methods | unit | `uv run pytest tests/test_plugin_contract.py -x` | ❌ W0 | ⬜ pending |
| CORE-05 | Markets loaded from YAML, not imported from enum | unit | `uv run pytest tests/test_market_config.py -x` | ❌ W0 | ⬜ pending |
| DATA-01 | `ApiFootballClient.get_fixtures()` retries on 429 | unit (mocked) | `uv run pytest tests/test_api_football_client.py -x` | ❌ W0 | ⬜ pending |
| DATA-02 | `FeatureParquetStore.write_features()` creates correct 4-level Hive dirs | unit | `uv run pytest tests/test_parquet_store.py -x` | ❌ W0 | ⬜ pending |
| DATA-03 | `LeagueRegistry` loads all 5 leagues from YAML | unit | `uv run pytest tests/test_league_registry.py -x` | ❌ W0 | ⬜ pending |
| DATA-04 | `AsyncIOScheduler` registers DateTrigger jobs for T-2h and T-30min | unit | `uv run pytest tests/test_scheduler.py -x` | ❌ W0 | ⬜ pending |
| DATA-05 | Feature matrix `computed_at` <= prediction time for all features | integration | `uv run pytest tests/test_feature_pipeline.py::test_no_future_data_leakage -x` | ❌ W0 | ⬜ pending |
| CLV-01 | `OddsApiClient.fetch_pinnacle_closing_odds()` returns Pinnacle odds | unit (mocked) | `uv run pytest tests/test_clv_client.py -x` | ❌ W0 | ⬜ pending |
| CLV-02 | `clv_percentage = (odds_at_pick / closing_odds - 1) * 100` | unit | `uv run pytest tests/test_clv_recorder.py -x` | ❌ W0 | ⬜ pending |
| CLV-03 | Rolling 50-pick average CLV calculation | unit | `uv run pytest tests/test_clv_recorder.py::test_rolling_average -x` | ❌ W0 | ⬜ pending |
| CLV-04 | `PerformanceMetric.to_supabase_dict()` includes `sport` field | unit | `uv run pytest tests/test_repositories.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`
- [ ] `tests/conftest.py` — shared fixtures (ported + extended from Football_analysis)
- [ ] `tests/test_plugin_contract.py` — CORE-01, CORE-04 ABC contract tests
- [ ] `tests/test_market_config.py` — CORE-05 YAML market config tests
- [ ] `tests/test_api_football_client.py` — DATA-01 retry/rate-limit tests (httpx mock)
- [ ] `tests/test_parquet_store.py` — DATA-02 4-level Hive partition tests (ported + extended)
- [ ] `tests/test_league_registry.py` — DATA-03 YAML loader tests (ported)
- [ ] `tests/test_scheduler.py` — DATA-04 APScheduler DateTrigger tests
- [ ] `tests/test_feature_pipeline.py` — DATA-05 point-in-time correctness test
- [ ] `tests/test_clv_client.py` — CLV-01 Odds API client tests (httpx mock)
- [ ] `tests/test_clv_recorder.py` — CLV-02, CLV-03 calculation + rolling average tests
- [ ] `tests/test_repositories.py` — CLV-04 sport field serialization tests (ported + extended)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 002 applies to live Supabase | CORE-03 | Requires live Supabase connection; no test DB in Phase 1 | Run `supabase db push` or apply SQL via dashboard; verify `sport` column exists on all 6 tables |
| Pinnacle closing odds actually available for all 5 leagues | CLV-01 | Requires live Odds API call; coverage is assumed | Fetch odds for a recent completed match in each league; confirm Pinnacle bookmaker appears in response |
| APScheduler actually fires at T-2h and T-30min for a real fixture | DATA-04 | Time-based triggers hard to test deterministically | Manual observation: run orchestrator with a fixture 3h away, watch job registration and firing in logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
