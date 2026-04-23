"""Backtest CLV — ML-02 opening odds + slippage."""


class TestBacktestClv:
    """ML-02: walk-forward CLV uses opening odds × (1 − slippage), not closing."""

    def test_uses_opening_odds_not_closing(self):
        """CLV staked_odds = opening_odds × (1 − slippage_pct) — ML-02."""
        # Will import: from bip.train.backtest import apply_slippage, compute_clv
        assert False, "not yet implemented"

    def test_slippage_default_0_015(self):
        """SLIPPAGE_PCT default = 0.015 (1.5%, mid of 1-2% spec) — ML-02."""
        assert False, "not yet implemented"

    def test_null_clv_excluded_from_summary(self):
        """Rows with null Pinnacle closing are excluded from CLV summary but counted in null_clv_rows."""
        assert False, "not yet implemented"
