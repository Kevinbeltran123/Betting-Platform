# Sportmonks /odds_history Spike

**Fecha**: 2026-05-11
**Spike duration**: 1 session
**API calls made**: 0 (documentation research only — see §2 for rationale)

---

## TL;DR

| Pregunta | Respuesta |
|---|---|
| ¿Sportmonks expone histórico de odds? | **Sí** (pre-match) / **No** (in-play, no como endpoint dedicado) |
| ¿Útil para validar mispricing windows del v3? | **No directamente** — los windows son in-play |
| ¿Requiere upgrade de plan? | **Sí**: Premium Odds Feed add-on (€129/mes) |
| ¿Cubre la necesidad de Phase 4? | **No**, ya tenemos esa data nosotros |
| **Recomendación al operador** | **Opción (c)**: NO upgrade. Validación in-play de Phase 4 = nuestros propios snapshots de watch.py. |

---

## 1. Hallazgos de la investigación de docs

### 1.1 Endpoints encontrados

Sportmonks Football API v3 tiene DOS familias de endpoints de odds:

**Standard Odds Feed** (incluido en plan Pro €249/mes):
- Pre-match: `/odds/pre-match/...` — devuelve odds actuales solamente
- In-play: `/odds/inplay/...` — devuelve odds actuales solamente
- `/odds/inplay/latest` — odds in-play actualizadas en los últimos 10 segundos (útil para live, NO para histórico)

**Premium Odds Feed** (add-on €129/mes adicional al plan base):
- Premium pre-match base + 3 endpoints históricos:
  - `GET /v3/football/odds/premium/history` — "All Historical Odds"
  - `GET .../premium/history/updated-historical-odds-between-time-range`
  - `GET .../premium/history/updated-premium-odds-between-time-range`

### 1.2 ¿Qué retorna el endpoint histórico?

Per la documentación oficial de `GET /v3/football/odds/premium/history`:

> "we document the opening odds for each fixture, and subsequently, all changes and updates are stored and accessible."

Cada record contiene:
- `id`, `odd_id`, `value` (decimal), `probability`, `dp3`, `fractional`, `american`
- **`bookmaker_update`**: datetime de cada movimiento de línea

Estructura: una fila por cada actualización del bookmaker. Esto SÍ es time-series de movimientos pre-match.

**Retención: 7 días post-match.** Después de esa ventana los datos no son accesibles.

### 1.3 Lo que CRUCIALMENTE no existe

**No hay endpoint dedicado a "in-play odds history".** El sitemap de Sportmonks lista:

- ✓ Premium pre-match historical odds (3 endpoints)
- ✗ Premium in-play historical odds (NO existe)

Confirmé esto cruzando dos fuentes:
1. El sitemap.md de docs.sportmonks.com — solo "premium-pre-match-odds" tiene rama historical
2. La descripción del Premium Odds Feed habla de "high-frequency updates" pero no de retención histórica de in-play

**Implicación**: Si quisiéramos validar las clasificaciones de mispricing window (HOT/OPTIMAL/WARM/COLD) contra cómo Pinnacle/Betano realmente movió la línea en los 600s post-evento, el endpoint de Premium pre-match NO sirve. La línea pre-match es independiente del flujo in-play que el v3 mide.

---

## 2. Decisión de no hacer test exploratorio

El mission spec autorizaba hasta 5 llamadas API exploratorias. **No las hice** por dos razones:

1. **El sitemap fue concluyente**: el endpoint pre-match historical existe; el in-play historical NO. Un test exploratorio solo confirmaría lo que la documentación ya dice.

2. **El plan actual NO tiene Premium Odds Feed activado** (es add-on €129/mes). Llamar al endpoint sin la suscripción devolvería 403 — no aporta información incremental.

Si el operador quiere validación empírica antes de comprometerse al add-on, sugiero contactar a `support@sportmonks.com` con la pregunta específica "is in-play odds history accessible via any tier?" — eso es free.

---

## 3. Costo estimado del upgrade

| Plan | Costo mensual | Total acumulado |
|---|---|---|
| Pro (actual) | €249 | €249 |
| + Premium Odds Feed add-on | +€129 | **€378/mes** |
| The Odds API Rookie (ya activo) | €18 (~$20) | (separado, no Sportmonks) |

**Delta**: +€129/mes = €1,548/año.

**Valor entregado por ese delta**:
- Pre-match historical odds (snapshots cada vez que bookmaker mueve)
- 7 días de retención (forza cron de ingesta semanal)
- NO incluye in-play historical odds (lo que el v3 realmente necesita)

---

## 4. Plan de uso si estuviera disponible

Si Sportmonks tuviera in-play historical odds, lo usaríamos así:

