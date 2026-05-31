# Roadmap — Enriquecimiento del flujo de análisis (5 conceptos)

> **Estado: 5/5 FASES ENTREGADAS (2026-05-31).** 8 commits atómicos en `main`
> (`179f780`..`08f99f8`). Resumen de cierre al final del documento.
>
> Cada fase queda especificada con: qué información se necesita, para qué, de dónde se consigue, y
> cómo se integra al flujo actual.
>
> **Principios rectores:**
> - Enfoque **analista** ([[feedback_analyst_approach]]): evidencia que el operador interpreta, no scores automáticos.
> - **Lente de mercado** ([[feedback_market_selection_low_collapse]]): priorizar mercados que el bookie NO colapsa (tarjetas, córners, faltas, props, AH no-redondo, next-to-score).
> - **Honestidad de datos**: marcar cobertura. StatsBomb = solo corpus (8 selecciones WC2026 sin datos). API-Football = universal pero sin event-level (presiones).
>
> Conecta con la referencia [[reference_playing_styles_by_formation]] y el flujo `39_analyze`.

---

## Leyenda de fuentes de datos

| Fuente | Qué da | Cobertura | Caveat |
|---|---|---|---|
| **API-Football** (`/fixtures/players`) | Por jugador/partido: fouls drawn+committed, duels won/total, dribbles success/past, tackles, cards, penalty | Universal (incl. selecciones, verificado) | Por partido; agregar a per-90 nosotros |
| **API-Football** (`/fixtures/statistics`) | Por equipo/partido: shots, posesión, córners, faltas, offsides, tarjetas, `expected_goals` | Universal | Agregado del partido, **NO** split por marcador |
| **API-Football** (`/fixtures/events`) | Timeline: goles (minuto), tarjetas, subs, VAR, penaltis | Universal | Para reconstruir estado de partido por minuto |
| **API-Football** (`/fixtures?referee=`) | Fixtures de un árbitro → derivar sus stats | Universal | **No hay endpoint de stats de árbitro**: se agrega a mano |
| **StatsBomb open-data** | Event-level: presiones, pass-under-pressure, set-piece, shot xG, freeze frames, fouls won | **Solo corpus** WC18/22, Euro20/24, Copa24, AFCON23 | 8 selecciones WC2026 sin cobertura |
| **lock_v1 predictor** (xg_blended) | Brecha de fuerza favorito/underdog | Universal | Ya existe; insumo para "quién persigue" |
| **Transfermarkt** | Lesiones, valor de plantilla | Universal | Ya integrado |

**Puntos de integración del flujo actual** (referencia para todas las fases):
- `intel_io.py` — `build_match_intel` (orquestador, 222-264), loaders por capa.
- `intel.py` — dataclass `MatchIntel` (118-135), `assemble_intel` (240-302).
- `tactical_identity.py` — `TacticalIdentity` (78-104, dims: press_intensity/set_piece/finishing), `MatchupRead` (293-307, tempo/game_shape/market_leans).
- `player_props.py` — `PlayerPropProfile` (45-79; tiene `fouls_committed_per90`, **NO** `fouls_drawn`).
- `player_advanced.py` — `PlayerAdvancedProfile` (aerials, dribbled_past, tackles).
- `tsv_schema.py` — vector de equipo (`xg_per90`, etc.).
- Live Engine v3 — regime bucketing por estado de partido (ya existe).

---

## Orden de fases (racional)

Priorizado por **valor de mercado × factibilidad de datos**:

| Fase | Mejora | Por qué este orden |
|---|---|---|
| **1** | Mapa de duelos + faltas recibidas | Mayor valor (cards/faltas/penalti) + datos **universales** en API-Football + reusa weak_links/creators existentes. Lo menos bloqueado. |
| **2** | Guion de partido (game-state) | Alto valor (córners con respaldo empírico) + MVP usa la brecha de fuerza que YA tienes (universal); enriquecimiento con StatsBomb. Puente al Live Engine. |
| **3** | Perfil de árbitro ampliado | Extiende el card-prior existente; derivable de API-Football; autocontenido. |
| **4** | Regresión finishing/varianza | Sharp pero riesgo de small-n; xG ya disponible. Cuidado estadístico. |
| **5** | Press-resistance vs presión | El más bloqueado (solo StatsBomb event-level, sin equivalente API; corpus-limitado). Va último. |

