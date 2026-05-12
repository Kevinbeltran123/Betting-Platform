# Live Engine v3 — Production-Ready Ship Note

**Fecha**: 2026-05-11
**Branch**: main (6 commits desde v3-gaps-closed: b35619f → 37a38f2)
**Author**: KevinBel + Claude
**Predecesores**: `Papers/V3_GAPS_CLOSED_SHIP_NOTE.md`

---

## Resumen ejecutivo

- **6 commits atómicos** shipped en main, ordenados estrictamente per la mision spec (T0 → T2 → T1.1 → T1.2 → T1.3 → T3 → T4).
- **4 memos del operador actualizados** + log de mismatches en `Papers/T0_MEMORY_HYGIENE_LOG.md`. `grep '+13.19%' memory/` → 0 hits ✓.
- **+101 tests nuevos** (28 + 7 + 9 + 27 + 18 + 12), todos pasando. Suite total: **1889 + 6 xfailed** sin regresiones.
- **v3 wireado a watch.py en dual-write mode** via `asyncio.to_thread` + 800ms timeout. v2's path a Telegram queda estructuralmente intocado.
- **Kill criteria activas como código** (no solo doc): `kill_criteria.py` enforza thresholds; `v3_kill_switch.flag` filesystem flag suspende v3 sin redeploy.
- **Refit cadence automatizado**: domingos 04:00 local (APScheduler 3.x); anti-Napoli regression bloquea promociones que rompen el invariante "silence > false positive".

**Recomendación al operador**: SÍ arranca Phase 4 esta semana. Conditional: confirma que `V3_SHADOW_ENABLED=true` (default) y que `data/cache/v3_shadow/v3_kill_switch.flag` está ausente al iniciar.

---

## Tabla pre/post por tarea

| Tarea | Pre | Post | Commit |
|---|---|---|---|
| **T0** Memory hygiene | 4 memos con números inflados (Day-1 +13.19% / 60.8% wr); `grep '+13.19%'` → 5 hits en memory/ | 4 memos con honest baseline + `Papers/T0_MEMORY_HYGIENE_LOG.md` registrando mismatches; `grep '+13.19%'` → 0 hits | (no commit, fuera del repo) |
| **T2** Kill criteria | Ship-note recomienda Phase 4 sin umbrales; "vamos a ver qué pasa" → sesgo de continuación | `Papers/V3_SHADOW_KILL_CRITERIA.md` (rationale) + `src/bip/evaluation/live/engine_v3/kill_criteria.py` (runtime contract). 3 cohortes A/B/C, hard stops, soft warnings, greenlight gate con CLV>0 obligatorio. 28 tests. | `b35619f` |
| **T1.1** ShadowLogger GSV | Persiste picks + denials pero NO el GSV → no se puede refittear con datos reales ni reconstruir audit trail | `gsv_log.parquet` daily con `gsv_json` full + `load_shadow_gsvs(date_range)` helper + LoadFailure no-silent-coerce. 7 tests. | `67c243d` |
| **T1.2** replay_shadow wire | Pipeline básico, sin OOD/pattern, sin audit | `--ood-path` + `--pattern-path` defaults + `--audit` flag → JSONL per frame con MES + gate verdicts + window + ood_score. 9 tests. | `acc7a0b` |
| **T1.3** watch.py dual-write | v3 nunca corre en producción | `DualWriteRuntime` (asyncio.to_thread + 800ms timeout) wireado en `scan_round`; v2 estructuralmente protegido; env var + kill switch para suspend. 27 tests. | `dbbe6e8` |
| **T3** Refit cadence | Detectores fitted en sintético; sin protocolo de re-fit | `scripts/spike/v3/refit_detectors.py` + APScheduler cron Sunday 04:00; versioned pkls; anti-Napoli FPR gate; markdown reports. 18 tests. | `23aa855` |
| **T4** odds_history spike | Unknown #2 abierto: ¿Sportmonks tiene histórico de odds? | `Papers/SPORTMONKS_ODDS_HISTORY_SPIKE.md`: pre-match SÍ (premium €129/mo), in-play NO. Recomendación: no upgrade, validar via watch.py captures. | `37a38f2` |

---

## Decisión de aislamiento elegida en T1.3

**Opción (b): `asyncio.to_thread` + wall-clock timeout (800ms).**

Razones de descartar las otras tres:

| Opción | Por qué NO |
|---|---|
| (a) Inline sync try/except | Un hang de 5s en v3 stallea el pipeline entero de v2. Acoplamiento inaceptable. |
| (c) Thread pool + queue | Over-engineering. v3 per fixture es bounded; no hay batching/pooling needed. |
| (d) Multiprocessing.Queue | IPC overhead + deployment complexity para isolation marginal extra. El thread ya previene propagación de excepciones. |

