---
phase: 260503-oml
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_market_key.py
  - src/bip/core/types.py
  - src/bip/core/picks/engine.py
  - src/bip/clv/client.py
  - src/bip/scheduler/orchestrator.py
  - src/bip/sports/football/plugin.py
autonomous: true
requirements: [G-MAINT-05]
must_haves:
  truths:
    - "MarketKey StrEnum exists in bip.core.types with ONEXTWO/BTTS/OU/AH/CORNERS members"
    - "MarketKey.from_str accepts 1X2, onextwo, h2h aliases (case/whitespace insensitive) and raises ValueError on unknown"
    - "MarketKey.to_odds_api maps ONEXTWO->h2h, OU->totals, AH->alternate_spreads, CORNERS->''"
    - "MarketKey.to_threshold_attr returns edge_threshold_1x2 for ONEXTWO and edge_threshold_<value> for others"
    - "PickEngine no longer references _NORMALIZE_MARKET dict; it normalizes via MarketKey.from_str"
    - "OddsApiClient.map_market_key delegates to MarketKey.from_str(internal).to_odds_api()"
    - "Existing 282 tests remain green; new test_market_key.py adds 8+ passing tests"
    - "StrEnum compatibility preserved: MarketKey.ONEXTWO == 'onextwo' is True"
  artifacts:
    - path: "tests/test_market_key.py"
      provides: "Unit tests for MarketKey enum (RED-first TDD)"
      min_lines: 60
    - path: "src/bip/core/types.py"
      provides: "MarketKey StrEnum with from_str/to_odds_api/to_threshold_attr"
      contains: "class MarketKey"
    - path: "src/bip/core/picks/engine.py"
      provides: "PickEngine using MarketKey for threshold lookup"
      contains: "MarketKey.from_str"
    - path: "src/bip/clv/client.py"
      provides: "OddsApiClient.map_market_key delegating to MarketKey"
      contains: "MarketKey"
    - path: "src/bip/scheduler/orchestrator.py"
      provides: "Orchestrator using MarketKey for canonical market identifiers"
      contains: "MarketKey"
    - path: "src/bip/sports/football/plugin.py"
      provides: "Plugin imports MarketKey (StrEnum compat for predict() arg)"
      contains: "MarketKey"
  key_links:
    - from: "src/bip/core/picks/engine.py"
      to: "bip.core.types.MarketKey"
      via: "import + MarketKey.from_str(prediction.market).to_threshold_attr()"
      pattern: "MarketKey\\.from_str"
    - from: "src/bip/clv/client.py"
      to: "bip.core.types.MarketKey"
      via: "map_market_key delegates to MarketKey.from_str(internal).to_odds_api()"
      pattern: "MarketKey\\.from_str"
    - from: "tests/test_market_key.py"
      to: "bip.core.types.MarketKey"
      via: "Direct enum coverage"
      pattern: "from bip\\.core\\.types import MarketKey"
---

<objective>
Replace the magic-string mess for 1X2/onextwo/h2h/1x2 across src/bip/ with a typed
`MarketKey` StrEnum living in `src/bip/core/types.py`. Eliminate the defensive
`_NORMALIZE_MARKET` dict in engine.py (parche from quick-260503-j74) and the
`MARKET_KEY_MAP` dict in clv/client.py by routing both through the new enum.

Purpose: G-MAINT-05 closure — one canonical type, three derived views (canonical
YAML key, The Odds API key, ModelParams attribute suffix). Prevents future
`market == "1X2"` vs `market == "onextwo"` bugs without breaking the existing
Pydantic str fields (StrEnum guarantees `MarketKey.ONEXTWO == "onextwo"`).

Output:
- `tests/test_market_key.py` (new, 8+ tests)
- `MarketKey` enum added to `src/bip/core/types.py`
- 4 callers migrated (engine, clv/client, orchestrator, plugin)
- `_NORMALIZE_MARKET` dict deleted; `MARKET_KEY_MAP` deleted
- All 282 existing tests still green; total ~290+ pass.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/AUDIT-GAPS.md
@src/bip/core/types.py
@src/bip/core/picks/engine.py
@src/bip/clv/client.py
@src/bip/scheduler/orchestrator.py
@src/bip/sports/football/plugin.py
@src/bip/sports/football/config/markets.yaml
@src/bip/sports/football/config/league_config.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from current codebase. -->

