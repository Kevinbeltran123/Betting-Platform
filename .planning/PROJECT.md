# betting-intelligence-platform

## What This Is

A unified, multi-sport betting intelligence platform built for scalability from day 1. Initially covering football across 5 top European leagues, it merges two existing systems — an ML prediction engine and a Claude-powered analysis methodology — into a single production pipeline. The system detects statistical edge using an ML ensemble, enriches analysis with Claude AI, and delivers Telegram alerts for qualified picks; the human makes the final betting decision.

## Core Value

Find and deliver bets with genuine statistical edge (CLV > +3% against Pinnacle closing lines) — if there's no edge, send nothing.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Core Infrastructure**
- [ ] sport-agnostic `core/` layer (EV engine, Claude layer, Telegram, CLV tracker, scheduler) with zero sport-specific code
- [ ] `SportPlugin` ABC interface implemented and enforced — all sports conform to it
- [ ] Supabase schema extended with `sport` column across all 6 tables (migration 002)
- [ ] Football plugin implementing full `SportPlugin` interface

**Data Pipeline**
- [ ] Async API-Football v3 client (fixtures, stats, lineups, corners history, injuries, H2H)
- [ ] Feature engineering pipeline for football using Polars/Parquet cache
- [ ] League config YAML loader extended from existing Football_analysis configs
- [ ] Pre-kickoff pipeline runs at 2h and 30min before kickoff via APScheduler

**ML Core — Football**
- [ ] XGBoost + CatBoost + LightGBM ensemble training pipeline
- [ ] Walk-forward backtesting with isotonic calibration per league (5 leagues)
- [ ] Probability outputs in `ProbabilityMap` format (SportPlugin interface)
- [ ] Model versioning and storage in Supabase

**Timed Corners Module**
- [ ] Historical corner timing data ingested from API-Football by time window (0-15, 15-30, 30-45, 45-60, 60-75, 75-90 min)
- [ ] Corner time-window distribution model per fixture (penaltyblog + custom features)
- [ ] Per-team corner timing profile (pressing style quantification)
- [ ] EV check integrated for corner window picks against available Betano odds

**Claude Integration**
- [ ] Role B: context augmentation — Claude reads pre-match context and outputs `confidence_modifier` (-15% to +15%) as ML feature
- [ ] Role C: pick validator — Claude checks pick against `learnings/football-learnings.md` red flags before Telegram alert
- [ ] Structured logging of Claude reasoning per pick in Supabase

**Pick Engine + Delivery**
- [ ] EV filter (min 5% edge), quarter-Kelly sizing, Betano pattern rotation
- [ ] Telegram alert with odds, edge %, Claude reasoning summary, stake suggestion
- [ ] CLV recording post-match via The Odds API (Pinnacle closing odds)
- [ ] Performance metrics: ROI and CLV aggregated by market and league

**Scalability Validation**
- [ ] Tennis `SportPlugin` scaffold implemented — validates ABC works without core changes
- [ ] Confirmed: Supabase schema, Telegram, EV engine, Claude layer require zero modification for tennis

### Out of Scope

- **Auto-placing bets** — System sends alerts; human places bets on Betano. Automation introduces legal and account-ban risk.
- **GPU training** — Gradient boosting trains on CPU; no CUDA dependencies.
- **Full tennis/NBA implementation** — Scaffold only in Phase 6; full implementation is a future milestone.
- **Real-time in-play pipeline** — Pre-kickoff pipeline only (2h and 30min windows). Live in-play is a future phase.
- **Multiple bookmakers** — Betano only for now; CLV reference uses Pinnacle via The Odds API (read-only).
- **Web dashboard** — Delivery is Telegram alerts only. No UI frontend in v1.

## Context

### Existing code to reuse (do not rebuild)

- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/`
  Supabase schema (6 tables: predictions, picks, odds_snapshots, results, clv_records, performance_metrics), YAML league configs for 5 leagues, Pydantic storage models and repositories. **REUSE AND EXTEND** with sport column migration.

- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/`
  EV calculator, Kelly criterion logic, `learnings/football-learnings.md` (red flag patterns for Claude validator), playbooks methodology. **PORT to `core/` layer.**

- `/Users/kevin_beltran/ProyectosPersonales/Apuestas/nba-wl-predictor/`
  Existing NBA predictor (XGBoost 60% + CatBoost 40%, 65.8% accuracy). Reference for future NBA plugin — **do not touch.**

### Domain knowledge

- Betano is a soft bookmaker (not sharp). Account longevity is a design constraint: wins consistently → restriction within weeks.
- CLV against Pinnacle is the only honest measure of real edge — tracked regardless of where the bet is placed.
- Timed corners market: corner distribution is non-uniform across match time. Team pressing style, motivation, and H2H history are the key predictive signals.
- Existing football-predictor achieves 4-6% calibration improvement over bookmakers per-league with isotonic calibration — proven baseline to build on.

