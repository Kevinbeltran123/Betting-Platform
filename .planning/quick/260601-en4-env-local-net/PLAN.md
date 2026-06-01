---
quick_id: 260601-en4
slug: env-local-net
status: complete
date: 2026-06-01
commit: 2ed2c7d
---

# Quick Task: #4 Reconciliar "entorno-local NETO" (host-fade vs altitud/descanso)

## Problema (auditoría #1)
Host-fade (−), altitud-ventaja (+) y descanso (+) se listaban como viñetas separadas que
el ojo suma; para Mexico/Azteca eran contradictorias. #3 lo marca como conflicto; #4 lo resuelve.

## Solución
`env_local_net(h, a, mh, ma, ven, tr)`: un read con signo + eje de mercado (NO inventa pp
combinado = falsa precisión):
- host + altitud aclimatada → ventaja física COMPENSA host-fade: neutro-a-leve a favor en
  TOTALES/hándicap; fade pesa en RESULTADO. No apilar.
- host a nivel del mar → host-fade en pie (prior débil n-pequeño WC-32).
- sin host → net físico de altitud/descanso.
Sección "## Entorno-local (neto)" tras la síntesis; footer de #3 ahora apunta aquí.

## Verificación
- Mexico-Azteca: NETO compensado. USA-Inglewood: host-fade en pie. Brazil-Morocco: rama física. exit 0.
