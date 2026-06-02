---
quick_id: 260601-rg5
slug: regime-split
status: complete
date: 2026-06-01
commit: 65ffff1
---

# Quick Task: #5 Separar régimen amistoso/competitivo en §6.6

## Problema (auditoría #3)
[41_team_stats_by_coach.py](../../../scripts/spike/tsp/41_team_stats_by_coach.py) promedia
los últimos ≤20 partidos SIN filtrar por tipo → mezcla amistosos y competitivo. El propio
hallazgo de transferencia dice que los amistosos INFLAN ofensiva y DEFLACTAN defensa → GF/GA
de §6.6 contaminados entran a la capa 4 (SoS corrige rival, no régimen).

## Solución
- Script 41: clasifica cada fixture friendly vs competitivo (league name "friendl"), emite
  `n_friendly`/`n_competitive` y GF/GA SOLO-competitivo (`goals_for_comp`/`goals_against_comp`).
- Brief: `stat_line` muestra el split `{c}c/{a}a` + GF/GA solo-comp; aviso en la sección Fuerza
  cuando ≥50% son amistosos (ofensiva inflada / defensa deflactada, no transfiere).
- Regen de caché vía API en vivo (background).

## Verificación
- Caché nueva tiene n_friendly/n_competitive/goals_*_comp.
- Brief muestra el split y avisa en equipos amistoso-pesados. Retrocompatible con caché vieja.

## Restricciones
KARPATHY quirúrgico. Caché gitignored (regenerable). Sin Co-Authored-By.
