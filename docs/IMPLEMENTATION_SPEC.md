# Betting Intelligence Platform — Implementation Specification

**Version:** 1.0  
**Date:** 2026-05-21  
**Status:** Approved — base para el refactor  

---

## 1. Decisiones clave (Decision Log)

Estas decisiones fueron tomadas en sesión de diseño y no se revisitan sin una razón explícita.

| # | Decisión | Alternativa descartada | Razón |
|---|----------|----------------------|-------|
| D-01 | Arquitectura D: Plugin Registry + Prediction Bus | Microservicios reales | Solo developer, sin Docker por ahora. El bus via Supabase da la misma observabilidad sin overhead |
| D-02 | Módulos core se rescatan, lógica de modelos se reescribe | Reescritura total / refactor quirúrgico | El bot v2, Supabase client y CLV son sólidos (>200 tests). La lógica de modelos necesita rediseño completo |
| D-03 | Sistema Mundial cubre solo WC2026 | Cualquier torneo de selecciones | Foco. Si funciona para WC2026 se generaliza después sin reescribir |
| D-04 | 5 señales externas en Mundial, implementadas progresivamente | Solo 2-3 señales | Todas aportan. "Progresivamente" = cada señal tiene su propio sprint, no todas en el día 1 |
| D-05 | Ligas: Phase 1 = 1X2 + O/U, Phase 2 = BTTS + Córners | Todos los mercados desde el día 1 | Validar pipeline completo con menos variables antes de expandir |
| D-06 | Sin límite de picks por partido — todos los que pasen el gate | 1 pick máximo por partido | Si hay EV real en 3 mercados del mismo partido, los 3 son válidos. La cuenta de salud gestiona la exposición total |
| D-07 | Walk-forward backtest obligatorio antes de ir live | Shadow mode / directo a producción | El backtest detecta look-ahead leaks y overfitting antes de arriesgar capital real |
| D-08 | Deployment: local (tmux) primero, VPS cuando CLV > +3% sostenido | VPS desde el día 1 | Evitar gasto hasta tener prueba de edge real |
| D-09 | Live Engine v3 congelado | Integrar al nuevo sistema | Demasiado complejo para refactorizar ahora. Se retoma si el sistema pre-partido prueba edge |

---

## 2. Arquitectura del Sistema

### Vista general

```
┌──────────────────────────────────────────────────────────────────┐
│  PLUGIN REGISTRY — Model Layer                                   │
│                                                                  │
│  ┌─────────────────────┐    ┌──────────────────────────────┐    │
│  │ LigasModel          │    │ MundialModel (WC2026)        │    │
│  │  Phase 1: 1X2, O/U  │    │  Bivariate Poisson           │    │
│  │  Phase 2: BTTS, Corn│    │  Signal Engineering          │    │
│  │  .can_handle()      │    │  Max-P Selection             │    │
│  │  .predict()         │    │  Locked Picks                │    │
│  │  .train()           │    │  .can_handle()               │    │
│  │  .evaluate()        │    │  .predict() / .lock()        │    │
│  └──────────┬──────────┘    └──────────────┬───────────────┘    │
└─────────────┼─────────────────────────────┼────────────────────┘
              └──────────────┬──────────────┘
                             ↓
              ┌──────────────────────────┐
              │  Supabase                │
              │  TABLE: predictions_raw  │  ← Prediction Bus
              └──────────────┬───────────┘
                             ↓
              ┌──────────────────────────┐
              │  Delivery Worker         │
              │  · lee predictions_raw   │
              │  · llama Claude          │
              │  · aplica gates finales  │
              │  · calcula Kelly         │
              │  · envía Telegram        │
              └──────────────┬───────────┘
                             ↓
              ┌──────────────────────────┐
              │  Telegram Bot v2         │  ← Sin cambios (rescatado)
              └──────────────┬───────────┘
                             ↓
              ┌──────────────────────────┐
              │  CLV Measurement Worker  │  ← T+2h post-partido
              │  Supabase: actualiza     │
              │  predictions_raw.clv     │
              └──────────────────────────┘
```

