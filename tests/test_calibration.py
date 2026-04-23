"""Calibration selection + FrozenEstimator usage — ML-03."""


class TestCalibrationSelection:
    """ML-03: Platt for <300, Isotonic for >500, Platt fallback for 300-500."""

    def test_method_selection(self):
        """<300 → sigmoid (Platt), 300-500 → sigmoid, >500 → isotonic — ML-03."""
        # Will import: from bip.train.calibration import select_calibrator
        # Expected: select_calibrator(250) == "platt"
        # Expected: select_calibrator(400) == "platt"
        # Expected: select_calibrator(600) == "isotonic"
        assert False, "not yet implemented"

    def test_uses_frozen_estimator(self):
        """calibration.py imports FrozenEstimator and does NOT use cv='prefit' — sklearn 1.8."""
        # Static check: read src/bip/train/calibration.py source, assert:
        #   'FrozenEstimator' in source and "cv='prefit'" not in source
        assert False, "not yet implemented"

    def test_calibration_improves_logloss(self, synthetic_training_data):
        """Calibrated logloss <= uncalibrated logloss on synthetic skewed probs — ML-03."""
        assert False, "not yet implemented"
