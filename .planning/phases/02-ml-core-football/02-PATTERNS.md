# Phase 2: ML Core — Football - Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 22 new/modified files
**Analogs found:** 16 / 22

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/seed_historical.py` | script | batch / request-response | `src/bip/sports/football/client.py` + `src/bip/core/storage/parquet_store.py` | role-match (orchestration layer) |
| `src/bip/sports/football/features.py` (MODIFY) | service | transform | `src/bip/sports/football/features.py` | exact (self-expand) |
| `src/bip/train/__init__.py` | config | — | `src/bip/sports/__init__.py` | role-match |
| `src/bip/train/pipeline.py` | service | batch | `src/bip/sports/football/plugin.py` | role-match (orchestrator) |
| `src/bip/train/stacking.py` | service | transform | `src/bip/sports/football/features.py` | partial-match (data transform) |
| `src/bip/train/calibration.py` | utility | transform | `src/bip/core/types.py` (CalibrationMethod enum) | partial-match |
| `src/bip/train/features.py` | service | transform | `src/bip/sports/football/features.py` | exact (same pattern) |
| `src/bip/train/registry.py` | service | file-I/O | `src/bip/core/storage/repositories.py` | role-match (registry/CRUD) |
| `src/bip/train/loader.py` | service | file-I/O | `src/bip/core/storage/repositories.py` | role-match |
| `src/bip/train/cli.py` | utility | request-response | `src/bip/sports/football/plugin.py` | partial-match (entry point) |
| `src/bip/train/metadata.py` | model | — | `src/bip/core/storage/models.py` | exact (Pydantic model) |
| `src/bip/train/walkforward.py` | service | batch | `src/bip/sports/football/features.py` | partial-match |
| `src/bip/train/backtest.py` | service | batch | `src/bip/core/storage/repositories.py` (ClvRecord pattern) | partial-match |
| `src/bip/train/base_models.py` | utility | transform | none | no analog |
| `src/bip/sports/football/plugin.py` (MODIFY) | service | request-response | `src/bip/sports/football/plugin.py` | exact (self-extend) |
| `src/bip/sports/football/model_loader.py` | service | file-I/O | `src/bip/core/storage/parquet_store.py` | role-match |
| `src/bip/core/storage/models.py` (MODIFY) | model | — | `src/bip/core/storage/models.py` | exact (self-extend) |
| `src/bip/core/storage/repositories.py` (MODIFY) | service | CRUD | `src/bip/core/storage/repositories.py` | exact (self-extend) |
| `src/bip/core/settings.py` (MODIFY) | config | — | `src/bip/core/settings.py` | exact (self-extend) |
| `supabase/migrations/20260423000000_add_is_shadow.sql` | migration | — | `supabase/migrations/20260422000000_add_sport_column.sql` | exact |
| Test stubs (13 files) | test | — | `tests/test_repositories.py`, `tests/test_parquet_store.py`, `tests/test_feature_pipeline.py` | exact |

---

## Pattern Assignments

### `scripts/seed_historical.py` (script, batch)

**Analogs:** `src/bip/sports/football/client.py` (async client with retry) + `src/bip/core/storage/parquet_store.py` (Parquet write)

**Imports pattern** — copy from `src/bip/sports/football/client.py` lines 1-21 and `src/bip/core/storage/parquet_store.py` lines 1-17:
```python
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import structlog

from bip.core.settings import Settings
from bip.core.storage.parquet_store import ParquetStore
from bip.sports.football.client import ApiFootballClient
from bip.sports.football.config.league_registry import LeagueRegistry

logger = structlog.get_logger(__name__)
```

**Async main pattern** — copy async-with-client pattern from `src/bip/sports/football/plugin.py` lines 66-84:
```python
async with ApiFootballClient(api_key=settings.api_football_key) as client:
    for league_cfg in registry.all_leagues():
        try:
            raw = await client.get_fixtures(
                league_id=league_cfg.api_mappings.api_football_league_id,
                date=date_str,
            )
        except Exception as exc:
            logger.warning("seed_failed", league=league_cfg.slug, error=str(exc))
```

**Checkpoint pattern** — new, no direct analog; use stdlib `json` read/write with atomic write semantics:
```python
# Checkpoint file: data/seed_checkpoint.json
# Schema: {"completed_fixture_ids": [12345, 12346, ...], "completed_at": "2026-04-22T..."}
CHECKPOINT_PATH = Path("data/seed_checkpoint.json")

