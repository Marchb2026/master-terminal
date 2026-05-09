"""Statystyki dziennika — Tharp.

Centralna metryka: expectancy w R.
    E = (P_win × avg_win_R) − (P_loss × avg_loss_R)

Dodatkowo: profit factor, Sharpe (Chan), max drawdown w R, kurtosis
(Taleb — uwaga na fat tails).
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev

from master.journal.trade import Trade


@dataclass
class ExpectancyStats:
    n: int
    expectancy_r: float
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    profit_factor: float
    sharpe: float
    max_drawdown_r: float
    sum_r: float


def compute_expectancy(trades: list[Trade]) -> ExpectancyStats:
    """Liczy pełen zestaw statystyk z listy zamkniętych trade'ów.

    Trade.r_multiple jest podstawą — jeśli go nie ma, trade jest pomijany.
    """
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    n = len(rs)
    if n == 0:
        return ExpectancyStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]

    win_rate = len(wins) / n if n else 0.0
    avg_win_r = mean(wins) if wins else 0.0
    avg_loss_r = mean(losses) if losses else 0.0

    expectancy = (win_rate * avg_win_r) + ((1 - win_rate) * avg_loss_r)

    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float("inf") if sum_wins > 0 else 0.0

    sharpe = (mean(rs) / stdev(rs) * (252 ** 0.5)) if n > 1 and stdev(rs) > 0 else 0.0

    # Max drawdown w R — liczone na equity curve
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        equity += r
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return ExpectancyStats(
        n=n,
        expectancy_r=expectancy,
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        profit_factor=profit_factor,
        sharpe=sharpe,
        max_drawdown_r=max_dd,
        sum_r=sum(rs),
    )
