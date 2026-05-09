"""Setup grader — Murphy (intermarket + confluence) + Komar (warsztat).

Grade A wymaga 5 z 5 czynników, B = 3 z 5, poniżej = C (no trade).

Pięć czynników:
    1. regime_compatible    — czy reżim pasuje do strony trade'a
    2. mtf_strong           — czy MTF score >= strong threshold
    3. magnet_proximity     — czy cena blisko magnetu (z EA)
    4. flow_confirms        — czy footprint potwierdza (bid/ask aggression)
    5. macro_aligned        — czy compute_sig (FRED+GEX) spójny z kierunkiem
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from master.config import MasterConfig
from master.core.mtf import MtfResult
from master.core.regime import RegimeResult, regime_allows_long, regime_allows_short
from master.core.verdict import SetupGrade, Side
from master.data.feature_store import FeatureStore

log = logging.getLogger(__name__)


@dataclass
class GradeResult:
    grade: SetupGrade = SetupGrade.NONE
    side: Side = Side.NONE
    factors_passed: int = 0
    factors_total: int = 5
    factors_detail: dict[str, bool] = field(default_factory=dict)
    template_id: str = ""    # do edge_lookup — np. "TREND_UP_WEAK_LONG_A"

    def make_template_id(self, regime_value: str) -> str:
        return f"{regime_value}_{self.side.value}_{self.grade.value}"


def grade(
    cfg: MasterConfig,
    fs: FeatureStore,
    regime: RegimeResult,
    mtf: MtfResult,
) -> GradeResult:
    """Klasyfikuje setup na A/B/C wg confluence pięciu czynników.

    TODO: implementacja pełna po feature_store. Na razie placeholder
    który ocenia 2/5 z dostępnych danych (regime + mtf).
    """
    # Wstępny side z MTF
    if mtf.direction_long:
        side = Side.LONG
    elif mtf.direction_short:
        side = Side.SHORT
    else:
        side = Side.NONE

    factors: dict[str, bool] = {}

    # 1. Regime kompatybilny
    if side == Side.LONG:
        factors["regime_compatible"] = regime_allows_long(regime.regime)
    elif side == Side.SHORT:
        factors["regime_compatible"] = regime_allows_short(regime.regime)
    else:
        factors["regime_compatible"] = False

    # 2. MTF strong
    factors["mtf_strong"] = abs(mtf.weighted_score) >= cfg.mtf.strong_align_threshold

    # 3-5. TODO: po feature_store
    factors["magnet_proximity"] = False    # fs.is_near_magnet(cfg.grader.magnet_proximity_atr)
    factors["flow_confirms"] = False        # fs.flow_aggression_side() == side
    factors["macro_aligned"] = False        # fs.compute_sig_bias() konsystentne z side

    passed = sum(factors.values())

    if passed >= cfg.grader.a_grade_min_factors:
        g = SetupGrade.A
    elif passed >= cfg.grader.b_grade_min_factors:
        g = SetupGrade.B
    else:
        g = SetupGrade.C

    result = GradeResult(
        grade=g,
        side=side,
        factors_passed=passed,
        factors_total=5,
        factors_detail=factors,
    )
    result.template_id = result.make_template_id(regime.regime.value)
    log.debug("setup.grade — %s (%d/5) side=%s template=%s",
              g.value, passed, side.value, result.template_id)
    return result
