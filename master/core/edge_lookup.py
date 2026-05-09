"""Edge lookup — Tharp (*Trade Your Way to Financial Freedom*).

Podstawowa idea: każdy setup ma policzalną historyczną expectancy
    E = (P_win × avg_win_R) − (P_loss × avg_loss_R)

w jednostkach R. Setup z E < threshold nie wchodzi, kropka. Bez expectancy
to nie jest trading, to jest hazard z fancy interface'em (Tharp's words).

Source of truth: dziennik trade'ów (journal/db.py) zawierający historyczne
realizacje. Importer pobiera EA's signal_log.csv jako proto-historię.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from master.config import MasterConfig
from master.core.setup_grader import GradeResult
from master.core.regime import RegimeResult
from master.core.verdict import SetupGrade
from master.journal.db import JournalDb
from master.journal.stats import compute_expectancy

log = logging.getLogger(__name__)


@dataclass
class EdgeResult:
    expected_r: float | None
    sample_size: int
    win_rate: float = 0.0
    profit_factor: float = 0.0
    tradeable: bool = False
    reason: str = ""


def lookup(
    cfg: MasterConfig,
    journal: JournalDb,
    regime: RegimeResult,
    grade: GradeResult,
) -> EdgeResult:
    """Wyciąga expectancy dla danego templatu setupu.

    Template ID = "{regime}_{side}_{grade}", np. "TREND_UP_WEAK_LONG_A".
    Liczymy expectancy na pasujących trade'ach z dziennika.
    """
    template = grade.template_id

    trades = journal.get_trades_by_template(template)
    n = len(trades)

    if n == 0:
        # Brak historii — Tharp: w trybie eksploracji bierzemy ½ size, ale
        # tu chcemy konserwatywnie odrzucić, póki nie zbierzemy danych.
        return EdgeResult(
            expected_r=None,
            sample_size=0,
            tradeable=False,
            reason=f"no historical trades for template {template}",
        )

    stats = compute_expectancy(trades)

    threshold = (
        cfg.edge.min_e_for_a if grade.grade == SetupGrade.A
        else cfg.edge.min_e_for_b
    )

    tradeable = stats.expectancy_r >= threshold and n >= cfg.edge.min_sample_size

    reason = ""
    if not tradeable:
        if n < cfg.edge.min_sample_size:
            reason = f"sample too small ({n} < {cfg.edge.min_sample_size})"
        else:
            reason = f"E {stats.expectancy_r:+.2f}R below threshold {threshold:.2f}R"

    return EdgeResult(
        expected_r=stats.expectancy_r,
        sample_size=n,
        win_rate=stats.win_rate,
        profit_factor=stats.profit_factor,
        tradeable=tradeable,
        reason=reason,
    )
