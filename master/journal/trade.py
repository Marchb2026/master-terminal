"""Trade dataclass — pojedynczy wpis w dzienniku Mastera.

Tharp jest tu autorytetem: każdy trade ma R-multiple jako podstawową
miarę wyniku, niezależnie od waluty/instrumentu/wielkości.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trade:
    """Pojedynczy zamknięty trade w jednostkach R (Tharpa)."""

    # identyfikatory
    trade_id: str = ""           # UUID lub timestamp-based
    template_id: str = ""        # np. "TREND_UP_WEAK_LONG_A" — klucz do edge_lookup
    instrument: str = "6EM26"

    # czas
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    # ceny
    entry_price: float | None = None
    exit_price: float | None = None
    stop_loss: float | None = None     # zamierzony, do liczenia R
    take_profit: float | None = None

    # wielkość i wynik
    side: str = "LONG"                  # LONG / SHORT
    contracts: float = 0.0
    risk_eur: float = 0.0               # ile zaryzykowano (1R w EUR)
    pnl_eur: float = 0.0                # zrealizowany P/L
    r_multiple: float = 0.0             # pnl_eur / risk_eur — kluczowa metryka

    # kontekst (dla analiz późniejszych)
    regime: str = "UNKNOWN"
    mtf_score: float = 0.0
    setup_grade: str = "C"
    expected_r_at_entry: float | None = None

    # meta
    source: str = "master"              # 'master' | 'ea_signal_log' | 'manual'
    notes: str = ""
    tags: list[str] = field(default_factory=list)
