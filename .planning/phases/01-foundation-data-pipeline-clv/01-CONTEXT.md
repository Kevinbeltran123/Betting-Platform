# Phase 1: Foundation + Data Pipeline + CLV - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the working foundation: sport-agnostic plugin architecture (`core/` + `SportPlugin` ABC), async data ingestion from API-Football, Supabase migration 002 (adds `sport` column to all 6 tables), Hive-partitioned Parquet feature store, APScheduler-driven pre-kickoff pipeline, and CLV recording against Pinnacle closing lines via The Odds API.

New capabilities belong in later phases: ML ensemble (Phase 2), pick engine/Telegram/Claude validation (Phase 3), production orchestration (Phase 4).

</domain>

<decisions>
## Implementation Decisions

### D-01: Code Migration Strategy
- **D-01**: Copy Football_analysis source files into the new repo and adapt in-place. Do NOT use a local editable dependency.
  - Copy: `src/football_betting/storage/models.py`, `repositories.py`, `supabase_client.py`, `shared/types.py`, `config/settings.py`, `config/league_config.py`, `config/league_registry.py`, league YAML configs (5 files), Supabase migration SQL.
  - Rename package namespace from `football_betting` → new platform package name (e.g., `bip` or `betting_intelligence`).
  - Add `sport: str = "football"` field to all 6 Pydantic models in the same commit as the copy — this IS migration 002 at the Python level.
  - Football_analysis is retired once the new platform is green on the same Supabase instance.
  - Rationale: all 6 files require structural changes (sport column, namespace rename, settings expansion) — cross-repo editable dep fights every CORE-0x requirement.

### D-02: SportPlugin ABC Design
- **D-02a**: `SportPlugin` defined as an ABC (`abc.ABC` + `@abstractmethod`) in `sports/__init__.py` (as specified in CORE-01). Not a `typing.Protocol`.
- **D-02b**: All return types are typed Pydantic `BaseModel` subclasses — no `dict` or `Any` returns at the plugin boundary. The EV engine in `core/` calls `prob_map.probabilities["1"]` (or iterates keys), not raw dict unpacking.
- **D-02c**: `ProbabilityMap` is **sport-agnostic from day 1** — structure:
  ```python
  class ProbabilityMap(BaseModel):
      fixture_id: int
      market: str       # e.g., "1X2", "btts", "ou_2.5"
      probabilities: dict[str, float]  # keys: outcome names (e.g., "1", "X", "2", "yes", "no")
      model_version: str
      computed_at: datetime
  ```
  Football fills `probabilities` with `{"1": 0.45, "X": 0.28, "2": 0.27}`. Tennis would fill `{"H": 0.60, "A": 0.40}`. EV engine iterates over keys — zero sport-specific code in `core/`.
- **D-02d**: `FixtureData`, `FeatureMatrix`, and `ClaudeContext` are similarly typed Pydantic models returned by `get_fixtures()`, `build_features()`, and `build_claude_context()` respectively. Exact field definitions are Claude's discretion — they must conform to what the football plugin produces and what `core/` consumes.
- **D-02e**: Interface contract tests in Phase 1 (`tests/test_plugin_contract.py`) verify the football plugin satisfies the ABC and that `ProbabilityMap` validates correctly.

### D-03: APScheduler Job Strategy
- **D-03a**: **Per-fixture DateTrigger jobs** — the daily orchestrator (CronTrigger at 06:00 UTC) fetches today's fixtures and calls `scheduler.add_job()` for each fixture, creating two jobs per fixture: one at `kickoff - 2h` and one at `kickoff - 30min`.
- **D-03b**: **Auto-recovery on startup** — on scheduler start, check if today's jobs have been registered (e.g., query existing jobs or check a daily-run flag). If missing AND current time is between 06:00 UTC and last fixture kickoff of the day, immediately re-run the orchestrator to re-schedule jobs for fixtures not yet kicked off. This handles VPS restart without manual intervention.
- **D-03c**: MemoryJobStore is fine — no persistence needed. Jobs are regenerated daily from the fixture list.
- **D-03d**: Uses `AsyncIOScheduler` (not `BackgroundScheduler`) because the Telegram bot and API clients are async.

### D-04: CLV Snapshot Timing
- **D-04a**: **Fixed-delay: kickoff + 105 minutes**. A `DateTrigger` job is registered at fixture-fetch time (same orchestrator that registers pre-kickoff jobs). This is the primary CLV snapshot.
- **D-04b**: **Nightly reconciliation at 03:00 UTC** — a `CronTrigger` job queries `clv_records` for rows where `pinnacle_closing_odds IS NULL` and re-fetches those via The Odds API. Covers extra-time edge cases. Costs at most 1-2 additional API requests per night.
- **D-04c**: The `odds_fetched_at` timestamp is logged alongside `pinnacle_closing_odds` in `clv_records` (already required by CLV-01 for data-freshness validation).
- **D-04d**: Polling eliminated — request budget math: 7 polls/match × 75 matches/month = 525 requests, exceeds 500-request Rookie tier.

