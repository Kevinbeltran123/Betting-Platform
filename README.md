# Betting Intelligence Platform

Multi-sport betting intelligence platform. Detects statistical edge using a gradient-boosting ensemble, enriches the analysis with Claude (Role C validator), and delivers qualified picks via Telegram. The human places the bet — there is no automated betting.

**Core thesis:** ship a pick only when CLV > +3% against Pinnacle closing lines. If there is no edge, the system sends nothing.

## Status

Pre-ROI. Phases 1–4 implemented (foundation, ML core, pick engine + delivery, production orchestration). Anthropic and Telegram run against mocks in development. Production deployment to Hetzner is gated by the Infrastructure Investment criterion in [.planning/PROJECT.md](.planning/PROJECT.md): 90 days of operation with positive CLV trend and verified ROI before paid infra is provisioned. Until then, operation is local via the tmux runbook in [deploy/README.md](deploy/README.md).

## Stack

- Python 3.12, [uv](https://docs.astral.sh/uv/) for environment + lockfile
- Polars 1.40, PyArrow, NumPy 2 / SciPy 1.15
- XGBoost 3.2, CatBoost 1.2, LightGBM 4.6, scikit-learn 1.8
- penaltyblog 1.9 (Dixon-Coles, bivariate Poisson)
- Pydantic v2.13 + pydantic-settings (all secrets loaded from env, never in code)
- Supabase Postgres + APScheduler 3.x
- Anthropic Python SDK (claude-sonnet-4-6, Role C pick validator)
- python-telegram-bot 22.7 (async)

Full rationale and version pins live in [CLAUDE.md](CLAUDE.md).

## Layout

```
src/bip/
  core/         # sport-agnostic: settings, storage, picks, claude, scheduler glue, telegram
  sports/       # plugin layer (currently football: API-Football client, league configs)
  clv/          # The Odds API client + CLV reconciliation
  train/        # backtesting + EV simulation
  production/   # production entrypoint + drift checker
  scheduler/    # PipelineOrchestrator (T-2h / T-30min / nightly jobs)
deploy/         # systemd units, tmpfiles, install.sh, smoke runbook
supabase/       # SQL migrations
scripts/        # one-shot probes, seed scripts, smoke E2E
tests/          # pytest suite organised by domain
.planning/      # PROJECT, ROADMAP, STATE, per-phase plans + research
```

## Quickstart

```bash
uv sync                      # install runtime + dev deps
cp .env.example .env         # then fill in keys (see file for sources)
uv run pytest tests/ -x -q   # ~20s, runs the full suite against mocks
```

Required env keys are documented in [.env.example](.env.example). The platform refuses to start if any required key is empty or commented out (validated in `deploy/install.sh` and at settings load).

## Running locally

For pre-ROI operation see [deploy/local/](deploy/local/) and [deploy/README.md](deploy/README.md). The systemd path (Phase 4 deliverables) is ready but only enabled after the ROI gate passes.

## Documentation

- [.planning/PROJECT.md](.planning/PROJECT.md) — project charter, success criteria, constraints
- [.planning/ROADMAP.md](.planning/ROADMAP.md) — phases and deliverables
- [.planning/STATE.md](.planning/STATE.md) — current decision log
- [deploy/SMOKE_TEST.md](deploy/SMOKE_TEST.md) — end-to-end smoke for production
- [CLAUDE.md](CLAUDE.md) — tech-stack rationale, what NOT to use, and why

## Security

- `.env` is gitignored; secrets are never committed.
- `deploy/install.sh` creates `/etc/bip/.env` once with mode 600 and **never overwrites** an existing file (T-4-02 mitigation).
- Validation of required keys uses `grep -q` so values are never echoed to logs.
- Account-protection caps (Kelly fraction, stake variance) are enforced in [src/bip/core/picks/account_longevity.py](src/bip/core/picks/).

## License

Private project. Not licensed for redistribution.
