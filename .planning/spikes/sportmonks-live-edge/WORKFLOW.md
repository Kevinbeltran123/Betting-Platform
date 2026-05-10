# Live betting workflow — empezar a probar HOY

**Goal:** correr el sistema en vivo, capturar picks reales, registrar
qué pasó después de cada uno, y al cabo de 1-2 semanas tener evidencia
empírica honesta de si encuentra valor.

---

## Setup inicial (1 vez, ~2 min)

```bash
# Confirma que la API responde (sólo deberías ver "8 LIVE FIXTURES" o
# similar — no errores)
uv run python -c "
import asyncio
from bip.sports.football.sportmonks.client import sportmonks_client_from_env
async def main():
    async with sportmonks_client_from_env() as c:
        live = await c.list_inplay_fixtures(includes=['state'])
        print(f'{len(live)} live fixtures right now')
asyncio.run(main())
"
```

Inicializa el DB (vacío):

```bash
uv run python -m scripts.spike.sportmonks.picks_cli stats
# Output: "Total picks: 0"
```

---

## Modo principal — Watcher persistente

Corre durante un partido / tarde de partidos. Sólo notifica picks NUEVOS
(dedup por ventana de 5 min):

```bash
# Cómodo: edge ≥ 4%, polling cada 45s, notificación macOS
uv run python -m scripts.spike.sportmonks.watch

# Más estricto (menos picks pero mayor confianza)
uv run python -m scripts.spike.sportmonks.watch --min-edge 6.0

# Con beep terminal (útil si tienes notifs apagadas)
uv run python -m scripts.spike.sportmonks.watch --beep --no-notify

# Test rápido (1 minuto)
uv run python -m scripts.spike.sportmonks.watch --duration 60 --interval 30
```

**Output esperado:**
```
🟢 Watching live matches.  edge ≥ 4.0%   interval=45s
   macOS notifications: ON

[14:32:15] round=   1 emitted= 12 new= 12 elapsed=4.7s

🚨 NEW PICK: + 9.05% Real Madrid vs Barcelona (min 32)
    fulltime_result/draw @ 4.30  stake=0.85%  id=42

🚨 NEW PICK: +12.40% Real Madrid vs Barcelona (min 32)
    btts/yes @ 1.65  stake=1.50%  id=43

[14:33:00] round=   2 emitted= 14 new= 2 elapsed=4.9s
```

Cada pick NUEVO genera:
1. Notificación macOS (toast)
2. Log file en `reports/sportmonks_live/watch.log` (tail-friendly)
3. Row en SQLite `data/cache/sportmonks/picks.db`
4. Print en terminal con id

**Ctrl+C** termina limpiamente.

---

## Workflow durante un partido

Cuando el watcher emite una notificación:

### 1. Mira el pick
```bash
uv run python -m scripts.spike.sportmonks.picks_cli list --limit 5
```

### 2. Verifica la cuota REAL en Betano
- Sportmonks expone bookmaker_id=2 (mansionbet); tú apuestas en
  Betano que tiene márgenes diferentes
- Compara: si Betano tiene cuota IGUAL o MEJOR → buen pick
- Si Betano tiene cuota MUCHO peor → el edge ya se cerró, ignora

### 3. Si decides apostar, márcalo
```bash
uv run python -m scripts.spike.sportmonks.picks_cli place 42 \
    --odd 4.20 --stake 1.0 --notes "Betano un poco peor que Sportmonks"
```

### 4. Cuando termine el partido, califícalo
```bash
# Si ganó (profit auto-calculado de cuota)
uv run python -m scripts.spike.sportmonks.picks_cli grade 42 won

# Si perdió
uv run python -m scripts.spike.sportmonks.picks_cli grade 42 lost

# Si fue void (anulado, lesión clave en min 1, etc)
uv run python -m scripts.spike.sportmonks.picks_cli grade 42 void
```

---

## Revisión periódica (cada 2-3 días)

```bash
# Ver picks pendientes (los de partidos terminados que aún no calificaste)
uv run python -m scripts.spike.sportmonks.picks_cli pending

# Ver TODOS los picks de un partido (útil para ver evolución)
uv run python -m scripts.spike.sportmonks.picks_cli fixture 19706148

# Resumen agregado — ESTO ES EL EXPERIMENTO
uv run python -m scripts.spike.sportmonks.picks_cli stats
```

**Output ejemplo después de 1 semana:**
```
======================================================================
PICK TRACKER — AGGREGATE STATS
======================================================================
  Total picks:              247
  Graded picks:             203
  Placed at Betano:         28
  Wins:                     91
  Win rate:                 44.8%
  Total P/L (units):        +12.40
  ROI per pick:             +6.10%

  MARKET                         N  WINS  WIN%   ROI%
  ------------------------------------------------------------
  fulltime_result               45    18 40.0%  +8.50
  btts                          38    23 60.5% +12.20
  ou_2_5                        32    14 43.8%  +5.30
  first_half_result             21     6 28.6%  -7.20
  ...
```

