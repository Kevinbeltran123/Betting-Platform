---
phase: quick-260503-jkf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/bip/sports/__init__.py
  - src/bip/sports/football/plugin.py
  - src/bip/sports/football/features.py
  - src/bip/scheduler/orchestrator.py
  - src/bip/core/picks/engine.py
  - tests/scheduler/test_orchestrator.py
  - tests/test_feature_pipeline.py
  - tests/test_plugin_predict.py
autonomous: true
requirements:
  - G-CODE-01
  - G-CODE-02
  - G-CODE-03
  - G-MAINT-04
  - G-MAINT-08
  - G-MAINT-11
sub_strategy_3e: "Option A — extend FeatureMatrix with kickoff_utc/home_team/away_team (data already in scope at FeatureEngineer.build_features_for_fixture; parquet schema unaffected since to_parquet_row constructs columns explicitly from features dict)"

must_haves:
  truths:
    - "Orchestrator pipeline runs end-to-end without AttributeError on any SportPlugin method"
    - "FootballPlugin.get_opening_odds returns the 1X2 dict {'1','X','2'} for the configured bookmaker (Betano)"
    - "Orchestrator builds a complete Prediction Pydantic object with real home_team/away_team/league/sport/kickoff_utc/is_lineup_adjusted before invoking PickEngine.evaluate"
    - "PickRepository.get_pending_for_fixture is called WITHOUT await (it is sync), and returned dicts are accessed via p['market'] / p['status']"
    - "When a pending 1X2 pick already exists, T-30min skips engine.evaluate (D-01 dup-alert guard works against real data shapes)"
    - "Prediction rows persisted by FootballPlugin._write_prediction_rows have real home_team/away_team/kickoff_utc (not blank/computed_at)"
    - "PickEngine.evaluate signature is `prediction: Prediction` (not Any) so mypy catches future shape errors"
    - "Spec-based mocks (AsyncMock(spec=SportPlugin), Mock(spec=PickRepository)) prevent future 'method doesn't exist' bugs from being masked in tests"
  artifacts:
    - path: src/bip/sports/__init__.py
      provides: "SportPlugin.get_opening_odds abstract method + FeatureMatrix with kickoff_utc/home_team/away_team fields"
      contains: "get_opening_odds"
    - path: src/bip/sports/football/plugin.py
      provides: "FootballPlugin.get_opening_odds implementation + fixed _write_prediction_rows (real home_team/away_team/kickoff_utc)"
      contains: "async def get_opening_odds"
    - path: src/bip/sports/football/features.py
      provides: "FeatureEngineer threads fixture.kickoff_utc/home_team/away_team into FeatureMatrix"
    - path: src/bip/scheduler/orchestrator.py
      provides: "_run_pipeline builds full Prediction, fixes sync get_pending_for_fixture, removes type:ignore decorations"
    - path: src/bip/core/picks/engine.py
      provides: "evaluate(prediction: Prediction, opening_odds) — typed signature"
    - path: tests/scheduler/test_orchestrator.py
      provides: "spec-based mocks; new tests for ABC compliance, full Prediction build, dup-alert guard with sync repo"
  key_links:
    - from: src/bip/scheduler/orchestrator.py::_run_pipeline
      to: src/bip/sports/football/plugin.py::get_opening_odds
      via: "self.plugin.get_opening_odds(fixture.fixture_id) — must exist on ABC"
      pattern: "self\\.plugin\\.get_opening_odds"
    - from: src/bip/scheduler/orchestrator.py::_run_pipeline
      to: src/bip/core/picks/engine.py::evaluate
      via: "Prediction Pydantic object (not raw ProbabilityMap) + opening_odds dict"
      pattern: "Prediction\\(.*\\)\\s*\\n.*await self\\.pick_engine\\.evaluate"
    - from: src/bip/scheduler/orchestrator.py::_run_pipeline
      to: src/bip/core/storage/repositories.py::PickRepository.get_pending_for_fixture
      via: "sync call, no await; dict access via p['market']"
      pattern: "self\\.pick_repo\\.get_pending_for_fixture\\("
---