### Interfaz base de todos los modelos

```python
# src/bip/models/base.py

from abc import ABC, abstractmethod
import polars as pl
from pydantic import BaseModel as PydanticModel
from datetime import datetime

class Prediction(PydanticModel):
    fixture_id:     str
    source:         str           # 'ligas' | 'mundial'
    competition:    str           # 'PL' | 'WC2026' | etc.
    home_team:      str
    away_team:      str
    match_datetime: datetime
    market:         str           # '1x2' | 'ou_2.5' | 'btts' | 'corners_ou'
    selection:      str           # 'home' | 'draw' | 'away' | 'over' | 'under' | 'yes' | 'no'
    p_model:        float         # probabilidad del modelo [0, 1]
    ev:             float | None  # expected value vs Pinnacle (None para mundial)
    odds_at_pick:   float | None  # Pinnacle odds en el momento
    payload:        dict          # señales, features, contexto completo

class ModelMetrics(PydanticModel):
    clv_rolling_90d: float
    hit_rate:        float
    roi:             float
    brier_score:     float | None  # solo para modelos con calibración explícita

class BaseModel(ABC):
    @abstractmethod
    def can_handle(self, fixture: dict) -> bool:
        """Retorna True si este modelo puede generar predicciones para el fixture."""
        ...

    @abstractmethod
    def predict(self, fixture: dict) -> list[Prediction]:
        """Genera 0-N predicciones para el fixture."""
        ...

    @abstractmethod
    def train(self, data: pl.DataFrame) -> None:
        """Entrena el modelo con datos históricos."""
        ...

    @abstractmethod
    def evaluate(self, holdout: pl.DataFrame) -> ModelMetrics:
        """Evalúa el modelo en un conjunto de validación."""
        ...
```

---

## 3. Plan de Rescate de Código

### Módulos que sobreviven (sin cambios)

| Módulo actual | Razón | Acción |
|---------------|-------|--------|
| `core/settings.py` | Pydantic settings, funciona bien | Mover a nueva estructura, sin cambios |
| `core/logging.py` | Structlog setup, correcto | Reusar directamente |
| `core/storage/supabase_client.py` | Async client validado | Reusar, añadir métodos para `predictions_raw` |
| `core/telegram/` | Bot v2, 233 tests, sólido | Sin cambios. Delivery Worker lo usa como dependencia |
| `clv/` | CLV measurement completo | Reusar. Conectar a `predictions_raw` en vez de tabla propia |
| `sports/football/client.py` | API-Football v3 client | Reusar como data source de LigasModel |
| `evaluation/tournaments/locked_predictions/` | WC2026 locks ya existentes | No tocar — son datos, no código |

### Módulos que se reescriben

| Módulo actual | Problema | Reemplazo |
|---------------|----------|-----------|
| `train/` completo | Acoplado a pipeline antiguo, sin interfaz BaseModel | `src/bip/models/ligas/` con nueva interfaz |
| `sports/football/features.py` | Feature engineering sin contratos claros | `src/bip/models/ligas/features.py` rediseñado |
| `core/picks/engine.py` | EV calc acoplado a modelos específicos | Movido a `src/bip/shared/ev.py` como función pura |
| `production/` | Orchestrador monolítico antiguo | `src/bip/pipeline/orchestrator.py` usando Plugin Registry |
| `evaluation/live/` (v1, v2) | Redundante con v3 congelado | Archivar, no reescribir |

### Módulos que se congelan (sin tocar)

| Módulo | Razón |
|--------|-------|
| `evaluation/live/engine_v3/` | Decisión D-09. Funcional pero fuera de scope |
| `sports/football/sportmonks/` | Depende de v3. Congelado con él |

---

## 4. Sistema 1 — Ligas Nacionales

### 4.1 Estructura de archivos

