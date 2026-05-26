# Team Style Profiler (TSP) — Design Document

**Locked 2026-05-24.** Diseño del sistema de perfilamiento estilístico para
WC2026, independiente de lock_v1.

**Filosofía operativa.** En vez de predecir matemáticamente al ganador
(donde lock_v1 ya hace su trabajo), perfilar el ADN de juego de cada
equipo y cruzar perfiles para predecir mercados de **estilo** (BTTS,
O/U goals, córners, tarjetas, AH, 1X2, live). Esto reconoce explícitamente
que predecir el ganador es difícil; el valor está en patrones recurrentes
del estilo de juego.

---

## 1. Alcance final (locked)

| Dimensión | Decisión | Razón |
|-----------|----------|-------|
| Data sources | API-Football Pro + StatsBomb open data | Cubierto en stack actual; no Sportmonks |
| Era para perfilar | Desde **Enero 2023** (ciclo WC2026) | Equipo actual, no histórico |
| Filtro DT | **Solo partidos con DT exacto que dirigirá WC2026** | Si DT distinto = otro equipo táctico |
| Mínimo partidos | **≥10 con DT actual = perfil válido** | Bajo de eso = flag rojo "no apostar" |
| Segmentación | **Perfil general + sub-perfil por confederación rival** | Permite "México vs CAF" específico |
| Cobertura parcial | Si un equipo flag rojo → **usar cohorte de su confederación** | Cabo Verde sin perfil = perfil CAF promedio |
| Mercados | BTTS, O/U goals (2.5, 3.5), O/U córners (9.5), O/U tarjetas (4.5), 1X2, Asian Handicap, **live** | Sin HT-FT combos |
| Edge threshold | **+3% uniforme** sobre cuotas Pinnacle/Betano | Simple para empezar |
| Integración lock_v1 | **Independiente** — no se mezclan | TSP es capa nueva |
| Live betting | **Prioridad alta** — diseñar desde inicio | El operador puede monitorear durante WC |

---

## 2. Team Style Vector (TSV) — Schema

Para cada equipo del Mundial 2026 perfilable, calcular un vector con
~20 dimensiones. Cada dimensión es **media + intervalo de confianza
bootstrap (95%)** sobre la ventana DT-actual.

### 2.1 Dimensiones ofensivas
| Feature | Descripción | Mercado que predice |
|---------|-------------|---------------------|
| `goals_for_per_match` | Goles que mete promedio | O/U goals, AH |
| `goals_for_per_15min` | Distribución de goles por cuarto de hora: 0-15, 15-30, 30-45, 45-60, 60-75, 75-90 | Live + HT goals + total goals |
| `shots_per_match` | Tiros totales | O/U goals (proxy) |
| `shots_on_target_per_match` | Tiros a puerta | O/U goals + BTTS |
| `shots_on_target_ratio` | SoT / shots = eficiencia ofensiva | BTTS, equipo marca |
| `corners_for_per_match` | Córners a favor | O/U córners |
| `possession_avg` | Posesión promedio (%) | Ritmo del partido, AH |
| `xg_for_per_match` (cuando disponible vía StatsBomb) | xG generado | O/U goals, edge sobre cuota |

### 2.2 Dimensiones defensivas
| Feature | Descripción | Mercado que predice |
|---------|-------------|---------------------|
| `goals_against_per_match` | Goles recibidos promedio | O/U goals, AH |
| `goals_against_per_15min` | Goles recibidos por cuarto de hora | Live, equipo concede temprano/tarde |
| `clean_sheet_rate` | % partidos sin recibir gol | BTTS (no), under |
| `shots_against_per_match` | Tiros recibidos | BTTS |
| `corners_against_per_match` | Córners en contra | O/U córners |
| `offsides_against_per_match` | Offsides cometidos por rival → proxy de presión defensiva alta | Característica táctica |

### 2.3 Dimensiones de "carácter del partido"
| Feature | Descripción | Mercado que predice |
|---------|-------------|---------------------|
| `fouls_per_match` | Faltas cometidas | O/U tarjetas |
| `yellow_cards_per_match` | Amarillas promedio | O/U tarjetas |
| `red_cards_rate` | Rojas por partido (raro, baja n) | Live tarjetas |
| `btts_rate` | % partidos BTTS | Mercado BTTS |
| `over_25_rate` | % partidos con +2.5 goles | Mercado O/U 2.5 |
| `over_35_rate` | % partidos con +3.5 goles | Mercado O/U 3.5 |
| `mean_total_goals` | Goles totales del partido (for + against) | O/U goals |

### 2.4 Metadata del perfil
| Field | Descripción |
|-------|-------------|
| `coach_name` | DT actual (canonical name) |
| `coach_start_date` | Fecha contratación |
| `n_matches` | Partidos con DT actual desde Ene 2023 |
| `flag` | `green` (≥10 partidos) / `red` (<10) |
| `confidence` | Width promedio de CIs (proxy de incertidumbre) |
| `last_updated` | Timestamp del último refresh del perfil |

