"""Training pipeline orchestrator — per-league ensemble training + calibration + save."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
import structlog

from bip.core.settings import Settings
from bip.core.storage.parquet_store import ParquetStore
from bip.train.backtest import SLIPPAGE_PCT
from bip.train.base_models import CB_PARAMS, LGBM_PARAMS, XGB_PARAMS
from bip.train.calibration import calibrate, select_calibrator
from bip.train.metadata import ModelMetadata, feature_set_hash
from bip.train.stacking import StackedEnsemble
from bip.train.walkforward import WalkForwardSplitter

logger = structlog.get_logger(__name__)


# 1X2 label mapping (matches penaltyblog): 0=home win, 1=draw, 2=away win
def _label_from_goals(hg: int, ag: int) -> int:
    if hg > ag:
        return 0
    if hg == ag:
        return 1
    return 2


@dataclass
class TrainingPipeline:
    settings: Settings

    def run(self, league: str, version: str) -> ModelMetadata:
        """Train ensemble for one league — ML-01 + ML-02 + ML-03 + ML-04."""
        logger.info("pipeline_start", league=league, version=version)
        store = ParquetStore(base_path=Path(self.settings.parquet_base_path))

        # Load all historical features for the league
        df = store.read_features(sport="football", league=league)
        if len(df) == 0:
            raise RuntimeError(
                f"No feature rows for league={league}. "
                f"Run scripts/seed_historical.py first."
            )

        # Expect columns: fixture_id, computed_at, and feature_* columns
        # Drop partition columns + metadata for the feature matrix
        drop_cols = {
            "fixture_id", "sport", "league", "season", "matchday", "computed_at",
        }
        # Labels come from the Parquet store: home_goals, away_goals columns must be present
        # (populated by seed script via post-match results join — if missing, pipeline raises)
        if "home_goals" not in df.columns or "away_goals" not in df.columns:
            raise RuntimeError(
                "Feature Parquet missing home_goals/away_goals — "
                "seed script must join results."
            )
        y = np.array([
            _label_from_goals(int(hg), int(ag))
            for hg, ag in zip(df["home_goals"], df["away_goals"], strict=True)
        ])
        feature_cols = [
            c for c in df.columns
            if c not in drop_cols and c not in {"home_goals", "away_goals"}
        ]
        feature_cols.sort()
        X = df.select(feature_cols).to_numpy()
        dates_col = df["computed_at"].to_list()
        dates = np.array([
            datetime.fromisoformat(d) if isinstance(d, str) else d
            for d in dates_col
        ])

        # Sort by date to guarantee monotonic increasing
        order = np.argsort(dates)
        X, y, dates = X[order], y[order], dates[order]

        # Walk-forward CV + nested OOF (ML-02, D-03b)
        splitter = WalkForwardSplitter(n_splits=5)
        fold_details: list[dict] = []
        all_test_probs: list[np.ndarray] = []
        all_test_idx: list[np.ndarray] = []
        last_ensemble: StackedEnsemble | None = None
        for fold_idx, train_idx, test_idx in splitter.split(X, dates):
            ens = StackedEnsemble()
            probs = ens.fit_fold(
                X[train_idx], y[train_idx], X[test_idx], dates[train_idx]
            )
            all_test_probs.append(probs)
            all_test_idx.append(test_idx)
            last_ensemble = ens
            # Per-fold CLV (placeholder — requires opening odds joined into df)
            fold_details.append({
                "fold_idx": fold_idx,
                "n_train": int(len(train_idx)),
                "n_test": int(len(test_idx)),
                "clv_pct": None,
            })

        assert last_ensemble is not None, "Walk-forward produced zero folds"

        # Calibration on the last fold's test window (ML-03)
        last_test_idx = all_test_idx[-1]
        calib_method = select_calibrator(len(last_test_idx))

        class _EnsembleProbaWrapper:
            def __init__(
                self,
                ens: StackedEnsemble,
                X_fit: np.ndarray,
                y_fit: np.ndarray,
                dates_fit: np.ndarray,
            ) -> None:
                ens.fit_fold(X_fit, y_fit, X_fit[:1], dates_fit)
                self._ens = ens
                self.classes_ = np.array([0, 1, 2])

            def predict_proba(self, X_in: np.ndarray) -> np.ndarray:
                from bip.train.stacking import _align_proba
                probs = np.mean(
                    [_align_proba(m, X_in) for m in self._ens._final_base],
                    axis=0,
                )
                return self._ens._meta.predict_proba(probs)

            def fit(self, X_in, y_in):
                return self

        wrapper = _EnsembleProbaWrapper(
            last_ensemble,
            X_fit=X[:max(all_test_idx[-1][0], 1)],
            y_fit=y[:max(all_test_idx[-1][0], 1)],
            dates_fit=dates[:max(all_test_idx[-1][0], 1)],
        )
        calibrator = calibrate(wrapper, X[last_test_idx], y[last_test_idx])

        # Compute walk-forward mean CLV (defaults to 0.0 when no odds columns present)
        null_clv_rows = int(sum(d.get("n_test", 0) for d in fold_details))
        clv_values = [
            d["clv_pct"] for d in fold_details if d.get("clv_pct") is not None
        ]
        mean_clv = float(np.mean(clv_values)) if clv_values else 0.0

        # Persist artifacts to models/football/{league}/{version}/
        artifact_dir = (
            Path(self.settings.model_dir) / "football" / league / version
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(last_ensemble, artifact_dir / "ensemble.joblib")
        joblib.dump(calibrator, artifact_dir / "calibrator.joblib")

        meta = ModelMetadata(
            league=league,
            version=version,
            training_date=datetime.now(UTC),
            training_data_seasons=["2023-2024", "2024-2025", "2025-2026"],
            training_rows=int(len(X)),
            feature_names=feature_cols,
            feature_set_hash=feature_set_hash(feature_cols),
            calibration_method=calib_method.value,
            calibration_samples=int(len(last_test_idx)),
            walk_forward_folds=len(fold_details),
            walk_forward_mean_clv_pct=mean_clv,
            walk_forward_fold_details=fold_details,
            base_model_params={
                "xgboost": XGB_PARAMS,
                "catboost": CB_PARAMS,
                "lightgbm": LGBM_PARAMS,
            },
            base_model_packages=last_ensemble.base_model_packages(),
            sklearn_version=sklearn.__version__,
            null_clv_rows=null_clv_rows,
            slippage_pct=SLIPPAGE_PCT,
        )
        (artifact_dir / "metadata.json").write_text(
            json.dumps(meta.to_dict(), indent=2, sort_keys=True)
        )
        logger.info(
            "pipeline_done",
            league=league, version=version,
            mean_clv_pct=mean_clv, rows=len(X),
        )
        return meta
