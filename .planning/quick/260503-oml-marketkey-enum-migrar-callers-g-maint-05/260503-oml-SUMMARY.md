---
phase: 260503-oml
plan: 01
subsystem: core/types + picks/engine + clv/client + scheduler/orchestrator + sports/football/plugin
tags: [refactor, types, market-key, enum, g-maint-05, audit-gap-closure]
requires:
  - bip.core.types (StrEnum baseline)
  - bip.train.backtest.EDGE_THRESHOLD_PCT (still the per-market fallback)
  - bip.sports.football.config.league_registry.LeagueRegistry (per-league thresholds)
provides:
  - bip.core.types.MarketKey: canonical market identifier with from_str/to_odds_api/to_threshold_attr
  - Single source of truth for market normalization across engine, clv/client, orchestrator
affects:
  - PickEngine.evaluate (threshold lookup now goes via MarketKey.to_threshold_attr)
  - OddsApiClient.map_market_key (delegates to MarketKey.from_str + to_odds_api)
  - PipelineOrchestrator (4 call-sites: dup-alert guard, predict, Prediction build, CLV pending filter, fetch_pinnacle market_key, clv_recorder.record market arg, reconcile market filter)
  - FootballPlugin.predict (signature widened to str | MarketKey for self-documentation)
tech-stack:
  added: []
  patterns:
    - StrEnum-as-canonical-key (single class, three derived views: YAML key, Odds API key, ModelParams attr)
    - Boundary normalization (orchestrator wraps raw DB market strings in MarketKey.from_str so legacy "1X2" rows AND canonical "onextwo" rows are both recognized at query-time)
key-files:
  created:
    - tests/test_market_key.py (10 unit tests)
  modified:
    - src/bip/core/types.py (+78 lines: MarketKey enum + 3 helper methods)
    - src/bip/core/picks/engine.py (-12 / +5: deleted _NORMALIZE_MARKET dict, replaced with MarketKey.from_str + to_threshold_attr)
    - src/bip/clv/client.py (-7 / +9: deleted MARKET_KEY_MAP dict, map_market_key now delegates to MarketKey)
    - src/bip/scheduler/orchestrator.py (4 call-sites migrated: guards normalize via MarketKey.from_str, persistence uses MarketKey.ONEXTWO, CLV market_key uses MarketKey.ONEXTWO.to_odds_api())
    - src/bip/sports/football/plugin.py (+1 import, predict() signature widened to str | MarketKey)
    - tests/scheduler/test_orchestrator.py (1-line assertion: prediction.market == "onextwo" instead of "1X2", reflecting canonical persistence)
decisions:
  - Canonical = lowercase YAML key (markets.yaml `key:` field). MarketKey.value mirrors it 1:1 — no schema migration needed.
  - ModelParams.edge_threshold_1x2 attribute name preserved (Python identifier, not a market string). MarketKey.to_threshold_attr() bridges via a single special-case (ONEXTWO -> "edge_threshold_1x2"); all other members compose with f"edge_threshold_{self.value}".
  - markets.yaml left untouched. The enum's value is downstream from the YAML, not the other way around.
  - StrEnum chosen over plain Enum so existing Pydantic `str` fields (Prediction.market, Pick.market) accept enum values without schema/serialization changes. JSON serialization persists as the canonical string value.
  - CORNERS uses "" empty-string sentinel from to_odds_api(); OddsApiClient.map_market_key converts "" to None at the boundary so the public None contract for unknown OR unsupported keys is preserved.
  - Orchestrator filter sites (dup-alert guard, CLV pending filter, reconcile) wrap raw DB market strings in MarketKey.from_str so both legacy "1X2" rows AND new canonical "onextwo" rows are recognized — backwards-compatible read path.
metrics:
  duration_minutes: 17
  completed_at: 2026-05-03T23:05:29Z
  tasks: 2
  files_modified: 6
  files_created: 1
  commits: 3
  test_count_before: 282
  test_count_after: 292
  new_tests: 10
---

# Quick Task 260503-oml: MarketKey Enum + Migrate Callers (G-MAINT-05) Summary

Replace the magic-string mess for 1X2/onextwo/h2h across `src/bip/` with a typed `MarketKey` StrEnum living in `bip.core.types`. Eliminate the defensive `_NORMALIZE_MARKET` dict in `engine.py` (parche from quick-260503-j74) and the `MARKET_KEY_MAP` dict in `clv/client.py`. Single canonical type, three derived views.

## Self-Check: PASSED

## What changed

- **New enum `MarketKey`** in `src/bip/core/types.py`: 5 members (`ONEXTWO/BTTS/OU/AH/CORNERS`) matching `markets.yaml` keys exactly, plus three helpers:
  - `from_str(raw)`: case- and whitespace-insensitive alias resolution (1X2/h2h -> ONEXTWO; totals/over_under -> OU; alternate_spreads/asian_handicap -> AH); `ValueError` with raw input embedded on miss.
  - `to_odds_api()`: returns The Odds API market key (CORNERS -> `""` sentinel).
  - `to_threshold_attr()`: bridges to `ModelParams.edge_threshold_<x>` attribute name; preserves `edge_threshold_1x2` legacy spelling.
