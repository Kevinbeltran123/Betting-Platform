---
phase: 260515-nxn
plan: 01
type: execute
wave: multi
depends_on: []
files_modified:
  - src/bip/evaluation/live/engine_v3/archetypes.py
  - src/bip/evaluation/live/engine_v3/runtime/dual_write.py
  - src/bip/evaluation/live/engine_v3/runtime/v3_grader.py
  - src/bip/evaluation/live/engine_v3/runtime/telegram_adapter.py
  - src/bip/evaluation/live/telegram_integration.py
  - src/bip/core/telegram/bot.py
  - src/bip/evaluation/live/engine_v3/no_bet_gate.py
  - src/bip/evaluation/live/engine_v3/mes.py
  - src/bip/evaluation/live/engine_v3/calibrator.py
  - src/bip/evaluation/live/engine_v3/drift_monitor.py
  - src/bip/evaluation/live/engine_v3/gsv_builder.py
  - scripts/spike/v3/
  - src/bip/clv/
  - tests/evaluation/live/engine_v3/
  - docs/v3_dead_signal_audit.md
requirements:
  - V3-OVERHAUL-3TIER
must_haves:
  truths:
    - "numerical_sustained is removed from the _ARCHETYPE_DETECTORS registry (archetype no longer fires) but the function and __all__ export remain intact"
    - "docs/v3_dead_signal_audit.md enumerates every archetype, its gated GSV fields, and flags A6/A9 as de-facto non-firing + the dead formation/elo/key_player_off/role_signal/ref_card_rate_prior branches"
    - "watch.py and dual_write.py V3_TELEGRAM_ENABLED parsing is reconciled (single shared parser or documented AND-gate with aligned truthy/falsy sets)"
    - "A single canonical grading entrypoint routes through v3_grader.grade_picks_for_date (authoritative client.get_fixture); the two circular replay scripts are marked deprecated in-file"
    - "deliveries.parquet is written from DualWriteRuntime._send_alerts_for with fixture_id, archetype, market_id, sent_ts, send_result, and telegram_message_id surfaced via a send_pick_safe/send_html signature change"
    - "A v3 CLV parquet sink records clv_percentage (vig-removed) for delivered v3 picks in goals/btts/totals/1X2 families, reusing calculate_clv_percentage + compute_rolling_clv_average; corners/cards/next_goal are explicitly skipped with a logged unsupported-family reason"
    - "A shadow-promotion report reads is_shadow gate_denials rows, grades them via the canonical v3_grader, and emits per-shadow-rule delta (P/L, precision, volume, CLV) for rule_8/rule_9/dominant-gap"
    - "CalibrationDriftMonitor carries return/stake plumbing and a live settlement feed (observe() fed from grading); Rule 11 drifts on calibration (predicted-vs-realized) or P&L, not raw WR; napoli exemption is removed only after the principled gate is in place"
    - "MESResult exposes a per-family calibrated win-prob; rule_5/rule_12 gate on the calibrated value (the [2.5,4.0) raw band is replaced or re-expressed in calibrated units)"
    - "A penaltyblog-based per-fixture lambda producer writes a lambda store; derive_priors_from_fixture reads ML lambda when present; _choose_dominant_team_id promotes ML lambda above the noisy market signal as a first-class precedence tier"
    - "engine_v3 suite + anti-Napoli regression pass on main after EVERY wave merge (re-run on main where data/cache pkls exist, not only in worktree)"
    - "Every item is an atomic commit; waves merge to main sequentially (file overlap forbids parallel waves)"
  artifacts:
    - path: "docs/v3_dead_signal_audit.md"
      provides: "Wave 0 #9 audit deliverable"
    - path: "src/bip/clv/v3_clv_sink.py"
      provides: "Wave 2 #1 parquet CLV sink for v3 live picks (new module)"
    - path: "scripts/spike/v3/shadow_promotion_report.py"
      provides: "Wave 2 #4 per-shadow-rule promotion delta report"
    - path: "scripts/spike/v3/build_lambda_store.py"
      provides: "Wave 3 #8 penaltyblog per-fixture lambda producer (new)"
  key_links:
    - from: "DualWriteRuntime._send_alerts_for"
      to: "deliveries.parquet"
      via: "new delivery-record write after send_pick_safe returns (message_id threaded out)"
      pattern: "deliveries|telegram_message_id"
    - from: "scripts/spike/v3/shadow_promotion_report.py"
      to: "v3_grader.grade_picks_for_date"
      via: "canonical grading of is_shadow rows"
      pattern: "grade_picks_for_date|is_shadow"
    - from: "gsv_builder._choose_dominant_team_id"
      to: "PreMatchPriors.lambda_home_prematch (ML-sourced)"
      via: "new precedence tier above _market_dominant_team_id"
      pattern: "lambda_home_prematch|ml_lambda"
