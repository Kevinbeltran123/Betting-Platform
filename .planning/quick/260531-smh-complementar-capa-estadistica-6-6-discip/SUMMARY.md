---
quick_id: 260531-smh
slug: complementar-capa-estadistica-6-6-discip
date: 2026-06-01
status: complete
---

# SUMMARY: Complementar §6.6 con disciplina y SOT (48 selecciones WC2026)

## Qué se hizo

Capa estadística §6.6 de `notes/PLAYING_STYLES_REFERENCE.md` profundizada con disciplina
y calidad de remate, surfaceando datos que ya existían o que la API exponía pero el flujo
no capturaba.

1. **Código** (`scripts/spike/tsp/41_team_stats_by_coach.py`): se añadió captura de
   `Yellow Cards`, `Red Cards` y `Shots on Goal` del rival (`sot_against`). Antes solo
   extraía `Fouls` + SOT propio. Se agregan al return y al print de verificación.
2. **Re-run**: regenerado `data/cache/tsp/api_team_stats_by_coach.json` (gitignored).
   46/48 con datos (Chequia/Koubek + Túnez/Lamouchi siguen sin stats bajo DT nuevo).
   Data fresca al 2026-06-01 (Brasil n=10, Senegal n=14, fixtures nuevos).
3. **Doc**: tabla §6.6 ampliada de 8→10 columnas — nuevas **SOT F/C** y **TA/p**, columna
   **Faltas** llena (antes 100% `—`), y añadidas las 4 grandes (Francia/España/Argentina/Brasil,
   que en §6.1-6.4 no tenían línea estadística). Nuevo bloque "Disciplina — lectura para
   mercado de tarjetas". Leyenda ampliada con caveats de fiabilidad.

## Hallazgo de calidad de dato (importante)

- **Faltas**: presente en TODOS los partidos → fiable.
- **Amarillas (TA/p)**: la API solo las reporta en partidos **competitivos** (en amistosos
  menores devuelve `null`) → n-efectivo < n; como el WC es competitivo, es el subconjunto relevante.
- **Rojas: NO se surfacean** — la API las devuelve `null` casi siempre; el promedio salía
  inflado (artefacto de promediar solo partidos con roja). Capturadas en el JSON pero no en el doc.

## Insight analítico clave

**Faltas ≠ tarjetas.** El ratio falta→amonestación varía mucho: CAF físicas (Senegal 14.5 faltas
pero 1.6 TA; Costa de Marfil 14.4/1.3) **no** son cards-over pese al volumen; los cards-over reales
son alto-TA aunque falten poco (Turquía 10.6 faltas / **2.6 TA**; Uruguay 2.3). Para team-cards-over
priorizar TA/p, no faltas, y cruzar siempre con el árbitro probable.

## Verificación

- Script corre sin error; JSON contiene `yellow_cards`/`red_cards`/`sot_against` para las 46.
- Tabla §6.6: 56 filas, todas con 10 columnas consistentes (11 pipes) — validado.
- Extremos bolded verificados contra cache (TA máx Turquía 2.6, mín Japón 0.9; SOT máx España 7.7;
  faltas mín Australia 8.5, máx Bosnia 14.8).

## No tocado (deliberado)

- Cambios pre-existentes no relacionados (pyproject.toml, uv.lock, notes/MATCH_RESULTS_LOG.md,
  scripts/spike/corners_next10min.py) quedan fuera del commit.
- Profundización **cualitativa** por equipo (lesiones/forma 2026/ABP/props) NO incluida — fue la
  opción descartada en el AskUserQuestion; queda como siguiente paso si el operador lo pide.