```
src/bip/models/
└── ligas/
    ├── __init__.py
    ├── model.py            ← LigasModel implementa BaseModel
    ├── features.py         ← Feature engineering pipeline
    ├── trainer.py          ← Walk-forward training harness
    ├── calibration.py      ← Isotonic calibration por liga
    ├── backtest.py         ← Backtest + gate de validación
    └── markets/
        ├── model_1x2.py    ← Phase 1
        ├── model_ou.py     ← Phase 1
        ├── model_btts.py   ← Phase 2
        └── model_corners.py← Phase 2
```

### 4.2 Fuentes de datos

| Dato | Fuente | Endpoint / Dataset |
|------|--------|--------------------|
| Fixtures del día | API-Football v3 | `GET /fixtures?date=YYYY-MM-DD` |
| Odds actuales (Pinnacle) | The Odds API v4 | `GET /sports/soccer/odds?regions=eu&bookmakers=pinnacle` |
| Historial de partidos | API-Football v3 | `GET /fixtures?league=&season=` |
| xG por partido | Understat | `understat_client.py` (ya existe) |
| Lesiones | API-Football v3 | `GET /injuries?fixture=` |
| Lineups | API-Football v3 | `GET /fixtures/lineups?fixture=` |

### 4.3 Feature Engineering

Features calculadas por partido, por mercado:

**Forma reciente (últimos 5 home / últimos 5 away):**
- `home_goals_scored_avg_5` / `away_goals_scored_avg_5`
- `home_goals_conceded_avg_5` / `away_goals_conceded_avg_5`
- `home_xg_for_avg_5` / `away_xg_for_avg_5`
- `home_points_last_5` / `away_points_last_5`
- `home_clean_sheets_pct_5` / `away_clean_sheets_pct_5`

**H2H (últimos 3 años, mismo venue cuando posible):**
- `h2h_home_win_pct` / `h2h_draw_pct` / `h2h_away_win_pct`
- `h2h_avg_total_goals`
- `h2h_btts_pct`

**Contexto del partido:**
- `home_league_position` / `away_league_position`
- `games_without_scoring_home` / `games_without_scoring_away`
- `home_is_injured_key_player: bool`
- `elo_home` / `elo_away` (calculado de historial de la liga)
- `days_since_last_match_home` / `days_since_last_match_away`

### 4.4 Modelos ML

**Ensemble por mercado:** XGBoost + CatBoost + LightGBM → meta-learner logístico

```python
# Parámetros base (ajustar por liga en validación)
xgb_params = {
    "n_estimators": 500, "max_depth": 5,
    "learning_rate": 0.05, "subsample": 0.8,
    "colsample_bytree": 0.8, "tree_method": "hist"
}
# Calibración: IsotonicRegression por (liga, mercado)
# NO usar CalibratedClassifierCV(cv="prefit") — eliminado en scikit-learn 1.8
```

**Ligas cubiertas (5):**
- Premier League (ID: 39)
- La Liga (ID: 140)  
- Serie A (ID: 135)
- Bundesliga (ID: 78)
- Ligue 1 (ID: 61)

### 4.5 EV Calculation y Gate

```python
# src/bip/shared/ev.py

def calculate_ev(p_model: float, decimal_odds: float) -> float:
    """EV = P_modelo × (odds - 1) - (1 - P_modelo)"""
    return p_model * (decimal_odds - 1) - (1 - p_model)

# Gate: EV > 0.05 (5%) para pasar al siguiente paso
EV_THRESHOLD = 0.05
```

### 4.6 Claude Enrichment (Delivery Worker)

Claude se llama **una vez por fixture** que tenga al menos un pick candidato, no una vez por pick.

```
Input al Delivery Worker:
  - fixture_context: stats, xG, posición liga, lesiones confirmadas
  - candidate_picks: lista de Prediction[] para este fixture
  - current_odds: cuotas al momento

Claude output (Pydantic model):
  - confidence_modifier: float  # [-0.3, +0.3]
  - red_flags: list[str]        # si no vacío, kill todos los picks del fixture
  - narrative: str              # 1-2 oraciones para el alert
```

