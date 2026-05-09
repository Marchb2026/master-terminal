"""Regime classifier — Clenow (*Following the Trend*) + Komar (*Sztuka spekulacji*).

Każdy reżim aktywuje inny katalog setupów:
- TREND_UP_*  → pullback-continuation longs
- TREND_DN_*  → pullback-continuation shorts
- RANGE       → mean-reversion od magnetów
- CHAOS       → no trade

Klasyfikacja na bazie TF240 (strategiczny) i TF60 (taktyczny).
Klasyczny Clenow: cena nad EMA200 = bull regime, momentum długo działa.
Komar: dodatkowy filtr ADX żeby odróżnić silny trend od słabego.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.core.verdict import Regime
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


@dataclass
class RegimeResult:
    regime: Regime
    adx: float = 0.0
    ema_slope_240: float = 0.0
    above_ema200: bool = False
    atr_pct: float = 0.0      # ATR jako % ceny — proxy zmienności
    detail: str = ""


def classify(cfg: MasterConfig, fs: FeatureStore) -> RegimeResult:
    """Klasyfikuje aktualny reżim rynku.

    TODO: implement using fs.get_bars("TF240") and fs.get_bars("TF60").
    Logika:
        1. Pobierz bars TF240 i TF60
        2. Policz ADX, EMA(20/50/200), ATR
        3. Zastosuj reguły:
           - ATR% > chaos_threshold → CHAOS
           - Cena > EMA200 i ADX > 25 → TREND_UP_STRONG
           - Cena > EMA200 i ADX 18-25 → TREND_UP_WEAK
           - Cena < EMA200 i ADX > 25 → TREND_DN_STRONG
           - ADX < 18 → RANGE
           - Inaczej → UNKNOWN

    Na razie zwraca UNKNOWN — implementacja po realnym schemacie feature_store.
    """
    log.debug("regime.classify — placeholder (TBI po feature_store)")

    # Placeholder: bez danych zwracamy UNKNOWN, pipeline pójdzie dalej
    # ale setup_grader to wykryje i zdegraduje grade
    return RegimeResult(
        regime=Regime.UNKNOWN,
        detail="not yet implemented — waiting for feature_store schema",
    )


def regime_allows_long(regime: Regime) -> bool:
    """Czy w danym reżimie longi są w ogóle w grze."""
    return regime in (
        Regime.TREND_UP_STRONG,
        Regime.TREND_UP_WEAK,
        Regime.RANGE,  # mean-reversion long od dolnej granicy
    )


def regime_allows_short(regime: Regime) -> bool:
    return regime in (
        Regime.TREND_DN_STRONG,
        Regime.TREND_DN_WEAK,
        Regime.RANGE,
    )
