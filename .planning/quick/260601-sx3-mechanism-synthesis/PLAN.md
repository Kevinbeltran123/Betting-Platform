---
quick_id: 260601-sx3
slug: mechanism-synthesis
status: complete
date: 2026-06-01
commit: 9fdffe0
---

# Quick Task: #3 Tag de mecanismo + descuento de correlación en el brief

## Problema (auditoría #2 + #6)
El brief lista evidencia plana → N viñetas se leen como N señales (falsa confianza) y
permiten cherry-picking. Doble conteo: host-fade vs ventaja-local/altitud/descanso
(contradictorios), córners por múltiples mecanismos solapados.

## Solución (lógica interna, sin dependencia externa)
Instrumentar cada lean direccional con (mercado, dirección, mecanismo, confianza) en una
lista SIG; nueva sección "Síntesis ponderada" que:
- cuenta MECANISMOS independientes por mercado/dirección (no viñetas),
- marca el mismo mecanismo repetido → cuenta como 1,
- marca lados opuestos como CONFLICTO (incertidumbre, no edge),
- apunta el net entorno-local a #4.

## Verificación
- Mexico-RSA (Azteca, host): CONFLICTO en Lado (host-fade ↔ altitud+Elo). OK.
- Brazil-Morocco (sin host): sin conflicto; Brasil 2 mec. indep. (confederación+Elo). OK.
- Brief completo exit 0.

## Notas
- N806/E501 del archivo son preexistentes (spike script); SIG sigue la convención local de L.
- El net con signo del cluster entorno-local es #4 (esta tarea solo lo SURFACEA).