def load_checkpoint() -> set[int]:
    if CHECKPOINT_PATH.exists():
        data = json.loads(CHECKPOINT_PATH.read_text())
        return set(data.get("completed_fixture_ids", []))
    return set()

def save_checkpoint(completed_ids: set[int]) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "completed_fixture_ids": sorted(completed_ids),
        "updated_at": datetime.now(UTC).isoformat(),
    }))
    tmp.replace(CHECKPOINT_PATH)  # atomic rename
```

**Parquet write pattern** — copy from `src/bip/sports/football/plugin.py` lines 133-137:
```python
season = f"{fixture.kickoff_utc.year}-{fixture.kickoff_utc.year + 1}"
matchday = 1  # Phase 2: parse from API "round" field
parquet_row = engineer.to_parquet_row(fm, matchday=matchday, season=season)
store.write_features(parquet_row)
```

**Error handling pattern** — copy from `src/bip/sports/football/plugin.py` lines 76-84 (per-league try/except, log+continue):
```python
except Exception as exc:
    logger.warning(
        "seed_league_failed",
        league=league_cfg.slug,
        error=str(exc),
    )
```

---

### `src/bip/sports/football/features.py` (MODIFY — expand _extract_features)

**Analog:** Self — current file `src/bip/sports/football/features.py`

**Existing class/method signature to preserve** (lines 22-67) — do not change the public interface:
```python
class FeatureEngineer:
    def build_features_for_fixture(
        self,
        fixture: FixtureData,
        raw_stats: dict,
        raw_lineups: dict,
        computed_at: datetime | None = None,
    ) -> FeatureMatrix:
```

**Existing `to_parquet_row()` to preserve** (lines 91-120) — unchanged by Phase 2.

**New method signatures to add inside `FeatureEngineer`** — use internal private method pattern matching `_extract_features()` (lines 69-89):
```python
def _rolling_form(
    self,
    team: str,
    historical: pl.DataFrame,
    cutoff: datetime,
    windows: list[int] = [3, 5, 10],
) -> dict[str, float]:
    """Return rolling form features (goals scored/conceded, W/D/L) up to cutoff."""

def _elo_snapshot(
    self,
    elo: object,  # penaltyblog.ratings.Elo
    home_team: str,
    away_team: str,
) -> dict[str, float]:
    """Return ELO rating features at current snapshot."""

def _h2h_features(
    self,
    home_team: str,
    away_team: str,
    historical: pl.DataFrame,
    cutoff: datetime,
) -> dict[str, float]:
    """Return H2H aggregate features up to cutoff."""
```

**Polars transform pattern** — copy from `src/bip/sports/football/features.py` lines 110-120 (dict-to-DataFrame with list wrapping):
```python
row: dict[str, list] = {
    "fixture_id": [fm.fixture_id],
    "sport": [fm.sport],
    ...
}
for key, val in fm.features.items():
    row[key] = [val]
return pl.DataFrame(row)
```

**Point-in-time enforcement pattern** (lines 49-51, CRITICAL — must replicate in every new feature method):
```python
if computed_at is None:
    computed_at = datetime.now(UTC)
# All data lookups MUST filter: data.filter(pl.col("kickoff_utc") < computed_at)
```

---

### `src/bip/train/__init__.py` (config, package init)

**Analog:** `src/bip/sports/__init__.py` (lines 1-10)

**Pattern** — expose public API from the training package:
```python
"""bip.train — offline ML training pipeline for football ensembles.

Phase 2: walk-forward stacking with XGBoost/CatBoost/LightGBM + LogisticRegression meta.
CLI entry point: python -m bip.train fit|backtest|promote
"""
```

---

### `src/bip/train/metadata.py` (model, Pydantic schema)

**Analog:** `src/bip/core/storage/models.py`

**Pydantic model pattern** — copy from `src/bip/core/storage/models.py` lines 1-12 (imports) and lines 14-32 (model definition with `model_dump()` serialization):
```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ModelMetadata(BaseModel):
    """Serialized to models/football/{league}/{version}/metadata.json."""

    sport: str = "football"
    league: str
    version: str
    training_date: datetime
    training_data_seasons: list[str]
    training_rows: int
    feature_names: list[str]
    feature_set_hash: str                # sha256[:16] of sorted(feature_names)
    calibration_method: str              # "sigmoid" | "isotonic"
    calibration_samples: int
    walk_forward_folds: int
    walk_forward_mean_clv_pct: float
    walk_forward_fold_details: list[dict]
    base_model_params: dict
    base_model_packages: dict
    sklearn_version: str
    null_clv_rows: int
    slippage_pct: float = 0.015
    git_commit: str | None = None

    def to_dict(self) -> dict:
        """Serialize for JSON file write."""
        data = self.model_dump()
        data["training_date"] = self.training_date.isoformat()
        return data
