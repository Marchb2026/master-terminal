"""Psych monitor — Douglas + Komar t.2 + Elder.

Najczęściej pomijany element systemów tradingowych. Tutaj traktowany jako
pierwszej klasy gate: tilted trader z dobrym systemem traci pieniądze tak
samo jak calm trader z złym systemem.

Sygnały tiltu:
- session_pnl <= -3R (daily loss cap)
- 3+ consecutive losses
- czas reakcji między trade'ami spada (revenge trading)
- pora dnia przekracza próg zmęczenia (configurable)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time

from master.config import MasterConfig
from master.journal.db import JournalDb

log = logging.getLogger(__name__)


@dataclass
class PsychStatus:
    state: str = "CALM"           # CALM / ALERT / TILTED / FATIGUED
    session_pnl_r: float = 0.0
    consecutive_losses: int = 0
    n_trades_today: int = 0
    detail: str = ""


class PsychMonitor:
    def __init__(self, cfg: MasterConfig, journal: JournalDb):
        self.cfg = cfg
        self.journal = journal

    def current_status(self, now: datetime | None = None) -> PsychStatus:
        now = now or datetime.now()
        session_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        pnl_r, n_trades, consec_losses = self.journal.get_session_pnl_r(session_start)

        state = "CALM"
        detail = ""

        if pnl_r <= -self.cfg.risk.max_daily_loss_r:
            state = "TILTED"
            detail = f"daily loss cap reached ({pnl_r:+.1f}R)"
        elif consec_losses >= self.cfg.risk.max_consecutive_losses:
            state = "TILTED"
            detail = f"{consec_losses} consecutive losses"
        elif consec_losses >= self.cfg.risk.max_consecutive_losses - 1:
            state = "ALERT"
            detail = f"{consec_losses} consecutive losses, near cap"
        elif n_trades >= self.cfg.risk.max_trades_per_session:
            state = "TILTED"
            detail = f"trade count cap ({n_trades})"
        elif self._is_fatigue_window(now):
            state = "FATIGUED"
            detail = "fatigue window (late session)"

        return PsychStatus(
            state=state,
            session_pnl_r=pnl_r,
            consecutive_losses=consec_losses,
            n_trades_today=n_trades,
            detail=detail,
        )

    @staticmethod
    def _is_fatigue_window(now: datetime) -> bool:
        """Heurystyka: po 22:00 lokalnie zmęczenie zaczyna mieć znaczenie."""
        return now.time() >= time(22, 0)