**Regla de red flags:** Si Claude retorna cualquier red flag → todos los picks del fixture mueren, sin excepción.

### 4.7 Kelly Sizing y Account Safety

```python
def kelly_fraction(ev: float, odds: float) -> float:
    p = (ev + 1) / odds          # probabilidad implícita del modelo
    q = 1 - p
    b = odds - 1
    return (b * p - q) / b       # Kelly completo

def safe_stake(kelly_f: float, bankroll: float) -> float:
    return min(kelly_f * 0.25, 0.05) * bankroll  # ¼ Kelly, cap 5% del bankroll
```

**Account Safety gates:**
- Stake máximo por pick: 5% del bankroll
- Exposición máxima diaria: 15% del bankroll
- Si un mercado específico tiene > 3 picks en 7 días: reducir stake 50%

### 4.8 Phasing de mercados

| Fase | Mercados | Condición para avanzar |
|------|----------|----------------------|
| Phase 1 | 1X2 + O/U 2.5 | Backtest walk-forward CLV > +3% en los 5 ligas |
| Phase 2 | + BTTS + Córners | Phase 1 lleva 60 días live con CLV > +1% sostenido |

---

## 5. Sistema 2 — Mundial WC2026

### 5.1 Scope exacto

- **Competencia:** FIFA World Cup 2026 (México / EE.UU. / Canadá)
- **Fase inicial de inicio:** Pre-torneo (3 semanas antes del primer partido, ~22 mayo 2026)
- **Partidos cubiertos:** Fase de grupos + octavos + cuartos + semifinales + final (88 partidos)
- **No incluye:** eliminatorias, amistosos previos, tercero y cuarto puesto (opcional)

### 5.2 Estructura de archivos

```
src/bip/models/
└── mundial/
    ├── __init__.py
    ├── model.py              ← MundialModel implementa BaseModel
    ├── signal_engineering.py ← 5 señales externas
    ├── poisson.py            ← Bivariate Poisson + Dixon-Coles
    ├── max_p_selector.py     ← Scan de mercados + selección Max-P
    ├── locker.py             ← Locked picks con SHA-256
    ├── matchday_validator.py ← Validación T-2h
    └── data/
        ├── wc2026_fixtures.json
        ├── team_profiles.json  ← generado por signal_engineering
        └── elo_ratings.json
```

### 5.3 Fuentes de datos

| Dato | Fuente | Dataset / Endpoint |
|------|--------|--------------------|
| Historial selecciones | `martj42/international_results` | 49k partidos desde 1872, CC0 |
| xG histórico torneos | StatsBomb open data | WC2018/2022, Euro2020/2024, Copa2024, AFCON2023 |
| Fixtures WC2026 | API-Football v3 | `GET /fixtures?league=1&season=2026` |
| Lesiones / lineups | API-Football v3 | `GET /injuries` + `GET /fixtures/lineups` |
| Técnicos actuales | API-Football v3 | `GET /coaches?team=` |
| Odds torneos | The Odds API v4 | `GET /sports/soccer_wc/odds` (si disponible) |

### 5.4 Signal Engineering — 5 señales

Implementadas en sprints independientes. Cada señal produce un campo en `team_profile`.

---

**Señal 1: Home/Away split en clasificatoria**

*Qué mide:* cuánto peor juega el equipo de visitante históricamente.

```python
# Fuente: martj42, filtrar solo partidos de clasificatoria (tournament = 'FIFA World Cup qualification')
# Para cada selección:
away_goals_rate = goals_scored_as_away / away_matches
home_goals_rate = goals_scored_as_home / home_matches
away_perf_ratio = away_goals_rate / home_goals_rate  # < 1 = peor de visitante

# Aplicación en modelo: ajuste de λ_attack
λ_attack_adjusted = λ_attack_base * away_perf_ratio
```