```

**No `to_supabase_dict()` needed** — writes to local JSON only, not Supabase.

---

### `src/bip/train/registry.py` (service, file-I/O)

**Analog:** `src/bip/core/storage/repositories.py` (dataclass + typed methods pattern)

**Dataclass pattern** — copy from `src/bip/core/storage/repositories.py` lines 27-43:
```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bip.core.errors import StorageError
from bip.train.metadata import ModelMetadata


@dataclass
class ModelRegistry:
    """Read/write models/football/registry.json.

    registry.json schema:
    {
      "schema_version": 1,
      "updated_at": "...",
      "leagues": {
        "premier_league": {"production": "v3", "shadow": "v4", "history": ["v1", "v2", "v3"]}
      }
    }
    """
    registry_path: Path

    @classmethod
    def load(cls, registry_path: Path) -> "ModelRegistry":
        """Load registry from JSON file, validate with Pydantic before use."""

    def promote(self, league: str, version: str) -> None:
        """Mark version as production for this league. No auto-promotion (D-05)."""

    def save(self) -> None:
        """Atomic write: write to .tmp then rename."""
```

**Error handling pattern** — copy from `src/bip/core/storage/repositories.py` lines 34-43:
```python
try:
    ...
except Exception as e:
    raise StorageError(f"Failed to read registry: {e}") from e
```

**Atomic write pattern** — same as checkpoint in seed script (write to `.tmp`, then `Path.replace()`).

---

### `src/bip/train/loader.py` (service, file-I/O)

**Analog:** `src/bip/core/storage/parquet_store.py` (read path) + `src/bip/core/storage/repositories.py` (dataclass pattern)

**Imports pattern** — copy from `src/bip/core/storage/parquet_store.py` lines 1-17:
```python
from __future__ import annotations

import joblib
from pathlib import Path

import structlog

from bip.core.errors import StorageError
from bip.train.metadata import ModelMetadata
from bip.train.registry import ModelRegistry

logger = structlog.get_logger(__name__)
```

**Path validation pattern** — copy safety constraint from RESEARCH.md (only load from `settings.model_dir`):
```python
@dataclass
class ModelLoader:
    model_dir: Path
    registry: ModelRegistry

    def load(self, league: str) -> object:
        """Load production ensemble for league. Validates path is under model_dir."""
        version = self.registry.get_production_version(league)
        artifact_path = self.model_dir / "football" / league / version / "ensemble.joblib"
        # Security: only load from project-owned model_dir
        artifact_path.resolve().relative_to(self.model_dir.resolve())  # raises if outside
        ...
```

**Feature hash check** — add before returning the loaded model:
```python
meta = ModelMetadata.model_validate_json(
    (artifact_path.parent / "metadata.json").read_text()
)
current_hash = feature_set_hash(current_feature_names)
if meta.feature_set_hash != current_hash:
    raise StorageError(
        f"Feature set mismatch for {league}/{version}: "
        f"model={meta.feature_set_hash!r} current={current_hash!r}"
    )
```

**Error handling** — raise `StorageError` (copy from `src/bip/core/storage/repositories.py` line 43 pattern).

---

### `src/bip/train/pipeline.py` (service, batch orchestrator)

**Analog:** `src/bip/sports/football/plugin.py` (orchestrator that calls sub-services)

**Imports pattern** — copy from `src/bip/sports/football/plugin.py` lines 1-32 (structlog, settings, dataclass pattern):
```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import structlog

from bip.core.settings import Settings
from bip.core.storage.parquet_store import ParquetStore
from bip.train.metadata import ModelMetadata
from bip.train.registry import ModelRegistry
from bip.train.stacking import StackedEnsemble
from bip.train.calibration import select_calibrator
from bip.train.walkforward import WalkForwardSplitter

