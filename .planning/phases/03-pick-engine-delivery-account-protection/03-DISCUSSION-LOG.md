# Phase 3: Pick Engine + Delivery + Account Protection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `03-CONTEXT.md` -- this log preserves the alternatives considered.

**Date:** 2026-05-02
**Phase:** 03-pick-engine-delivery-account-protection
**Areas discussed:** Pick selection & dedup, Claude Role C integration, Account longevity enforcement, CORNERS-01 gate execution, Telegram alert UX

**Areas deferred to Claude's discretion:** Pick result reconciliation (covered as D-16), internal pick-engine class API, Telegram template renderer, Polars-vs-Supabase market-cap query.

---

## Area 1: Pick Selection & Dedup

### Q1.1: T-2h vs T-30min re-prediction collision strategy

| Option | Description | Selected |
|--------|-------------|----------|
| T-2h sends, T-30min recovers only | T-2h primary; T-30min only acts if T-2h was REJECTed (and recovered) or had no qualifying edge. Sent picks never retracted. Maximises CLV vs Pinnacle. | YES |
| T-30min sends only | T-2h is data refresh + speculative; only T-30min reaches Telegram. Loses ~90 min of closing-line edge. | -- |
| Both can send, edit if changed | T-2h sends, T-30min sends edit/retract on change. Highest fidelity but adds Telegram message-state complexity. | -- |

**User's choice:** T-2h sends, T-30min recovers only (recommended).
**Notes:** Encoded as D-01.

### Q1.2: Filtered-pick persistence (PICK-05 requires logging both sent and filtered)

| Option | Description | Selected |
|--------|-------------|----------|
| Extend PickStatus with `filtered`+`rejected` | Add to enum; widen `picks.status` CHECK constraint via migration 004. One source of truth for analytics. | YES |
| Filtered -> predictions only | Picks table = sent only. Breaks PICK-05 wording; hit-rate analysis becomes a JOIN. | -- |
| Picks table with NULL stake/selection | Single table but fuzzy semantics (a "pick" with no selection is not a pick). | -- |

**User's choice:** Extend PickStatus with `filtered` + `rejected` (recommended).
**Notes:** Encoded as D-03 + D-04 + part of migration 004 (D-08).

---

## Area 2: Claude Role C Integration

### Q2.1: Validator prompt input

| Option | Description | Selected |
|--------|-------------|----------|
| Pick + learnings.md + curated feature signals | Pick row, full learnings.md (Spanish), recent form/H2H/motivation/lineups subset. Not the full ~50-feature row. | YES |
| Pick + learnings.md only | Minimal; pattern-match only. Cheaper but loses context-specific red flags. | -- |
| Pick + learnings.md + full feature row + recent fixtures dump | Maximum context (~5-10k tokens); risks over-reasoning false REJECTs. | -- |

**User's choice:** Pick + learnings.md + curated feature signals (recommended).
**Notes:** Encoded as D-05.

### Q2.2: Tool_use schema and language

| Option | Description | Selected |
|--------|-------------|----------|
| tool_use, English keys + Spanish reasoning | English schema, Spanish `reasoning_es`, English `reasoning_summary_en`. Matches Kevin's learnings.md voice. | -- |
| tool_use, all English | All output English; learnings.md content stays Spanish in prompt input. Easier to scan/grep across logs. | YES |
| Plain text + regex parsing | Free-form Claude reply, regex extraction. Fragile, no schema validation. | -- |

**User's choice:** tool_use, all English (deviates from recommendation).
**Notes:** Encoded as D-06. The Spanish learnings.md remains as prompt input; only output is English. Simplifies log scanning and downstream English-language Telegram alerts.

### Q2.3: Anthropic API outage behaviour

| Option | Description | Selected |
|--------|-------------|----------|
| Block the pick, log skipped, retry once after 60s | Pick held `pending`; after 2 consecutive failures marked `filtered` (`reason_code='claude_api_unavailable'`). Phase 4 wires SKIPPED-mode behind a flag. | YES |
| Send with 'SKIPPED' tag immediately | Maximum uptime but a single Anthropic outage produces a wave of unvalidated picks -- defeats the validator's purpose. | -- |
| Drop pick silently, log only | Safest; loses real edge to transient outages. | -- |

**User's choice:** Block the pick, log skipped, retry once after 60s (recommended).
**Notes:** Encoded as D-07.

### Q2.4: Where Claude Role C output is persisted

| Option | Description | Selected |
|--------|-------------|----------|
| Migration 004 -- new claude_* columns on picks table | claude_validation, claude_reasoning, claude_summary, claude_validated_at on `picks`. Predictions.claude_* reserved for Phase 5 Role B. | YES |
| Reuse predictions.claude_* fields | Avoid migration 004 but mixes Role B and Role C audit trails. | -- |
| Separate claude_validations table | Cleanest but premature normalisation; adds JOIN overhead per pick. | -- |

**User's choice:** Migration 004 -- new claude_* columns on picks table (recommended).
**Notes:** Encoded as D-08.

---

## Area 3: Account Longevity Enforcement

### Q3.1: 60% market-cap window and enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Rolling 7-day, drop if cap hit | Trailing 168 h window; drop on bind, log `reason_code='market_cap'`. | YES |
| ISO calendar week, defer to next week | Mon-Sun count, queue picks above cap. Calendar-clean reporting; "stale pick" UX issue. | -- |
| Rolling 7d, downgrade alert (no Kelly) | Send 0.5u monitoring alert at cap. Mixes audit + action. | -- |

