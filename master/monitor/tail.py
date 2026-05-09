"""Tail monitor — Taleb (*Fooled by Randomness* / *Black Swan*).

Cel: nie pozwolić Masterowi wejść w trade w momencie gdy pojedyncze
zewnętrzne zdarzenie (event makro, gap, low liquidity window) może
unieważnić cały statystyczny edge.

Mechanizm: blackout window wokół eventów wysokiego impactu z
data/calendar.py. W blackoutcie pre-checks wraca FAIL i pipeline
zamyka się na STAND_DOWN.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from master.config import MasterConfig
from master.data.calendar import (
    Event,
    in_blackout_window,
    load_events_from_json,
    next_high_impact_event,
)

log = logging.getLogger(__name__)


@dataclass
class TailStatus:
    in_blackout: bool = False
    blackout_reason: str = ""
    next_event: Event | None = None
    next_event_label: str = "—"


class TailMonitor:
    def __init__(self, cfg: MasterConfig, events_path: Path | None = None):
        self.cfg = cfg
        # Domyślny plik kalendarza
        self._events_path = events_path or (
            cfg.journal_db.parent / "calendar_events.json"
        )

    def current_status(self, now: datetime | None = None) -> TailStatus:
        now = now or datetime.now()
        events = load_events_from_json(self._events_path)

        # 1. Czy jesteśmy w aktywnym blackoucie?
        for ev in events:
            if ev.impact != "high":
                continue
            if in_blackout_window(
                ev,
                now=now,
                minutes_before=self.cfg.tail.blackout_minutes_before_event,
                minutes_after=self.cfg.tail.blackout_minutes_after_event,
            ):
                return TailStatus(
                    in_blackout=True,
                    blackout_reason=f"{ev.name} @ {ev.when:%H:%M}",
                    next_event=ev,
                    next_event_label=f"{ev.name} (blackout)",
                )

        # 2. Najbliższy event
        nxt = next_high_impact_event(events, now=now)
        if nxt is None:
            return TailStatus(in_blackout=False, next_event_label="—")

        delta = nxt.when - now
        hours = delta.total_seconds() / 3600
        if hours < 1:
            label = f"{nxt.name} in {int(delta.total_seconds() / 60)}min"
        elif hours < 24:
            label = f"{nxt.name} in {hours:.0f}h"
        else:
            label = f"{nxt.name} in {hours / 24:.1f}d"

        return TailStatus(
            in_blackout=False,
            next_event=nxt,
            next_event_label=label,
        )
