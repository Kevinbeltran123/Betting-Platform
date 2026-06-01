---
quick_id: 260601-pe4
slug: price-layer
status: complete
date: 2026-06-01
commit: adbe29d
---

# SUMMARY — Capa de precio (#1)

## Qué se entregó
La capa de precio del brief prepartido, en alcance **híbrido**:
- `scripts/spike/tsp/45_match_odds.py` (nuevo): resuelve el fixture vía API-Football,
  pull `/odds`, parsea los mercados que el API puebla fiable (Match Winner, Goals O/U,
  BTTS, Asian Handicap) de Betano/Pinnacle/Betfair, de-viga el "justo" desde Pinnacle,
  mergea cuotas manuales y escribe `data/cache/tsp/odds/{slug}.json`. Degrada limpio
  cuando las cuotas aún no están en la ventana ~7-14d pre-KO.
- `scripts/spike/tsp/43_match_brief.py` (editado): sección `## Precio y línea` con el
  puente evidencia↔mercado. AUTO (1X2/OU/BTTS/AH con fair Pinnacle + alerta si Elo y
  mercado discrepan) y MANUAL (córners/tarjetas vs rate combinado crudo). Sin EV ni pick.
- `scripts/spike/tsp/manual_odds_TEMPLATE.json` (nuevo): plantilla del input manual.

## Verdad de campo que moldeó el diseño (probe en vivo, key Ultra, 2026-06-01)
- API-Football `/odds`: cuotas en ventana móvil ~7-14d pre-KO (WC season 2026 → results=0 hoy).
- Cuando hay: 9 casas incl. Betano/Pinnacle/Betfair, pero córners/tarjetas NO se pueblan
  pese a estar en el catálogo (337 bet types) → córners/tarjetas/props van por MANUAL.
- Suscripción Ultra expira 2026-06-24 (operador confirmó que renueva).

## Verificación
- Parser AUTO contra fixture real con cuotas (id 1400644): 1X2 three-way de-vig correcto
  (0.718/0.182/0.099), OU/BTTS/AH parseados con fair. OK.
- Brief: 3 ramas OK — AUTO poblado (con alerta de discrepancia Elo↔mercado), AUTO
  vacío + MANUAL (córners 9.5 vs ~7.7 → Under blanda; tarjetas 4.5 vs ~3.7), y sin caché.
- `ruff check` 45: limpio. 43: E501 preexistentes del archivo (no introducidas por el cambio).

## Notas / deuda (alimenta el roadmap)
- El rate de córners/tarjetas del puente es CRUDO (no SoS-ajustado) y la capa de tarjetas
  no cruza árbitro todavía → se afina con #2 (props/tarjetas desde /fixtures/players+events)
  y #7 (tabla de árbitros desde API-Football).
- La sección de precio vive en 43 (el ensamblador "brief"); unificar con build_match_intel
  queda para #9.

## Siguiente
#2 del roadmap: props de jugador y tarjetas desde `/fixtures/players` + `/fixtures/events`
de la selección actual (reemplaza StatsBomb-torneo viejo) — alimenta el puente MANUAL de #1.