logger = structlog.get_logger(__name__)
```

**Orchestrator method pattern** — copy from `src/bip/sports/football/plugin.py` lines 56-85 (public method orchestrates private sub-steps, logs entry + exit, wraps exceptions):
```python
def run(self, league: str, version: str) -> ModelMetadata:
    """Train ensemble for one league. Called by CLI `fit` command.

    Flow:
    1. Load feature Parquet for league
    2. Validate temporal ordering (assert dates ASC)
    3. Walk-forward outer loop (TimeSeriesSplit)
    4. Inner OOF loop per fold
    5. Calibrate meta-learner output
    6. Compute walk-forward CLV
    7. Save artifacts to models/football/{league}/{version}/
    8. Write metadata.json
    """
    logger.info("pipeline_start", league=league, version=version)
    try:
        ...
    except Exception as exc:
        logger.error("pipeline_failed", league=league, error=str(exc))
        raise
    logger.info("pipeline_done", league=league, version=version)
    return metadata
```

---

### `src/bip/train/stacking.py` (service, transform)

**Analog:** `src/bip/sports/football/features.py` (transform service with private methods, structlog)

**Core pattern** — the nested OOF loop from RESEARCH.md Pattern 1 (hand-rolled, not sklearn StackingClassifier). Implement as a class with `fit_fold()` and `predict_proba()`:
```python
from __future__ import annotations

import numpy as np
import structlog
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier

logger = structlog.get_logger(__name__)

CLASSES = [0, 1, 2]  # home win, draw, away win


class StackedEnsemble:
    """XGBoost + CatBoost + LightGBM base models with LogisticRegression meta-learner.

    OOF predictions are generated WITHIN each walk-forward fold's train window (D-03b).
    Never generates global OOF across full dataset.
    """

    def fit_fold(
        self,
        X_tr: np.ndarray,
        y_tr: np.ndarray,
        X_te: np.ndarray,
        dates_tr: np.ndarray,
        n_inner: int = 5,
    ) -> np.ndarray:
        """Fit base models + meta-learner on fold's train window; return test predictions."""
        inner = TimeSeriesSplit(n_splits=n_inner)
        oof = np.zeros((len(X_tr), len(CLASSES)))
        for inner_train, inner_val in inner.split(X_tr):
            # Temporal integrity: inner splits of train window are also time-ordered
            assert dates_tr[inner_train].max() < dates_tr[inner_val].min()
            ...
```

**Error handling** — assert-based for temporal integrity (not try/except — assertions should propagate):
```python
assert dates[train_idx].max() < dates[test_idx].min(), \
    f"Fold {fold_idx} temporal leakage: train max={dates[train_idx].max()} >= test min={dates[test_idx].min()}"
```

---

### `src/bip/train/calibration.py` (utility, transform)

**Analog:** `src/bip/core/types.py` (CalibrationMethod enum already exists) + patterns from RESEARCH.md Pattern 2

**Imports pattern** — CalibrationMethod is already in `src/bip/core/types.py` line 26-29, import it:
```python
from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.isotonic import IsotonicRegression

from bip.core.types import CalibrationMethod
```

**Core calibration pattern** — sklearn 1.8 FrozenEstimator (CRITICAL, do NOT use cv='prefit'):
```python
def select_calibrator(n_samples: int) -> str:
    """ML-03 threshold selection: <300 → sigmoid (Platt), >500 → isotonic, 300-500 → sigmoid."""
    if n_samples > 500:
        return CalibrationMethod.isotonic
    return CalibrationMethod.platt  # 300-500 falls back to Platt (safer)


def calibrate(
    ensemble: object,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
) -> CalibratedClassifierCV:
    """Calibrate ensemble output probability. MUST use FrozenEstimator in sklearn 1.8."""
    method = select_calibrator(len(y_cal))
    calibrated = CalibratedClassifierCV(
        estimator=FrozenEstimator(ensemble),
        method=method.value,  # "sigmoid" or "isotonic"
        cv=None,              # Does not re-fit; uses frozen estimator as-is
    )
    calibrated.fit(X_cal, y_cal)
    return calibrated