---

## Modo "captura silenciosa" (paralelo al watcher)

Si quieres tener el predictor capturando snapshots para backtest pero
sin que te notifique (por ejemplo durante sueño / trabajo):

```bash
# Background, sin alertas, captura cada 30s
nohup uv run python -m scripts.spike.sportmonks.capture_loop \
    --interval 30 > /tmp/capture.log 2>&1 &
```

Esto acumula snapshots en `data/cache/sportmonks/snapshots/` para que el
backtest replay tenga material.

---

## Backtest (cuando hayas acumulado partidos completos)

```bash
uv run python -m scripts.spike.sportmonks.backtest
```

Output: `reports/sportmonks_backtest/backtest_<ts>.json` con ROI / win rate
agregado y per-market.

**Cuando esto se vuelve útil:** después de 2-3 días corriendo el capture
loop durante prime-time europeo, deberías tener ~30-50 partidos
COMPLETOS cacheados → el backtest puede emitir ROI honesto.

---

## Heurísticas operativas

### Stake & bankroll

- Default: ¼ Kelly, max 1.5% bankroll por pick
- Si Kelly sugiere 1.5% y la cuota es 5.0+, considera reducir a 1.0%
  (varianza alta)
- Si Kelly sugiere <0.5%, considera no apostar (transaction cost)

### Cuándo confiar en el pick

| Señal | Acción |
|---|---|
| Edge ≥ 8% en 1X2 / Match Goals con cuota 1.50-3.00 | Apuesta |
| Edge ≥ 5% en BTTS / OU con cuota 1.50-2.50 | Apuesta |
| Edge ≥ 10% en HT/FT, Correct Score, exotic | Mira con cuidado, varianza alta |
| Edge ≥ 50% (probable cuota stale) | Verifica Betano antes de apostar |
| Min < 15 (early game) | Skip — modelo aún no tiene suficiente data live |
| Min > 85 con score-state extremo | Skip — bookies suelen suspender pronto |

### Red flags que invalidan un pick

- Cuota Betano más de 10% peor que Sportmonks (pick ya cerrado)
- Pick aparece, desaparece, vuelve a aparecer dentro de 2-3 min
  (señal de mercado nervioso)
- Lineup confirmado tiene un cambio sorpresivo no reflejado en
  Sportmonks predictions
- Equipo perdiendo recibe gol del otro lado mientras estabas verificando
  (escenario cambió radicalmente)

---

## Datos para juzgar al final del trial (2026-05-23)

### Verde — Continuar pagando trial

- ≥ 100 picks calificados
- ≥ 30 picks placed-at-Betano (volumen real, no sólo recomendaciones)
- ROI per pick ≥ +3% NETO (después margen Betano)
- Win rate dentro de ±3pp del esperado por las cuotas

### Amarillo — Más datos antes de decidir

- 50-100 picks calificados
- ROI entre 0% y +3%
- Variance alta entre mercados

### Rojo — Cancelar trial

- < 50 picks placed (no hay volumen)
- ROI ≤ 0%
- Picks consistentemente "se cerraron antes" (Betano peor que Sportmonks)
- Modelo emite picks en mercados específicos donde NUNCA gana

---

## Comandos referencia rápida

```bash
# Lo más usado
uv run python -m scripts.spike.sportmonks.watch                    # iniciar watcher
uv run python -m scripts.spike.sportmonks.picks_cli stats          # ver agregado
uv run python -m scripts.spike.sportmonks.picks_cli pending        # qué falta calificar
uv run python -m scripts.spike.sportmonks.picks_cli grade 42 won   # calificar

# Inspección
uv run python -m scripts.spike.sportmonks.picks_cli list --limit 50
uv run python -m scripts.spike.sportmonks.picks_cli fixture <fixture_id>

# Marcar pick como apostado
uv run python -m scripts.spike.sportmonks.picks_cli place 42 \
    --odd 4.20 --stake 1.0 --notes "..."

# Backtest replay
uv run python -m scripts.spike.sportmonks.backtest
```

Output canónico:
- `data/cache/sportmonks/picks.db` — SQLite con TODO el historial
- `data/cache/sportmonks/snapshots/{fixture_id}/{ts}.json` — replay corpus
- `reports/sportmonks_live/watch.log` — log tail-friendly del watcher
- `reports/sportmonks_live/picks_<ts>.{md,json}` — reports per-scan (live_picks)
- `reports/sportmonks_backtest/backtest_<ts>.json` — backtest aggregate