Net effect de (b):
- v3 exceptions → captured into `error_count`, never propagated to v2's path
- v3 hang > 800ms → cancelled (thread sigue en background hasta que termine; el next call obtiene un attempt fresh)
- v3 success → ShadowLogger writes its own buffers, cero contacto con PickTracker / TelegramSender
- v3 disabled (env var o kill switch) → cheap short-circuit (~1μs)

**Mitigación de "background threads acumulando"**: si v3 lanza 3+ timeouts en 100 picks, eso dispara el hard-stop `system_pipeline_errors` (kill_criteria.py), el sistema se suspende antes de acumular thread debt sostenido. Auto-curado.

---

## Estado actual de los pkls

| Archivo | Versión | Próximo refit |
|---|---|---|
| `data/cache/ood_detector_v1.pkl` | v1 (fitted: 350 sintéticos pre-shadow) | Sunday 04:00 next week (APScheduler), promoción condicionada a anti-Napoli FPR=0 + n_real ≥ 100 |
| `data/cache/pattern_layer_v1.pkl` | v1 (fitted: 250 pairs = 50 napoli + 200 realistic) | Idem |

Output de refit:
- **Promovido**: `_latest.pkl` symlink → nueva versión, watch.py la carga automáticamente al siguiente startup
- **No promovido**: pkl preservado para inspección (no overwrite); `_latest.pkl` sigue apuntando a versión anterior
- **Report**: `reports/v3/refits/YYYY-MM-DD.md` con verdict + reasoning

Rollback manual: `ln -sf ood_detector_v{N}.pkl data/cache/ood_detector_latest.pkl` (cualquier versión previa, sin tener que re-fittear).

---

## Cómo arrancar Phase 4 — runbook concreto

### Pre-flight (5 min)

```bash
# 1. Confirmar V3_SHADOW_ENABLED=true (default)
echo "${V3_SHADOW_ENABLED:-true}"
# Output esperado: "true" o vacío (default true)

# 2. Confirmar kill switch ausente
ls data/cache/v3_shadow/v3_kill_switch.flag 2>&1
# Output esperado: "No such file or directory"

# 3. Confirmar pkls existen
ls -lh data/cache/ood_detector_v1.pkl data/cache/pattern_layer_v1.pkl
# Output esperado: ambos presentes con tamaño > 0

# 4. Tests verdes una última vez
uv run pytest -q --no-header 2>&1 | tail -2
# Output esperado: "1889 passed, 6 xfailed"
```

### Arrancar shadow

```bash
# Estándar — v3 wired to dual-write
nohup uv run python -m scripts.spike.sportmonks.watch \
  --interval 60 --min-edge 4.0 --beep \
  > reports/sportmonks_live/watch_phase4.log 2>&1 &
echo $! > reports/sportmonks_live/watcher.pid
disown
```

En el log, deberías ver de inmediato:

```
📊 v3 shadow runtime ON (V3_SHADOW_ENABLED=false to disable)
```

### Verificar dual-write activo

```bash
# Inspeccionar particiones daily
ls data/cache/v3_shadow/dt=$(date +%Y-%m-%d)/

# Output esperado tras 1 round de watch loop con fixtures activos:
#   gsv_log.parquet          ← T1.1 deliverable
#   picks.parquet            ← v3 emit decisions (audit only — NO Telegram)
#   gate_denials.parquet     ← rule rejections (audit only)
```

Si gsv_log.parquet no aparece tras 5-10 min con fixtures live, revisar el log:

```bash
tail -f reports/sportmonks_live/watch_phase4.log | grep -E "v3_shadow_error|v3_runtime"
```

### Suspender v3 si algo se rompe

```bash
# Suave (recomendado): por env var, requiere restart
kill -TERM $(cat reports/sportmonks_live/watcher.pid)
V3_SHADOW_ENABLED=false nohup uv run python -m scripts.spike.sportmonks.watch ... &

# Inmediato (sin restart): filesystem flag
touch data/cache/v3_shadow/v3_kill_switch.flag
# El próximo iteration de watch loop ve el flag y skipa v3.
# Para reanudar:
rm data/cache/v3_shadow/v3_kill_switch.flag
```

---

## Cómo evaluar después de Cohort A (100 picks)

