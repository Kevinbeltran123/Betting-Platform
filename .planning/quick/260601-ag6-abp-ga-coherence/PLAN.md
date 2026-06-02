---
quick_id: 260601-ag6
slug: abp-ga-coherence
status: complete
date: 2026-06-01
commit: 65ffff1
---

# Quick Task: #6 Cross-check ABP↔GA en aerial_flag

## Problema (auditoría #1)
`aerial_flag` dispara "concede córner/header" si la zaga es 🔴 o el portero débil (gk),
SIN mirar la GA real → puede emitir un flag que la stat desmiente (equipo 🔴-ABP pero GA baja).

## Solución
`_abp_ga_coherence(dfn)`: cruza el rating cualitativo con la GA (prefiere goals_against_comp
de #5). GA<=1.0 → "⚠️ CONFLICTO, confirmar"; GA>=1.4 → "corroborado"; intermedio → "media".
El flag se sigue emitiendo (el rating ABP es de balón parado, la GA es global — no se
suprime) pero ANOTADO, para que el humano vea la tensión.

## Verificación
- Germany (dlv) × South Africa (🔴+gk, GA 0.8-0.9) → flag + "⚠️ CONFLICTO". Correcto.

## Nota
Shipped junto con #5 en commit 65ffff1 (ambos tocan 43_match_brief.py, entrelazados).
