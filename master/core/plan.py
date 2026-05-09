"""Trade plan — generator konkretnego planu trade'a.

Filozofia: Lefèvre (line of least resistance) + Faith (mechaniczne reguły).
Wejście tylko przez konkretny trigger, SL twardy, TP wieloetapowy
(TP1 zabezpiecza, TP2 leci do magnetu lub trail by ATR).

Każdy plan ma invalidation_minutes — jeśli setup nie aktywuje się
w tym czasie, plan jest anulowany. To jest Faith's mechaniczność:
nie trzymasz kotwicy "może jeszcze".
"""
from __future__ import annotations

import logging

from master.config import MasterConfig
from master.core.regime import RegimeResult
from master.core.sizer import SizingResult
from master.core.verdict import Side, TradePlan
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


def build(
    cfg: MasterConfig,
    fs: FeatureStore,
    regime: RegimeResult,
    sizing: SizingResult,
) -> TradePlan:
    """Składa konkretny plan trade'a.

    TODO: implementacja po feature_store. Logika:
        1. Pobierz ostatni close + ATR z TF5/TF15
        2. Znajdź najbliższy magnet po stronie kierunku (entry trigger)
        3. SL = entry - sl_atr_multiplier × ATR (lub poniżej structural low)
        4. TP1 = entry + 1.5 × (entry - SL)   [min RR]
        5. TP2 = następny magnet
        6. invalidation_minutes = 30 (configurable per regime)
    """
    if sizing.contracts <= 0:
        return TradePlan()

    # Placeholder — bez feature_store nie mamy live ceny
    return TradePlan(
        side=Side.NONE,
        entry=None,
        stop_loss=None,
        take_profit_1=None,
        take_profit_2=None,
        invalidation_minutes=30,
        position_size_contracts=sizing.contracts,
        risk_eur=sizing.risk_eur,
        risk_r=sizing.risk_r,
    )
