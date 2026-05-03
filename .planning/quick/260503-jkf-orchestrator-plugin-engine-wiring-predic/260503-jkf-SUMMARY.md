---
quick_id: 260503-jkf
description: Orchestrator/Plugin/Engine wiring (Strategy 2 — Prediction in orchestrator)
status: complete
date: 2026-05-03
strategy: Strategy 2 (orchestrator builds full Prediction; plugin.predict stays ProbabilityMap-pure)
audit_gaps_closed:
  - G-CODE-01  # get_opening_odds added to ABC + FootballPlugin
  - G-CODE-02  # await on sync get_pending_for_fixture removed; dict access fixed
  - G-CODE-03  # build_features return now captured; predict receives FeatureMatrix
  - G-MAINT-04 # ProbabilityMap -> Prediction shape mismatch resolved via orchestrator-built Prediction
  - G-MAINT-08 # kickoff_utc no longer set to features.computed_at
  - G-MAINT-11 # home_team/away_team blanks resolved via FeatureMatrix extension
commits:
  - 7c9ad62: feat(quick-260503-jkf-01) — extend SportPlugin ABC + FeatureMatrix + FootballPlugin
  - 1484f76: feat(quick-260503-jkf-02) — rewire orchestrator pipeline + tighten engine signature
  - e68df0e: chore — merge quick task worktree (260503-jkf orchestrator wiring)
tests:
  baseline: 265
  final: 273
  delta: +8 (5 get_opening_odds + 3 orchestrator wiring)
---

# Quick Task 260503-jkf — Orchestrator/Plugin/Engine Wiring

## Outcome

Closed 6 audit gaps from `.planning/AUDIT-GAPS.md` that together prevented the
orchestrator from running end-to-end. Before this task, every test in
`tests/scheduler/test_orchestrator.py` used bare `AsyncMock()` patches that
hid three structural bugs from production. The first real run of
`scripts/smoke_e2e_pick.py` would have crashed in cascade.

## Strategy

**Strategy 2 (chosen by user):** Orchestrator constructs a complete `Prediction`
Pydantic object before invoking `engine.evaluate(prediction, opening_odds)`.
`plugin.predict()` stays returning a pure `ProbabilityMap` (no fixture context
mixed in). Engine accepts a typed `Prediction` (no more `Any`).

## Tasks Executed

### Task 1 — ABC + FeatureMatrix + plugin Prediction inserts (commit `7c9ad62`)

- **`src/bip/sports/__init__.py`**: added abstract method `get_opening_odds(fixture_id) -> dict[str, float]`. Extended `FeatureMatrix` with `kickoff_utc: datetime`, `home_team: str`, `away_team: str` (Option A from plan).
- **`src/bip/sports/football/plugin.py`**: implemented `get_opening_odds` using existing `ApiFootballClient.get_odds(fixture_id=...)`. Parses Betano (configurable bookmaker) 1X2 odds; returns `{}` on coverage gap (graceful, orchestrator handles).
- **`src/bip/sports/football/features.py`**: `FeatureEngineer.build_features_for_fixture` now populates `kickoff_utc`, `home_team`, `away_team` from the fixture context (data was already in scope; no extra API calls).
- **`src/bip/sports/football/plugin.py:_write_prediction_rows`**: `kickoff_utc` and team names now sourced from `features.kickoff_utc/home_team/away_team` instead of the wrong `features.computed_at` and blank strings.
- New test file: `tests/sports/football/test_plugin_get_opening_odds.py` (5 tests).

### Task 2 — Orchestrator rewrite + engine type tightening (commit `1484f76`)

- **`src/bip/scheduler/orchestrator.py:_run_pipeline`**:
  - `features = await self.plugin.build_features(fixture)` — retorno capturado.
  - `prob_map = await self.plugin.predict(features, market="1X2")` — pasa features (no fixture).
  - `opening_odds = await self.plugin.get_opening_odds(fixture.fixture_id)`.
  - Construye `Prediction(...)` Pydantic completo con todos los campos del modelo.
  - Pasa `prediction` tipado a `engine.evaluate(prediction, opening_odds)`.
  - Removió `# type: ignore[attr-defined]` del cuerpo de `_run_pipeline` (4 quedan en métodos OUT-OF-SCOPE: `_register_fixture_jobs`, `_record_clv`, `_reconcile_results` — los toca Step 4).