### 2.5 Sub-perfil por confederación rival

Para cada confederación rival (CONMEBOL, UEFA, CAF, AFC, CONCACAF, OFC),
si hay ≥3 partidos del DT actual contra esa confederación:
- subset de las features anteriores
- `n_matches_vs_conf` (debe ser ≥3 para reportar)

Si <3 partidos: sub-perfil ausente; fallback al perfil general.

---

## 3. Arquitectura del módulo

```
src/bip/evaluation/tournaments/team_style_profiler/
├── __init__.py
├── ingest.py                 # API-Football client extension
├── coach_history.py          # Mapeo equipo → DT actual + fecha
├── tsv_schema.py             # Pydantic model TeamStyleVector
├── tsv_calculator.py         # Cálculo de las ~20 métricas desde API-Football
├── tsv_validator.py          # Flag rojo / verde + threshold ≥10
├── confederation_cohort.py   # Perfil promedio por confederación (fallback)
├── cross_team_predictor.py   # Cruza dos TSVs → probs por mercado
├── value_detector.py         # Compara contra cuotas → alerta edge ≥+3%
├── live/                     # Pipeline live (Fase 6)
│   ├── state_tracker.py      # Pull estado del partido en tiempo real
│   └── conditional_predictor.py  # Re-pred dado estado live
└── pipeline.py               # Orquestación end-to-end
```

---

## 4. Pipeline end-to-end (operativo)

### Pre-match (24-48h antes del partido):
```
1. ingest.fetch_team_matches(team, since=2023-01-01)
2. coach_history.filter_to_current_coach(matches, team)
3. tsv_validator.flag(matches)  # green/red
4. IF red: skip team; use confederation_cohort fallback
5. tsv_calculator.compute(matches)  # → TeamStyleVector
6. cross_team_predictor.predict(home_tsv, away_tsv)
   → dict de probs: btts=0.62, over_2_5=0.71, ...
7. value_detector.detect(probs, pinnacle_odds, threshold=0.03)
   → list de alertas con (mercado, prob, cuota, edge, decisión)
```

### Live (durante el partido):
```
1. state_tracker.poll_match(fixture_id)  # cada 30-60s
2. extract_state: minuto actual, score, tarjetas, córners
3. live.conditional_predictor.predict(home_tsv, away_tsv, current_state)
   - Combina: TSV pre-match + ajuste por estado actual
   - Usa también HT_LIVE_TABLE cuando se llega al HT
4. value_detector.detect_live(probs, live_odds)
   → alerta vía Telegram (o stdout) cuando edge ≥+3%
```

---

## 5. Validación y backtest

### 5.1 Backtest sobre torneos pasados
Aplicar el TSP retroactivamente a:
- **WC2022**: validación cross-tournament; perfilar equipos con DT en
  ese momento, predecir mercados, comparar contra cuotas históricas
- **AFCON 2023**: validar para equipos africanos
- **Copa América 2024**: validar para CONMEBOL
- **Euro 2024**: validar para UEFA

Métricas clave a reportar:
- Brier score por mercado (BTTS, O/U, córners, tarjetas, 1X2, AH)
- ROI flat sobre alertas (cuántos edge ≥+3% serían profitable)
- Calibración (ECE) por confederación
- Cobertura: % de partidos con perfil completo

### 5.2 Dry-run pre-WC2026
- **Copa Oro 2025** (CONCACAF, junio-julio 2025): testear con USA/MEX/CAN
  que son hosts WC2026
- **Amistosos pre-WC2026** (marzo-mayo 2026): testear con equipos
  europeos en sus FIFA windows
- Solo después del dry-run con ROI positivo → activar live durante WC

---

## 6. Costos y rate limits

### API-Football Pro ($79/mes)
- Plan Pro: 300 requests/min, 7500/day
- Costo por equipo perfilado (refresh completo): ~80 calls
  - 1 fixtures list call
  - ~30 stats por partido × ~25 partidos
  - ~10 lineup calls
- 48 equipos perfilados completos = ~3840 calls
- Refresh diario durante WC2026 = ~1000 calls/día → bien dentro del límite

### StatsBomb open data (gratuito, CC BY-NC)
- Ya cacheada en `data/cache/statsbomb/`
- Usado para xG (no disponible en API-Football)

### Almacenamiento
- ~50 KB por TSV
- 48 equipos × 50 KB = 2.4 MB (despreciable)
- Backtest results: ~5-10 MB
- **Total <50 MB**

---

## 7. Timeline ejecutable

