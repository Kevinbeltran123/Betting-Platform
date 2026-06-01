---
quick_id: 260601-pp2
slug: player-props-af
status: in-progress
date: 2026-06-01
---

# Quick Task: #2 Player-props/tarjetas desde API-Football (selección actual)

## Problema (de la auditoría)
El prop board —mercado más blando del operador— sale 100% de StatsBomb-torneo 2022-24
([30_build_player_props.py](../../../scripts/spike/tsp/30_build_player_props.py)): n minúsculo,
jugadores 2025-emergentes con cero data, 8 selecciones sin StatsBomb. API-Football
`/fixtures/players`+`/fixtures/events` da por jugador de la selección ACTUAL bajo el DT actual.

## Verdad de campo (probe en vivo 2026-06-01)
- Cobertura BUENA en todo el gradiente, incl. minnow: Curaçao (sin StatsBomb) 15 FT, ~15
  jugadores/partido con minutos + eventos de tarjeta. Recencia 2025-26 (vs 2022-24).
- `fouls.committed` a veces None (→0); **tarjetas FIABLES desde /events** (player.id+min,
  filtrar por team.id). xG no existe para internacionales (→0, el perfil cae a goles).

## Diseño (reusa la agregación existente, agnóstica de fuente)
`build_player_profiles(per_match, source=...)` + `prop_board()` no se tocan. Solo añado un
parser que produce las tuplas (counts, meta, minutes) desde API-Football.

## Tareas
1. NEW `src/.../team_style_profiler/player_props_apifootball.py`: `parse_fixture(players_resp,
   events_resp, team_id)` → (counts, meta, minutes). Cards desde events; fouls None→0; DNP fuera.
2. NEW `scripts/spike/tsp/46_build_player_props_apifootball.py`: loop COACH_SINCE (de 41),
   fixtures FT bajo DT actual, /fixtures/players + /fixtures/events, parsea, build_player_profiles
   (source="api_football"), prop_board → `data/cache/tsp/player_props_af/{slug}.json` (esquema de 30).
3. `player_props.py`: PropSource Literal += "api_football" (1 línea).
4. `intel_io.py`: load_props prefiere player_props_af sobre player_props; _props_from mapea source.
5. NEW test del parser (None fouls, DNP, cards desde events, filtro de rival).

## Verificación
- pytest del parser verde.
- Build de Spain/Senegal/Curaçao → prop board impreso con n>0; Curaçao (sin StatsBomb) produce board.
- 39_analyze de un partido carga props AF (load_props los prefiere).

## Restricciones
KARPATHY quirúrgico; reusar agregación; sin Co-Authored-By.