Señal de alto impacto — muchas selecciones CONMEBOL y CAF tienen away_perf_ratio < 0.70.

---

**Señal 2: Cambio de técnico reciente**

*Qué mide:* inestabilidad del sistema táctico.

```python
# Fuente: API-Football GET /coaches?team={team_id}
coach_start_date: date  # inicio del técnico actual
coach_tenure_days = (today - coach_start_date).days

# Aplicación: descuento sobre λ si el DT lleva menos de 90 días
if coach_tenure_days < 90:
    λ_home *= 0.88
    λ_away *= 0.88
elif coach_tenure_days < 180:
    λ_home *= 0.94
    λ_away *= 0.94
# > 180 días: sin ajuste
```

---

**Señal 3: Goal timing distribution**

*Qué mide:* cuándo tienden a meter goles (relevante para BTTS y O/U en tiempo específico).

```python
# Fuente: martj42 (si tiene campo `minute`) o API-Football events históricos
# Franjas: 0-30, 30-60, 60-75, 75-90
goal_timing = {
    "0_30": goals_in_range / total_goals,
    "30_60": ...,
    "60_75": ...,
    "75_90": ...,
}
late_goal_rate = goal_timing["75_90"]  # > 0.30 = equipo que suele decidir tarde

# Aplicación: contexto para Claude (no ajuste directo de λ)
# También útil para construir features de BTTS en Phase 2
```

---

**Señal 4: Situación en el grupo**

*Qué mide:* motivación real en el momento del partido.

```python
# Fuente: standings API-Football + cálculo propio
# Calculado justo antes de cada partido (match day)

group_context = {
    "must_win_home": bool,        # si pierde, queda eliminado
    "must_win_away": bool,
    "already_through_home": bool, # ya clasificó a octavos
    "already_through_away": bool,
    "already_eliminated_home": bool,
    "already_eliminated_away": bool,
    "points_diff": int,           # diferencia con el 3er clasificado
}

# Aplicación: λ penalty si equipo ya está clasificado Y juega de visitante
if already_through_home and home_is_away_team_in_tournament:
    λ_adjusted *= 0.90  # menor motivación
# También: contexto crítico para Claude (puede invalidar picks)
```

---

**Señal 5: Calidad del plantel (liga de los jugadores)**

*Qué mide:* nivel competitivo de los jugadores vs la media del torneo.

```python
# Fuente: API-Football squads + mapeo liga → tier manual
# Tier de ligas:
LEAGUE_TIER = {
    "Premier League": 1, "La Liga": 1, "Serie A": 1,
    "Bundesliga": 1, "Ligue 1": 1,
    "Eredivisie": 2, "Primeira Liga": 2, "Pro League (Bélgica)": 2,
    # tier 3+: ligas nacionales menores
}

squad_quality = sum(LEAGUE_TIER[player.league] for player in squad) / len(squad)
top5_pct = len([p for p in squad if LEAGUE_TIER[p.league] == 1]) / len(squad)

# Aplicación: ajuste del ELO prior
elo_adjusted = elo_base * (1 + 0.05 * (top5_pct - 0.50))
# equipo con 80% en top-5 ligas → ELO +15% vs equipo con 20%
```

---

### 5.5 Modelo Estadístico: Bivariate Poisson + Dixon-Coles

```python
# Librería: penaltyblog (1.9.0) — no reinventar la rueda
from penaltyblog.models import DixonColes

# Calibración:
# - Entrenar en WC2018 + WC2022 + Euro2020 + Euro2024 + Copa2024 + AFCON2023
# - NO incluir ligas domésticas (dinámicas distintas)
# - Peso temporal: partido más reciente = peso mayor

# Output: P(goals_home=g1, goals_away=g2) para g1, g2 en [0, 7]
# Del output se derivan todos los mercados
```

### 5.6 Max-P Selection

