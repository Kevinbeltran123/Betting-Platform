"""Stacking OOF generation — ML-01 + D-03b (no global OOF reuse)."""


class TestStackingOOF:
    """Nested OOF generated WITHIN each fold's train window — D-03b."""

    def test_oof_temporal_scope(self, synthetic_training_data):
        """Inner OOF uses only fold's train window — D-03b non-negotiable."""
        # Will import: from bip.train.stacking import StackedEnsemble
        assert False, "not yet implemented"

    def test_ensemble_forward_pass(self, synthetic_training_data):
        """XGB+CB+LGB → LogReg meta produces proba vector summing to 1 — ML-01."""
        assert False, "not yet implemented"

    def test_base_models_are_xgb_catboost_lightgbm(self):
        """Base model list matches D-03a: XGBClassifier, CatBoostClassifier, LGBMClassifier."""
        assert False, "not yet implemented"

    def test_meta_learner_is_logistic_regression(self):
        """Meta-learner is sklearn.linear_model.LogisticRegression — D-03a."""
        assert False, "not yet implemented"