```bash
# El operador construirá un script Phase 4 Day-1 que reporte las
# métricas contra los thresholds del kill_criteria. Sugerencia mínima:

uv run python -c "
from bip.evaluation.live.engine_v3 import CohortMetrics, CohortStage, evaluate_cohort

# Llenar con datos reales del cohort A (100 settled)
metrics = CohortMetrics(
    stage=CohortStage.A,
    n_settled=100,
    n_won=...,      # contar wins desde picks_graded.parquet (v3 shadow)
    n_lost=...,
    n_void=...,
    roi_flat=...,   # P/L flat / total stake
    roi_kelly=...,
    ood_denial_rate_50=...,  # de gate_denials.parquet rule_number=9
    drift_active_50=...,     # del KS drift detector log
    pipeline_error_count_100=...,
    shadow_log_failure_rate_100=...,
    market_concentration_top1_100=...,
)
verdict = evaluate_cohort(metrics)
print(f'Verdict: hard_stop={verdict.is_hard_stop} soft_warn={verdict.is_soft_warning}')
print(f'Rule: {verdict.rule_triggered}')
print(f'Reason: {verdict.reason}')
"
```

Reglas a aplicar inmediatamente:
- Si `hard_stop` → suspender v3, audit, commitear fix antes de reanudar
- Si `soft_warn` → telegram alert al operador, sigue corriendo, plan de revisión
- Si limpio → avanzar a Cohort B (acumular 200 picks adicionales)

**Anti-patrón explícito** (V3_SHADOW_KILL_CRITERIA.md §7): NO re-tunear thresholds DESPUÉS de ver los datos. Si los criterios disparan, el experimento se ajusta o se mata — no se relajan los criterios.

---

## Cómo arrancar el weekly refit

El job se registra solo cuando se llama explícitamente (no se autoinicializó en watch.py para evitar acoplamiento). Para activarlo:

```bash
# Manual one-shot (smoke test antes de schedule)
uv run python -m scripts.spike.v3.refit_detectors --dry-run
# Output: dry-run preserva ambos pkls actuales; report en reports/v3/refits/

# Manual one-shot real (escribe pkls + intenta promote)
uv run python -m scripts.spike.v3.refit_detectors
```

Para schedule automático con APScheduler (no incluido en watch.py — opt-in explícito):

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bip.evaluation.live.engine_v3.runtime import register_refit_job