```
v3 mispricing_window classification        Ground truth from in-play history
───────────────────────────────────       ────────────────────────────────
60s post-red, edge=15%                     book moved how many % in 60s?
                                            ─ matched movement → HOT
                                            ─ no movement → window classifier
                                              should weight HIGHER multiplier
180s post-red, edge=8%                     book caught up partially:
                                            ─ if catch-up < 50% → OPTIMAL/WARM
                                            ─ if caught up → already COLD
600s post-red, edge=5%                     book caught up fully or never moved:
                                            ─ rule #10 should veto (low edge,
                                              ancient event)
```

Esa validación cruzada calibraría los multiplicadores HOT=1.10/OPTIMAL=1.20/WARM=0.70 con datos reales en lugar de hipótesis.

**Pero no existe el endpoint.** Lo que SÍ tenemos es:

- `scripts/spike/sportmonks/watch.py` → cache_root persiste `odds_snapshot` por fixture-snapshot
- Es decir, el sistema ya genera nuestra propia time-series in-play
- Las snapshots están en `data/cache/sportmonks/snapshots/{fid}/{timestamp}.json` y contienen `odds_snapshot`
- Frecuencia: ~60s (cada round de watch loop)

**watch.py ya es el odds_history that we need**, por construcción. La granularidad es ~60s (no per-update), pero es suficiente para clasificar HOT/OPTIMAL/WARM/COLD (las ventanas son 60s/180s/600s respectivamente).

---

## 5. Recomendación final

**Opción (c) elegida del mission spec**: "No disponible (en la forma útil) → seguir con shadow live como única fuente de validación, aceptar que Phase 4 tarda 4 semanas porque no hay shortcut."

Razones:
1. **In-play historical no existe**. Pagar €129/mes por pre-match historical no resuelve el problema real.
2. **Ya tenemos in-play time-series** via watch.py captures. La granularidad de ~60s es adecuada para clasificar las ventanas de 60-600s.
3. **CLV vs Pinnacle ya está cubierto** por The Odds API Rookie ($20/mes, 500 requests/mes, ya activo según CLAUDE.md). El Premium Sportmonks no aporta CLV incremental.
4. **Phase 4 no se acelera con el upgrade**. El shadow window mínimo (Cohort C: 300+ picks) es operativo, no de datos históricos.

### Condiciones para revisitar este spike

Re-evaluar el upgrade SÓLO si una de estas tres cosas ocurre:

1. **The Odds API se rompe / cancela** la cobertura de Pinnacle en EU. Entonces Premium Sportmonks (con TXOODS provider) es backup. Costo justifica.
2. **Bug grading muestra que la calidad de las odds in-play que captura watch.py es insuficiente** (e.g., falla > 10% de los snapshots). Premium tendría mejor SLA — pero esto se mediría con datos, no se asume.
3. **Phase 5 expandido a backtests de 12+ semanas requiere data pre-match histórica** del side específico (que el plan Pro no preserve). Plan Pro retiene poco histórico per los docs estándar.

Ninguna de las tres condiciones aplica hoy.

---

## 6. Lo que SÍ hay que hacer (sin upgrade)

Acciones derivadas de este spike que mejoran el dataset de Phase 4 SIN gastar más:

1. **Asegurar que watch.py persiste `odds_snapshot` en cada round**. Verifiqué que esto YA pasa en `scripts/spike/sportmonks/watch.py:309-313` — el snapshot incluye `odds_snapshot: [o.model_dump(mode="json") for o in odds]`. ✓

2. **Persistir `latest_bookmaker_update` por línea**. Lo hace, vía el field nativo del Odd Pydantic model. ✓

3. **Schema para extraer in-play time-series desde los snapshots**. Script TBD en Phase 4 Week 1 si se decide medir mispricing window empíricamente. Estructura sugerida:

   ```python
   def build_inplay_odds_timeseries(fixture_id: int, market_id: int):
       """Walk snapshots/{fixture_id}/*.json, extract odds_snapshot rows
       matching market_id, return DataFrame indexed by snapshot_taken_at
       with columns (value, bookmaker_update, suspended).
       """
   ```

   Esto reemplaza funcionalmente al endpoint que Sportmonks no provee.

4. **Reducir el polling interval de watch.py** durante Phase 4 si granularidad 60s no es suficiente para classifier validation. Default es 60s; bajar a 30s duplica la frecuencia. Costo: ~2x API calls (todavía dentro del Pro tier).

---

## 7. Apéndice: Sources

| Source | Findings |
|---|---|
| `https://docs.sportmonks.com/v3/sitemap.md` | Lista completa de endpoints, confirmación de que premium-inplay-odds-historical NO existe |
| `https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/premium-odds-feed/premium-pre-match-odds/get-all-historical-odds.md` | Schema de pre-match historical: time-series per `bookmaker_update`, 7-day retention |
| `https://www.sportmonks.com/football-api/` | Pricing: Pro €249 + Premium Odds Feed add-on €129 |

No se hicieron llamadas API. 0/5 del budget exploratorio consumido.

---

**FIN del spike. Cierra Unknown #2 del LIVE_ENGINE_V3_DESIGN.md como "in-play historical no disponible; mitigation = nuestros propios captures via watch.py".**