```

---

### `src/bip/train/walkforward.py` (service, batch)

**Analog:** `src/bip/sports/football/features.py` (data-processing service structure)

**Core pattern** — thin wrapper around `sklearn.model_selection.TimeSeriesSplit` with logging:
```python
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import structlog
from sklearn.model_selection import TimeSeriesSplit

logger = structlog.get_logger(__name__)


@dataclass
class WalkForwardSplitter:
    """Temporal walk-forward CV splitter with built-in leakage assertions."""
    n_splits: int = 5

    def split(self, X: np.ndarray, dates: np.ndarray):
        """Yield (fold_idx, train_idx, test_idx). Asserts dates[train].max() < dates[test].min()."""
        tscv = TimeSeriesSplit(n_splits=self.n_splits)
        for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X)):
            assert dates[train_idx].max() < dates[test_idx].min(), \
                f"Fold {fold_idx} temporal leakage detected"
            logger.info("fold_split", fold=fold_idx, n_train=len(train_idx), n_test=len(test_idx))
            yield fold_idx, train_idx, test_idx
```

---

### `src/bip/train/backtest.py` (service, batch)

**Analog:** `src/bip/core/storage/repositories.py` (ClvRecord read pattern) + `src/bip/core/storage/models.py` (ClvRecord model at lines 104-123)

**CLV computation pattern** — from RESEARCH.md Pattern 3:
```python
SLIPPAGE_PCT: float = 0.015  # 1.5% (mid-range of 1-2% spec, ML-02)


def apply_slippage(opening_odds: float) -> float:
    """Bet-taker loses 1.5% of odds to market movement."""
    return opening_odds * (1 - SLIPPAGE_PCT)


def compute_clv(staked_odds: float, pinnacle_closing: float) -> float:
    """CLV % vs Pinnacle closing (ML-02/CLV-02)."""
    return (staked_odds / pinnacle_closing - 1) * 100.0
```

**Null CLV handling** — document `null_clv_rows` in metadata, don't impute:
```python
# If Pinnacle closing not available, exclude from CLV summary (count null_clv_rows)
# but still include in logloss/accuracy computation
```

---

### `src/bip/train/base_models.py` (utility, factory)

**No analog in codebase.** Use RESEARCH.md defaults directly:
```python
XGB_PARAMS = {
    "n_estimators": 500,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",   # CPU-optimized in XGBoost 3.x
    "device": "cpu",
    "objective": "multi:softprob",
    "num_class": 3,
    "eval_metric": "mlogloss",
    "random_state": 42,
}

CB_PARAMS = {
    "iterations": 500,
    "depth": 4,
    "learning_rate": 0.05,
    "loss_function": "MultiClass",
    "task_type": "CPU",
    "verbose": 0,
    "random_seed": 42,
}

LGBM_PARAMS = {
    "n_estimators": 500,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "verbose": -1,
    "random_state": 42,
}
```

**Polars→numpy coercion** — standardize ALL three base models on numpy input at the call site to prevent silent column reordering (RESEARCH.md Pitfall 3):
```python
# Convert Polars to numpy ONCE at the training driver boundary
X = df.select(feature_cols).to_numpy()  # shape (n_samples, n_features)
feature_names = feature_cols  # keep as separate list for metadata
```

---

### `src/bip/train/cli.py` (utility, request-response)

**Analog:** None directly; pattern from RESEARCH.md Code Examples (Typer scaffold)

**Typer CLI pattern:**
```python
# src/bip/train/__main__.py (entry point for `python -m bip.train`)
import typer
import structlog

from bip.core.settings import Settings
from bip.train.pipeline import TrainingPipeline
from bip.train.registry import ModelRegistry

logger = structlog.get_logger(__name__)
app = typer.Typer(help="bip.train — offline ML training pipeline for football.")


@app.command()
def fit(
    league: str = typer.Argument(..., help="League slug, e.g. premier_league"),
    version: str = typer.Option("auto", help="Version tag, e.g. v2. 'auto' increments."),
) -> None:
    """Train ensemble for a league and save artifacts."""
    settings = Settings()
    pipeline = TrainingPipeline(settings=settings)
    metadata = pipeline.run(league=league, version=version)
    typer.echo(f"Trained {league}/{metadata.version} — CLV {metadata.walk_forward_mean_clv_pct:.2f}%")