- **PickEngine.evaluate** (`src/bip/core/picks/engine.py`): `_NORMALIZE_MARKET` dict deleted; threshold lookup now `getattr(model_params, MarketKey.from_str(market).to_threshold_attr(), EDGE_THRESHOLD_PCT)` inside a `try / except (KeyError, ValueError)` so unknown leagues OR unknown market aliases both fall back to the backtest default.
- **OddsApiClient.map_market_key** (`src/bip/clv/client.py`): `MARKET_KEY_MAP` dict deleted; method now delegates to `MarketKey.from_str(internal).to_odds_api()`, returning `None` for both unknown keys and CORNERS (preserved public contract).
- **PipelineOrchestrator** (`src/bip/scheduler/orchestrator.py`): four call-sites migrated.
  - Dup-alert guard (`_run_pipeline` t_minus_30m): wraps raw `p.get("market")` in `MarketKey.from_str` so legacy "1X2" rows AND canonical "onextwo" rows both block.
  - `plugin.predict(features, market=MarketKey.ONEXTWO)` — was the literal "1X2".
  - `Prediction(..., market=MarketKey.ONEXTWO, ...)` — DB persistence now writes the canonical "onextwo" key.
  - CLV pending filter (`_record_clv`): same `MarketKey.from_str` wrapping for read-path compatibility.
  - `fetch_pinnacle_closing_odds(..., market_key=MarketKey.ONEXTWO.to_odds_api())` — self-documenting.
  - `clv_recorder.record(..., market=MarketKey.ONEXTWO, ...)`.
  - Reconcile loop: `MarketKey.from_str(raw) != MarketKey.ONEXTWO -> continue`.
- **FootballPlugin.predict** (`src/bip/sports/football/plugin.py`): signature widened to `market: str | MarketKey` (StrEnum-compatible, purely documentation; body unchanged).
- **Test fixture update**: a single line in `tests/scheduler/test_orchestrator.py::TestPipelineABCCompliance::test_pipeline_builds_full_prediction` updated from `prediction.market == "1X2"` to `prediction.market == "onextwo"` to reflect the canonical persistence contract. All other test fixtures using `"1X2"` continue to pass because the orchestrator's filter sites normalize via `MarketKey.from_str`.

## Why these design choices

- **Canonical = lowercase YAML key**: `markets.yaml` is the existing source of truth. Making the enum's `.value` mirror it 1:1 means no schema migration, no DB rewrite, and no breaking change to downstream consumers (Pydantic `Prediction.market: str`, `Pick.market: str`).
- **`ModelParams.edge_threshold_1x2` preserved**: the field name is a Python identifier — the `1x2` spelling is a Pydantic attribute, not a market string. Renaming would cascade through every YAML league config. `to_threshold_attr()` absorbs the asymmetry in one place.
- **StrEnum, not plain Enum**: `MarketKey.ONEXTWO == "onextwo"` is `True`, so existing `str` fields and JSON serialization continue to work unchanged. New rows persist as `"onextwo"`; old `"1X2"` rows are still recognized at query-time via `MarketKey.from_str`.
- **`""` sentinel for CORNERS in `to_odds_api()`**: keeps the enum total (every member has a mapping). The clv/client boundary converts `""` to `None`, so the public None contract for "unsupported by The Odds API" is preserved unchanged.

## Verification numbers (before / after)

| Check | Before | After |
|------|--------|-------|
| Tests passing | 282 | 292 |
| `_NORMALIZE_MARKET` occurrences in `src/bip/` | 1 dict (8 entries + helper) | 0 |
| `MARKET_KEY_MAP` occurrences in `src/bip/` | 1 dict (4 entries) | 0 |
| `MarketKey` imports in `src/bip/` | 0 files | 5 files (types, engine, clv/client, orchestrator, plugin) |
| Magic-string count `'1X2' \| 'onextwo' \| 'h2h'` in `src/bip/` | ~30 (across engine + orchestrator + clv/client) | 10 (residuals: enum self-definition, migration comments, API-Football H2H endpoint param, canonical YAML) |
| `markets.yaml` diff | n/a | empty |
| `league_config.py` diff (ModelParams) | n/a | empty |

## Commits

- `2a9663f` test(260503-oml): add failing tests for MarketKey enum (RED gate)
- `acba05e` feat(260503-oml): MarketKey StrEnum with from_str/to_odds_api/to_threshold_attr (G-MAINT-05) (GREEN gate)
- `(this commit)` refactor(260503-oml): migrate callers to MarketKey enum; delete _NORMALIZE_MARKET + MARKET_KEY_MAP parches (G-MAINT-05) (REFACTOR gate)

## Deviations from Plan

None. Plan executed exactly as written:

- 10 RED tests written and failing first (ImportError on `MarketKey`).
- 10 GREEN tests passing after enum implementation; full suite 292/292.
- 4 callers migrated; 2 parche dicts deleted; 1 test assertion updated (explicitly authorized in plan).
- 3 commits in TDD-gate order (test -> feat -> refactor); no Co-Authored-By trailers; no emojis.
- YAML and ModelParams untouched (verified via `git diff` empty).

## Audit Gap Closure

- **G-MAINT-05** (canonical market type) — closed. Single `MarketKey` enum is now the only authoritative source of market keys; all four runtime call-sites import and use it; the `_NORMALIZE_MARKET` parche introduced by quick-260503-j74 is removed.

## Known Stubs

None introduced. The enum + helpers are fully wired; no placeholder data flows.
