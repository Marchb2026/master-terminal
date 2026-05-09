"""Regime classifier — Clenow (*Following the Trend*) + Komar (*Sztuka spekulacji*).

Każdy reżim aktywuje inny katalog setupów:
  TREND_UP_*  → continuation longs (pullback)
  TREND_DN_*  → continuation shorts
  RANGE       → mean-reversion od magnetów (Komar)
  CHAOS       → no trade (Taleb-style abstain)
  UNKNOWN     → not enough data

Bez prawdziwego TF feedu (TF240/TF60 EMAs) używamy uproszczonej klasyfikacji
opartej o:
  1. composite.json (m1-m12 meta-aggregator) — direction + conviction
  2. signal distribution z signals_unified (LONG/SHORT ratio z fade-aware logic)
  3. estimate_atr_pips — proxy zmienności (Komar's ADX surrogate)

Klasyfikacja:
  composite BULL HIGH + low/normal vol     → TREND_UP_STRONG
  composite BULL MEDIUM/LOW                → TREND_UP_WEAK
  composite BEAR HIGH + low/normal vol     → TREND_DN_STRONG
  composite BEAR MEDIUM/LOW                → TREND_DN_WEAK
  composite NEUT + balanced signals        → RANGE
  high vol + no clear bias                 → CHAOS
  brak danych                              → UNKNOWN
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.core.verdict import Regime
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)

# Próg "wysokiej zmienności" (Komar: dramatic vol = unstable regime)
HIGH_VOL_ATR_PIPS = 30.0
LOW_VOL_ATR_PIPS = 8.0

# Próg balansu LONG/SHORT votes dla RANGE
RANGE_BALANCE_TOLERANCE = 0.20    # |long_ratio - 0.5| < 0.20 → range


@dataclass
class RegimeResult:
    regime: Regime
    adx: float = 0.0                  # tu używamy ATR pips jako proxy
    ema_slope_240: float = 0.0
    above_ema200: bool = False
    atr_pct: float = 0.0
    detail: str = ""

    # Diagnostic fields
    composite_direction: str = "UNKNOWN"
    composite_conviction: str = "UNKNOWN"
    long_short_ratio: float = 0.5     # 0.0 = wszystko SHORT, 1.0 = wszystko LONG
    n_directional_signals: int = 0


def classify(cfg: MasterConfig, fs: FeatureStore) -> RegimeResult:
    """Klasyfikuje aktualny reżim na bazie composite + signal distribution + vol."""

    composite = fs.read_composite()
    atr_pips = fs.estimate_atr_pips() or 0.0

    # Long/short distribution
    recent = fs.read_recent_signals(since_minutes=30, limit=2000)
    long_count = 0
    short_count = 0
    for sig in recent:
        if sig.confidence > 0 and sig.direction in ("LONG", "SHORT"):
            if sig.direction == "LONG":
                long_count += 1
            else:
                short_count += 1
    total_dir = long_count + short_count
    long_ratio = (long_count / total_dir) if total_dir > 0 else 0.5

    # ─── Decision tree ───
    if not composite and total_dir == 0:
        return RegimeResult(
            regime=Regime.UNKNOWN,
            detail="brak composite + brak directional signals",
            n_directional_signals=0,
        )

    # CHAOS: bardzo wysoka zmienność i brak konsensusu
    if atr_pips > HIGH_VOL_ATR_PIPS and (
        not composite or composite.direction == "NEUT"
    ) and abs(long_ratio - 0.5) < 0.15:
        return RegimeResult(
            regime=Regime.CHAOS,
            adx=atr_pips,
            atr_pct=atr_pips,
            detail=f"high vol ({atr_pips:.1f}p) + brak kierunku",
            composite_direction=composite.direction if composite else "UNKNOWN",
            composite_conviction=composite.conviction if composite else "UNKNOWN",
            long_short_ratio=long_ratio,
            n_directional_signals=total_dir,
        )

    # Trend reżimy — bazują na composite
    if composite:
        if composite.direction == "BULL":
            if composite.conviction == "HIGH":
                regime = Regime.TREND_UP_STRONG
                detail = f"composite BULL HIGH (score {composite.score:+.2f})"
            else:
                regime = Regime.TREND_UP_WEAK
                detail = f"composite BULL {composite.conviction}"
            return RegimeResult(
                regime=regime, adx=atr_pips, atr_pct=atr_pips,
                composite_direction=composite.direction,
                composite_conviction=composite.conviction,
                long_short_ratio=long_ratio,
                n_directional_signals=total_dir,
                detail=detail,
            )
        if composite.direction == "BEAR":
            if composite.conviction == "HIGH":
                regime = Regime.TREND_DN_STRONG
                detail = f"composite BEAR HIGH (score {composite.score:+.2f})"
            else:
                regime = Regime.TREND_DN_WEAK
                detail = f"composite BEAR {composite.conviction}"
            return RegimeResult(
                regime=regime, adx=atr_pips, atr_pct=atr_pips,
                composite_direction=composite.direction,
                composite_conviction=composite.conviction,
                long_short_ratio=long_ratio,
                n_directional_signals=total_dir,
                detail=detail,
            )

    # composite NEUT lub brak — używamy long/short distribution
    if total_dir > 0 and abs(long_ratio - 0.5) < RANGE_BALANCE_TOLERANCE:
        return RegimeResult(
            regime=Regime.RANGE, adx=atr_pips, atr_pct=atr_pips,
            composite_direction=composite.direction if composite else "NEUT",
            composite_conviction=composite.conviction if composite else "LOW",
            long_short_ratio=long_ratio,
            n_directional_signals=total_dir,
            detail=f"NEUT composite + balanced signals ({long_count}/{short_count})",
        )

    # Asymetryczne signals ale composite NEUT — słaby trend by direction
    if long_ratio > 0.6:
        return RegimeResult(
            regime=Regime.TREND_UP_WEAK, adx=atr_pips, atr_pct=atr_pips,
            composite_direction=composite.direction if composite else "NEUT",
            composite_conviction=composite.conviction if composite else "LOW",
            long_short_ratio=long_ratio,
            n_directional_signals=total_dir,
            detail=f"signal-derived weak up (long_ratio {long_ratio:.0%})",
        )
    if long_ratio < 0.4:
        return RegimeResult(
            regime=Regime.TREND_DN_WEAK, adx=atr_pips, atr_pct=atr_pips,
            composite_direction=composite.direction if composite else "NEUT",
            composite_conviction=composite.conviction if composite else "LOW",
            long_short_ratio=long_ratio,
            n_directional_signals=total_dir,
            detail=f"signal-derived weak down (long_ratio {long_ratio:.0%})",
        )

    # Default: RANGE jeśli mamy jakiekolwiek dane
    return RegimeResult(
        regime=Regime.RANGE, adx=atr_pips, atr_pct=atr_pips,
        composite_direction=composite.direction if composite else "NEUT",
        composite_conviction=composite.conviction if composite else "LOW",
        long_short_ratio=long_ratio,
        n_directional_signals=total_dir,
        detail="default range",
    )


def regime_allows_long(regime: Regime) -> bool:
    """Czy w danym reżimie longi są w grze."""
    return regime in (
        Regime.TREND_UP_STRONG,
        Regime.TREND_UP_WEAK,
        Regime.RANGE,
    )


def regime_allows_short(regime: Regime) -> bool:
    return regime in (
        Regime.TREND_DN_STRONG,
        Regime.TREND_DN_WEAK,
        Regime.RANGE,
    )
