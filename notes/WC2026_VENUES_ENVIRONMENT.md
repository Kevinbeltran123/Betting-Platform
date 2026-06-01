# Entorno de sede + calendario WC2026 — Referencia de análisis

> **Propósito.** Capa de **contexto físico** (sede, altitud, calor, techo/AC, viaje, descanso, franja
> horaria) que el read de estilo/stats asume neutral — pero que mueve **totales y ritmo** más que medio
> arquetipo. Mejora #2 del roadmap (`project_wc2026_analysis_gaps_roadmap`). Conocible HOY: sedes y sorteo
> (5-dic-2025) confirmados.
>
> **Régimen de uso (honestidad).** Lo **estructural** (altitud, techo, AC, cluster, huso, días de descanso)
> es fiable y durable. Las **temperaturas** son aproximaciones climatológicas de jun-jul → **cruzar SIEMPRE
> con el pronóstico real del día del partido** antes de fijar un lean por calor. Peso **modesto**, evidencia
> que tú interpretas — no veredicto. Combina con la matriz de totales de §6.6 ([[PLAYING_STYLES_REFERENCE]])
> y las reglas live de patterns_v2 (HT 0-0 → U2.5, etc.).

---

## 1. Las 16 sedes

| Sede (estadio) | Ciudad, País | Altitud | Techo | ¿AC/clima controlado? | Temp. máx jun-jul (~) | Humedad | Capacidad |
|---|---|---|---|---|---|---|---|
| Mercedes-Benz Stadium | Atlanta, USA | ~320 m | Retráctil | **Sí** | ~31 °C | Alta | 75.000 |
| Gillette Stadium | Foxborough (Boston), USA | ~90 m | No | No | ~28 °C | Media-alta | 65.000 |
| AT&T Stadium | Arlington (Dallas), USA | ~180 m | Retráctil | **Sí** | ~36-37 °C ext. | Media | 94.000 |
| NRG Stadium | Houston, USA | ~15 m | Retráctil | **Sí** | ~35-37 °C ext. | Muy alta | 72.000 |
| Arrowhead Stadium | Kansas City, USA | ~270 m | No | No | ~32-33 °C | Alta | 73.000 |
| SoFi Stadium | Inglewood (LA), USA | ~30 m | Fijo translúcido (lados abiertos) | No AC (ventilación natural) | ~28-29 °C | Baja-media | 70.000 |
| Hard Rock Stadium | Miami Gardens, USA | ~2 m | Marquesina parcial (campo abierto) | No confirmado | ~32-33 °C | **Muy alta (~80%)** | 65.000 |
| MetLife Stadium **(FINAL)** | East Rutherford (NY/NJ), USA | ~5 m | No | No | ~29-30 °C | Alta | 82.500 |
| Lincoln Financial Field | Filadelfia, USA | ~10 m | No | No | ~31 °C | Alta | 69.000 |
| Levi's Stadium | Santa Clara (SF Bay), USA | ~5 m | No | No | ~27-28 °C | Media | 71.000 |
| Lumen Field | Seattle, USA | ~5 m | Marquesina parcial (NO retráctil) | No | ~23-24 °C | Media | 69.000 |
| Estadio Azteca (Banorte) | Ciudad de México, México | **~2.200 m** | No | No | ~24-25 °C | Media | ~83.000 |
| Estadio Akron | Guadalajara, México | **~1.566 m** | No | No | ~27-28 °C | Media (lluvias) | ~48.000 |
| Estadio BBVA | Monterrey, México | ~500 m | No | No | **~35-37 °C** | Alta | 53.500 |
| BMO Field | Toronto, Canadá | ~80 m | No | No | ~26-27 °C | Media | ~45.000 |
| BC Place | Vancouver, Canadá | ~0-5 m | Retráctil | **Sí** | ~22-23 °C | Media | 54.000 |

> Las 5 sedes con **césped natural sobre estructura indoor** (Atlanta, Dallas, Houston, Vancouver, +mixtas)
> fueron un reto logístico para FIFA. Azteca: capacidad en rango por remodelación. Hard Rock: AC de campo
> **no confirmado** (marquesina sobre gradas, no clima de campo).

## 2. Clasificación clima/altitud → totales y ritmo

- **(a) Clima controlado — neutro, el calor exterior NO aplica:** **Atlanta, Dallas (AT&T), Houston (NRG),
  Vancouver** (techo retráctil + AC). Trátalas como condiciones normales aunque fuera haga 37 °C. **SoFi (LA)**
  ≈ neutro (techo fijo + clima benigno de LA, sin AC).
- **(b) Calor/humedad extremo — riesgo real jun-jul, lean a *Under* / caída de ritmo 2ª parte / calambres:**
  **Monterrey (BBVA) = el de MAYOR riesgo del torneo** (abierto, ~36-37 °C). Le siguen **Miami** (calor +
  humedad ~80%), **Kansas City**, **Filadelfia**, **Guadalajara**. Efecto SOLO si el partido es de
  **mediodía/tarde** (ver §4) y a cielo abierto.
- **(c) Altitud:** **Ciudad de México (Azteca ~2.200 m)** = efecto fuerte (balón vuela más, fatiga acelerada
  para visitantes no aclimatados → micro-tilt *Over*/ritmo + ventaja del aclimatado, p.ej. México).
  **Guadalajara (~1.566 m)** = moderado. **Monterrey ~500 m** = despreciable (allí el factor es calor, no altura).

## 3. Clusters geográficos / husos

