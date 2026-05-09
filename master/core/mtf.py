"""Multi-timeframe alignment — Elder (*Trading for a Living*).

Triple screen: wyższy TF definiuje strategiczny kierunek, średni taktyczny
setup, niski moment wejścia. Z 9 TF EA generujemy ważony score 0-9.

Każdy TF głosuje +1 (bull), -1 (bear), 0 (neutral) na podstawie prostych
filtrów (np. close vs EMA20). Wagę określa cfg.mtf.weights (wyższe TF
ważniejsze, bo definiują kontekst).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from master.config import MasterConfig
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


@dataclass
class MtfResult:
    weighted_score: float = 0.0      # 0-9 (znak + dla longów, - dla shortów)
    raw_votes: dict[str, int] = field(default_factory=dict)
    summary: str = "unknown"

    @property
    def direction_long(self) -> bool:
        return self.weighted_score > 0

    @property
    def direction_short(self) -> bool:
        return self.weighted_score < 0


def align(cfg: MasterConfig, fs: FeatureStore) -> MtfResult:
    """Liczy weighted alignment score dla wszystkich TF z konfiguracji.

    TODO: implement po schemat feature_store.
    Logika:
        for tf in cfg.mtf.timeframes:
            bars = fs.get_bars(tf, n=50)
            ema = ema(bars.close, 20)
            vote = +1 if bars.close[-1] > ema[-1] else -1
            raw_votes[tf] = vote

        weighted = sum(votes[tf] * cfg.mtf.weights[tf] for tf in tfs)
        normalized = weighted / sum(weights) * 9   # do skali 0-9
    """
    log.debug("mtf.align — placeholder (TBI po feature_store)")

    return MtfResult(
        weighted_score=0.0,
        raw_votes={tf: 0 for tf in cfg.mtf.timeframes},
        summary="not yet implemented",
    )