---

<objective>
Address all 3 improvement tiers (9 items) on the v3 live engine, dependency-ordered into 4
SEQUENTIAL waves. The governing principle from the forensic analysis: make the system MEASURABLE
before promoting shadow rules before tuning calibration. Waves are sequential because of source-file
overlap (no_bet_gate.py: #6+#7; dual_write.py: #1+#2+#8). Each item = one atomic commit. The
engine_v3 suite + anti-Napoli regression must pass on `main` (where data/cache pkls exist) after
every wave merge.

Grounded scope corrections (from the integration map — these are constraints, not options):
- CLV (#1): ClvRecorder is Supabase/1X2-only and cannot take v3 parquet picks; OddsApiClient has
  NO Betfair, NO corners, historical is a stub. v3 CLV is a NEW parquet sink, scoped to
  goals/btts/totals/1X2 only. corners/cards/next_goal: log "clv_unsupported_family" and skip.
- Grading (#3): the non-circular path already exists (v3_grader.grade_picks_for_date →
  client.get_fixture authoritative). Work = make it canonical + deprecate the 2 replay scripts.
- ML λ (#8): NO ML λ pipeline exists. This is a NEW producer (penaltyblog bivariate/Dixon-Coles
  fit → per-fixture λ store) + a reader in derive_priors_from_fixture + a precedence change in
  _choose_dominant_team_id. Largest item; keep its surface contained.
- Rule 11 (#6): drift monitor is WR-only AND read-only at gate time (no live observe() feed).
  Needs return/stake fields + a settlement feed (new) before the napoli exemption can be revoked.
- Delivery (#2): message_id is returned by bot.send_html but discarded for v3 (no pick_id). A
  signature change is required to surface it to _send_alerts_for.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@.planning/quick/260515-ghb-v3-engine-5-vetted-shadow-run-fixes-susp/260515-ghb-SUMMARY.md
</context>

<global_constraints>
- One atomic commit per item with a conventional message + rationale body. NO Co-Authored-By.
- Waves are STRICTLY SEQUENTIAL. Within a wave, items touching disjoint files may be separate
  atomic commits by one executor; never parallelize waves (file overlap → merge conflicts).
- Shadow/measurement additions must NOT change enforced gate behavior unless the item explicitly
  says ENFORCED. #6's napoli-exemption removal is the only enforced gate behavior change, and only
  AFTER the principled drift gate is implemented and tested.
- Run `uv run pytest tests/evaluation/live/engine_v3/ -q` + the anti-Napoli regression before each
  commit. Suites must also be re-run on `main` post-merge (worktrees lack data/cache/*.pkl, which
  silently skips the OOD/calibrator-dependent tests — the 260515-ghb lesson).
- Do NOT run network/API calls in tests; mock SportmonksClient.get_fixture and OddsApiClient.
- Match existing stack: Pydantic v2, Polars, structlog, ruff, pytest, joblib for pkl, JSON for
  phase3 calibration persistence.
</global_constraints>

<wave id="0" theme="Zero-dependency, low-risk, ship immediately">

<task id="0.1" type="execute">
**#5 — Suppress numerical_sustained (ENFORCED, trivial, pure precision)**
files: src/bip/evaluation/live/engine_v3/archetypes.py, tests/evaluation/live/engine_v3/
action: Remove `detect_numerical_sustained` from the `_ARCHETYPE_DETECTORS` tuple
(archetypes.py:829). Keep the function defined and in `__all__` (no import breakage). Add a
one-line comment citing the net-negative evidence (D3 -5.79u wr0.50 n=42; D4 -1.00u; MES
anti-predictive). Test: `generate_theses` never yields a NUMERICAL_SUSTAINED thesis even on a GSV
that previously triggered it (construct the qualifying GSV; assert absence).
verify: new test passes; engine_v3 + anti-Napoli green.
done: commit `feat(engine_v3/archetypes): suppress numerical_sustained (net-negative both days)`.
</task>

<task id="0.2" type="execute">
**#9 — Dead-signal audit (read-only deliverable)**
files: docs/v3_dead_signal_audit.md
action: Write the audit. Table of all 13 detectors (A1..A12 + A2b) → GSV fields gated → population
status (real / heuristic-proxy / DEAD). Explicitly flag: A6 (`ref_card_rate_prior` defaults 0.0,
`>=5.0` never met → never fires), A9 (`key_player_off` defaults (False,False) → never fires),
A8/A10 formation-confidence branches dead, `elo_diff` dominant tier permanently dead (always 0.0).
Recommendations section: (a) kill or feed A6/A9; (b) remove dead formation/elo branches or wire
real data; (c) which heuristic proxies (xg.*, role_signal, tactical phase) are acceptable vs
risky. No code change.
verify: file exists, covers all 13 detectors + the 5 hard-dead signals.
done: commit `docs(engine_v3): dead-signal audit — A6/A9 non-firing, dead formation/elo branches`.
</task>

<task id="0.3" type="execute">
**#2b — Reconcile V3_TELEGRAM_ENABLED parser (tiny latent-bug fix)**
files: scripts/spike/sportmonks/watch.py, src/bip/evaluation/live/engine_v3/runtime/dual_write.py,
tests/evaluation/live/engine_v3/
action: Make watch.py (~L600, fail-closed, truthy set {"1","true","yes","on"}) and
dual_write.is_v3_shadow_enabled (fail-open, {"1","true","yes","on","y","t"}) consistent. Preferred:
have watch.py reuse `is_v3_shadow_enabled("V3_TELEGRAM_ENABLED")` so there is ONE parser; preserve
the intended AND-gate semantics (sender wired AND runtime-enabled) but make the truthy/falsy token
sets identical. Document the AND-gate in a comment. Test: parametrized {unset, "true", "y", "on",
"false", "0", "garbage"} → assert watch.py decision matches dual_write parser.
verify: parametrized parser test passes; engine_v3 + anti-Napoli green.
done: commit `fix(engine_v3): reconcile V3_TELEGRAM_ENABLED parser (watch.py vs dual_write)`.
</task>
</wave>

<wave id="1" theme="Measurement foundation — promotion decisions depend on this">

<task id="1.1" type="execute">
**#3 — Canonical independent grading (deprecate circular replay scripts)**
files: src/bip/evaluation/live/engine_v3/runtime/v3_grader.py, scripts/spike/v3/grade_day3_replay.py,
scripts/spike/v3/regrade_day4_from_raw.py, tests/evaluation/live/engine_v3/
action: Make `v3_grader.grade_picks_for_date` (authoritative `client.get_fixture(...,
includes=[participants,state,periods,scores,statistics,events])` → `final_outcome_from_fixture`)
the single canonical grading path. Ensure it is import-clean and has a thin CLI/callable
entrypoint usable by the Wave-2 promotion report. Add a module-top deprecation banner +
`warnings.warn(DeprecationWarning)` (guarded, not at import of pure helpers) to
grade_day3_replay.py and regrade_day4_from_raw.py pointing to the canonical path; do NOT delete
them (historical reproducibility). Test: grade_picks_for_date with a mocked get_fixture returning
a FT fixture grades a known goals + btts + corners pick deterministically; assert it does NOT read
gsv_log.parquet (no circularity).
verify: grading test (mocked, offline) passes; engine_v3 + anti-Napoli green.
done: commit `feat(engine_v3/grader): canonical authoritative grading; deprecate circular replays`.
</task>

<task id="1.2" type="execute">
**#2 — deliveries.parquet (delivery observability + message_id)**
files: src/bip/core/telegram/bot.py, src/bip/evaluation/live/telegram_integration.py,
src/bip/evaluation/live/engine_v3/runtime/dual_write.py,
src/bip/evaluation/live/engine_v3/runtime/telegram_adapter.py, tests/evaluation/live/engine_v3/
action: Thread the Telegram message_id out so v3 can persist it. Minimal signature change:
`LiveAlertSender.send_pick_safe` returns the message_id (or a small SendResult dataclass with
`{ok: bool, message_id: int | None}`) instead of bare bool; keep the bool-truthiness backward
compatible if feasible, otherwise update all call sites. In `DualWriteRuntime._send_alerts_for`,
after each send, append a row to a buffered `deliveries.parquet` (same partition convention as
shadow_logger: data/cache/v3_shadow/dt=YYYY-MM-DD/deliveries.parquet, diagonal_relaxed append,
flushed from the same per-round watch.py flush site): fixture_id, timestamp_utc, thesis_id,
archetype, family, market_id, direction, bookmaker_odd, telegram_message_id, send_result
(sent/skipped/failed). Test: a fake sender returning a message_id → _send_alerts_for writes one
deliveries row with that id and correct send_result; a skipped pick writes send_result=skipped.
verify: delivery-row test passes; existing telegram tests still pass; engine_v3 + anti-Napoli green.
done: commit `feat(engine_v3/runtime): deliveries.parquet trace with telegram_message_id`.
</task>
</wave>

<wave id="2" theme="CLV + promotion harness (depends on Wave 1)">

<task id="2.1" type="execute">
**#1 — v3 CLV parquet sink (goals/btts/totals/1X2 scope)**
files: src/bip/clv/v3_clv_sink.py (new), src/bip/evaluation/live/engine_v3/runtime/dual_write.py,
tests/evaluation/live/engine_v3/
action: New module `src/bip/clv/v3_clv_sink.py`. Reuse pure functions
`bip.clv.recorder.calculate_clv_percentage` + `compute_rolling_clv_average` (do NOT touch
ClvRecorder/Supabase). For delivered v3 picks (join on deliveries.parquet from #2 — CLV is
measured on what was SENT, not shadow), near kickoff+ fetch the closing line via OddsApiClient
(`find_event_by_fixture` + `fetch_pinnacle_closing_odds`) for families in
{goals, btts, totals, result_1x2} ONLY; for {corners, cards, next_goal} write a row with
clv_percentage=None and reason="clv_unsupported_family" (documented limitation — odds source has
no corners/Betfair). Persist data/cache/v3_shadow/dt=*/clv.parquet (partition convention). Provide
a callable the orchestrator/scheduler can invoke at kickoff+ (do NOT wire a live scheduler job in
this commit — just the sink + a tested function; wiring is a follow-up note in the commit body).
Test: with a mocked OddsApiClient returning a Pinnacle price, a delivered goals pick yields a
clv.parquet row with vig-removed clv_percentage; a corners pick yields clv_unsupported_family.
verify: CLV sink tests (mocked, offline) pass; engine_v3 + anti-Napoli green.
done: commit `feat(clv): v3 live CLV parquet sink (goals/btts/totals; corners unsupported)`.
</task>

<task id="2.2" type="execute">
**#4 — Shadow-promotion report harness**
files: scripts/spike/v3/shadow_promotion_report.py (new), tests/evaluation/live/engine_v3/
action: New script. Input: a date range. Read `data/cache/v3_shadow/dt=*/gate_denials.parquet`
filtered to `is_shadow=True` (rule_8, rule_9) + the shadow `dominant_team_id` diff from
gsv_log.parquet. Grade the underlying theses via the canonical `v3_grader` (#3) — NOT GSV
reconstruction. For each shadow rule compute: counterfactual ΔP/L, Δprecision, Δvolume if it had
been ENFORCED vs SHADOW, plus CLV delta when clv.parquet (#1) has coverage. Emit a markdown/JSON
report with a per-rule PROMOTE / KEEP-SHADOW / REVERT recommendation and the n / effective-N so a
single blowout fixture cannot dominate. Test: synthetic gate_denials + a stubbed grader →
deterministic report with expected per-rule deltas; assert effective-N column present.
verify: report test (synthetic, offline) passes; engine_v3 + anti-Napoli green.
done: commit `feat(scripts/v3): shadow-promotion report (per-rule promote/keep/revert deltas)`.
</task>
</wave>

<wave id="3" theme="Systemic calibration + ML λ (depends on measurement; biggest/riskiest)">

<task id="3.1" type="execute">
**#6 — Rule 11: P&L/calibration drift + live settlement feed (ENFORCED change, last)**
files: src/bip/evaluation/live/engine_v3/drift_monitor.py,
src/bip/evaluation/live/engine_v3/no_bet_gate.py,
src/bip/evaluation/live/engine_v3/runtime/v3_grader.py, tests/evaluation/live/engine_v3/
action: Add return/stake plumbing: `_CellWindow` + `DriftStatus` + `observe()` gain
`profit_units` (and the realized return) alongside `outcome`. Add a settlement feed: a function
that, given graded picks from the canonical v3_grader (#3), calls `monitor.observe(...)` with
predicted_p, outcome, profit_units (this is the missing live feed). Redesign `rule_11`: drift on
CALIBRATION (predicted-vs-realized frequency divergence, e.g. reliability gap / Brier delta) OR
rolling P&L sign, NOT raw WR vs a single prior. THEN remove the napoli special-case exemption
(now safe because long-shot archetypes are judged on calibration/P&L, not WR). Keep the
revoke-history comment but note it is superseded. Tests: (a) a well-calibrated long-shot
(predicted 0.2, realized ~0.2, +EV) does NOT trip rule_11 — proving napoli no longer needs an
exemption; (b) a genuinely mis-calibrated/-P&L cell DOES trip; (c) settlement feed updates a cell
from a graded pick.
verify: calibration-drift tests pass; engine_v3 + anti-Napoli green; the existing napoli-exempt
test is updated to assert the principled path (not the special-case).
done: commit `feat(engine_v3/gate): Rule 11 calibration/P&L drift + settlement feed; drop napoli special-case`.
</task>

<task id="3.2" type="execute">
**#7 — MES per-family calibrated gate (subsumes the bin-3 patch)**
files: src/bip/evaluation/live/engine_v3/mes.py,
src/bip/evaluation/live/engine_v3/no_bet_gate.py,
src/bip/evaluation/live/engine_v3/calibrator.py, tests/evaluation/live/engine_v3/
action: Add a per-family MES→win-prob calibrated value. Reuse the wired
`engine_v3/calibrator.py::IsotonicCalibrator` seam (fit on graded picks: predicted=mes-derived,
outcome from canonical grader). Add `calibrated_winprob: float | None` to `MESResult`
(mes.py:254-272), computed in compute_mes when a fitted MES-calibrator is available (None →
fall back to raw-score gating, no behavior change). Re-express rule_5 (floor) and rule_12 (the
[2.5,4.0) cruise_mode/goals dead-zone) in calibrated-winprob units when calibrated_winprob is
present; keep raw-score thresholds as the fallback. The bin-3 patch becomes a principled
"calibrated winprob below family-specific floor" rule. Tests: with a fitted MES-calibrator,
rule_12 suppresses exactly the low-calibrated-winprob cruise_mode/goals candidates and passes
high ones; with NO calibrator the old raw-band behavior is byte-identical (regression).
verify: calibrated-gate tests + raw-fallback regression pass; engine_v3 + anti-Napoli green.
done: commit `feat(engine_v3/mes): per-family calibrated win-prob gate (subsumes MES bin-3 patch)`.
</task>

<task id="3.3" type="execute">
**#8 — ML λ producer + live dominant-team prior (largest; contained surface)**
files: scripts/spike/v3/build_lambda_store.py (new),
src/bip/evaluation/live/engine_v3/runtime/dual_write.py,
src/bip/evaluation/live/engine_v3/gsv_builder.py, tests/evaluation/live/engine_v3/
action: (a) New offline producer `scripts/spike/v3/build_lambda_store.py`: fit penaltyblog
Dixon-Coles / bivariate Poisson on available historical results (reuse the project's penaltyblog
dependency + the martj42 / statsbomb datasets already used elsewhere; if no fit corpus is
wired, parametrize the input path and ship with a tested synthetic fixture so the producer is
correct even if not yet run on real data — structure-first per project convention). Output a
per-fixture λ parquet: {fixture_id, lambda_home, lambda_away, model_version}. (b) In
`derive_priors_from_fixture` (dual_write.py:159-195): if a λ-store row exists for fixture.id,
populate PreMatchPriors.lambda_home_prematch/away from it (else keep the Sportmonks type_id-240
derivation — graceful fallback). (c) In `_choose_dominant_team_id` (gsv_builder.py:377-414): add
an ML-λ precedence tier ABOVE `_market_dominant_team_id` but BELOW the elo tier, gated on a
configurable min λ-gap so coin-flip λ defers to market. Tests: λ-store read populates priors;
dominant-team resolves to the higher-λ team when λ-gap is decisive and falls back to market when
λ is coin-flip; producer emits a correct λ row on a synthetic fit corpus.
verify: λ-store + priors + dominant-resolution tests (offline, synthetic) pass; engine_v3 +
anti-Napoli green.
done: commit `feat(engine_v3): penaltyblog lambda store + ML-lambda dominant-team prior tier`.
</task>
</wave>

<sequence>
Wave 0 (0.1, 0.2, 0.3) → merge to main, verify on main → Wave 1 (1.1, 1.2) → merge, verify →
Wave 2 (2.1 needs #2, 2.2 needs #1+#3) → merge, verify → Wave 3 (3.1, 3.2, 3.3) → merge, verify.
One executor per wave (atomic commits per item). Re-run suites on `main` after each wave merge.
Do NOT commit docs artifacts (PLAN/SUMMARY/STATE) from the executor — orchestrator handles those.
</sequence>