Sorteo 5-dic-2025: grupos y sedes **confirmados**. FIFA agrupó en 3 regiones para minimizar vuelos en fase de
grupos (la mayoría juega sus 3 partidos dentro de un cluster):
- **Oeste (PT):** Vancouver, Seattle, SF, LA, Guadalajara.
- **Centro (CT):** Dallas, Houston, Kansas City, Monterrey, Atlanta, Ciudad de México.
- **Este (ET):** NY/NJ, Boston, Filadelfia, Miami, Toronto.

Husos PT→ET = **hasta 3 h**. Coast-to-coast ≈ 3.500-4.000 km (vuelo 5-6 h). **Anfitriones** (México=Grupo A,
Canadá=Grupo B, USA=Grupo D) juegan sus 3 de grupo **en casa** → mínimo viaje. Octavos rompen el cluster;
cuartos en adelante, todo en USA.

## 4. Franjas de kickoff + exposición al calor

Hasta 13 horarios; FIFA cargó partidos hacia sedes Este para prime-time europeo, pero hay **slots de
mediodía/15:00 ET por TV europea** (12:00 ET = 18:00 CET) que exponen a calor. **FIFPRO marcó riesgo de calor
"extremadamente alto" en partidos de tarde en: Atlanta, Dallas, Houston, Kansas City, Miami y Monterrey.**
Mitigación oficial: más nocturnos en sedes calurosas + **pausas de hidratación obligatorias** en los 104
partidos (las cooling breaks en sí ya alargan y cortan ritmo). **Regla operativa:** el lean por calor solo
aplica si **sede abierta (§2b) × franja de día**; en Atlanta/Dallas/Houston el techo lo anula aunque sea tarde.

## 5. Descanso y asimetría de viaje

- **Calendario grupos:** MD1 11-15 jun · MD2 16-21 · MD3 23-28. ~**3-4 días** entre partidos; **asimetrías
  reales** (un equipo puede tener 3 días vs 4 del rival — verificar por partido).
- **Torneo de 39 días** (vs 32 en 2014/18) → más largo, fatiga acumulada distinta.
- **Viaje:** equipos intra-cluster (mayoría) viajan poco; los pocos **coast-to-coast** cargan jetlag
  conocible. **Anfitriones = ventaja de descanso/fatiga infravalorada.** El cruce de huso pega sobre todo en
  knockouts.

## 6. Formato de grupos + MD3 (corrige el supuesto "dead-rubber")

12 grupos de 4; pasan **1º + 2º + 8 mejores terceros**. **Efecto clave: casi NO hay dead rubbers** — con 8
terceros clasificando (3 pts suelen bastar; el desempate es diferencia de gol), casi nadie está eliminado ni
clasificado con seguridad antes de MD3 → **los terceros persiguen goles**. **Esperar MD3 ABIERTOS, no cagey** →
sesgo **Over / equipos atacando**, lo contrario al "rotación/dead-rubber" clásico de mundiales de 32.
(Consistente con que la EDA ya había falsificado el patrón "MD3 dead-rubber" — ver `project_wc2026_historical_patterns`.)

## 7. Aplicación de apuestas (consolidado, peso modesto)

- **Under por calor:** solo en las 6 sedes de riesgo **abiertas × franja de día** (Monterrey, Miami, KC,
  Filadelfia, Guadalajara; Atlanta/Dallas/Houston **anulado por techo**), reforzado si hay europeo sin aclimatar.
- **Altitud Azteca (~2.200 m):** micro-tilt ritmo/Over + ventaja del aclimatado (México). Guadalajara, leve.
- **Fatiga/jetlag:** tilt *Under* / favorito-frena tras coast-to-coast (raro en grupos, frecuente en KO);
  **ventaja de descanso del anfitrión** y de equipos intra-cluster, infravalorada.
- **MD3:** NO asumir cagey/rotación → lean **Over/ataque** en grupos con terceros vivos.
- **Cruce obligatorio antes del lean:** sede (techo? altitud?) × **pronóstico real del día** × franja horaria
  × huso/viaje del rival. Nunca aplicar el tilt de calor a ciegas sobre la media climatológica.

---

## Fuentes
- FIFA / Wikipedia — 2026 FIFA World Cup (sedes, sorteo, formato): https://en.wikipedia.org/wiki/2026_FIFA_World_Cup
- Heat Risk Index de las 16 sedes: https://bettercollective26.github.io/World_Cup_Heat_Risk_Index/Index.html
- Estadio Azteca / Akron / BBVA (altitud, capacidad): https://en.wikipedia.org/wiki/Estadio_Azteca
- SoFi clima/ventilación: https://www.accuweather.com/en/sports/the-incredible-environmental-innovation-of-sofi-stadium/1141307
- Césped natural en estadios indoor: https://www.foxsports.com/stories/soccer/fifa-tackling-unique-problem-2026-world-cup-natural-grass-in-5-indoor-stadiums
- Viaje/logística + clusters: https://voz.us/en/sports/260526/35180/fifa-world-cup-2026-map-venues-logistical-wear-tear-rival.html
- Franjas europeas: https://www.euronews.com/2026/05/30/the-euronews-guide-to-the-2026-world-cup-groups-fixtures-and-european-kick-off-times
- Calor (FIFPRO/Time/ESPN): https://time.com/7303535/extreme-heat-fifa-world-cup-2026/
- Formato/terceros (MD3): https://www.espn.com/soccer/story/_/id/48703925/world-cup-group-stage-explained-tiebreakers-third-place-teams