---

## FASE 1 — Mapa de duelos individuales + faltas recibidas

**Objetivo.** Pasar del weak-link genérico a **duelos concretos** por zona/banda, y añadir el dato que hoy falta: faltas que **provoca** cada jugador.

**Qué información se necesita.**
- Por jugador: **fouls drawn** (faltas recibidas), dribbles completados/intentados, duels won/total, aerial won/lost (ya parcial), zona/banda de acción.
- Del rival: weak-link por banda (ya derivado en `weak_links`) y altura de línea (ya en `AdvancedShape`).

**Para qué.**
- **Tarjetas del rival**: su regateador que provoca muchas faltas × tu lateral flojo → faltas/amarillas contra ese lateral.
- **Mercado de faltas** (props) y **penaltis**: faltas recibidas en zonas peligrosas.
- **Remate de cabeza / córner**: mismatch aéreo atacante vs defensor débil.

**De dónde.**
- **API-Football `/fixtures/players`** → `fouls.drawn`, `dribbles.success/past`, `duels.won/total` por jugador y partido (universal, incl. selecciones). Agregar a per-90 como ya se hace con props.
- StatsBomb event-level como refuerzo (fouls won + ubicación) para los equipos del corpus.

**Cómo se integra.**
- Extender `PlayerPropProfile` (`player_props.py`) con `fouls_drawn_per90` (+ opcional `dribbles_completed_per90`).
- Nueva derivación `DuelMatchup` en `intel.py`: cruza dribblers/amenazas aéreas de un equipo vs `weak_links` del otro → lista de duelos prioritarios.
- Añadir `duel_matchups` a `MatchIntel`; surfacear en el dossier junto al prop board; alimentar el **card-prior** del árbitro (Fase 3 lo amplifica).

**Dependencias.** Ninguna (reusa weak_links/creators). **Cobertura.** Universal. **Riesgo.** Matching de nombres cross-source (ya tienen algoritmo conservador).

---

## FASE 2 — Guion esperado del partido (game-state dynamics)

**Objetivo.** Proyectar **cómo evoluciona el partido por marcador** y quién termina persiguiendo — el contexto que da sentido a todas las demás señales.

**Qué información se necesita.**
- **(MVP)** Brecha de fuerza favorito/underdog → quién se espera que domine y quién persiga.
- **(Enriquecimiento)** Perfil de cada equipo **por estado** (ganando/empatando/perdiendo): posesión, shots, córners, faltas, línea defensiva.

**Para qué.**
- **Córners** (la señal con mejor respaldo empírico: el que persigue gana córners → un gol temprano del favorito invierte el favorito de córners).
- **Over/Under** vía guion (favorito domina → rival se mete en bloque bajo → under + córners del favorito).
- **Hipótesis pre-partido para el Live Engine v3**: el guion esperado es lo que el live confirma o rompe.

**De dónde.**
- **MVP**: `lock_v1` (brecha de fuerza, ya existe, universal) + `patterns_v2` (favorite-xG-gap).
- **Enriquecimiento (split por estado)**: **StatsBomb** event-level tagueado con marcador (offline, solo corpus). API-Football **no** da split por estado; lo máximo es reconstruir la línea de tiempo desde `/fixtures/events` (minutos de gol) como proxy grueso universal.

**Cómo se integra.**
- Nueva capa `GameScriptProjection` derivada en `intel_io.py` (brecha de fuerza + TSV).
- Enriquecer `MatchupRead.game_shape`/`tempo` (`tactical_identity.py`) con el guion proyectado.
- Exponer en `MatchIntel`; pasar como **prior** al regime bucketing del Live Engine v3 (puente pre-partido ↔ live).