<objective>
Wire the production orchestrator so its pipeline matches the SportPlugin/PickEngine contracts that already exist. Today `_run_pipeline` calls `plugin.get_opening_odds(...)` (no such ABC method), `await self.pick_repo.get_pending_for_fixture(...)` (the method is sync), and feeds a raw ProbabilityMap into `pick_engine.evaluate(...)` even though the engine reads `prediction.home_team / .away_team / .league / .sport / .kickoff_utc / .is_lineup_adjusted`. AsyncMock-everywhere tests masked all five bugs. The first real run will throw AttributeError. This plan closes G-CODE-01/02/03 + G-MAINT-04/08/11 from `.planning/AUDIT-GAPS.md` using Strategy 2 (orchestrator constructs the Prediction; plugin.predict stays pure).

Purpose: unblock the only production caller of PickEngine. Without this, Phase 3 ships dead code.
Output: green test suite (≥265 passing), green new tests for ABC compliance + full-Prediction build + sync dup-alert guard, zero `# type: ignore[attr-defined]` in orchestrator, zero `AsyncMock()` desnudos for plugin/pick_repo.

**Sub-strategy chosen for 3e:** Option A — extend `FeatureMatrix` with `kickoff_utc/home_team/away_team`. The data is already in scope at `FeatureEngineer.build_features_for_fixture` (line 190, has `fixture: FixtureData`). `to_parquet_row` builds columns explicitly from the `features` dict and a small whitelist (fixture_id/sport/league/season/matchday/computed_at/feature_schema_version) — adding three model-level fields does not break the parquet schema. The five test-side `FeatureMatrix(...)` constructions get the new kwargs filled in from values already in the test fixture context.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/AUDIT-GAPS.md
@src/bip/sports/__init__.py
@src/bip/sports/football/plugin.py
@src/bip/sports/football/client.py
@src/bip/sports/football/features.py
@src/bip/scheduler/orchestrator.py
@src/bip/core/picks/engine.py
@src/bip/core/storage/models.py
@src/bip/core/storage/repositories.py
@tests/scheduler/test_orchestrator.py
@tests/picks/test_engine.py
@tests/test_feature_pipeline.py
@tests/test_plugin_predict.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from codebase. Do NOT explore — use these directly. -->

From src/bip/sports/__init__.py (current shape — task 1 extends FeatureMatrix and adds get_opening_odds to ABC):
```python
class FixtureData(BaseModel):
    fixture_id: int
    league: str
    sport: str
    home_team: str
    away_team: str
    kickoff_utc: datetime

class FeatureMatrix(BaseModel):
    fixture_id: int
    sport: str
    league: str
    computed_at: datetime
    features: dict[str, float]
    # ADD in task 1: kickoff_utc: datetime, home_team: str, away_team: str

class ProbabilityMap(BaseModel):
    fixture_id: int
    market: str
    probabilities: dict[str, float]
    model_version: str
    computed_at: datetime

class SportPlugin(abc.ABC):
    async def get_fixtures(self, date: datetime) -> list[FixtureData]: ...
    async def build_features(self, fixture: FixtureData) -> FeatureMatrix: ...
    async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap: ...
    async def build_claude_context(self, fixture: FixtureData) -> ClaudeContext: ...
    def get_available_markets(self) -> list[str]: ...
    # ADD in task 1: async def get_opening_odds(self, fixture_id: int) -> dict[str, float]
```

From src/bip/core/storage/models.py — Prediction (full field list orchestrator must populate):
```python
class Prediction(BaseModel):
    fixture_id: int
    league: str
    sport: str = "football"
    market: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    probabilities: dict
    model_version: str
    is_lineup_adjusted: bool = False
    is_shadow: bool = False
```

From src/bip/core/storage/repositories.py:169 (CONFIRMED SYNC — do NOT change to async):
```python
def get_pending_for_fixture(self, fixture_id: int) -> list[dict]:
    """Returns list of dicts (Supabase rows). Access via row['market'], row['status'], row['id']."""
```

From src/bip/sports/football/client.py:181 — already exists, fixture-id mode is what plugin will use:
```python
async def get_odds(self, fixture_id: int | None = None, league_id: int | None = None,
                   season: int | None = None, bookmaker: str = "Betano") -> dict:
    # Returns API-Football /odds JSON; bookmaker arg is INFORMATIONAL ONLY,
    # not sent to API — caller must filter response by bookmaker name.
    # Response shape: {"response": [{"bookmakers": [{"name": "Betano", "bets": [
    #   {"name": "Match Winner", "values": [{"value": "Home", "odd": "1.85"}, ...]}
    # ]}]}]}
```