From src/bip/core/types.py (current state — extend, don't replace):
```python
from enum import StrEnum

class League(StrEnum): ...
class PickStatus(StrEnum): ...
class CalibrationMethod(StrEnum): ...
class AggregationPeriod(StrEnum): ...
```

From src/bip/sports/football/config/league_config.py (DO NOT modify — bridge via to_threshold_attr):
```python
class ModelParams(BaseModel):
    edge_threshold_btts: float = 0.05
    edge_threshold_ah: float = 0.06
    edge_threshold_ou: float = 0.05
    edge_threshold_1x2: float = 0.08          # <-- "1x2" identifier, not market string
    edge_threshold_corners: float = 0.07
```

From src/bip/sports/football/config/markets.yaml (DO NOT modify — canonical keys):
```yaml
markets:
  - key: "btts"      odds_api_key: "btts"
  - key: "ou"        odds_api_key: "totals"
  - key: "onextwo"   odds_api_key: "h2h"
  - key: "ah"        odds_api_key: "alternate_spreads"
  - key: "corners"   odds_api_key: null
```

From src/bip/core/picks/engine.py (current parche to remove):
```python
_NORMALIZE_MARKET = {
    "1X2": "1x2", "onextwo": "1x2", "h2h": "1x2",
    "BTTS": "btts", "OU": "ou", "AH": "ah", "CORNERS": "corners",
}
# ...
market_normalized = _NORMALIZE_MARKET.get(market, market.lower())
threshold = getattr(league_cfg.model_params, f"edge_threshold_{market_normalized}", EDGE_THRESHOLD_PCT)
```

From src/bip/clv/client.py (current parche to remove):
```python
MARKET_KEY_MAP: dict[str, str] = {
    "onextwo": "h2h", "btts": "btts", "ou": "totals", "ah": "alternate_spreads",
}
def map_market_key(self, internal_key: str) -> str | None:
    return MARKET_KEY_MAP.get(internal_key)
```

From src/bip/scheduler/orchestrator.py (sites using "1X2" / "onextwo"):
- line 247: `if p.get("market") == "1X2"`  (D-01 dup-alert guard)
- line 257: `await self.plugin.predict(features, market="1X2")`
- line 272: `Prediction(..., market="1X2", ...)`
- line 328: `pending_1x2 = [p for p in pending if p.get("market") == "1X2"]`
- line 410: `market="onextwo",`  (clv_recorder.record call — already canonical)
- line 516: `if pick.get("market") != "1X2": continue`

From src/bip/sports/football/plugin.py (sites using market strings):
- line 183: `async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap`
- The `market` arg is opaque string passed through to ProbabilityMap. StrEnum
  compatibility means callers can pass `MarketKey.ONEXTWO` OR `"1X2"` and the
  string survives. Plugin only needs an import + light type-hint update; no
  behavioral change.
</interfaces>

<critical_constraints>
- DO NOT modify markets.yaml — "onextwo" is the canonical key the enum's value
  matches.
- DO NOT modify ModelParams field names — `edge_threshold_1x2` is a Python
  identifier; the bridge is `MarketKey.to_threshold_attr()`.
- DO NOT change Pydantic field types — `Prediction.market: str` and
  `Pick.market: str` stay as `str`. StrEnum values serialize as their string
  value, so writes still produce "onextwo" (or "1X2" if a caller still passes
  that — both compare equal to the enum).
- DO NOT touch selection keys ("1"/"X"/"2", "yes"/"no", "over"/"under") inside
  probabilities/odds dicts — different concern.
- DO NOT add Co-Authored-By trailers to commits.
- DO NOT use emojis in code/comments/SUMMARY.
</critical_constraints>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TDD — define MarketKey enum and unit tests (Stage 1 + Stage 2)</name>
  <files>tests/test_market_key.py, src/bip/core/types.py</files>
  <behavior>
    RED first — write all 8 tests in tests/test_market_key.py BEFORE adding the
    enum. Run pytest, confirm tests fail with ImportError or AttributeError on
    MarketKey. Then implement MarketKey in src/bip/core/types.py and confirm
    GREEN.

    Required tests (one assertion focus each):
    1. test_marketkey_is_strenum — `isinstance(MarketKey.ONEXTWO, str)` is True;
       `MarketKey.ONEXTWO == "onextwo"` is True.
    2. test_marketkey_members_match_yaml — values are exactly
       {"onextwo","btts","ou","ah","corners"} (matches markets.yaml keys).
    3. test_from_str_canonical — `MarketKey.from_str("onextwo")` returns
       `MarketKey.ONEXTWO`; same for "btts","ou","ah","corners".
    4. test_from_str_aliases_1x2 — `MarketKey.from_str("1X2")`,
       `MarketKey.from_str("1x2")`, and `MarketKey.from_str("h2h")` all return
       `MarketKey.ONEXTWO`. Confirms case-insensitive + alias handling.
    5. test_from_str_ou_ah_aliases — `from_str("totals")` -> OU,
       `from_str("over_under")` -> OU, `from_str("alternate_spreads")` -> AH,
       `from_str("asian_handicap")` -> AH.
    6. test_from_str_whitespace_insensitive — `from_str("  ONEXTWO  ")` returns
       `MarketKey.ONEXTWO`.
    7. test_from_str_rejects_unknown — `from_str("garbage")` raises ValueError
       with the raw input present in the message.
    8. test_to_odds_api_mapping — ONEXTWO->"h2h", BTTS->"btts", OU->"totals",
       AH->"alternate_spreads", CORNERS->"" (empty string sentinel for
       unsupported markets — clv/client.map_market_key still returns None for
       CORNERS via a separate guard).
    9. test_to_threshold_attr — ONEXTWO -> "edge_threshold_1x2";
       BTTS -> "edge_threshold_btts"; OU -> "edge_threshold_ou";
       AH -> "edge_threshold_ah"; CORNERS -> "edge_threshold_corners".
    10. test_json_serialization — `json.dumps({"market": MarketKey.ONEXTWO})`
        produces `'{"market": "onextwo"}'` (StrEnum serializes as string value).
  </behavior>
  <action>
    Step 1 (RED): Create `tests/test_market_key.py` with 10 tests above. Each
    test imports `from bip.core.types import MarketKey`. Run
    `uv run pytest tests/test_market_key.py -v` — MUST fail with ImportError or
    AttributeError on MarketKey. Commit the failing test:
    `test(260503-oml): add failing tests for MarketKey enum`.

    Step 2 (GREEN): Append `MarketKey` to `src/bip/core/types.py` after the
    existing enums. Use the full implementation from the task brief:

    ```python
    class MarketKey(StrEnum):
        """Canonical market identifier. String-valued for backwards compat with
        YAML keys.

        The canonical key is the lowercase YAML form (matches markets.yaml).
        Aliases used by external systems (The Odds API "h2h", legacy "1X2") are
        mapped via `MarketKey.from_str` and `MarketKey.to_odds_api`.

        Alias matrix:
          ONEXTWO   <- "1x2", "1X2", "onextwo", "h2h"
          BTTS      <- "btts"
          OU        <- "ou", "totals", "over_under"
          AH        <- "ah", "alternate_spreads", "asian_handicap"
          CORNERS   <- "corners"
        """
        ONEXTWO = "onextwo"
        BTTS = "btts"
        OU = "ou"
        AH = "ah"
        CORNERS = "corners"

        @classmethod
        def from_str(cls, raw: str) -> "MarketKey":
            normalized = raw.lower().strip()
            aliases = {
                "1x2": cls.ONEXTWO, "onextwo": cls.ONEXTWO, "h2h": cls.ONEXTWO,
                "btts": cls.BTTS,
                "ou": cls.OU, "totals": cls.OU, "over_under": cls.OU,
                "ah": cls.AH, "alternate_spreads": cls.AH,
                "asian_handicap": cls.AH,
                "corners": cls.CORNERS,
            }
            if normalized in aliases:
                return aliases[normalized]
            raise ValueError(f"Unknown market key: {raw!r}")

        def to_odds_api(self) -> str:
            mapping = {
                MarketKey.ONEXTWO: "h2h",
                MarketKey.BTTS: "btts",
                MarketKey.OU: "totals",
                MarketKey.AH: "alternate_spreads",
                MarketKey.CORNERS: "",
            }
            return mapping[self]

        def to_threshold_attr(self) -> str:
            if self == MarketKey.ONEXTWO:
                return "edge_threshold_1x2"
            return f"edge_threshold_{self.value}"
    ```

    Run `uv run pytest tests/test_market_key.py -v` — MUST be 10/10 GREEN.
    Then run `uv run pytest -q` to confirm no regression in the full suite.
    Commit: `feat(260503-oml): MarketKey StrEnum with from_str/to_odds_api/to_threshold_attr (G-MAINT-05)`.

    DO NOT touch any caller in this task. Migration is Task 2.
  </action>
  <verify>
    <automated>uv run pytest tests/test_market_key.py -v && uv run pytest -q</automated>
  </verify>
  <done>
    - tests/test_market_key.py exists with 10 tests, all passing.
    - MarketKey class exists in src/bip/core/types.py with from_str,
      to_odds_api, to_threshold_attr.
    - StrEnum compat verified: `MarketKey.ONEXTWO == "onextwo"` is True.
    - Full pytest suite still GREEN (no regressions).
    - Two commits landed: failing-tests then implementation.
  </done>
</task>

<task type="auto">
  <name>Task 2: Migrate callers + delete parches (Stages 3 + 4)</name>
  <files>src/bip/core/picks/engine.py, src/bip/clv/client.py, src/bip/scheduler/orchestrator.py, src/bip/sports/football/plugin.py</files>
  <action>
    Migrate the four call-sites to MarketKey, one boundary at a time. After each
    file edit, run `uv run pytest -q` to catch regressions early. Final commit
    after all four files are clean and tests are GREEN.

    --- A. src/bip/core/picks/engine.py ---
    1. Add import: `from bip.core.types import MarketKey, PickStatus`.
    2. DELETE the `_NORMALIZE_MARKET = {...}` dict (lines ~50-60) and its
       comment block.
    3. In `evaluate()`, replace:
       ```python
       market_normalized = _NORMALIZE_MARKET.get(market, market.lower())
       try:
           league_cfg = self._league_registry.get(prediction.league)
           threshold = getattr(
               league_cfg.model_params,
               f"edge_threshold_{market_normalized}",
               EDGE_THRESHOLD_PCT,
           )
       except KeyError:
           threshold = EDGE_THRESHOLD_PCT
       ```
       With:
       ```python
       try:
           market_key = MarketKey.from_str(market)
           league_cfg = self._league_registry.get(prediction.league)
           threshold = getattr(
               league_cfg.model_params,
               market_key.to_threshold_attr(),
               EDGE_THRESHOLD_PCT,
           )
       except (KeyError, ValueError):
           # Unknown league OR unknown market alias -> backtest default.
           threshold = EDGE_THRESHOLD_PCT
       ```
    4. Leave `prediction.market: str` untouched (StrEnum compat preserves
       downstream behavior). Pick.market still receives `prediction.market`
       (a str), so persistence is unchanged.

    --- B. src/bip/clv/client.py ---
    1. Add import: `from bip.core.types import MarketKey`.
    2. DELETE the `MARKET_KEY_MAP: dict[str, str] = {...}` dict (lines ~23-29).
    3. Replace `map_market_key` body:
       ```python
       def map_market_key(self, internal_key: str) -> str | None:
           """Convert internal market key to Odds API market key.

           Returns None for markets not supported by The Odds API
           (e.g., corners) or for any unrecognized key.
           """
           try:
               key = MarketKey.from_str(internal_key)
           except ValueError:
               return None
           odds_key = key.to_odds_api()
           return odds_key or None  # CORNERS -> "" -> None
       ```
       Rationale: `to_odds_api()` returns "" for CORNERS; convert to None at the
       boundary so the caller's existing None-check (e.g., "skip CLV for
       corners") keeps working unchanged. This preserves the `None` return for
       both "corners" AND truly unknown keys — the public contract of the
       method does not regress.

    --- C. src/bip/scheduler/orchestrator.py ---
    1. Add import: `from bip.core.types import MarketKey`.
    2. Line ~247 (D-01 dup-alert guard): change
       `if p.get("market") == "1X2"` -> `if p.get("market") == MarketKey.ONEXTWO`.
       (StrEnum equality with "1X2" via `MarketKey.from_str`? No — direct
       equality only matches the canonical "onextwo". The DB persists whatever
       string was passed; today it's "1X2". To remain backwards-compatible with
       existing DB rows AND new ones, use the explicit normalization:)
       ```python
       blocking = []
       for p in existing:
           raw = p.get("market")
           if raw is None:
               continue
           try:
               if (MarketKey.from_str(raw) == MarketKey.ONEXTWO
                       and p.get("status") == PickStatus.pending.value):
                   blocking.append(p)
           except ValueError:
               continue
       ```
    3. Line ~257: `await self.plugin.predict(features, market="1X2")` ->
       `await self.plugin.predict(features, market=MarketKey.ONEXTWO)`.
       (StrEnum -> str works; plugin signature is `market: str`.)
    4. Line ~272: `Prediction(..., market="1X2", ...)` ->
       `Prediction(..., market=MarketKey.ONEXTWO, ...)`.
       Pydantic accepts StrEnum in a `str` field; the persisted value will be
       "onextwo". DB rows going forward will use the canonical key.
    5. Line ~328 (CLV path): same shape as step 2 — wrap with
       `MarketKey.from_str`:
       ```python
       pending_1x2 = []
       for p in pending:
           raw = p.get("market")
           if raw is None:
               continue
           try:
               if MarketKey.from_str(raw) == MarketKey.ONEXTWO:
                   pending_1x2.append(p)
           except ValueError:
               continue
       ```
    6. Line ~410 (`market="onextwo"` in clv_recorder.record call): change to
       `market=MarketKey.ONEXTWO`. Already canonical, just typed now.
    7. Line ~363 (`market_key="h2h"` in fetch_pinnacle_closing_odds): change to
       `market_key=MarketKey.ONEXTWO.to_odds_api()`. Self-documenting.
    8. Line ~516 (reconcile path): same shape as step 2:
       ```python
       for pick in pending:
           raw = pick.get("market")
           if raw is None:
               continue
           try:
               if MarketKey.from_str(raw) != MarketKey.ONEXTWO:
                   continue
           except ValueError:
               continue
           # ...rest of loop body unchanged...
       ```

    --- D. src/bip/sports/football/plugin.py ---
    1. Add import: `from bip.core.types import MarketKey`.
    2. Update `predict` signature type hint:
       `async def predict(self, features: FeatureMatrix, market: str | MarketKey) -> ProbabilityMap`.
       (Accept both — StrEnum already IS a str, so the union is purely
       documentation.) The body is unchanged: `market` is passed straight into
       `_probs_to_map(market=market, ...)` which writes it onto ProbabilityMap.
    3. DO NOT touch `_CLASS_TO_OUTCOME` or `_ODDS_VALUE_TO_KEY` — those are
       SELECTION keys, not market keys. Out of scope.
    4. DO NOT touch `get_opening_odds` return shape — those are also selection
       keys.

    --- Verification before commit ---
    Run the full verification suite:
    ```bash
    uv run pytest -q
    grep -n "_NORMALIZE_MARKET" src/bip/                     # MUST be empty
    grep -n "MARKET_KEY_MAP" src/bip/                        # MUST be empty
    grep -n "MarketKey" src/bip/core/picks/engine.py         # MUST find usage
    grep -n "MarketKey" src/bip/clv/client.py                # MUST find usage
    grep -n "MarketKey" src/bip/scheduler/orchestrator.py    # MUST find usage
    grep -n "MarketKey" src/bip/sports/football/plugin.py    # MUST find usage
    grep -rnE "['\"]1X2['\"]|['\"]h2h['\"]" src/bip/ | wc -l # SHOULD be <= 5
    ```

    If any test fails: read the failure, fix the regression, re-run. Likely
    failure modes:
    - A test asserts `pick.market == "1X2"` literal — these tests should still
      pass because StrEnum.value of MarketKey.ONEXTWO is "onextwo", not "1X2".
      If a test asserts the old "1X2" persisted value, the orchestrator change
      at step 4 will trip it. Resolution: update those tests to assert
      `MarketKey.ONEXTWO` (or "onextwo"). Do this minimally — only fixtures
      asserting market equality, not all 282 tests.

    Final single commit (after all four files clean + tests green):
    `refactor(260503-oml): migrate callers to MarketKey enum; delete _NORMALIZE_MARKET + MARKET_KEY_MAP parches (G-MAINT-05)`.
  </action>
  <verify>
    <automated>uv run pytest -q && test -z "$(grep -rn '_NORMALIZE_MARKET' src/bip/ 2>/dev/null)" && test -z "$(grep -rn 'MARKET_KEY_MAP' src/bip/ 2>/dev/null)" && grep -q "MarketKey" src/bip/core/picks/engine.py && grep -q "MarketKey" src/bip/clv/client.py && grep -q "MarketKey" src/bip/scheduler/orchestrator.py && grep -q "MarketKey" src/bip/sports/football/plugin.py</automated>
  </verify>
  <done>
    - `_NORMALIZE_MARKET` dict removed from engine.py.
    - `MARKET_KEY_MAP` dict removed from clv/client.py.
    - All four callers (engine, clv/client, orchestrator, plugin) import and
      use MarketKey at the appropriate boundaries.
    - Orchestrator persists "onextwo" canonical key on new Prediction rows
      while still recognizing legacy "1X2" rows in DB queries via
      `MarketKey.from_str` normalization.
    - clv/client.map_market_key still returns `None` for unknown OR
      unsupported (corners) market keys — behavioral contract preserved.
    - Full test suite green: `uv run pytest -q` reports 290+ passed, 0 failed
      (282 prior + 10 new MarketKey tests, minus any old fixtures updated).
    - One commit landed: refactor(260503-oml): migrate callers ...
    - SUMMARY documents that the parche `_NORMALIZE_MARKET` is now removed.
  </done>
</task>

</tasks>

<verification>
End-to-end checks (run after Task 2 completes):

1. **Tests green**: `uv run pytest -q` reports 0 failed, >= 290 passed.
2. **Parches removed**:
   - `grep -n "_NORMALIZE_MARKET" src/bip/` returns empty.
   - `grep -n "MARKET_KEY_MAP" src/bip/` returns empty.
3. **Enum adopted**: `grep -rln "MarketKey" src/bip/` includes core/types.py,
   core/picks/engine.py, clv/client.py, scheduler/orchestrator.py,
   sports/football/plugin.py (5+ files minimum).
4. **Magic strings reduced**: `grep -rnE "['\"]1X2['\"]|['\"]h2h['\"]" src/bip/ | wc -l`
   drops from ~30 to <= 5 (residuals: docstrings, log messages, test fixtures
   intentionally exercising legacy aliases).
5. **YAML untouched**: `git diff src/bip/sports/football/config/markets.yaml`
   shows no changes.
6. **ModelParams untouched**: `git diff src/bip/sports/football/config/league_config.py`
   shows no changes.
7. **Pydantic compat preserved**: a test inserts a Pick with
   `market=MarketKey.ONEXTWO` and reads it back — value persists as "onextwo"
   string (already covered by Task 1 test_json_serialization + the existing
   pick repository tests that should continue passing).
</verification>

<success_criteria>
- MarketKey StrEnum exists with all 5 members + 3 helper methods.
- `tests/test_market_key.py` has 10 passing tests covering aliases, mappings,
  rejections, JSON serialization.
- 4 callers migrated; 2 parche dicts deleted.
- 282+ existing tests still pass; total pytest suite GREEN.
- Three commits landed (RED test, GREEN enum, refactor migration), all without
  Co-Authored-By trailers and without emojis.
- G-MAINT-05 audit gap closable.
</success_criteria>

<output>
After completion, create `.planning/quick/260503-oml-marketkey-enum-migrar-callers-g-maint-05/260503-oml-SUMMARY.md` documenting:
- The MarketKey enum design (canonical = YAML form; aliases mapped at
  boundaries via from_str).
- Why ModelParams.edge_threshold_1x2 attribute name was preserved (Python
  identifier, not market string; bridged by to_threshold_attr).
- Why YAML keys were preserved (canonical source of truth that the enum value
  matches).
- Removal of `_NORMALIZE_MARKET` (engine.py) and `MARKET_KEY_MAP` (clv/client.py)
  parches.
- Final test count and grep verification numbers (before/after magic-string
  count).
</output>
