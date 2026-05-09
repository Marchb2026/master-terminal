"""Pre-checks — gate'y wykluczające, uruchamiane przed całym pipelinem.

Filozofia: Taleb (tail risk) + Douglas/Elder (psychologia).
Lepiej nie tradować niż tradować w warunkach, w których edge jest podważony
przez pojedyncze zewnętrzne zdarzenie.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.data.feature_store import FeatureStore
from master.monitor.psych import PsychMonitor
from master.monitor.tail import TailMonitor

log = logging.getLogger(__name__)


@dataclass
class PrecheckResult:
    passed: bool
    detail: str = ""

    # snapshot do werdyktu (żeby nie wołać dwa razy)
    psych_state: str = "UNKNOWN"
    session_pnl_r: float = 0.0
    consecutive_losses: int = 0
    next_event: str = "—"
    tail_ok: bool = True


def precheck(
    cfg: MasterConfig,
    fs: FeatureStore,
    psych: PsychMonitor,
    tail: TailMonitor,
) -> PrecheckResult:
    """Sprawdza wszystkie warunki wykluczające w odpowiedniej kolejności.

    Pierwszy fail kończy check. Reszta przyczyn jest informacyjna.
    """
    result = PrecheckResult(passed=True)

    # 1. Świeżość danych (Schwager Wizards: nie tradujesz na danych których nie ufasz)
    freshness = fs.check_freshness()
    if not freshness.is_fresh:
        result.passed = False
        result.detail = f"stale data: {freshness.reason}"
        log.warning("Pre-check FAIL: %s", result.detail)
        return result

    # 2. Tail risk (Taleb): blackout window wokół eventów makro
    tail_status = tail.current_status()
    result.next_event = tail_status.next_event_label
    result.tail_ok = tail_status.in_blackout is False
    if tail_status.in_blackout:
        result.passed = False
        result.detail = f"event blackout: {tail_status.blackout_reason}"
        log.info("Pre-check FAIL: %s", result.detail)
        return result

    # 3. Psych state (Douglas, Elder): tilt detection, daily caps
    psych_status = psych.current_status()
    result.psych_state = psych_status.state
    result.session_pnl_r = psych_status.session_pnl_r
    result.consecutive_losses = psych_status.consecutive_losses

    if psych_status.session_pnl_r <= -cfg.risk.max_daily_loss_r:
        result.passed = False
        result.detail = (
            f"daily loss cap hit: {psych_status.session_pnl_r:+.1f}R "
            f"<= -{cfg.risk.max_daily_loss_r:.1f}R"
        )
        log.info("Pre-check FAIL: %s", result.detail)
        return result

    if psych_status.consecutive_losses >= cfg.risk.max_consecutive_losses:
        result.passed = False
        result.detail = f"consecutive losses: {psych_status.consecutive_losses}"
        log.info("Pre-check FAIL: %s", result.detail)
        return result

    if psych_status.state == "TILTED":
        result.passed = False
        result.detail = "tilt detected"
        log.info("Pre-check FAIL: %s", result.detail)
        return result

    result.detail = "all gates passed"
    return result