### Claude's Discretion
- Exact Pydantic field names for `FixtureData`, `FeatureMatrix`, `ClaudeContext` return types (must be consistent with football plugin outputs and `core/` consumers).
- New platform package name (`bip`, `betting_intelligence`, or similar).
- Exact directory layout within `src/` (Claude should follow the pattern from Football_analysis: `src/{package}/core/`, `src/{package}/sports/football/`, etc.).
- Whether `Settings` class is extended in-place or split into `CoreSettings` + sport-specific overrides.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Code to Port
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/storage/models.py` — 6 Pydantic storage models to copy and extend with `sport` field
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/storage/repositories.py` — Repository pattern to copy and extend
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/storage/supabase_client.py` — Supabase client factory to copy
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/config/settings.py` — pydantic-settings config to extend (add API-Football key, The Odds API key, Telegram token)
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/config/league_config.py` — League config Pydantic models to copy
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/config/league_registry.py` — League registry to copy
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/shared/types.py` — Market, League, PickStatus enums to port into `core/`
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/shared/errors.py` — Error types to port
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/config/leagues/` — 5 league YAML configs to copy (API-Football IDs, edge thresholds)
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/supabase/migrations/20260323000000_initial_schema.sql` — Existing schema; migration 002 ADDs `sport VARCHAR(20) NOT NULL DEFAULT 'football'` to all 6 tables

### Existing Code to Reference (not copy)
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/storage/parquet_store.py` — Existing Parquet store (reference; Phase 1 extends with Hive partitioning by `sport/league/season/matchday`)

### Requirements (locked)
- `.planning/REQUIREMENTS.md` §CORE-01 through CORE-05 — Plugin architecture requirements
- `.planning/REQUIREMENTS.md` §DATA-01 through DATA-05 — Data pipeline requirements
- `.planning/REQUIREMENTS.md` §CLV-01 through CLV-04 — CLV recording requirements

### Tech Stack Constraints
- `CLAUDE.md` §Technology Stack — Full version matrix (APScheduler 3.11.x NOT 4.x, XGBoost 3.x, Python 3.12, etc.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Football_analysis/storage/models.py` — 6 clean Pydantic v2 `BaseModel` subclasses with `to_supabase_dict()` methods; ready to copy with `sport: str = "football"` addition
- `Football_analysis/storage/repositories.py` — Typed repository classes (`PredictionRepository`, `PickRepository`, etc.) using `@dataclass` + `supabase.Client`; copy and parameterize with `sport` column in queries
- `Football_analysis/config/league_config.py` — Rich Pydantic models for league config (`ApiMappings`, `SeasonStructure`, `ModelParams`); already has `api_football_league_id` and per-market edge thresholds
- `Football_analysis/shared/types.py` — `Market` (5 markets), `League` (5 leagues), `PickStatus`, `CalibrationMethod` enums — move to `core/` and extend

### Established Patterns
- `pydantic-settings` + `.env` for config (copy `Settings` pattern, extend with new API keys)
- `@dataclass` for repository classes (dependency injection via `client: Client`)
- `to_supabase_dict()` method on every storage model (standardized serialization)
- YAML-based league config with Pydantic validation at load time

### Integration Points
- Supabase migration 002 must ADD `sport` column to all 6 existing tables (not recreate them); existing Football_analysis data remains valid with `sport = 'football'` default
- New async API-Football client (DATA-01 requires `httpx` + `tenacity`) connects to the Parquet feature store and then to Supabase via the ported repositories
- APScheduler `AsyncIOScheduler` wraps the async data client and prediction pipeline; Telegram bot (Phase 3) will share the same event loop

</code_context>

<specifics>
## Specific Ideas

- `ProbabilityMap.probabilities` uses string keys like `"1"`, `"X"`, `"2"` for 1X2 market (matching API-Football and Betano market terminology) rather than `"home_win"` etc. — keeps it closest to the raw odds format.
- The nightly reconciliation job (D-04b) should be a simple `SELECT pick_id, fixture_id FROM clv_records WHERE pinnacle_closing_odds IS NULL AND created_at < now() - interval '2 hours'` — keeps it targeted, avoids re-fetching already-recorded CLV.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope.

</deferred>

---

*Phase: 01-foundation-data-pipeline-clv*
*Context gathered: 2026-04-22*