## Constraints

- **Tech Stack**: Python 3.11+, uv, Polars, Pydantic v2, Supabase PostgreSQL — match existing Football_analysis stack exactly.
- **No GPU**: All ML training on CPU (gradient boosting); inference must be < 500ms per fixture.
- **API Limits**: API-Football Pro required (100 req/day free tier insufficient for corners history). The Odds API Rookie tier ($20/mo) sufficient for CLV-only use.
- **Account Safety**: Max 1/4 Kelly on Betano, vary stake patterns, rotate markets. Monitor CLV trend — if drops below +1%, pause and audit.
- **Semi-manual**: System sends Telegram alerts; human places bets. No automated bet placement.
- **Corners market verification**: Confirm exact Betano corner time-window markets available before building Phase 3.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Plugin architecture (SportPlugin ABC) | Adding tennis/NBA later without plugin = rewrite 70% of codebase | — Pending |
| Market as runtime YAML (not hardcoded enum) | Adding markets without code changes; existing Football_analysis already uses YAML for leagues | — Pending |
| Claude as confidence_modifier feature (not gatekeeper) | Model sees Claude's reasoning as a numeric feature; keeps pipeline deterministic | — Pending |
| Quarter-Kelly max on Betano | Protects account longevity; Betano restricts consistent winners | — Pending |
| CLV vs Pinnacle as primary success metric | Pinnacle is the sharpest market; positive CLV = genuine edge regardless of short-term results | — Pending |
| Reuse Football_analysis Supabase schema | Already designed for this exact use case; migration 002 adds sport column for multi-sport | — Pending |

## Infrastructure Investment Gate

The pipeline runs in **local mode** by default — operator-supervised `python -m bip.production` in a tmux session per `deploy/local/RUNBOOK.md`. No paid infrastructure. This is intentional: the platform must demonstrate real edge before any recurring infrastructure cost is justified.

### Promotion criteria — ALL must hold to graduate to a paid VPS

A paid VPS (Hetzner per `deploy/systemd/bip.service`, or equivalent) is justified ONLY when ALL of the following are simultaneously true:

| # | Criterion | Source of truth | Why this threshold |
|---|-----------|-----------------|--------------------|
| 1 | **90 consecutive days** of pipeline runtime in local mode | `clv_records` row span — `max(snapshot_at) - min(snapshot_at) ≥ 90 days` with no >48h gap | Filters out short-term variance. 90 days covers ≥3 typical Bundesliga matchweeks across multiple leagues. |
| 2 | **Rolling-50 CLV ≥ +3%** sustained for the final 30 days of the window | `compute_rolling_clv_average(last_50_settled)` ≥ 3.0 every day for 30 days | The "core value" metric in this PROJECT.md. Anything below is project-failing. |
| 3 | **2 consecutive calendar months of positive realized ROI** (real money, not paper) | Operator's own betting ledger reconciled against `picks` table — picks where `result IN ('won','lost','void')` produced net-positive P&L per month | CLV is a *predictor* of profit, not a guarantee. Two months of real ROI confirms the predictor translated to outcomes. |
| 4 | **Operator availability has become the bottleneck**, not infrastructure | Self-assessment: "Am I missing fixtures because I'm not running the pipeline, AND those missed fixtures had qualifying picks I'd have placed?" | Local mode's ~30% missed coverage only matters if the missed picks would've been profitable. If they wouldn't have, paying for a VPS solves nothing. |

### What graduation looks like

When all 4 hold:
1. Audit `deploy/systemd/bip.service` against current code (drift may have accumulated).
2. Run `deploy/SMOKE_TEST.md` end-to-end on the chosen VPS (currently 8 checks; the `MemoryDenyWriteExecute=true` enable check is part of this).
3. Update SC#3 in ROADMAP.md once VPS is the primary deployment target.
4. Local mode stays documented in `deploy/local/RUNBOOK.md` as the dev/fallback path.

### What graduation does NOT require

- Hitting **CLV +3%** in early periods. Calibration takes time; the criterion above wants 30 days *at the end of* a 90-day window.
- Approval from anyone other than the operator. This is a personal project; the gate is self-imposed discipline, not external sign-off.

### Failure mode — when to scrap, not graduate

If after **6 months** of local-mode operation criterion #2 has *never* been met for any rolling-50 window, the project's core thesis is unproven. At that point, paying for a VPS to keep the same pipeline running longer is throwing good money after a bad bet. The correct decision is to either pivot the methodology (not the infra) or close the project.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-22 after initialization*