@app.command()
def promote(
    league: str = typer.Argument(..., help="League slug"),
    version: str = typer.Argument(..., help="Version to promote to production"),
) -> None:
    """Mark version as production for this league (manual review required — D-05)."""
    settings = Settings()
    registry = ModelRegistry.load(registry_path=...)
    registry.promote(league=league, version=version)
    registry.save()
    typer.echo(f"Promoted {league}/{version} to production")


if __name__ == "__main__":
    app()
```

**structlog usage** — copy from `src/bip/sports/football/plugin.py` lines 32-33 (`logger = structlog.get_logger(__name__)`).

---

### `src/bip/sports/football/plugin.py` (MODIFY — extend predict())

**Analog:** Self — current `src/bip/sports/football/plugin.py`

**Constructor extension** — add `ModelLoader` to `__init__` (lines 44-50 pattern):
```python
def __init__(self, settings: Settings) -> None:
    self._settings = settings
    self._markets = load_markets()
    self._registry = LeagueRegistry(_LEAGUES_DIR)
    self._store = ParquetStore(base_path=Path(settings.parquet_base_path))
    self._engineer = FeatureEngineer()
    # Phase 2 additions:
    self._model_registry = ModelRegistry.load(Path(settings.model_dir) / "football" / "registry.json")
    self._loader = ModelLoader(model_dir=Path(settings.model_dir), registry=self._model_registry)
```

**predict() replacement** (lines 141-149, replace stub):
```python
async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap:
    """Run ML ensemble. Writes shadow prediction if shadow version configured (ML-05)."""
    computed_at = datetime.now(UTC)
    ensemble = self._loader.load(features.league)
    X = self._to_numpy(features)
    probs = ensemble.predict_proba(X)[0]  # shape (3,): [p_home, p_draw, p_away]
    return ProbabilityMap(
        fixture_id=features.fixture_id,
        market=market,
        probabilities={"1": float(probs[0]), "X": float(probs[1]), "2": float(probs[2])},
        model_version=self._model_registry.get_production_version(features.league),
        computed_at=computed_at,
    )
```

**Error handling pattern** — copy from plugin.py lines 76-84 (log warning + re-raise or return stub):
```python
except Exception as exc:
    logger.warning("predict_failed", league=features.league, error=str(exc))
    raise
```

---

### `src/bip/sports/football/model_loader.py` (service, file-I/O)

**Analog:** `src/bip/core/storage/parquet_store.py` (read path with path validation)

Same pattern as `src/bip/train/loader.py` — this is the runtime loader (called by FootballPlugin) while `src/bip/train/loader.py` is the training-time loader. Both use the same `ModelLoader` class — can be a single shared module (planner decides which package owns it).

---

### `src/bip/core/storage/models.py` (MODIFY — add is_shadow to Prediction)

**Analog:** Self — `src/bip/core/storage/models.py` lines 14-33

**Field addition pattern** — copy OddsSnapshot's bool field pattern (lines 67-68):
```python
class Prediction(BaseModel):
    # ... existing fields ...
    is_shadow: bool = False          # ML-05: shadow mode flag (migration 003 adds column)
```

**to_supabase_dict() extension** (lines 28-31) — `is_shadow` is a bool, no special serialization needed since `model_dump()` handles it; no change to the method body required.

---

### `src/bip/core/storage/repositories.py` (MODIFY — extend insert() with is_shadow filter)

**Analog:** Self — `src/bip/core/storage/repositories.py` lines 33-43

**insert() extension** — the `is_shadow` flag is now on the `Prediction` model itself; `insert()` already calls `prediction.to_supabase_dict()` which will include `is_shadow` after the model change. No change to `insert()` body needed.

**New `get_production()` method to add** (copies `get_by_fixture()` pattern lines 44-59):
```python
def get_production(
    self, fixture_id: int, market: str | None = None
) -> list[dict]:
    """Get non-shadow predictions for a fixture (Phase 3 pick engine reads these)."""
    try:
        query = (
            self.client.table("predictions")
            .select("*")
            .eq("fixture_id", fixture_id)
            .eq("is_shadow", False)
        )
        if market is not None:
            query = query.eq("market", market)
        return query.execute().data
    except Exception as e:
        raise StorageError(f"Failed to select from predictions: {e}") from e
