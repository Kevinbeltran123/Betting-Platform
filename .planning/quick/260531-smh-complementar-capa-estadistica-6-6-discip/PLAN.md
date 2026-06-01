---
quick_id: 260531-smh
slug: complementar-capa-estadistica-6-6-discip
date: 2026-06-01
status: in-progress
---

# Quick Task: Complementar §6.6 con disciplina y SOT (48 selecciones WC2026)

## Problema

La capa estadística §6.6 de `notes/PLAYING_STYLES_REFERENCE.md` tiene 3 huecos
concretos que dejan ciego el análisis en el mercado de tarjetas (el más blando):

1. **Faltas**: columna 100% vacía (`—`) pese a que el dato YA está en el cache
   `api_team_stats_by_coach.json` (campo `fouls`) para las 46 con datos.
2. **Tarjetas (amarillas/rojas)**: el script `41_team_stats_by_coach.py` NUNCA las
   captura — la línea de extracción solo pide `Fouls`, no `Yellow Cards`/`Red Cards`.
   Es el input MÁS directo al mercado de cards. Requiere cambio de código + re-run.
3. **SOT (remates a puerta)**: `sot_for` está en cache pero no en la tabla; `sot_against`
   ni se captura. Mejor señal de finalización / team-totals que remates totales.

§1 (REGLA DE ORO) confirma: la formación es empíricamente inerte para tarjetas → el
driver del mercado es el **historial de faltas/tarjetas del propio equipo**. Ese dato falta.

## Tareas

1. **Código** — `scripts/spike/tsp/41_team_stats_by_coach.py`: capturar
   `Yellow Cards`, `Red Cards` (de `mine`) y `Shots on Goal` del rival (`sot_against`);
   agregarlos en el return; mostrarlos en el print de verificación.
2. **Re-run** — ejecutar el script (API_FOOTBALL_KEY desde .env) → regenerar
   `data/cache/tsp/api_team_stats_by_coach.json` con faltas + cards + SOT for/against.
3. **Doc** — surfacear columnas **Faltas · Tarjetas (Am/Roj) · SOT (F/C)** en la tabla
   §6.6 para las 48; añadir un bloque de lectura de mercado de tarjetas (extremos
   alto/bajo) bajo el enfoque analista (evidencia, no veredicto).

## Verificación

- El script corre sin error y el JSON regenerado contiene `yellow_cards`, `red_cards`,
  `sot_against` para todas las selecciones con datos.
- La tabla §6.6 renderiza con las nuevas columnas y los números coinciden con el cache.
- Las selecciones n=1-2 siguen marcadas baja-confianza; Chequia/Túnez siguen sin datos.
