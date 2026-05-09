"""Trade plan — Lefèvre (cut losses) + Faith Turtle (let winners run).

Faith Turtle Rules (zaadaptowane):
  - SL = entry ± sl_atr_multiplier × ATR    (Lefèvre: cut losses fast, hard SL)
  - TP1 = entry ± tp1_r_multiple × R        (lock 50% pozycji przy ~1.5R)
  - TP2 = entry ± tp2_r_multiple × R        (kolejne 30% przy ~3R)
  - runner (20%) → trailing stop = high - trailing_atr_multiplier × ATR
                                   (Faith: never cap profit)

Plan ma `invalidation_minutes` — jeśli setup nie aktywuje się w tym czasie,
plan jest anulowany (Faith mechaniczność, nie trzymamy "może jeszcze").

R = stop_distance_pips. TP1 = entry ± 1.5×R, TP2 = entry ± 3×R.
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
    side: Side,
) -> TradePlan:
    """Składa konkretny plan trade'a."""

    # Walidacja
    if sizing.contracts <= 0:
        return TradePlan(side=side)
    if side == Side.NONE:
        return TradePlan()

    # Aktualna cena
    spot = fs.get_current_spot()
    if spot is None or spot <= 0:
        log.warning("plan.build: brak current_spot — pusty plan")
        return TradePlan(
            side=side,
            position_size_contracts=sizing.contracts,
            risk_eur=sizing.risk_eur,
            risk_r=sizing.risk_r,
        )

    pip_size = cfg.execution.pip_size
    stop_pips = sizing.stop_distance_pips

    # Entry / SL / TP — opaque per side
    if side == Side.LONG:
        entry = spot
        stop_loss = entry - stop_pips * pip_size
        # R to dystans entry → SL (= stop_pips × pip_size)
        r_distance = stop_pips * pip_size
        tp1 = entry + r_distance * cfg.execution.tp1_r_multiple
        tp2 = entry + r_distance * cfg.execution.tp2_r_multiple
    elif side == Side.SHORT:
        entry = spot
        stop_loss = entry + stop_pips * pip_size
        r_distance = stop_pips * pip_size
        tp1 = entry - r_distance * cfg.execution.tp1_r_multiple
        tp2 = entry - r_distance * cfg.execution.tp2_r_multiple
    else:
        return TradePlan()

    return TradePlan(
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=tp1,
        take_profit_2=tp2,
        invalidation_minutes=cfg.execution.invalidation_minutes,
        position_size_contracts=sizing.contracts,
        risk_eur=sizing.risk_eur,
        risk_r=sizing.risk_r,
    )


def render_plan_text(plan: TradePlan) -> str:
    """Czytelne podsumowanie planu — do logów / UI."""
    if plan.entry is None or plan.side == Side.NONE:
        return "no plan"

    return (
        f"{plan.side.value} {plan.position_size_contracts}c @ {plan.entry:.4f} | "
        f"SL {plan.stop_loss:.4f} | TP1 {plan.take_profit_1:.4f} | "
        f"TP2 {plan.take_profit_2:.4f} | risk {plan.risk_eur:.0f}EUR ({plan.risk_r:.1f}R) | "
        f"invalidate {plan.invalidation_minutes}min"
    )