```

---

### `src/bip/core/settings.py` (MODIFY — add model_dir)

**Analog:** Self — `src/bip/core/settings.py` lines 6-20

**Field addition** — copy `parquet_base_path` field pattern (line 16):
```python
parquet_base_path: str = "data/cache"
model_dir: str = "models"           # Phase 2: root for model artifacts
```

---

### `supabase/migrations/20260423000000_add_is_shadow.sql` (migration)

**Analog:** `supabase/migrations/20260422000000_add_sport_column.sql` — exact pattern

**Migration pattern** — copy from `supabase/migrations/20260422000000_add_sport_column.sql` lines 1-10:
```sql
-- Migration 003: Add is_shadow for ML-05 shadow-mode prediction logging
-- Must be applied BEFORE any shadow prediction write (RESEARCH.md anti-pattern warning)

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS is_shadow BOOLEAN NOT NULL DEFAULT false;

-- Index for production-only reads (Phase 3 pick engine reads is_shadow=false)
CREATE INDEX IF NOT EXISTS idx_predictions_is_shadow ON predictions (is_shadow);
```

---

## Test Stubs — Wave 0 Pattern

**Analog:** `tests/test_repositories.py`, `tests/test_parquet_store.py`, `tests/test_feature_pipeline.py`

### Class/method structure pattern

Copy from `tests/test_repositories.py` lines 11-41 (class grouping by requirement ID, docstring on every test):
```python
class TestWalkForwardSplitter:
    """ML-02: temporal integrity — no future dates in training window."""

    def test_no_future_dates_in_train(self):
        """All training dates must be strictly < all test dates per fold."""
        import numpy as np
        from bip.train.walkforward import WalkForwardSplitter
        dates = np.array([...])  # synthetic sorted dates
        splitter = WalkForwardSplitter(n_splits=3)
        for fold_idx, train_idx, test_idx in splitter.split(X_dummy, dates):
            assert dates[train_idx].max() < dates[test_idx].min()
