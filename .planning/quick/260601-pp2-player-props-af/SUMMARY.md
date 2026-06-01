---
quick_id: 260601-pp2
slug: player-props-af
status: complete
date: 2026-06-01
commit: db51545
---

# SUMMARY — #2 Player-props desde API-Football (selección actual)

## Qué se entregó
El prop board (mercado más blando del operador) ahora se puede generar desde los fixtures
RECIENTES de la selección bajo el DT actual, vía API-Football, reemplazando el StatsBomb-torneo
2022-24. Reusa toda la agregación existente (agnóstica de fuente).

- `src/.../team_style_profiler/player_props_apifootball.py` (nuevo): `parse_fixture(players_resp,
  events_resp, team_id)` → tuplas `(counts, meta, minutes)` que consume
  `player_props.build_player_profiles`. Cards desde `/fixtures/events` (fiable, por player.id,
  filtra rival); `fouls.committed` None→0; DNP excluidos; xG=0 (cae a tasa de goles);
  penaltis = scored+missed.
- `scripts/spike/tsp/46_build_player_props_apifootball.py` (nuevo): loop COACH_SINCE (DT actual,
  reusa script 41), fixtures FT, `build_player_profiles(source="api_football")` + `prop_board` →
  `data/cache/tsp/player_props_af/{slug}.json` (mismo esquema que script 30 + `source`).
- `intel_io.load_props`: prefiere `player_props_af/` sobre `player_props/` (StatsBomb), con
  fallback. `_props_from` mapea `source=api_football`. `player_props.PropSource += api_football`.
- `tests/.../test_player_props_apifootball.py` (nuevo): None fouls, DNP, cards desde events,
  filtro de rival, penaltis, bloque ausente.

## Verdad de campo (probe en vivo 2026-06-01)
- Cobertura buena en todo el gradiente, incl. minnow: Curaçao (SIN StatsBomb, antes 0 props)
  → board completo green/yellow. Recencia 2025-26 (vs 2022-24). Invierte la anti-correlación
  dato↔edge marcada en la auditoría (#5).
- `fouls.committed` a veces None → se cuenta 0 (no se fabrica). Tarjetas FIABLES desde /events.

## Verificación
- pytest: 6 nuevos + 45 existentes (player_props + intel) = 51 verdes. ruff limpio.
- Build vivo Spain (48 jug)/Senegal (33)/Curaçao (32): boards con n>0; Curaçao produce board.
- `load_props`: spain/curaçao → source=api_football (preferido); argentina → statsbomb (fallback). OK.
- Build completo: **47/48 equipos** con board. Único gap: Chequia (0 fixtures bajo Koubek,
  DT desde 2025-12-01) → cae a su StatsBomb (Euro24) vía fallback, no queda sin props.
  1672 perfiles totales (467 green / 369 yellow / 836 red excluidos del board).

## Notas / deuda
- El minuto de la tarjeta (time-to-first-card) se parsea de /events pero NO se persiste todavía
  (el schema PlayerPropProfile no lo guarda) → futura extensión para props live de tarjetas.
- xG ausente en internacionales: anytime-scorer cae a tasa de goles cruda (menos fino que el xG
  de StatsBomb). Para potencias con buen StatsBomb, se podría conservar el xG — no se hizo
  (KARPATHY: no fusionar fuentes hasta que el caso lo pida).
- El prop board aún no se cablea a la sección de Precio del brief (#1) — eso es el puente de
  props automático, pendiente.

## Siguiente
#3 del roadmap: tag de mecanismo + descuento de correlación en el brief (mata el doble conteo).