```python
# src/bip/models/mundial/max_p_selector.py

MARKETS_TO_SCAN = [
    ("1x2", "home"), ("1x2", "draw"), ("1x2", "away"),
    ("ou_1.5", "over"), ("ou_1.5", "under"),
    ("ou_2.5", "over"), ("ou_2.5", "under"),
    ("ou_3.5", "over"), ("ou_3.5", "under"),
    ("btts", "yes"), ("btts", "no"),
    ("corners_ou", "over"), ("corners_ou", "under"),
]

P_MAX_THRESHOLD = 0.65  # ajustar post-calibración en torneos históricos

def select_max_p_pick(match_probs: dict, threshold: float) -> Prediction | None:
    """
    Escanea todos los mercados y retorna el pick con mayor P_modelo.
    Retorna None si ninguno supera el threshold.
    """
    candidates = [
        (market, selection, prob)
        for (market, selection), prob in match_probs.items()
    ]
    best = max(candidates, key=lambda x: x[2])
    market, selection, p_max = best

    if p_max < threshold:
        return None

    return Prediction(
        market=market, selection=selection,
        p_model=p_max, ev=None,  # EV no aplica en Mundial
        ...
    )
```

### 5.7 Locked Picks

```python
# src/bip/models/mundial/locker.py
import hashlib, json
from datetime import datetime

def lock_pick(prediction: Prediction, narrative: str) -> dict:
    content = {
        "fixture_id": prediction.fixture_id,
        "market": prediction.market,
        "selection": prediction.selection,
        "p_model": prediction.p_model,
        "timestamp_locked": datetime.utcnow().isoformat(),
        "narrative": narrative,
    }
    content_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True).encode()
    ).hexdigest()

    return {**content, "sha256": content_hash, "status": "locked"}
```

### 5.8 Match Day Validation (T-2h)

```python
# Checks antes de enviar el locked pick:
def validate_locked_pick(pick: dict, fixture: dict) -> tuple[bool, str | None]:
    # 1. ¿Lineup disponible?
    if not fixture["lineup_confirmed"]:
        return True, None  # esperar hasta 30min antes, no invalidar

    # 2. ¿Cambio de titular clave desde que se bloqueó?
    key_players_missing = check_key_player_absence(pick, fixture)
    if key_players_missing:
        return False, f"Titular clave ausente: {key_players_missing}"

    # 3. ¿Odds still available? (si el libro cerró el mercado)
    if not fixture["odds_available"][pick["market"]]:
        return False, "Mercado cerrado por el libro"

    return True, None
```

---

## 6. Shared Infrastructure

### 6.1 Prediction Bus — Schema Supabase

```sql
CREATE TABLE predictions_raw (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source              TEXT NOT NULL,         -- 'ligas' | 'mundial'
    fixture_id          TEXT NOT NULL,
    competition         TEXT NOT NULL,
    home_team           TEXT NOT NULL,
    away_team           TEXT NOT NULL,
    match_datetime      TIMESTAMPTZ NOT NULL,
    market              TEXT NOT NULL,
    selection           TEXT NOT NULL,
    p_model             FLOAT NOT NULL,
    ev                  FLOAT,                 -- NULL para mundial
    odds_at_pick        FLOAT,
    confidence_modifier FLOAT,                 -- Claude output
    red_flags           TEXT[],                -- Claude output
    narrative           TEXT,                  -- Claude output
    payload             JSONB NOT NULL,        -- contexto completo del modelo
    status              TEXT NOT NULL DEFAULT 'pending',
    -- valores: 'pending' | 'sent' | 'killed' | 'invalidated' | 'shadow'
    kill_reason         TEXT,
    sent_at             TIMESTAMPTZ,
    stake_units         FLOAT,                 -- Kelly calculado
    -- post-match
    result              TEXT,                  -- 'win' | 'loss' | 'void'
    clv                 FLOAT,
    closing_odds        FLOAT,
    pl_units            FLOAT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_predictions_raw_status   ON predictions_raw (status);
CREATE INDEX idx_predictions_raw_source   ON predictions_raw (source);
CREATE INDEX idx_predictions_raw_match_dt ON predictions_raw (match_datetime);
CREATE INDEX idx_predictions_raw_fixture  ON predictions_raw (fixture_id);
```