```

### conftest.py additions pattern

Copy from `tests/conftest.py` lines 17-86 (fixtures with docstrings, monkeypatch for settings, `setup_mock_chain` helper):
```python
@pytest.fixture
def synthetic_training_data() -> tuple:
    """50-row synthetic dataset with known temporal ordering for fast ML tests."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 50
    X = rng.standard_normal((n, 5))
    y = rng.integers(0, 3, size=n)
    dates = np.array([datetime(2024, 1, 1) + timedelta(days=i * 7) for i in range(n)])
    return X, y, dates


@pytest.fixture
def tmp_model_dir(tmp_path: Path) -> Path:
    """Temporary models/ directory for registry and loader tests."""
    model_dir = tmp_path / "models" / "football"
    model_dir.mkdir(parents=True)
    return tmp_path / "models"
```

### Async test pattern

Copy from `tests/test_api_football_client.py` lines 10-15 (async test method, `httpx_mock` fixture):
```python
async def test_plugin_predict_returns_probability_map(self, settings, tmp_model_dir):
    """FootballPlugin.predict() returns calibrated ProbabilityMap — ML-01."""
```

Note: `asyncio_mode = "auto"` is already set in `pyproject.toml` line 38 — no `@pytest.mark.asyncio` decorator needed.

### Mock pattern

Copy `setup_mock_chain()` from `tests/conftest.py` lines 53-69 (MagicMock fluent chain). For repository tests with `is_shadow`:
```python
def test_insert_shadow_prediction(self, mock_client):
    """insert() with is_shadow=True writes is_shadow flag to Supabase."""
    builder = setup_mock_chain(mock_client, data=[{"id": 1, "is_shadow": True}])
    ...
    pred = Prediction(..., is_shadow=True)
    repo.insert(pred)
    builder.insert.assert_called_once()
    call_data = builder.insert.call_args[0][0]
    assert call_data["is_shadow"] is True
```

---

## Shared Patterns

### Structlog logging
**Source:** `src/bip/sports/football/client.py` lines 20-21 + `src/bip/sports/football/plugin.py` line 32
**Apply to:** All new service modules in `src/bip/train/`
```python
import structlog
logger = structlog.get_logger(__name__)
```

Log entry/exit of major operations with relevant context fields (league, version, fold index, etc.).

### StorageError wrapping
**Source:** `src/bip/core/storage/repositories.py` lines 34-43
**Apply to:** `src/bip/train/registry.py`, `src/bip/train/loader.py`
```python
try:
    ...
except Exception as e:
    raise StorageError(f"Failed to [operation] [target]: {e}") from e
```

### `from __future__ import annotations`
**Source:** `src/bip/core/storage/repositories.py` line 11, `src/bip/sports/football/plugin.py` line 3
**Apply to:** All new Python modules — project-wide convention.

### Pydantic model serialization (`model_dump()` + custom datetime ISO)
**Source:** `src/bip/core/storage/models.py` lines 28-32 (Prediction.to_supabase_dict()):
```python
def to_supabase_dict(self) -> dict:
    data = self.model_dump()
    data["kickoff_utc"] = self.kickoff_utc.isoformat()
    return data
```
**Apply to:** `src/bip/train/metadata.py` `to_dict()` method — same pattern for datetime fields.

### Settings injection via `Settings` dataclass
**Source:** `src/bip/core/settings.py` lines 6-20 + `src/bip/sports/football/plugin.py` lines 45-50
**Apply to:** `src/bip/train/pipeline.py`, `src/bip/train/cli.py`
```python
from bip.core.settings import Settings
# In __init__:
def __init__(self, settings: Settings) -> None:
    self._settings = settings
```

### Point-in-time enforcement (`computed_at` cutoff)
**Source:** `src/bip/sports/football/features.py` lines 6-8 (module docstring) + lines 49-51
**Apply to:** ALL feature methods in expanded `features.py` — every data lookup must filter by `computed_at`.

### Polars lazy scan for reads
**Source:** `src/bip/core/storage/parquet_store.py` lines 131-145 (`scan_parquet` + lazy filter + `collect()`)
**Apply to:** `src/bip/train/features.py` (feature matrix builder that reads Parquet for training)
```python
lf = pl.scan_parquet(target_dir / "**/*.parquet", hive_partitioning=True)
lf = lf.filter(pl.col("league") == league)
df = lf.collect()
```

### ruff compliance
**Source:** `pyproject.toml` lines 41-45 (ruff config: line-length=100, target py312, select E/F/I/N/W/UP)
**Apply to:** All new files — imports must be `isort`-compatible (stdlib → third-party → local).

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns as primary reference):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/bip/train/base_models.py` | utility | transform | No ML model factory exists anywhere in the codebase; first gradient-boosting code in project |
| `src/bip/train/stacking.py` | service | transform | No stacking or OOF generation code exists; entirely new ML pattern |
| `src/bip/train/cli.py` / `__main__.py` | utility | request-response | No Typer CLI exists; first CLI entry point in project (scheduler is the only entry point currently) |

For these three files, the RESEARCH.md Code Examples section is the authoritative pattern source (Patterns 1, 2, and the Typer scaffold).

---

## Critical Implementation Notes for Planner

1. **Sequencing is mandatory:** `supabase/migrations/20260423000000_add_is_shadow.sql` → `src/bip/core/storage/models.py` → `src/bip/core/storage/repositories.py` → shadow prediction writes. Any plan that writes `is_shadow=True` before migration 003 is applied will fail with a Postgres column-not-found error.

2. **cv='prefit' is removed:** Any calibration code must import `FrozenEstimator` from `sklearn.frozen`. The `CalibrationMethod` enum is already in `src/bip/core/types.py` lines 26-29 — import it rather than defining a new one.

3. **Polars→numpy coercion at ML boundary:** Convert Polars DataFrame to numpy once before passing to any base model. See `base_models.py` pattern above.

4. **No `scripts/` directory exists yet:** Plan must create it. File must NOT be inside `src/bip/` (D-01 constraint).

5. **`matchday` placeholder:** `src/bip/sports/football/plugin.py` line 134 uses `matchday = 1` as a placeholder. Phase 2 must parse the real matchday from the API `round` field (see RESEARCH.md Open Question 3).

6. **Test markers:** `pyproject.toml` line 37 (`[tool.pytest.ini_options]`) needs `markers = ["slow: mark test as slow"]` added before the slow integration tests are written.

---

## Metadata

**Analog search scope:** `src/bip/`, `tests/`, `supabase/migrations/`
**Files scanned:** 18 source files + 2 migration files + 12 test files
**Pattern extraction date:** 2026-04-22