**Dependencias.** Ninguna para el MVP. **Cobertura.** MVP universal; split-por-estado solo corpus. **Riesgo.** No confundir guion proyectado con certeza — es hipótesis.

---

## FASE 3 — Perfil de árbitro ampliado

**Objetivo.** Ir más allá del card-rate hacia **penaltis, umbral de falta, sesgo local y ventaja**.

**Qué información se necesita.**
- Por árbitro: penaltis/partido, faltas/partido, tarjetas/partido (ya), % victoria local, tendencia a la ley de ventaja.

**Para qué.**
- **Mercado de tarjetas** (ya empezado) y **penaltis** — empíricamente las tarjetas las domina árbitro + rivalidad + match-status (NO la formación), así que el árbitro es input de primera línea aquí.

**De dónde.**
- **API-Football**: el árbitro viene como campo del fixture. **No hay endpoint de stats de árbitro** → derivar agregando los fixtures históricos que pitó (`/fixtures` filtrando por `referee` + sus `/fixtures/statistics` y `/fixtures/events` para faltas/penaltis/tarjetas).
- Alternativa: sitios de stats de árbitros (worldfootball / Transfermarkt referee pages) por scraping si la derivación API es insuficiente para selecciones (árbitros internacionales pitan pocos partidos/temporada → small-n).

**Cómo se integra.**
- Extender el **card-prior** existente a un `RefereeProfile` (penalty_rate, foul_threshold, home_bias).
- Aplicar al prop board (ya se aplica card-rate) y como modificador del mercado de penaltis/faltas.

**Dependencias.** Se potencia con Fase 1 (duelos → faltas). **Cobertura.** Universal pero small-n en árbitros internacionales (marcar confianza). **Riesgo.** Muestra pequeña por árbitro de selección.

---

## FASE 4 — Regresión a la media de finishing / varianza

**Objetivo.** Detectar equipos que **sobre/infra-rinden su xG** (suerte de cara / portero) para fade/back — concepto sharp puro.

**Qué información se necesita.**
- xG vs goles reales (a favor y en contra) en ventana → over/under-performance.
- Post-shot xG del portero (GSAA) → cuánto del rendimiento es el GK.

**Para qué.**
- **Team totals / AH**: fade al equipo que viene caliente de cara (regresa a la media); back al frío.

**De dónde.**
- **StatsBomb**: shot xG (y post-shot xG / métricas de GK computables) en el corpus — fuente precisa.
- **API-Football `/fixtures/statistics`**: `expected_goals` por partido en muchos fixtures → ruta **universal** xG-vs-goles por ventana (menos granular que StatsBomb, sin post-shot).
- Ya tienen `xg_per90` (TSV) y `finishing_profile` (clinical/wasteful) como etiqueta.

**Cómo se integra.**
- Convertir `finishing_profile` de etiqueta a **prior de regresión** (magnitud del over/under-rendimiento) en `tactical_identity.py` o un campo en `AdvancedShape`/TSV.
- Surfacear como **ajuste/caveat** en `MatchupRead.market_leans`.

**Dependencias.** xG ya disponible. **Cobertura.** Precisa = corpus; aproximada = universal (API xG). **Riesgo.** **Small-n** (problema recurrente del proyecto) — exigir n mínimo y marcar confianza; no sobre-ajustar con pocas muestras.

---

## FASE 5 — Press-resistance vs intensidad de presión

**Objetivo.** Cruzar cuánto presiona un equipo (PPDA, ya lo tienen) con la **fragilidad de salida del rival bajo presión**.

**Qué información se necesita.**
- Del presionador: PPDA / press_intensity (ya en `TacticalIdentity`).
- Del rival: press-resistance — pérdidas en campo propio, % de pase completado **bajo presión**, % de balón largo cuando lo presionan.

