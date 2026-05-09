"""Werdykt — końcowy output pipeline'u Mastera.

Werdykt to dataclass, nigdy string. Jeden ekran w UI to renderowany
Verdict, jedna linia w CLI to też renderowany Verdict.

Filozofia: każdy trade jest niezależnym wydarzeniem probabilistycznym
(Douglas), więc werdykt zawsze niesie expectancy w R, a nie pseudopewność
"buy/sell".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class VerdictState(str, Enum):
    """Cztery główne stany operacyjne + EXIT."""

    STAND_DOWN = "STAND_DOWN"   # aktywny no-trade
    WATCH = "WATCH"             # warunki się rozwijają, czekamy
    READY = "READY"             # wszystko zielone, trigger uzbrojony
    ENGAGED = "ENGAGED"         # w pozycji, monitoring
    EXIT = "EXIT"               # sygnał wyjścia


class SetupGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    NONE = "NONE"


class Regime(str, Enum):
    TREND_UP_STRONG = "TREND_UP_STRONG"
    TREND_UP_WEAK = "TREND_UP_WEAK"
    RANGE = "RANGE"
    TREND_DN_WEAK = "TREND_DN_WEAK"
    TREND_DN_STRONG = "TREND_DN_STRONG"
    CHAOS = "CHAOS"
    UNKNOWN = "UNKNOWN"


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class TradePlan:
    """Konkretny plan trade'a — wypełnione tylko dla READY/ENGAGED."""

    side: Side = Side.NONE
    entry: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    invalidation_minutes: int | None = None
    position_size_contracts: float | None = None
    risk_eur: float | None = None
    risk_r: float | None = None      # zawsze 1.0 R per trade w naszej konwencji


@dataclass
class AuditStep:
    """Pojedynczy krok pipeline'u — czy przeszedł, z jakim wynikiem."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class Verdict:
    """Końcowy werdykt Mastera."""

    timestamp: datetime
    instrument: str
    state: VerdictState

    # context
    regime: Regime = Regime.UNKNOWN
    mtf_score: float = 0.0          # 0–9 (weighted)
    setup_grade: SetupGrade = SetupGrade.NONE
    expected_r: float | None = None     # E z journala dla tego templatu
    sample_size: int = 0

    # psych & tail
    psych_state: str = "UNKNOWN"
    session_pnl_r: float = 0.0
    consecutive_losses: int = 0
    next_event: str = "—"
    tail_ok: bool = True

    # plan (tylko dla READY/ENGAGED)
    plan: TradePlan = field(default_factory=TradePlan)

    # audit trail — kolejność jak w pipeline
    audit: list[AuditStep] = field(default_factory=list)

    # surowe dane dla UI/debug
    extras: dict[str, Any] = field(default_factory=dict)

    def render_text(self) -> str:
        """Render do CLI / loga — krótki, czytelny, bez markdownu."""
        lines = []
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"=== MASTER · {self.instrument} · {ts} ===")
        lines.append("")
        lines.append(f"  >>> {self.state.value} <<<")
        lines.append("")
        lines.append(f"  regime: {self.regime.value:<20s}  mtf: {self.mtf_score:.1f}/9")
        e_str = f"{self.expected_r:+.2f}R (n={self.sample_size})" if self.expected_r is not None else "n/a"
        lines.append(f"  setup:  {self.setup_grade.value:<20s}  edge: {e_str}")
        lines.append(f"  psych:  {self.psych_state:<20s}  pnl: {self.session_pnl_r:+.1f}R")
        lines.append(f"  tail:   {'OK' if self.tail_ok else 'BLOCKED':<20s}  next: {self.next_event}")

        if self.state in (VerdictState.READY, VerdictState.ENGAGED) and self.plan.entry is not None:
            lines.append("")
            lines.append(f"  PLAN  side={self.plan.side.value}  entry={self.plan.entry:.4f}  "
                         f"sl={self.plan.stop_loss:.4f}  tp1={self.plan.take_profit_1:.4f}")
            lines.append(f"        size={self.plan.position_size_contracts}  "
                         f"risk={self.plan.risk_eur:.2f} EUR  ({self.plan.risk_r:.2f}R)")

        if self.audit:
            lines.append("")
            lines.append("  audit trail:")
            for step in self.audit:
                mark = "✓" if step.passed else "✗"
                detail = f" — {step.detail}" if step.detail else ""
                lines.append(f"    {mark} {step.name}{detail}")
        return "\n".join(lines)