### 6.2 Delivery Worker

```
Cron: cada 15 minutos (APScheduler)

Lógica:
1. SELECT * FROM predictions_raw
   WHERE status = 'pending'
   AND match_datetime BETWEEN now() + 30min AND now() + 4h

2. Para cada fixture con picks pending:
   a. Llamar Claude (una vez por fixture, no por pick)
   b. Si red_flags → marcar todos como 'killed', skip
   c. Aplicar confidence_modifier a EV (ligas) o p_model (mundial)
   d. Calcular stake via Kelly
   e. Verificar account safety (exposición diaria)
   f. Enviar Telegram alert
   g. UPDATE predictions_raw SET status='sent', sent_at=now()
```

### 6.3 Formato Telegram Alert

**Ligas:**
```
[LIGA] Premier League
Arsenal vs Chelsea
Pick: Over 2.5 @ 1.95
EV: +7.2% · Stake: 1.2u
---
[narrativa Claude, 1-2 oraciones]
```

**Mundial:**
```
[WC2026] Fase de Grupos
Argentina vs Arabia Saudita
Pick: Over 1.5 @ 1.35
P_modelo: 81%
Stake: 0.8u
---
[narrativa Claude, 1-2 oraciones]
```

### 6.4 CLV Measurement Worker

```
Trigger: T + 2h después de cada partido

1. SELECT * FROM predictions_raw WHERE status='sent' AND result IS NULL
   AND match_datetime < now() - 2h

2. Para cada pick:
   a. Fetch Pinnacle closing line (The Odds API)
   b. CLV = implied_prob(odds_at_pick) - implied_prob(closing_odds)
   c. Fetch resultado del partido (API-Football)
   d. Calcular result ('win'/'loss'/'void') y P/L
   e. UPDATE predictions_raw SET result=, clv=, closing_odds=, pl_units=

3. Calcular rolling KPI (Supabase function):
   - CLV rolling 90d por source ('ligas' | 'mundial')
   - Si CLV_ligas < +1% → notificar por Telegram (audit alert)
```

---

## 7. Estrategia de Validación

### 7.1 Ligas — Walk-Forward Backtest (gate obligatorio)

```
Configuración:
  - Window de entrenamiento: 3 temporadas
  - Window de test: 4 semanas (walk-forward)
  - Iteraciones: mínimo 20 folds por liga

Gate de producción (HARD — no negociable):
  - CLV promedio > +3% en test set
  - Brier score < 0.25 (calibración aceptable)
  - Mínimo 100 picks en test set por mercado

Si no se pasa el gate: el modelo NO va a producción.
No hay excepción, no hay "lo ajustamos live".
```

### 7.2 Mundial — Backtest en torneos históricos

```
Dataset de validación:
  - WC2022 (64 partidos) — test principal
  - Euro2024 (51 partidos) — test secundario
  - Copa2024 (32 partidos) — test terciario

Entrenar en: WC2018 + Euro2020 + AFCON2023 + todo lo anterior al test

Gate de producción:
  - Hit rate en picks P_max > 65% debe ser > 60% (mejor que azar calibrado)
  - Brier score < 0.22
  - Mínimo 30 picks en cada torneo de test

KPI post-WC2026:
  - Brier score del modelo vs baseline (ELO puro)
  - Hit rate por franja de P_max (65-70%, 70-80%, 80%+)
  - ROI realizado
```

---

## 8. Plan de Fases de Implementación

