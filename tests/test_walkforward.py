"""Walk-forward temporal integrity — ML-02."""


class TestWalkForwardSplitter:
    """ML-02: all training dates strictly < test dates per fold."""

    def test_no_future_dates_in_train(self, synthetic_training_data):
        """Every training date must be strictly < every test date per fold — ML-02."""
        # Will import: from bip.train.walkforward import WalkForwardSplitter
        assert False, "not yet implemented"

    def test_n_splits_produces_n_folds(self, synthetic_training_data):
        """WalkForwardSplitter(n_splits=5) yields 5 folds — ML-02."""
        assert False, "not yet implemented"

    def test_assertion_raises_on_unsorted_dates(self):
        """Splitter raises AssertionError when dates are not monotonically increasing."""
        assert False, "not yet implemented"
