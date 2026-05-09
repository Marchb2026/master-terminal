"""Macro calendar i sezonowość — Zaremba + Murphy intermarket.

Eventy makro: FOMC, ECB, NFP, CPI, PCE, GDP. Wokół nich Master odmawia
trade'a (blackout window konfigurowalny w config.tail).

Sezonowość 6E (EUR futures): koniec miesiąca/kwartału, Triple Witching,
ECB cycle, Fed cycle. Zaremba mocno podkreśla tę warstwę dla FX i surowców.

W pierwszej iteracji: prosta lista eventów ładowana z pliku JSON.
W drugiej: integracja z economic calendar API (np. FRED, ForexFactory feed).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Event:
    name: str
    when: datetime
    impact: str = "high"   # high / medium / low
    region: str = "US"     # US / EU / GLOBAL


def load_events_from_json(path: Path) -> list[Event]:
    """Ładuje eventy z prostego pliku JSON.

    Format:
    [
      {"name": "FOMC", "when": "2026-05-15T18:00:00", "impact": "high", "region": "US"},
      ...
    ]
    """
    if not path.exists():
        log.warning("Calendar file %s not found, returning empty list", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Failed to parse %s: %s", path, e)
        return []

    events: list[Event] = []
    for item in raw:
        try:
            events.append(Event(
                name=item["name"],
                when=datetime.fromisoformat(item["when"]),
                impact=item.get("impact", "high"),
                region=item.get("region", "GLOBAL"),
            ))
        except KeyError as e:
            log.warning("Skipping event due to missing key %s: %s", e, item)
    return events


def next_high_impact_event(
    events: list[Event],
    now: datetime | None = None,
    impact_filter: tuple[str, ...] = ("high",),
) -> Event | None:
    """Najbliższy nadchodzący event o danym impact'cie."""
    now = now or datetime.now()
    upcoming = [e for e in events if e.when > now and e.impact in impact_filter]
    if not upcoming:
        return None
    return min(upcoming, key=lambda e: e.when)


def in_blackout_window(
    event: Event,
    now: datetime | None = None,
    minutes_before: int = 30,
    minutes_after: int = 15,
) -> bool:
    """Czy now mieści się w oknie [event - before, event + after]."""
    now = now or datetime.now()
    window_start = event.when - timedelta(minutes=minutes_before)
    window_end = event.when + timedelta(minutes=minutes_after)
    return window_start <= now <= window_end


# ─────────── Sezonowość 6E ───────────

def is_month_end(now: datetime | None = None, days_window: int = 2) -> bool:
    """Czy jesteśmy w ostatnich N dniach roboczych miesiąca (FX flow effect)."""
    # TODO: business-day logic
    now = now or datetime.now()
    return False


def is_triple_witching(now: datetime | None = None) -> bool:
    """3-cia środa marca/czerwca/września/grudnia (US derivatives expiry)."""
    # TODO
    return False