**Para qué.**
- **BTTS / Over** (presionador alto × rival que regala el balón → muchas pérdidas y ocasiones).
- **Under** (presionador × rival press-resistente → se neutraliza).

**De dónde.**
- **StatsBomb event-level**: pressure events + pass-under-pressure → única fuente para press-resistance. **API-Football no tiene equivalente** (sin eventos de presión).

**Cómo se integra.**
- Añadir dimensión `press_resistance` a `TacticalIdentity` (`tactical_identity.py`).
- Cruzar en `MatchupRead` (presión de A vs resistencia de B y viceversa).

**Dependencias.** Reusa PPDA existente. **Cobertura.** **Solo corpus** — 8 selecciones WC2026 sin datos (el más bloqueado). **Riesgo.** Cobertura; por eso va último.

---

## Resumen de cobertura por fase

| Fase | Mejora | Fuente principal | Cobertura | Mercado objetivo |
|---|---|---|---|---|
| 1 | Mapa de duelos + fouls drawn | API-Football `/fixtures/players` | **Universal** | Tarjetas, faltas, penalti, cabeza |
| 2 | Guion de partido | lock_v1 (MVP) + StatsBomb | Universal (MVP) / corpus (split) | Córners, O/U, live |
| 3 | Árbitro ampliado | API-Football (derivado) | Universal (small-n) | Tarjetas, penaltis |
| 4 | Regresión finishing | StatsBomb / API xG | Corpus (preciso) / universal (aprox) | Team totals, AH |
| 5 | Press-resistance | StatsBomb event-level | **Solo corpus** | BTTS, O/U |

---

## Cierre de implementación (2026-05-31)

| Fase | Commit(s) | Entregado |
|---|---|---|
| 1 | `179f780`, `c46a415` | `fouls_drawn_per90` (StatsBomb "Foul Won") + "Faltas recibidas" en el board; mapa de duelos (amenaza × weak-link → faltas/penal o cabeza/córner) en `MatchIntel.duels`, §6 |
| 2 | `5a94110` | `game_script`: brecha λ del TSV → favorito/persigue → córners (el que persigue gana), Under/BTTS; `MatchIntel.game_script`, §3b |
| 3 | `889e161` | FIX contaminación shootout en penaltis; `foul_volume` + `pen_tendency` (@property, terciles reales); `referee_match_note` en notas del intel |
| 4 | `9e43d40` | `finishing_regression`: over/infra-rendir xG → FADE/BACK team-total; `MatchIntel.regression_notes`, §3b (MVP ofensivo; defensiva bloqueada sin `xg_against` en TSV) |
| 5 | `e835823`, `08f99f8` | módulo `press_resistance` (completion-under-pressure, terciles corpus) + build 40 + loader + cruce presión×build-up; `MatchIntel.press_notes`, §3b |

**Cobertura realizada vs plan:** Fase 1 implementada sobre StatsBomb (mismo stream "Foul Won", más
quirúrgico que ingesta API nueva — `fouls.drawn` de API-Football `/fixtures/players` queda como
extensión para las 8 selecciones sin StatsBomb). Fases 2-5 corpus-StatsBomb. Regresión defensiva
(Fase 4) y las 8 selecciones sin StatsBomb siguen sin perfil — honesto, no fabricado. Tests
parametrizados en boundaries, delta-ruff cero, nada toca el schema versionado.

## Notas finales

- **Cada fase fue independiente y entregable por separado.** Para extender: ver "Cobertura" arriba.
- **Dependencia transversal de datos**: Fases 1 y 3 comparten `/fixtures/players` + agregación de fixtures; Fases 2, 4 y 5 dependen del corpus StatsBomb para su versión rica. Conviene una pequeña capa de ingesta API-Football `/fixtures/players` → per-90 que sirva a Fases 1 y 3 a la vez.
- **Coherente con la regla de oro** de [[reference_playing_styles_by_formation]]: todas estas señales son tilts de mercados secundarios con peso a validar contra datos propios, no drivers de 1X2.
