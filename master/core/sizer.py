"""Position sizing — Tharp (R-multiples) + Kaufman (vol-adjusted).

Reguła: ryzyko per trade jako % kapitału, **stała**, niezależna od
"przekonania". Wielkość pozycji wynika z R i ze stop distance, nie
odwrotnie.

    risk_eur = account × risk_pct
    stop_distance = max(structural_invalidation, atr_multiplier × ATR)
    position_size = risk_eur / (stop_distance × point_value)

Dla 6E (EUR/USD futures): point value = 12.50 USD per 0.0001
(ale dla simplicity tu przyjmujemy EUR i 6.25 EUR per 0.5 tick — TBI
po zweryfikowaniu z Marcinem specyfikacji kontraktu).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.core.edge_lookup import EdgeResult
from master.core.setup_grader import GradeResult
from master.core.verdict import SetupGrade
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


# 6E (Euro FX futures) tick value
# 1 punkt (0.0001) = $12.50; 1 minimum tick (0.00005) = $6.25
# TODO: verify z Marcinem/IBKR specs, na razie używamy USD jako proxy EUR
TICK_SIZE = 0.00005
TICK_VALUE_USD = 6.25
POINT_SIZE = 0.0001
POINT_VALUE_USD = 12.50


@dataclass
class SizingResult:
    contracts: float = 0.0
    risk_eur: float = 0.0
    risk_r: float = 1.0           # zawsze 1.0 R (z definicji)
    stop_distance_points: float = 0.0
    detail: str = ""


def size(
    cfg: MasterConfig,
    fs: FeatureStore,
    grade: GradeResult,
    edge: EdgeResult,
) -> SizingResult:
    """Liczy wielkość pozycji wg Tharpa.

    risk_pct zależy od grade (A = pełne 1%, B = 0.5%, C = 0).
    Jeśli sample size < minimum → eksploracja, ½ wielkości (Tharp).
    """
    if grade.grade == SetupGrade.A:
        risk_pct = cfg.risk.risk_pct_grade_a
    elif grade.grade == SetupGrade.B:
        risk_pct = cfg.risk.risk_pct_grade_b
    else:
        return SizingResult(detail="grade C — no sizing")

    # Tharp eksploracja: mała próbka → połowa pozycji
    if edge.sample_size < cfg.edge.min_sample_size:
        risk_pct *= 0.5

    risk_eur = cfg.risk.account_size_eur * risk_pct

    # Stop distance — TBI: pobranie ATR z feature_store
    # Na razie placeholder z konfiguracji (1.5 × placeholder ATR)
    atr = fs.get_atr(timeframe="TF15") or 0.0010   # placeholder 10 pips
    stop_distance = atr * cfg.risk.sl_atr_multiplier

    if stop_distance <= 0:
        return SizingResult(detail="invalid stop distance")

    # Wartość 1 punktu w EUR (proxy = USD na razie)
    risk_per_contract = stop_distance * POINT_VALUE_USD / POINT_SIZE
    if risk_per_contract <= 0:
        return SizingResult(detail="invalid risk per contract")

    raw_contracts = risk_eur / risk_per_contract
    # Zaokrąglenie w dół (lepiej mniejsza pozycja niż większa — Taleb)
    contracts = max(0, int(raw_contracts))

    return SizingResult(
        contracts=contracts,
        risk_eur=risk_eur,
        stop_distance_points=stop_distance,
        detail=f"risk_pct={risk_pct:.3%}, atr={atr:.5f}, raw={raw_contracts:.2f}",
    )
