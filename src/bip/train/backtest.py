"""Walk-forward CLV backtest math -- ML-02.

CLV staked odds MUST use opening odds x (1 - slippage_pct), NOT closing odds.
Retrofitting closing-odds CLV later invalidates every earlier backtest result.
"""

from __future__ import annotations

SLIPPAGE_PCT: float = 0.015  # 1.5% -- mid-range of 1-2% spec (ML-02)


def apply_slippage(opening_odds: float) -> float:
    """Bet-taker loses SLIPPAGE_PCT of odds edge to market movement."""
    return opening_odds * (1.0 - SLIPPAGE_PCT)


def compute_clv(staked_odds: float, pinnacle_closing: float) -> float:
    """CLV percentage vs Pinnacle closing (ML-02 / CLV-02).

    CLV% = (staked_odds / pinnacle_closing - 1) * 100.
    Positive -> the bet was taken at a better price than the closing line.
    """
    return (staked_odds / pinnacle_closing - 1.0) * 100.0
