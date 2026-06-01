---
quick_id: 260601-pe4
slug: price-layer
status: in-progress
date: 2026-06-01
---

# Quick Task: Capa de precio (#1 del roadmap de mejoras de análisis WC2026)

## Problema
El brief prepartido ([43_match_brief.py](../../../scripts/spike/tsp/43_match_brief.py)) no
muestra ningún precio. La tesis del sistema es batir mercados blandos secundarios, pero sin
una línea al lado de la evidencia el humano no puede ver dónde está el valor → produce
evidencia sobre equipos, no sobre apuestas.

## Verdad de campo (probe en vivo /odds, key Ultra, 2026-06-01)
- Catálogo: 337 bet types (córners O/U id45, tarjetas O/U id80, AH id4, etc.).
- Cuotas se pueblan en ventana móvil ~7-14d pre-KO. WC (league=1 season=2026) → results=0 HOY.
- Cuando hay: 9 casas incl. Betano, Pinnacle, Betfair. Profundidad secundaria THIN:
  solo AH/Handicap poblados; córners/tarjetas NO → van por input MANUAL.

## Alcance: HÍBRIDO (confirmado por operador)
Auto-pull de lo que el API trae (1X2/OU/BTTS/AH) + de-vig Pinnacle como ancla sharp;
input manual para córners/tarjetas/props. Brief añade sección "Precio y línea" con el
puente evidencia↔línea, marcando AUTO vs MANUAL. SIN EV ni pick (feedback_analyst_approach).
Key se renueva → no se diseña fallback especial por caducidad, solo degradación normal
cuando las cuotas aún no estén en la ventana.

## Tareas
1. `scripts/spike/tsp/45_match_odds.py` — resuelve fixture (reusa alias de intel_io),
   pull /odds, parsea 1X2/OU/BTTS/AH (Betano+Pinnacle+Betfair), de-vig Pinnacle, mergea
   manual, escribe `data/cache/tsp/odds/{slug}.json`. Degrada limpio si results=0.
2. Editar `43_match_brief.py` — sección "## Precio y línea": córners/tarjetas (MANUAL)
   vs rate combinado; AH/totales/1X2 (AUTO) vs Elo + fair Pinnacle. Etiquetas AUTO/MANUAL.
3. `scripts/spike/tsp/manual_odds_TEMPLATE.json` (versionado; las reales van en
   data/cache/tsp/manual_odds/ que está gitignored) + nota en el brief.

## Verificación
- (a) `45` contra fixture real con cuotas hoy (id 1400644, liga 334) → parsea AH/1X2/OU/BTTS + de-vig.
- (b) manual_odds de prueba mexico_vs_south_africa.json + correr `43` → puente manual córners/tarjetas
  + degradación del auto (WC sin cuotas aún).

## Restricciones
KARPATHY (quirúrgico, simple, sin abstracción especulativa, match estilo spike). No Co-Authored-By.