From src/bip/core/picks/engine.py:82 — current signature (task 2 tightens prediction: Any -> Prediction):
```python
async def evaluate(self, prediction: Any, opening_odds: dict[str, Any]) -> Pick | None:
    # Reads: prediction.fixture_id, .market, .probabilities, .league, .sport,
    #        .home_team, .away_team, .kickoff_utc, .is_lineup_adjusted, .model_version, .id
```

From src/bip/scheduler/orchestrator.py:213-256 — _run_pipeline (current broken state — fully rewritten in task 2):
- line 224: `await self.plugin.build_features(fixture)` — return value IGNORED (G-CODE-03)
- line 229: `await self.pick_repo.get_pending_for_fixture(...)` — WRONG, sync method (G-CODE-02)
- line 231: `getattr(p, "market", None)` — WRONG, dicts not objects (G-CODE-02)
- line 242: `self.plugin.predict(fixture, market="1X2")` — WRONG arg, predict takes FeatureMatrix not FixtureData
- line 247: `self.plugin.get_opening_odds(...)` — method doesn't exist on ABC yet (G-CODE-01)
- line 250: `self.pick_engine.evaluate(prob_map, opening_odds)` — WRONG, engine expects Prediction not ProbabilityMap (G-MAINT-04)

From src/bip/sports/football/features.py:190 — FeatureMatrix construction in build_features_for_fixture (task 1 threads kickoff_utc/home_team/away_team here; `fixture: FixtureData` is in scope and has all three):
```python
return FeatureMatrix(
    fixture_id=fixture.fixture_id, sport=fixture.sport, league=fixture.league,
    computed_at=computed_at, features=features,
    # ADD: kickoff_utc=fixture.kickoff_utc, home_team=fixture.home_team, away_team=fixture.away_team
)
```