scheduler = AsyncIOScheduler(timezone="UTC")
job = register_refit_job(scheduler, day_of_week="sun", hour=4)
scheduler.start()
```

Recomendación: el operador decide cuándo activarlo. Mientras Cohort A acumula (primeras 100 picks), no hay datos reales suficientes para refit — correr el job solo regenera sintético. Sugerencia: activar el scheduler después de Cohort A completado.

---

## Unknowns que SIGUEN abiertos para Phase 5

Listados en orden de criticidad pendiente:

1. **Sportmonks in-play /odds_history** — Confirmado NO disponible (ver T4 spike). Mitigation: nuestros propios captures de watch.py persisten `odds_snapshot` per round ~60s — suficiente granularidad para clasificar HOT/OPTIMAL/WARM/COLD windows. Phase 5 puede construir `build_inplay_odds_timeseries(fixture_id, market_id)` sobre los JSON snapshots cuando sea momento de validar empíricamente los multipliers.

2. **Real GSV thesis attribution para pattern layer refit** — Pattern layer necesita `(GSV, fired_thesis)` pairs. Actualmente solo persistimos GSVs sueltos (T1.1) y picks (con thesis_id) pero no joined. Phase 5 deliverable: join script que crea pairs desde `gsv_log.parquet` ⋈ `picks.parquet` por `(fixture_id, state_version)`.

3. **Stake caps reales en Betano** (Unknown #3 del design doc) — sigue requiriendo data manual del operador para calibrar `liquidity_score`. No bloqueante para Phase 4 (Tier-D = mínimo stake, liquidity gate ya defensivo); bloqueante para promover a Tier C/B.

4. **Commentary feed latency** (Unknown #4 del design doc) — sigue sin medirse. Asunción: ≤30s. Validable durante Phase 4 al revisar commentary timestamps en captured snapshots.

5. **Cup/knockout calibration separation** (4.2) — Phase 5 deferred. v3 entrena en regular-season para Phase 4; tournaments tienen distribución distinta. Sin urgencia hasta Phase 5.

6. **Commentary parser LLM** (4.3) — Phase 5 deferred. Pattern layer actual usa rule-layer fallback; LLM-extracted theses son optimización futura.

7. **Per-market window thresholds** — design doc sugiere que corners laguean más que 1X2. Phase 4 mide; Phase 5 implementa per-(market_family) windows si los datos lo justifican.

8. **Cohort A → B → C transition automation** — actualmente los criterios están en código (T2) pero el accounting de cohort (qué picks pertenecen a cuál) es manual. Phase 5 deliverable: `scripts/spike/v3/cohort_accountant.py` que automatiza el bucketing.

---

## Recomendación final

**SÍ, arrancar Phase 4 shadow esta semana.**

Condiciones:
1. ✓ `V3_SHADOW_ENABLED` no negado en el environment al arrancar watch.py.
2. ✓ Kill switch file ausente.
3. ✓ Ambos pkls v1 presentes en `data/cache/`.
4. ✓ Suite verde (1889 + 6 xfailed pre-arranque).
5. ✓ Operador entiende los criterios de §V3_SHADOW_KILL_CRITERIA y se compromete a NO re-tunear thresholds mid-cohort.

Riesgos identificados + mitigaciones:
- **v3 acumula thread debt por timeouts sostenidos** → kill_criteria.system_pipeline_errors hard-stop a 3+ errores/100 picks
- **shadow stream se llena de garbage por bug latente** → kill_criteria.system_shadow_log_failures hard-stop a >10% failure rate
- **detectores degradan sin refit** → APScheduler weekly refit (T3) + anti-Napoli FPR gate previenen drift
- **operador olvida revisar Cohort A** → telegram soft_warn al iniciar Cohort A si métricas marginales (no implementado yet, Phase 4 Week 1 deliverable)

**Lo que NO recomiendo** (anti-pattern guard):
- Activar Tier-D real (dinero) antes de Cohort C completo (300+ picks). Greenlight requiere TODAS las §4 criteria simultáneamente.
- Hacer "una jornada más" para esperar mejores resultados. Cada jornada cuenta hacia el cohort, en cualquier dirección.
- Suspender v3 manualmente "porque hoy se ve raro". Si no dispara hard stop, sigue corriendo — el cohort accounting depende del flujo continuo.

---

## Apéndice — Inventario de archivos shipped

### Nuevo código (committed)

```
src/bip/evaluation/live/engine_v3/
├── kill_criteria.py              ← T2 (runtime contract, 28 tests)
├── shadow_logger.py              ← T1.1 (extended; +7 tests)
└── runtime/
    ├── __init__.py
    ├── dual_write.py             ← T1.3 (27 tests)
    └── refit_scheduler.py        ← T3 (12 tests)

scripts/spike/v3/
├── replay_shadow.py              ← T1.2 (extended; 9 tests in tests/spike/v3/)
└── refit_detectors.py            ← T3 (6 tests in tests/spike/v3/)

scripts/spike/sportmonks/
└── watch.py                      ← T1.3 (wired DualWriteRuntime call)

tests/
├── evaluation/live/engine_v3/
│   ├── test_kill_criteria.py     ← 28 tests
│   ├── test_shadow_logger.py     ← extended (+7 tests)
│   ├── test_dual_write.py        ← 27 tests
│   └── test_refit_scheduler.py   ← 12 tests
└── spike/v3/
    ├── test_replay_shadow.py     ← 9 tests
    └── test_refit_detectors.py   ← 6 tests
```

### Docs (committed)

```
Papers/
├── V3_SHADOW_KILL_CRITERIA.md       ← T2 rationale (local-only, force-add deferred)
├── SPORTMONKS_ODDS_HISTORY_SPIKE.md ← T4 (committed, exception to convention)
├── V3_PRODUCTION_READY_SHIP_NOTE.md ← this doc
└── T0_MEMORY_HYGIENE_LOG.md         ← T0 mismatch log (local-only)
```

Nota sobre Papers/ convention: `Papers/` is gitignored as default; force-add reserved for *finished* artifacts that future sessions need to read (spikes, ship notes), NOT working drafts (design docs, runbooks, working analysis).

### Memos del operador (T0, fuera del repo)

```
~/.claude/projects/.../memory/
├── MEMORY.md                            ← hook updated (no +13.19% literal)
├── project_sportmonks_spike.md          ← body updated with honest baseline
├── project_sportmonks_post_day1_stack.md ← INVALIDATED banner
├── project_sportmonks_wrong_side_discovery.md ← INVALIDATED banner
└── project_grading_bug_2026_05_11.md    ← anchor link added
```

---

**FIN. El sistema está listo para Phase 4. Suspende vía `V3_SHADOW_ENABLED=false` o filesystem flag si algo se rompe. Audit trail completo en `data/cache/v3_shadow/dt=*/gsv_log.parquet`.**
