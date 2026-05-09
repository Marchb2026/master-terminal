"""COT (Commitments of Traders) — Williams + Zaremba.

CFTC publikuje co piątek 15:30 ET pozycjonowanie commercials, large specs
i small traders dla każdego futures kontraktu, w tym 6E (Euro FX).

Williams używa COT extremes jako sentiment indicator: gdy commercials
(smart money) są historycznie net long, large specs są w distress short
i odwrotnie — to sygnał kontrarian dla mainstreamu, bullish dla nas.

Implementacja: download CFTC weekly disaggregated report, parsowanie,
trzymanie historii w cache, query po dacie i kontrakcie.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

log = logging.getLogger(__name__)


@dataclass
class CotSnapshot:
    """Tygodniowy snapshot COT dla jednego instrumentu."""

    report_date: date
    commercial_long: int
    commercial_short: int
    large_spec_long: int
    large_spec_short: int
    small_trader_long: int
    small_trader_short: int

    @property
    def commercial_net(self) -> int:
        return self.commercial_long - self.commercial_short

    @property
    def large_spec_net(self) -> int:
        return self.large_spec_long - self.large_spec_short


def fetch_cot_history(contract_code: str = "099741", weeks: int = 52) -> list[CotSnapshot]:
    """Pobiera ostatnie N tygodni z CFTC.

    contract_code dla 6E (Euro FX) = "099741" (CME).

    TODO: implement download z https://www.cftc.gov/dea/futures/deacmesf.htm
    lub via Quandl/Nasdaq Data Link API.
    """
    log.debug("fetch_cot_history(%s, weeks=%d) — TBI", contract_code, weeks)
    return []


def commercial_extreme(
    history: list[CotSnapshot],
    lookback_weeks: int = 52,
    percentile: float = 0.90,
) -> str:
    """Zwraca BULLISH / BEARISH / NEUTRAL na podstawie commercial net positioning.

    BULLISH gdy commercial net jest w top 10% (smart money long extreme).
    BEARISH gdy w bottom 10%.
    """
    if len(history) < 10:
        return "NEUTRAL"

    recent = sorted(history, key=lambda s: s.report_date)[-lookback_weeks:]
    nets = sorted([s.commercial_net for s in recent])
    if not nets:
        return "NEUTRAL"

    current = recent[-1].commercial_net
    n = len(nets)
    rank = sum(1 for v in nets if v <= current) / n

    if rank >= percentile:
        return "BULLISH"
    if rank <= 1 - percentile:
        return "BEARISH"
    return "NEUTRAL"
