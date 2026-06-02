---
quick_id: 260601-un9
slug: unify
status: complete
date: 2026-06-01
commit: ecd3872
---
# Quick Task: #9 Unificar TEAM_META↔§6.8 + rol de los dos ensambladores
## Hallazgos
- TEAM_META completo (48/48), falla-ruidoso en equipo desconocido (no había 47-vs-48 real).
- Confederación canónica vive en los TSV (gitignored, no apto para test CI).
## Solución (scoped, sin refactor de riesgo)
- Guard fail-loud: cf ∈ {UEFA,CONMEBOL,CONCACAF,CAF,AFC,OFC} (drift del campo cf se cae al import).
- Documenta rol CANÓNICO: 43 = brief analista lean; 39 = auto-dossier de datos. NO se fusionan
  a propósito (feedback_analyst_approach evita auto-emit). Merge completo DEFERIDO por diseño.
- Arregla "(pendiente #3)" obsoleto de Tarjetas → apunta a la tabla de árbitros (#7).
## Verificación
Guard pasa (48/48), brief render OK, línea de Tarjetas corregida.
