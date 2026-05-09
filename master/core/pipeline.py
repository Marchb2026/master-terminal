"""Pipeline decyzyjny — orchestrator wszystkich kroków v0.6.

Sekwencja:
    1. gates.precheck            — HARD GATE
    2. weighted_decision         — PRIMARY (7-layer confluence)
    3. regime.classify           — gate na long/short kompatybilność z reżimem
    4. mtf.align                 — informacyjnie
    5. sizer.size                — Tharp R-multiples
    6. plan.build                — Faith Turtle entry/SL/TP1/TP2

Mapa weighted_score → SetupGrade:
    >= 1.0R   → A
    >= 0.5R   → B
    >= 0.3R   → C  (watch only — no sizing)
    <  0.3R   → NONE → STAND_DOWN

State transitions:
    weighted < 0.3        → STAND_DOWN
    A/B + regime allows + plan complete → READY
    A/B + plan incomplete → WATCH
"""
from __future__ import annotations

import logging
from datetime import datetime

from master.config import MasterConfig
from master.core import (
    decision as decision_mod,
    gates,
    mtf,
    plan as plan_mod,
    regime as regime_mod,
    sizer as sizer_mod,
)
from master.core.verdict import (
    AuditStep,
    SetupGrade,
    Side,
    Verdict,
    VerdictState,
)
from master.data.feature_store import FeatureStore
from master.journal.db import JournalDb
from master.monitor.psych import PsychMonitor
from master.monitor.tail import TailMonitor

log = logging.getLogger(__name__)


def _grade_from_score(score: float) -> SetupGrade:
    if score >= 1.0:
        return SetupGrade.A
    if score >= 0.5:
        return SetupGrade.B
    if score >= 0.3:
        return SetupGrade.C
    return SetupGrade.NONE