Existing FeatureMatrix(...) construction sites that will need new kwargs added:
- tests/test_feature_pipeline.py: lines 14, 34, 48, 78
- tests/test_plugin_predict.py: line 61
(All 5 sites already have access to kickoff/team values from test fixtures or can use sensible defaults.)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend ABC + FeatureMatrix + FootballPlugin (3a + 3e Option A) — TDD</name>
  <files>src/bip/sports/__init__.py, src/bip/sports/football/plugin.py, src/bip/sports/football/features.py, tests/test_feature_pipeline.py, tests/test_plugin_predict.py, tests/sports/football/test_plugin_get_opening_odds.py (NEW)</files>
  <behavior>
    Tests drive shape of new contract. Write/extend tests FIRST, watch RED, then implement GREEN.

    NEW test file `tests/sports/football/test_plugin_get_opening_odds.py`:
    - Test 1 (RED first): `test_get_opening_odds_returns_1x2_dict_for_betano` — mock `ApiFootballClient.get_odds(fixture_id=999)` to return a realistic API-Football /odds shape with Betano in bookmakers list and "Match Winner" bet with values `[{"value":"Home","odd":"1.85"}, {"value":"Draw","odd":"3.40"}, {"value":"Away","odd":"4.20"}]`. Assert plugin.get_opening_odds(999) returns `{"1":1.85, "X":3.40, "2":4.20}`.
    - Test 2: `test_get_opening_odds_returns_empty_dict_when_betano_missing` — response has only "Pinnacle" bookmaker → returns `{}` (graceful).
    - Test 3: `test_get_opening_odds_returns_empty_dict_when_no_match_winner_bet` — Betano present but only "Both Teams to Score" bet → returns `{}`.
    - Test 4: `test_get_opening_odds_returns_empty_dict_on_empty_response` — `{"response": []}` → returns `{}`.
    - Test 5: `test_get_opening_odds_calls_client_with_fixture_id` — assert get_odds called with `fixture_id=999, bookmaker="Betano"` (per-fixture mode, not bulk).

    EXTEND `tests/test_feature_pipeline.py` (4 sites) and `tests/test_plugin_predict.py` (1 site):
    - Add kwargs `kickoff_utc=<existing kickoff or sensible default>, home_team="Home FC", away_team="Away FC"` to every `FeatureMatrix(...)` call. Use the kickoff value already present in the test (e.g., the matching fixture's kickoff_utc); for tests without a fixture, use `datetime(2026,5,1,15,0,tzinfo=UTC)` and team names "Home FC"/"Away FC".
    - Tests must initially FAIL with `pydantic.ValidationError: missing kickoff_utc/home_team/away_team` once the model fields are added (RED), then GREEN once kwargs are filled in.
  </behavior>
  <action>
    **3a — Add `get_opening_odds` to ABC + FootballPlugin:**

    1. In `src/bip/sports/__init__.py`, add to `SportPlugin`:
       ```python
       @abc.abstractmethod
       async def get_opening_odds(self, fixture_id: int) -> dict[str, float]:
           """Return opening decimal odds for the fixture's primary 1X2 market.
           Shape: {"1": <home_odd>, "X": <draw_odd>, "2": <away_odd>}.
           Returns empty dict {} when the configured bookmaker has no coverage
           (caller is responsible for handling empty-dict gracefully — no exceptions
           are raised for coverage gaps; only network/API failures bubble up)."""
       ```

    2. In `src/bip/sports/football/plugin.py`, implement using existing client.get_odds (per-fixture mode):
       ```python
       _ODDS_VALUE_TO_KEY = {"Home": "1", "Draw": "X", "Away": "2"}

       async def get_opening_odds(self, fixture_id: int) -> dict[str, float]:
           """Fetch 1X2 opening odds from API-Football for the configured bookmaker."""
           bookmaker = "Betano"  # CLAUDE.md: Betano is the staking bookmaker
           async with ApiFootballClient(api_key=self._settings.api_football_key) as client:
               raw = await client.get_odds(fixture_id=fixture_id, bookmaker=bookmaker)
           response = raw.get("response", []) or []
           if not response:
               logger.info("get_opening_odds_no_response", fixture_id=fixture_id)
               return {}
           # Walk: response[0].bookmakers[?name==Betano].bets[?name=="Match Winner"].values
           for fixture_block in response:
               for bm in fixture_block.get("bookmakers", []) or []:
                   if bm.get("name") != bookmaker:
                       continue
                   for bet in bm.get("bets", []) or []:
                       if bet.get("name") != "Match Winner":
                           continue
                       odds: dict[str, float] = {}
                       for v in bet.get("values", []) or []:
                           key = _ODDS_VALUE_TO_KEY.get(v.get("value", ""))
                           if key is None:
                               continue
                           try:
                               odds[key] = float(v.get("odd"))
                           except (TypeError, ValueError):
                               continue
                       if {"1", "X", "2"}.issubset(odds.keys()):
                           return odds
           logger.info("get_opening_odds_no_betano_match_winner", fixture_id=fixture_id)
           return {}
       ```

    **3e Option A — Extend FeatureMatrix:**

    3. In `src/bip/sports/__init__.py`, extend FeatureMatrix:
       ```python
       class FeatureMatrix(BaseModel):
           fixture_id: int
           sport: str
           league: str
           computed_at: datetime
           features: dict[str, float]
           kickoff_utc: datetime  # NEW — sourced from FixtureData; needed by Prediction inserts
           home_team: str         # NEW — fixes G-MAINT-08/11 blank-team Prediction rows
           away_team: str         # NEW
       ```

    4. In `src/bip/sports/football/features.py:190`, thread fixture fields into FeatureMatrix construction:
       ```python
       return FeatureMatrix(
           fixture_id=fixture.fixture_id,
           sport=fixture.sport,
           league=fixture.league,
           computed_at=computed_at,
           features=features,
           kickoff_utc=fixture.kickoff_utc,
           home_team=fixture.home_team,
           away_team=fixture.away_team,
       )
       ```

    5. In `src/bip/sports/football/plugin.py:_write_prediction_rows`, fix both Prediction inserts (production at line 304-315 and shadow at line 327-338):
       - Replace `home_team=""` with `home_team=features.home_team`
       - Replace `away_team=""` with `away_team=features.away_team`
       - Replace `kickoff_utc=features.computed_at` with `kickoff_utc=features.kickoff_utc`

    6. Update the 5 test-side `FeatureMatrix(...)` calls per <behavior> spec.

    **Note:** Do NOT add the new fields to `to_parquet_row` columns — parquet schema stays unchanged (it builds columns explicitly from the `features` dict + a fixed whitelist). Verify by re-running `tests/test_feature_pipeline.py::test_to_parquet_row_includes_schema_version_v2` (must stay green).
  </action>
  <verify>
    <automated>uv run pytest tests/sports/football/test_plugin_get_opening_odds.py tests/test_feature_pipeline.py tests/test_plugin_predict.py -v</automated>
  </verify>
  <done>
    - SportPlugin ABC has `get_opening_odds` abstract method.
    - FootballPlugin.get_opening_odds returns `{"1","X","2"}` dict for Betano per-fixture mode; returns `{}` on coverage gaps; never raises on missing bookmaker / missing market.
    - FeatureMatrix has `kickoff_utc`, `home_team`, `away_team` fields.
    - FeatureEngineer.build_features_for_fixture populates them from `fixture: FixtureData`.
    - FootballPlugin._write_prediction_rows uses real values (no blanks, no computed_at as kickoff).
    - 5 NEW tests for get_opening_odds all pass.
    - All previously-existing tests in test_feature_pipeline.py + test_plugin_predict.py still pass after FeatureMatrix kwarg updates.
    - to_parquet_row test (`test_to_parquet_row_includes_schema_version_v2`) still passes — parquet schema unchanged.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rewire orchestrator + tighten engine type (3b + 3c + 3d) — TDD</name>
  <files>src/bip/scheduler/orchestrator.py, src/bip/core/picks/engine.py, tests/scheduler/test_orchestrator.py</files>
  <behavior>
    Tests drive the new wiring contract. Write/replace tests FIRST, watch RED on the wiring bugs, then implement GREEN.

    REWRITE existing tests in `tests/scheduler/test_orchestrator.py` and ADD three NEW tests:

    **Replace AsyncMock() desnudos with spec-based mocks (catches future ABC drift):**
    - All `MagicMock()` for plugin → `AsyncMock(spec=SportPlugin)` (import from `bip.sports`).
    - All `MagicMock()` for pick_repo → `Mock(spec=PickRepository)` (import from `bip.core.storage.repositories`). Configure each method explicitly: `pick_repo.get_pending_for_fixture = Mock(return_value=[...])` (SYNC, not AsyncMock).
    - All `MagicMock()` for pick_engine → keep MagicMock but explicitly: `pick_engine.evaluate = AsyncMock()` (engine.evaluate is genuinely async).

    **Update existing TestT30DupAlertGuard tests:**
    - `test_t30_skipped_when_t2h_pending`: change `pick_repo.get_pending_for_fixture = AsyncMock(return_value=[existing_pick])` → `Mock(return_value=[{"id": 42, "market": "1X2", "status": "pending"}])` (DICTS, not Mock objects with attributes — matches real return type). Also stub `plugin.build_features` to return a valid FeatureMatrix-like object (use `MagicMock(spec=FeatureMatrix)` with `.league = "premier_league"`).
    - `test_t30_proceeds_when_t2h_rejected`: dict shape `{"id": 43, "market": "1X2", "status": "rejected"}`.
    - `test_t30_proceeds_when_t2h_filtered`: empty list `[]`.
    - For tests that proceed past the guard: stub `plugin.build_features` to return a `FeatureMatrix`-shaped MagicMock with `.league`, `.fixture_id`, `.sport`; stub `plugin.predict` to return a `ProbabilityMap`-shaped MagicMock with `.probabilities = {"1": 0.5, "X": 0.3, "2": 0.2}` and `.model_version = "test-v1"`; stub `plugin.get_opening_odds` to return `{"1": 1.85, "X": 3.40, "2": 4.20}`.

    **NEW test 1: `test_pipeline_invokes_only_plugin_abc_methods`:**
    - Build orchestrator with `plugin = AsyncMock(spec=SportPlugin)`. Configure all ABC methods to return harmless values (build_features → MagicMock, predict → MagicMock with .probabilities + .model_version, get_opening_odds → `{"1":2.0,"X":3.0,"2":4.0}`). Stub pick_engine.evaluate as AsyncMock.
    - Call `await orch._run_pipeline(fixture, "t_minus_2h")` once.
    - Assert no `AttributeError` raised. Assert `plugin.get_opening_odds.assert_awaited_once_with(fixture.fixture_id)`. Assert `plugin.build_features.assert_awaited_once()`. Assert `plugin.predict.assert_awaited_once()`.

    **NEW test 2: `test_pipeline_builds_full_prediction`:**
    - Stub plugin to return known FeatureMatrix-shaped object (`.league="premier_league"`, `.fixture_id=999`, `.sport="football"`) from build_features; ProbabilityMap-shaped (`.probabilities={"1":0.5,"X":0.3,"2":0.2}`, `.model_version="ensemble-v3"`) from predict; `{"1":2.0,"X":3.0,"2":4.0}` from get_opening_odds.
    - Build fixture with `fixture_id=999, home_team="Arsenal", away_team="Chelsea", kickoff_utc=datetime(2026,5,1,15,0,tzinfo=UTC), league="premier_league", sport="football"`.
    - Stub `pick_engine.evaluate = AsyncMock()`.
    - Call `await orch._run_pipeline(fixture, "t_minus_30m")` (with `pick_repo.get_pending_for_fixture` returning `[]` so guard does not trigger).
    - Assert `pick_engine.evaluate.assert_awaited_once()`. Inspect the first call positional arg `prediction = pick_engine.evaluate.call_args.args[0]`.
    - Assert: `prediction.fixture_id == 999`, `prediction.home_team == "Arsenal"`, `prediction.away_team == "Chelsea"`, `prediction.league == "premier_league"`, `prediction.sport == "football"`, `prediction.kickoff_utc == datetime(2026,5,1,15,0,tzinfo=UTC)`, `prediction.market == "1X2"`, `prediction.model_version == "ensemble-v3"`, `prediction.probabilities == {"1":0.5,"X":0.3,"2":0.2}`, `prediction.is_lineup_adjusted is True` (because stage is t_minus_30m).
    - Assert: second positional arg `opening_odds == {"1":2.0,"X":3.0,"2":4.0}`.

    **NEW test 3: `test_dup_alert_guard_uses_sync_repo_and_dict_access`:**
    - `pick_repo = Mock(spec=PickRepository)`. `pick_repo.get_pending_for_fixture = Mock(return_value=[{"id": 42, "market": "1X2", "status": "pending"}])` — SYNC, returns list[dict].
    - Stub `plugin.build_features = AsyncMock(return_value=MagicMock(spec=FeatureMatrix))`.
    - Stub `pick_engine.evaluate = AsyncMock()`.
    - Call `await orch._run_pipeline(fixture, "t_minus_30m")`.
    - Assert `pick_repo.get_pending_for_fixture.assert_called_once_with(fixture.fixture_id)` (NOT awaited).
    - Assert `pick_engine.evaluate.assert_not_called()` (guard fired on dict access).
    - Assert `plugin.predict.assert_not_called()` (skipped after guard).
  </behavior>
  <action>
    **3d — Tighten engine signature (do this first to surface type errors at compile-check time):**

    1. In `src/bip/core/picks/engine.py`:
       - Add import: `from bip.core.storage.models import Prediction`
       - Change line 82 signature from `async def evaluate(self, prediction: Any, opening_odds: dict[str, Any])` → `async def evaluate(self, prediction: Prediction, opening_odds: dict[str, Any])`.
       - Leave the internal `prediction: Any` hints on `_persist_*` / `_build_*` helpers alone for now (they accept Prediction but downstream typing tightening is out of scope for this quick task).

    **3b + 3c — Rewrite `_run_pipeline`:**

    2. In `src/bip/scheduler/orchestrator.py`:
       - Add at module top: `from bip.core.storage.models import Prediction`
       - Add: `from bip.sports import FeatureMatrix, FixtureData, ProbabilityMap` (for type hints — keep `from bip.sports import SportPlugin` intact).
       - Replace the entire `_run_pipeline` body (lines 213-256) with Strategy 2 wiring:
         ```python
         async def _run_pipeline(self, fixture: FixtureData, stage: str) -> None:
             """Run prediction pipeline for a fixture at the specified stage.

             Strategy 2: orchestrator constructs the typed Prediction; plugin.predict()
             stays pure (returns ProbabilityMap). PickEngine.evaluate is the only entry
             point into the Pick lifecycle.

             D-01: T-30min skips evaluate when a pending 1X2 pick already exists for the
             fixture (prevents dup-alert from successful T-2h pick).
             """
             fixture_id = fixture.fixture_id
             logger.info("pipeline_started", fixture_id=fixture_id, stage=stage)
             try:
                 features = await self.plugin.build_features(fixture)

                 if self.pick_engine is None or stage not in ("t_minus_2h", "t_minus_30m"):
                     logger.info("pipeline_completed", fixture_id=fixture_id, stage=stage)
                     return

                 if stage == "t_minus_30m" and self.pick_repo is not None:
                     # D-01 dup-alert guard — repo method is SYNC, returns list[dict]
                     existing = self.pick_repo.get_pending_for_fixture(fixture_id)
                     blocking = [
                         p for p in existing
                         if p.get("market") == "1X2" and p.get("status") == PickStatus.pending.value
                     ]
                     if blocking:
                         logger.info(
                             "t30_skipped_pending_already",
                             fixture_id=fixture_id,
                             t2h_pick_id=blocking[0].get("id"),
                         )
                         return

                 prob_map = await self.plugin.predict(features, market="1X2")
                 if prob_map is None:
                     logger.info(
                         "pipeline_skip_evaluate_no_prediction",
                         fixture_id=fixture_id, stage=stage,
                     )
                     logger.info("pipeline_completed", fixture_id=fixture_id, stage=stage)
                     return

                 opening_odds = await self.plugin.get_opening_odds(fixture_id)

                 prediction = Prediction(
                     fixture_id=fixture_id,
                     league=features.league,
                     sport="football",
                     market="1X2",
                     home_team=fixture.home_team,
                     away_team=fixture.away_team,
                     kickoff_utc=fixture.kickoff_utc,
                     probabilities=prob_map.probabilities,
                     model_version=prob_map.model_version,
                     is_lineup_adjusted=(stage == "t_minus_30m"),
                 )

                 try:
                     await self.pick_engine.evaluate(prediction, opening_odds)
                 except Exception as exc:
                     logger.error(
                         "pipeline_evaluate_failed",
                         fixture_id=fixture_id, stage=stage, error=str(exc),
                     )

                 logger.info("pipeline_completed", fixture_id=fixture_id, stage=stage)
             except Exception as exc:
                 logger.error("pipeline_failed", fixture_id=fixture_id, stage=stage, error=str(exc))
         ```
       - **Critical:** retain the `# type: ignore[attr-defined]` decorations on OTHER methods (`_register_fixture_jobs`, `_record_clv`, `_reconcile_results`) that still use `fixture: object` — those are out of scope. Only `_run_pipeline` is being typed properly here. The acceptance criteria below says "removed from `_run_pipeline`," not from the entire file.
       - Note `PickStatus.pending.value` — repo returns Supabase row dicts where status is a string ("pending"), not a PickStatus enum.

    3. Implement test changes per <behavior> spec. Imports for spec-based mocks:
       ```python
       from unittest.mock import AsyncMock, MagicMock, Mock
       from bip.sports import SportPlugin, FeatureMatrix, FixtureData, ProbabilityMap
       from bip.core.storage.repositories import PickRepository
       from bip.core.storage.models import Prediction
       ```
  </action>
  <verify>
    <automated>uv run pytest tests/scheduler/ tests/picks/ -v</automated>
  </verify>
  <done>
    - `_run_pipeline` builds `Prediction` from `features` + `fixture` + `prob_map` + `opening_odds`.
    - `pick_repo.get_pending_for_fixture` called WITHOUT await (sync); status comparison uses string `PickStatus.pending.value`, not the enum.
    - `pick_engine.evaluate` receives a typed `Prediction` Pydantic object as first arg.
    - `engine.py` signature is `prediction: Prediction`.
    - Try/except wraps `pick_engine.evaluate` with structured `pipeline_evaluate_failed` log.
    - `# type: ignore[attr-defined]` decorations REMOVED from `_run_pipeline` body (other methods may keep theirs — out of scope).
    - All AsyncMock() desnudos for plugin/pick_repo in `tests/scheduler/test_orchestrator.py` replaced with `AsyncMock(spec=SportPlugin)` / `Mock(spec=PickRepository)`.
    - 3 NEW tests pass: `test_pipeline_invokes_only_plugin_abc_methods`, `test_pipeline_builds_full_prediction`, `test_dup_alert_guard_uses_sync_repo_and_dict_access`.
    - All existing scheduler + picks tests still pass.
  </done>
</task>

<task type="auto">
  <name>Task 3: Full-suite green check + grep guards</name>
  <files>(verification only — no source changes expected)</files>
  <action>
    Run full suite and grep guards. If anything fails, debug and fix in the appropriate task above (do not patch in this task — go back).

    1. `uv run pytest -q` — must show ≥265 passing, 0 failed.
    2. `grep -n "type: ignore\[attr-defined\]" src/bip/scheduler/orchestrator.py` — entries inside `_run_pipeline` body must be gone (entries in `_register_fixture_jobs`, `_record_clv`, `_reconcile_results`, `_send_recovered_pick` may remain — those are out of scope).
    3. `grep -n "AsyncMock()" tests/scheduler/test_orchestrator.py` — any remaining bare `AsyncMock()` calls must be on `pick_engine.evaluate` only (which is genuinely async). All plugin/pick_repo bare AsyncMocks must be replaced with `spec=` variants.
    4. `grep -rn "PickEngine(" src/` — should find at least one production caller path. Currently the engine is instantiated only by app composition root; document the wiring location in the SUMMARY. The orchestrator still receives `pick_engine` via constructor injection — confirm that hasn't regressed.
    5. `grep -n "await self.pick_repo.get_pending_for_fixture" src/bip/scheduler/orchestrator.py` — must return EMPTY (the await is bug G-CODE-02; sync call only).
    6. `grep -n "self.plugin.predict(fixture" src/bip/scheduler/orchestrator.py` — must return EMPTY (predict takes FeatureMatrix not FixtureData).
  </action>
  <verify>
    <automated>uv run pytest -q && echo "---" && grep -c "type: ignore\[attr-defined\]" src/bip/scheduler/orchestrator.py | head -1 && echo "---" && grep -n "AsyncMock()" tests/scheduler/test_orchestrator.py | grep -v "pick_engine.evaluate" || echo "OK: no bare AsyncMock for plugin/pick_repo"</automated>
  </verify>
  <done>
    - `uv run pytest -q` reports ≥265 passing, 0 failed.
    - `_run_pipeline` body has zero `type: ignore[attr-defined]` decorations.
    - No bare `AsyncMock()` in `tests/scheduler/test_orchestrator.py` for plugin or pick_repo (only pick_engine.evaluate may use bare AsyncMock).
    - `await self.pick_repo.get_pending_for_fixture` and `self.plugin.predict(fixture` patterns return empty grep.
    - Audit gaps G-CODE-01, G-CODE-02, G-CODE-03, G-MAINT-04, G-MAINT-08, G-MAINT-11 closed.
  </done>
</task>

</tasks>

<verification>
- All 265+ existing tests remain green: `uv run pytest -q`
- Targeted suites green: `uv run pytest tests/scheduler/ tests/sports/ tests/picks/ -v`
- AUDIT-GAPS.md gaps G-CODE-01/02/03 + G-MAINT-04/08/11 closed (verified by code grep + new test coverage).
- No `AsyncMock()` bare for plugin/pick_repo in scheduler tests (spec-based mocks installed).
- `_run_pipeline` body free of `type: ignore[attr-defined]`.
</verification>

<success_criteria>
- ≥265 tests passing, 0 failed.
- `FootballPlugin.get_opening_odds(fixture_id)` returns `{"1","X","2"}` for Betano, `{}` on coverage gaps.
- `_run_pipeline` builds a fully-populated `Prediction` (real home/away/league/kickoff_utc, `is_lineup_adjusted=True` at t_minus_30m) and passes it to `pick_engine.evaluate(prediction, opening_odds)`.
- `pick_repo.get_pending_for_fixture` called sync; dict-shaped row access via `p.get("market")` / `p.get("status")` matches `PickStatus.pending.value` string.
- `engine.evaluate` signature is `prediction: Prediction` (no longer `Any`).
- `FootballPlugin._write_prediction_rows` writes real `home_team`/`away_team`/`kickoff_utc` (no blanks, no `computed_at` masquerading as kickoff).
- AsyncMock-spec drift bug class eliminated for the two highest-leverage interfaces (SportPlugin, PickRepository).
- Three new orchestrator tests document the contract: ABC compliance, full Prediction build, sync dup-alert guard with dict access.
</success_criteria>

<output>
After completion, create `.planning/quick/260503-jkf-orchestrator-plugin-engine-wiring-predic/260503-jkf-SUMMARY.md` documenting:
- Strategy chosen (Strategy 2 — orchestrator builds Prediction, plugin.predict stays pure).
- Sub-strategy for 3e (Option A — extended FeatureMatrix).
- Six gaps closed (G-CODE-01/02/03 + G-MAINT-04/08/11).
- Test count delta (before / after).
- Any deferred follow-ups (e.g., engine internal helpers still typed as `Any` — out of scope here).
- Note on `PickEngine(` wiring — confirm the production composition root that instantiates it (or flag as next-step if still TBD).
</output>
