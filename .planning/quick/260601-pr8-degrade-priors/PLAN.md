---
quick_id: 260601-pr8
slug: degrade-priors
status: complete
date: 2026-06-01
commit: 56fd037
---
# Quick Task: #8 Degradar patrones WC-32 a "prior, dirección>magnitud"
## Problema (auditoría #4)
host-fade -12/-18pp, CONMEBOL +5%, CAF ×1.40, MD3-Over: priors calibrados en WCs de 32
equipos, aplicados a uno de 48 sin precedente → falsa precisión tratada como ley.
## Solución
Quita los números puntuales del output del brief: host-fade → "PRIOR DÉBIL, dirección leve
contra anfitrión, no magnitud fija"; CONF_EDGE pierde +5%/×1.40 (dirección, no magnitud);
J3-Over → "PRIOR NO TESTEADO". Alineado con la confianza 'baja' de la síntesis (#3).
## Verificación
grep del brief: sin -12-18pp / +5% / ×1.40. Render OK.