```
FASE 0 — Fundación (Semana 1-2)
  · Definir estructura de directorios nueva
  · Implementar BaseModel + Prediction schema
  · Crear tabla predictions_raw en Supabase
  · Rescatar y adaptar módulos core (settings, Supabase client, Telegram)
  · Delivery Worker skeleton (sin Claude, sin gates — solo lee y logea)

FASE 1 — Ligas Phase 1 (Semana 3-6)
  · LigasModel con mercados 1X2 + O/U
  · Feature engineering pipeline
  · Ensemble XGB + CatBoost + LGB
  · Walk-forward backtest harness
  · Pasar gate: CLV > +3% en backtest
  · Claude enrichment en Delivery Worker
  · Shadow mode (status='shadow') para 2 semanas

FASE 2 — Ligas Live + Phase 2 (Semana 7-10)
  · Activar picks reales (status='sent') con stake mínimo 0.5u
  · Añadir mercados BTTS + Córners
  · CLV Measurement Worker completo
  · KPI dashboard en Supabase

FASE 3 — Mundial WC2026 (Semana 11-18)
  · Signal Engineering (5 señales, 1 sprint por señal)
  · Bivariate Poisson calibrado en torneos históricos
  · Max-P Selector + gate de confianza
  · Locker con SHA-256
  · Backtest en WC2022 + Euro2024
  · Claude validation para mundial
  · Matchday Validator
  · Pre-torneo: generar y lockear picks para fase de grupos

FASE 4 — Producción (Semana 19+)
  · Monitoreo CLV continuo
  · VPS cuando CLV_ligas > +3% sostenido 90 días
  · Evaluar expansión a BTTS + Córners si Phase 1 cumple gate
```

---

## 9. Restricciones Técnicas

| Restricción | Detalle |
|-------------|---------|
| Sin GPU | Todo ML en CPU. XGBoost `tree_method="hist"` obligatorio |
| Inference < 500ms | Por fixture. Monitorear con structlog timings |
| API-Football Pro | 300 req/min. Rate limiting en el cliente, no en los modelos |
| The Odds API Rookie | 500 req/mes. Solo para CLV (closing lines post-partido), no para odds en tiempo real |
| Stake máximo Betano | ¼ Kelly hard cap. Sin excepciones en el código |
| Account safety | Rotar mercados, variar patrones de stake. Lógica en Delivery Worker |
| Python 3.12 | No 3.13+ (CatBoost wheels). No 3.11 (sin mejoras de perf de 3.12) |
| APScheduler 3.x | NO 4.x (alpha, API rota). Pin a 3.11.x |
| Sin FastAPI | No hay servidor web. Telegram-only delivery |

---

## 10. Fuera de Scope (V1)

| Item | Razón | Cuándo revisar |
|------|-------|----------------|
| Live Engine v3 | Decisión D-09. Congelado. | Cuando pre-partido pruebe edge sostenido |
| Otros torneos (Euro, Copa América, AFCON) | Decisión D-03. WC2026 primero. | Post-WC2026 si el sistema funciona |
| Mercados de jugador (anytime scorer, tarjetas) | Datos insuficientes | Phase 3 o posterior |
| API web / dashboard | Sin servidor web en V1 | Si se despliega en VPS con demanda |
| Bet placement automático | Fuera de alcance por diseño. Sistema siempre semi-manual | Nunca (riesgo de cuenta) |
| Arbitraje entre libros | Requiere múltiples cuentas activas | No planificado |
| Docker / orquestación de contenedores | Single-VPS, overkill | Al escalar a múltiples modelos independientes |

---

## 11. Convenciones del nuevo codebase

*(Se irán definiendo a medida que emergen patrones. Este espacio es vivo.)*

- `Prediction.payload` siempre tiene `features_snapshot: dict` con los valores de features en el momento del pick (para reproducibilidad y debug)
- Los modelos no llaman a APIs externas directamente — reciben datos ya hidratados del orchestrador
- Todo log de un pick incluye `fixture_id` y `prediction_id` como campos estructurados (structlog)
- Tests de modelos usan fixtures sintéticos vía `conftest.py`, nunca datos de producción
- No `print()` en ningún módulo de producción — solo `structlog`
