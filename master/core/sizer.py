"""Position sizing — Tharp (R-multiples) + Kaufman (vol-adjusted).

Tharp: ryzyko per trade jako % kapitału, **stała**, niezależna od
"przekonania". Wielkość pozycji wynika z R i ze stop distance.

    risk_eur = account × risk_pct
    stop_distance_pips = atr_pips × sl_atr_multiplier
    risk_per_contract_eur = stop_distance_pips × pip_value_eur
    contracts = floor(risk_eur / risk_per_contract_eur)

Dla 6E (EUR/USD futures CME):
  1 pip = 0.0001
  pip value = $12.50 / kontrakt → ~€10.65 / kontrakt (przy EUR/USD ≈ 1.17)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.core.verdict import SetupGrade
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


@dataclass
class SizingResult:
    contracts: int = 0
    risk_eur: float = 0.0                 # actual risk po zaokrągleniu kontraktów
    target_risk_eur: float = 0.0          # docelowy risk (przed floor)
    risk_r: float = 1.0                   # zawsze 1.0 R
    stop_distance_pips: float = 0.0
    atr_pips: float = 0.0
    pip_value_eur: float = 0.0
    risk_pct: float = 0.0
    detail: str = ""


def size(
    cfg: MasterConfig,
    fs: FeatureStore,
    grade: SetupGrade,
    weighted_score: float = 0.0,
) -> SizingResult:
    """Liczy wielkość pozycji wg Tharpa.

    Args:
        cfg: MasterConfig
        fs: FeatureStore (do ATR estimation)
        grade: SetupGrade (A/B/C/NONE)
        weighted_score: opcjonalny boost factor — mocniejszy edge może uzyskać
                        nieznacznie większy risk pct (do max 1.5x).
    """
    # Risk pct na podstawie grade
    if grade == SetupGrade.A:
        risk_pct = cfg.risk.risk_pct_grade_a
    elif grade == SetupGrade.B:
        risk_pct = cfg.risk.risk_pct_grade_b
    else:
        return SizingResult(detail=f"grade {grade.value} — no sizing")

    # ATR z signals (proxy)
    atr_pips = fs.estimate_atr_pips() or cfg.execution.default_atr_pips
    atr_pips = max(atr_pips, cfg.execution.min_atr_pips)  # noise floor

    # Stop distance
    stop_distance_pips = atr_pips * cfg.execution.sl_atr_multiplier
    if stop_distance_pips <= 0:
        return SizingResult(
            atr_pips=atr_pips,
            risk_pct=risk_pct,
            detail="invalid stop distance",
        )

    # Risk EUR
    target_risk_eur = cfg.risk.account_size_eur * risk_pct

    # Risk per kontrakt
    pip_value_eur = cfg.execution.pip_value_eur
    risk_per_contract_eur = stop_distance_pips * pip_value_eur
    if risk_per_contract_eur <= 0:
        return SizingResult(
            atr_pips=atr_pips,
            risk_pct=risk_pct,
            detail="invalid pip_value_eur or stop",
        )

    raw_contracts = target_risk_eur / risk_per_contract_eur
    # Floor — lepiej mniejsza pozycja (Taleb, ruin aversion)
    contracts = max(0, int(raw_contracts))

    actual_risk_eur = contracts * risk_per_contract_eur

    return SizingResult(
        contracts=contracts,
        risk_eur=actual_risk_eur,
        target_risk_eur=target_risk_eur,
        risk_r=1.0,
        stop_distance_pips=stop_distance_pips,
        atr_pips=atr_pips,
        pip_value_eur=pip_value_eur,
        risk_pct=risk_pct,
        detail=(
            f"grade={grade.value}, risk_pct={risk_pct:.3%}, "
            f"atr={atr_pips:.1f}p, sl={stop_distance_pips:.1f}p, "
            f"raw={raw_contracts:.2f} → {contracts}c"
        ),
    )