def run_pipeline(cfg: MasterConfig) -> Verdict:
    """Wykonuje pełen pipeline i zwraca werdykt."""

    verdict = Verdict(
        timestamp=datetime.now(),
        instrument=cfg.instrument,
        state=VerdictState.STAND_DOWN,
    )

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

    # ─── 2. Weighted Decision ───
    wd = decision_mod.compute_weighted_decision(fs)

    verdict.extras["weighted_score"] = wd.weighted_score
    verdict.extras["weighted_direction"] = wd.direction
    verdict.extras["weighted_long"] = wd.weighted_long
    verdict.extras["weighted_short"] = wd.weighted_short
    verdict.extras["fade_count"] = wd.fade_count
    verdict.extras["sources_active"] = wd.n_sources_with_edge
    verdict.extras["contributing"] = wd.contributing
    verdict.extras["composite_contribution"] = wd.composite_contribution
    verdict.extras["liquidity_modifier"] = wd.liquidity_modifier
    verdict.extras["gex_warning"] = wd.gex_warning
    verdict.extras["mtf_alignment"] = wd.mtf_alignment
    verdict.extras["decision_threshold_used"] = wd.decision_threshold_used
    verdict.extras["sources_unstable"] = wd.sources_unstable
    verdict.extras["decision_notes"] = wd.notes

    verdict.expected_r = wd.weighted_score if wd.direction != "FLAT" else 0.0
    verdict.sample_size = wd.n_sources_with_edge
    verdict.setup_grade = _grade_from_score(wd.weighted_score)

    decision_passed = wd.weighted_score >= decision_mod.DEFAULT_DECISION_THRESHOLD \
                      and wd.direction != "FLAT"

    verdict.audit.append(AuditStep(
        "weighted decision",
        decision_passed,
        f"{wd.direction} {wd.weighted_score:+.2f}R "
        f"(sources={wd.n_sources_with_edge}, fade={wd.fade_count}, "
        f"flat-skipped={wd.flat_skipped})",
    ))

    if not decision_passed:
        log.info("Pipeline halted at weighted_decision: score=%.3f dir=%s",
                 wd.weighted_score, wd.direction)
        return verdict

    side = Side.LONG if wd.direction == "LONG" else Side.SHORT
    verdict.plan.side = side

    # ─── 3. Regime — gate na long/short ───
    regime_result = regime_mod.classify(cfg, fs)
    verdict.regime = regime_result.regime
    verdict.extras["regime_detail"] = regime_result.detail
    verdict.extras["regime_long_short_ratio"] = regime_result.long_short_ratio

    # Sprawdź czy regime pozwala na ten kierunek
    if side == Side.LONG and not regime_mod.regime_allows_long(regime_result.regime):
        verdict.audit.append(AuditStep(
            "regime classified", False,
            f"{regime_result.regime.value} blocks LONG: {regime_result.detail}",
        ))
        verdict.state = VerdictState.STAND_DOWN
        return verdict
    if side == Side.SHORT and not regime_mod.regime_allows_short(regime_result.regime):
        verdict.audit.append(AuditStep(
            "regime classified", False,
            f"{regime_result.regime.value} blocks SHORT: {regime_result.detail}",
        ))
        verdict.state = VerdictState.STAND_DOWN
        return verdict
    if regime_result.regime.value == "CHAOS":
        verdict.audit.append(AuditStep(
            "regime classified", False,
            f"CHAOS — abstain (Taleb): {regime_result.detail}",
        ))
        verdict.state = VerdictState.STAND_DOWN
        return verdict

    verdict.audit.append(AuditStep(
        "regime classified",
        regime_result.regime.value not in ("CHAOS", "UNKNOWN"),
        f"{regime_result.regime.value} (atr {regime_result.adx:.1f}p): {regime_result.detail}",
    ))

    # ─── 4. MTF align (informacyjnie) ───
    try:
        mtf_result = mtf.align(cfg, fs)
        verdict.mtf_score = mtf_result.weighted_score
        verdict.audit.append(AuditStep(
            "mtf align",
            mtf_result.weighted_score >= cfg.mtf.no_trade_threshold,
            f"{mtf_result.weighted_score:.1f}/9 ({mtf_result.summary})",
        ))
    except Exception as e:
        log.warning("mtf.align failed: %s", e)
        verdict.audit.append(AuditStep(
            "mtf align", False,
            f"skipped: {type(e).__name__}",
        ))

    # WATCH baseline (jeśli grade się kwalifikuje)
    if verdict.setup_grade in (SetupGrade.A, SetupGrade.B):
        verdict.state = VerdictState.WATCH

    # ─── 5. Position sizing (Tharp) ───
    sizing = sizer_mod.size(cfg, fs, verdict.setup_grade, wd.weighted_score)
    verdict.audit.append(AuditStep(
        "position sizing",
        sizing.contracts > 0,
        f"size={sizing.contracts}c, risk={sizing.risk_eur:.0f}EUR, "
        f"atr={sizing.atr_pips:.1f}p, sl={sizing.stop_distance_pips:.1f}p",
    ))
    verdict.extras["sizing_detail"] = sizing.detail
    verdict.extras["atr_pips"] = sizing.atr_pips
    verdict.extras["stop_distance_pips"] = sizing.stop_distance_pips

    if sizing.contracts <= 0:
        return verdict

    # ─── 6. Trade plan (Faith Turtle) ───
    plan = plan_mod.build(cfg, fs, regime_result, sizing, side)
    verdict.plan = plan

    if plan.entry is not None and plan.stop_loss is not None:
        verdict.audit.append(AuditStep(
            "trade plan",
            True,
            plan_mod.render_plan_text(plan),
        ))
        # READY: pełen plan z entry/SL/TP — to jest moment "uzbrojonego trigger'a"
        verdict.state = VerdictState.READY
    else:
        verdict.audit.append(AuditStep(
            "trade plan", False,
            "incomplete plan — brak spot",
        ))

    return verdict