- **`src/bip/scheduler/orchestrator.py:229-239`**: `pick_repo.get_pending_for_fixture` ahora se llama síncronamente (sin `await`) y se accede via `p.get("market")` / `p.get("status")` (dict access).
- **`src/bip/core/picks/engine.py:65`**: firma de `evaluate` ahora `prediction: Prediction` (no `Any`).
- **`tests/scheduler/test_orchestrator.py`**: 3 nuevos tests:
  - `test_pipeline_invokes_only_plugin_abc_methods`: usa `AsyncMock(spec=SportPlugin)` — falla si el orchestrator llama un método inexistente.
  - `test_pipeline_builds_full_prediction`: verifica que el `Prediction` pasado al engine tiene todos los campos esperados.
  - `test_dup_alert_guard_skips_when_pending_pick_exists`: seed un pick pending → engine.evaluate NO se llama en t_minus_30m.
- Reemplazados todos los `AsyncMock()` desnudos para `plugin`/`pick_repo` por `AsyncMock(spec=SportPlugin)` y `Mock(spec=PickRepository)`.

### Task 3 — Verification + grep guards

- Full suite: `uv run pytest -q` → **273 passed, 0 failed** (baseline 265 → +8).
- Targeted: `tests/scheduler/ tests/sports/ tests/picks/` → 66 passed.
- All grep guards pass:
  - `_run_pipeline` body: 0 `type: ignore[attr-defined]` (4 fuera de scope).
  - `AsyncMock()` desnudos para plugin/pick_repo en scheduler tests: 0.
  - `await self.pick_repo.get_pending_for_fixture`: 0.
  - `self.plugin.predict(fixture`: 0.

## Auto-Fixed Deviations

- **Rule 1 — `tests/test_plugin_contract.py`**: extendido para incluir `get_opening_odds` en el set de métodos ABC esperados (la ABC creció de 5 a 6 métodos por design del plan).

## Pre-Existing Environmental Note

Worktree `.venv` faltaba `pytest-asyncio` + `pytest-httpx`. Resuelto con
`uv sync --extra dev` (one-time, sin lockfile changes). Documentado para
futuras spawns de worktrees.

## Files Modified

```
src/bip/core/picks/engine.py                          |   4 +-
src/bip/scheduler/orchestrator.py                     | 101 +++++----
src/bip/sports/__init__.py                            |  17 ++
src/bip/sports/football/features.py                   |   3 +
src/bip/sports/football/plugin.py                     |  65 +++++-
tests/scheduler/test_orchestrator.py                  | 227 +++++++++++++++++----
tests/sports/__init__.py                              |   0
tests/sports/football/__init__.py                     |   0
tests/sports/football/test_plugin_get_opening_odds.py | 175 ++++++++++++++++
tests/test_feature_pipeline.py                        |  12 ++
tests/test_plugin_contract.py                         |   3 +-
tests/test_plugin_predict.py                          |   3 +
12 files changed, 519 insertions(+), 91 deletions(-)
```

## What's Still Open (Step 4 of parent plan)

The orchestrator still calls `_record_clv` as a logging-only stub. Next quick
task wires `ClvRecorder` + `OddsApiClient` into the constructor and implements
the actual CLV recording (using the vig-removed math from Step 1 of the parent
plan). The 4 remaining `type: ignore[attr-defined]` in `_record_clv` /
`_reconcile_results` will fall when Step 4 lands.

## Note on SUMMARY.md Recovery

This SUMMARY was regenerated from the executor's structured report after the
worktree was removed before its uncommitted SUMMARY could be rescued. The
content matches the executor's verification output exactly; commit hashes,
test counts, and gap closures were copied verbatim. Future quick task merges
should follow the workflow's "rescue uncommitted SUMMARY.md" safety net.