| Fase | Semanas | Entregable |
|------|---------|------------|
| 0 | (hoy) | Este documento + alcance lockeado |
| 1 | 1-2 | TSV schema + ingest client + coach_history |
| 2 | 2-3 | Cálculo de TSV completo + tests |
| 3 | 3-4 | Validador (flag rojo/verde) + sub-perfiles por confederación |
| 4 | 4-5 | Cross-team predictor + tests |
| 5 | 5-6 | Detector de valor + integración con cuotas Pinnacle |
| 6 | 6-8 | Pipeline live (state tracker + conditional predictor) |
| 7 | 8-9 | Backtest histórico + ajustes de calibración |
| **8** | **9-10** | Dry-run Copa Oro 2025 |
| 9 | 10-12 | Iteración post-dry-run + ajustes finales |
| **10** | **>12** | Producción para WC2026 (junio 2026) |

**Holgura**: ~2 meses entre el fin del desarrollo y el inicio del Mundial.
Suficiente para ajustes basados en amistosos pre-tournament (marzo-mayo 2026).

---

## 8. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| API-Football no tiene granularidad suficiente para X feature | Media | Para esas features, usar StatsBomb open data como complemento (solo 6 torneos pero alta calidad) |
| Equipos chicos (Cabo Verde, Curacao) con <10 partidos del DT actual → quedan fuera | Alta (esperado) | Cohorte de confederación como fallback (decisión locked) |
| Cuotas históricas no disponibles para backtest | Media | Usar The Odds API histórico ($20/mes Rookie cubre); fallback: simular cuotas Pinnacle desde Brier |
| Live betting requiere monitoreo durante partidos | Alta | Decisión operador: tiene tiempo para monitorear durante WC. Pipeline emite alertas vía Telegram (ya tenemos bot v2 deployado) |
| Cambio de DT durante el Mundial (ej. técnico despedido tras MD1) | Baja | Re-perfilar inmediatamente; flag rojo hasta que tenga ≥3 partidos nuevos del DT interino |
| El sistema "no apuesta" en muchos partidos | Media | **Esto es feature, no bug.** Filosofía: apostar solo donde hay evidencia. Aceptar que ~20-30% de partidos WC quedarán sin pick |

---

## 9. Métricas de éxito (qué define que funcionó)

### Backtest histórico
- ROI flat ≥+5% sobre apuestas con edge ≥+3% detectado
- Brier score por mercado dentro de gate de cada mercado:
  - BTTS: Brier ≤ 0.235
  - O/U 2.5: Brier ≤ 0.230
  - 1X2: Brier ≤ 0.215
  - Córners O/U: Brier ≤ 0.250

### WC2026 (post-tournament)
- ROI flat ≥+3% sobre todas las apuestas emitidas
- CLV vs Pinnacle ≥+2% promedio
- Cobertura ≥40% de partidos del Mundial (≥30 de 80 partidos con pick)
- 0 alertas falsas catastróficas (ej: apostar al equipo con cambio de DT no detectado)

---

## 10. Open questions (a resolver durante implementación)

1. **¿Cómo manejar partidos con prórroga / penales?** Estilo de equipos puede
   variar en knockouts (más defensivos). Decisión propuesta: subir un flag
   "tournament_stage" en TSV (group / knockout) y testear si hay diferencia.

2. **¿Refresh frecuency del perfil?** Propuesto: diario durante FIFA windows,
   semanal en resto. Antes de cada partido del Mundial: refresh forzado.

3. **¿Pesos temporales en el TSV?** ¿Partido más reciente cuenta más?
   Propuesto: exponential decay con half-life de 6 meses. Validar en backtest.

4. **¿Cuotas Pinnacle vs Betano para el detector de valor?** Pinnacle = más
   eficiente, menos juice. Betano = lo que usa el operador. Propuesto: usar
   Pinnacle para detectar valor, ejecutar en Betano.

---

## 11. Próximo paso inmediato

**Después de aprobar este documento, Fase 1 (semana 1-2):**

1. Crear `src/bip/evaluation/tournaments/team_style_profiler/` con esqueleto
2. Extender `src/bip/data/api_football/` (ya existe) con métodos para:
   - `get_team_fixtures(team_id, since_date)`
   - `get_fixture_statistics(fixture_id)`
   - `get_fixture_events(fixture_id)`
3. Construir `coach_history.py` con mapeo manual de DT actual por
   selección del Mundial 2026 (datos públicos de Transfermarkt)
4. Implementar `tsv_schema.py` (Pydantic v2) con las ~20 dimensiones
5. Tests para los 3 módulos anteriores

---

## Provenance

- Decisiones lockeadas via AskUserQuestion 2026-05-24 (4 rondas de preguntas)
- Memoria relacionada: [[wc2026-operational-signals]], [[wc2026-historical-patterns-v2]]
- Predecesor: patterns_v2 session 1 + 4 iteraciones (ya shipped)
- Próximo paso: Fase 1 implementation