**User's choice:** Rolling 7-day, drop if cap hit (recommended).
**Notes:** Encoded as D-09. Largely dormant in 1X2-only Phase 3; mechanism built for Phase 6 corners and future BTTS/OU.

### Q3.2: Stake jitter mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic +-10% jitter from fixture_id hash | `md5(fixture_id-market) % 21 - 10` percent. Reproducible for replay; bounded; breaks fingerprinting. | YES |
| Random uniform +-10% | Pure RNG; not reproducible; complicates incident postmortems. | -- |
| No jitter, just round to 0.5u | Stakes cluster at quarter-Kelly multiples; easy fingerprint. | -- |

**User's choice:** Deterministic +-10% jitter from fixture_id hash (recommended).
**Notes:** Encoded as D-10. `hashlib.md5` not Python `hash()` (PYTHONHASHSEED).

### Q3.3: Send-time variance

| Option | Description | Selected |
|--------|-------------|----------|
| Random delay 0-30 min, deterministic from fixture_id | `random.Random(fixture_id).randint(0, 1800)` -> APScheduler DateTrigger. | YES |
| Pre-scheduled offsets per league | Hard-coded; trivial to fingerprint over time. | -- |
| Variance from per-fixture kickoffs only | Same-slot fixtures (Sat 15:00 GMT cluster) all alert simultaneously. | -- |

**User's choice:** Random delay 0-30 min, deterministic from fixture_id (recommended).
**Notes:** Encoded as D-11.

---

## Area 4: CORNERS-01 Gate Execution

### Q4.1: Betano time-window market probe (CORNERS-01a)

| Option | Description | Selected |
|--------|-------------|----------|
| Manual probe + structured checklist file | `scripts/corners_gate_probe.md` checklist; Kevin runs manually; findings written to `corners_gate_findings.md`. | YES |
| Scripted Selenium / Playwright scrape | Automation overkill for a one-time gate; account-detection risk. | -- |
| Skip probe, assume market exists | Risks Phase 6 sunk-cost if assumption wrong. | -- |

**User's choice:** Manual probe + structured checklist file (recommended).
**Notes:** Encoded as D-17 (a).

### Q4.2: API-Football coverage check + gate-fail policy

| Option | Description | Selected |
|--------|-------------|----------|
| Polars query over existing 02.1 seed Parquet + auto-descope | `corners_gate_coverage.py`; coverage thresholds; on fail, single ROADMAP edit moving Phase 6 to v2-deferred + STATE entry + commit. | YES |
| Coverage check via fresh API-Football pull | Burns rate-limit; redundant -- 02.1 seed already has the data. | -- |
| Polars check + manual roadmap edit on fail | Less automated; gives Kevin final descope call but adds friction. | -- |

**User's choice:** Polars + auto-descope (recommended).
**Notes:** Encoded as D-17 (b) + D-18.

---

## Bonus Area: Telegram Alert UX

### QB.1: Format and batching

| Option | Description | Selected |
|--------|-------------|----------|
| HTML, one message per pick | parse_mode='HTML'; templated; one alert per pick (respects D-10/D-11 variance). | YES |
| MarkdownV2, one message per pick | Same UX, MarkdownV2 escape hell on dynamic values. | -- |
| HTML, batched matchday digest | Defeats stake/timing variance; one error voids whole digest. | -- |

**User's choice:** HTML, one message per pick (recommended).
**Notes:** Encoded as D-12.

### QB.2: FLAG visualisation and recipient

| Option | Description | Selected |
|--------|-------------|----------|
| WARNING emoji prefix + same private channel | Single channel; FLAG picks render with WARNING + flag-reason line. CONFIRM clean. REJECT never sent. | YES |
| Separate FLAG channel | Doubles operational state for solo use. | -- |
| FLAG = same message, no special marker | Risk of treating FLAG as full-confidence. | -- |

**User's choice:** WARNING emoji prefix + same private channel (recommended).
**Notes:** Encoded as D-13 + D-14.

### QB.3: Source of reasoning bullets

| Option | Description | Selected |
|--------|-------------|----------|
| Claude's claude_summary split into bullets | Reuse migration-004 `claude_summary`; up to 3 short English bullets. Single source of truth. | YES |
| Deterministic top-3 SHAP / feature-importance bullets | Rigorous, auditable, but no narrative. Adds SHAP pipeline this phase. | -- |
| Hybrid: 2 Claude + 1 SHAP | Best of both but bleeds into Phase 5 territory. | -- |

**User's choice:** Claude's claude_summary (recommended).
**Notes:** Encoded as D-15.

---

## Claude's Discretion

Areas explicitly handed to Claude during planning (no user lock-in):

- Internal API of the pick engine (class vs free functions in `core/picks/`).
- Telegram template renderer (Jinja2 vs `string.Template` vs f-string).
- Exact SQL for the rolling-7d market-cap query (Polars vs Supabase).
- Schema of `corners_gate_*.md` artifact files (markdown headers vs YAML front-matter).
- Whether the Telegram bot runs in-process (recommended) or as a separate polling worker.
- Pick-result reconciliation specifics (D-16 is a recommended default; planner may revise).

## Deferred Ideas

Mentioned during discussion, captured for future phases:

- Telegram bot user commands (`/status`, `/clv_today`, `/pause`).
- Multi-recipient paid sub-feed channels (v2).
- SHAP-based deterministic feature attribution in alerts.
- Phase 6 corners implementation (conditional on D-17 gate).
- Auto-promotion of model registry on CLV improvement (Phase 4 scope).
- Pinnacle /historical backfill (inherits 02.1 deferral).
- Bot-token rotation / secrets hardening (Phase 4 ops).
- Spanish localisation of Telegram alerts.
