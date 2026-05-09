"""Pipeline decyzyjny — orchestrator wszystkich kroków.

Sekwencja:
    1. gates.precheck            (events, psych, stale data)
    2. regime.classify           (Clenow, Komar)
    3. mtf.align                 (Elder)
    4. setup_grader.grade        (Murphy, Komar)
    5. edge_lookup.lookup        (Tharp)
    6. sizer.size                (Tharp)
    7. plan.build                (cut losses + asymmetric R:R)

Każdy krok dopisuje AuditStep do werdyktu. Pierwsza porażka
gate'a kończy pipeline werdyktem STAND_DOWN.
"""
from __future__ import annotations

import logging
from datetime import datetime

from master.config import MasterConfig
from master.core import (
    edge_lookup,
    gates,
    mtf,
    plan as plan_mod,
    regime as regime_mod,
    setup_grader,
    sizer as sizer_mod,
)
from master.core.verdict import (
    AuditStep,
    SetupGrade,
    Verdict,
    VerdictState,
)
from master.data.feature_store import FeatureStore
from master.journal.db import JournalDb
from master.monitor.psych import PsychMonitor
from master.monitor.tail import TailMonitor

log = logging.getLogger(__name__)


def run_pipeline(cfg: MasterConfig) -> Verdict:
    """Wykonuje pełen pipeline i zwraca werdykt."""

    verdict = Verdict(
        timestamp=datetime.now(),
        instrument=cfg.instrument,
        state=VerdictState.STAND_DOWN,
    )

    # Inicjalizacja komponentów (lekka, lazy gdzie się da)
    fs = FeatureStore(cfg)
    journal = JournalDb(cfg.journal_db)
    psych = PsychMonitor(cfg, journal)
    tail = TailMonitor(cfg)

    # ─── 1. Pre-checks ───
    pre = gates.precheck(cfg, fs, psych, tail)
    verdict.audit.append(AuditStep("pre-checks", pre.passed, pre.detail))
    verdict.psych_state = pre.psych_state
    verdict.session_pnl_r = pre.session_pnl_r
    verdict.consecutive_losses = pre.consecutive_losses
    verdict.next_event = pre.next_event
    verdict.tail_ok = pre.tail_ok
    if not pre.passed:
        log.info("Pipeline halted at pre-checks: %s", pre.detail)
        return verdict

    # ─── 2. Regime ───
    regime_result = regime_mod.classify(cfg, fs)
    verdict.regime = regime_result.regime
    verdict.audit.append(AuditStep(
        "regime classified",
        regime_result.regime.value != "CHAOS",
        f"{regime_result.regime.value} (adx={regime_result.adx:.1f})",
    ))
    if regime_result.regime.value == "CHAOS":
        return verdict

    # ─── 3. MTF align ───
    mtf_result = mtf.align(cfg, fs)
    verdict.mtf_score = mtf_result.weighted_score
    passed = mtf_result.weighted_score >= cfg.mtf.no_trade_threshold
    verdict.audit.append(AuditStep(
        "mtf align",
        passed,
        f"{mtf_result.weighted_score:.1f}/9 ({mtf_result.summary})",
    ))
    if not passed:
        return verdict

    # ─── 4. Setup grade ───
    grade_result = setup_grader.grade(cfg, fs, regime_result, mtf_result)
    verdict.setup_grade = grade_result.grade
    passed = grade_result.grade in (SetupGrade.A, SetupGrade.B)
    verdict.audit.append(AuditStep(
        "setup grade",
        passed,
        f"{grade_result.grade.value} ({grade_result.factors_passed}/5 factors)",
    ))
    if not passed:
        return verdict

    # ─── 5. Edge lookup ───
    edge_result = edge_lookup.lookup(cfg, journal, regime_result, grade_result)
    verdict.expected_r = edge_result.expected_r
    verdict.sample_size = edge_result.sample_size
    passed = edge_result.tradeable
    verdict.audit.append(AuditStep(
        "edge lookup",
        passed,
        f"E={edge_result.expected_r:+.2f}R, n={edge_result.sample_size}"
        if edge_result.expected_r is not None else "no historical data",
    ))
    if not passed:
        return verdict

    # WATCH: setup się kwalifikuje, ale czekamy na trigger cenowy
    verdict.state = VerdictState.WATCH

    # ─── 6. Position sizing ───
    sizing = sizer_mod.size(cfg, fs, grade_result, edge_result)
    verdict.audit.append(AuditStep(
        "position sizing",
        sizing.contracts > 0,
        f"size={sizing.contracts}, risk={sizing.risk_eur:.2f} EUR",
    ))

    # ─── 7. Trade plan ───
    plan = plan_mod.build(cfg, fs, regime_result, sizing)
    verdict.plan = plan
    if plan.entry is not None:
        verdict.audit.append(AuditStep(
            "trade plan",
            True,
            f"entry={plan.entry:.4f}, sl={plan.stop_loss:.4f}",
        ))
        # READY: plan jest gotowy, oczekujemy że cena go aktywuje
        verdict.state = VerdictState.READY

    return verdict
