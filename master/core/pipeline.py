"""Pipeline decyzyjny — orchestrator wszystkich kroków.

Sekwencja v0.4 (po commit #4 — pipeline integration):
    1. gates.precheck            (events, psych, stale data)  — HARD GATE
    2. weighted_decision         (PRIMARY: edge-aware confluence po fade)  ← główny krok
    3. regime.classify           (informacyjnie, nie haltuje)
    4. mtf.align                 (informacyjnie, nie haltuje)
    5. sizer.size                (skip jeśli brak ATR/spot)
    6. plan.build                (skip jeśli brak ATR/spot)

Mapa weighted_score → SetupGrade:
    >= 1.0R   → A
    >= 0.5R   → B
    >= 0.3R   → C  (watch only)
    <  0.3R   → NONE → STAND_DOWN

Master nie haltuje przy CHAOS/UNKNOWN regime — placeholdery regime/mtf
są rejestrowane jako warning, ale weighted_decision jest źródłem prawdy.
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
    setup_grader,
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
    """Map weighted_score (in R-multiples) to SetupGrade."""
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

    # Inicjalizacja komponentów
    fs = FeatureStore(cfg)
    journal = JournalDb(cfg.journal_db)
    psych = PsychMonitor(cfg, journal)
    tail = TailMonitor(cfg)

    # ─── 1. Pre-checks (HARD GATE) ───
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

    # ─── 2. Weighted Decision (PRIMARY) ───
    wd = decision_mod.compute_weighted_decision(fs)

    # Zapisz do extras dla UI/audit
    verdict.extras["weighted_score"] = wd.weighted_score
    verdict.extras["weighted_direction"] = wd.direction
    verdict.extras["weighted_long"] = wd.weighted_long
    verdict.extras["weighted_short"] = wd.weighted_short
    verdict.extras["fade_count"] = wd.fade_count
    verdict.extras["sources_active"] = wd.n_sources_with_edge
    verdict.extras["contributing"] = wd.contributing

    # Set expected_r i sample_size z weighted decision
    verdict.expected_r = wd.weighted_score if wd.direction != "FLAT" else 0.0
    verdict.sample_size = wd.n_sources_with_edge

    # Set setup grade
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

    # Set side z weighted direction
    side = Side.LONG if wd.direction == "LONG" else Side.SHORT
    verdict.plan.side = side

    # ─── 3. Regime (informacyjnie, nie haltuje) ───
    try:
        regime_result = regime_mod.classify(cfg, fs)
        verdict.regime = regime_result.regime
        verdict.audit.append(AuditStep(
            "regime classified",
            regime_result.regime.value not in ("CHAOS", "UNKNOWN"),
            f"{regime_result.regime.value} (adx={regime_result.adx:.1f})",
        ))
    except Exception as e:
        log.warning("regime.classify failed: %s", e)
        verdict.audit.append(AuditStep(
            "regime classified", False,
            f"skipped: {type(e).__name__}: {e}",
        ))

    # ─── 4. MTF align (informacyjnie, nie haltuje) ───
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
            f"skipped: {type(e).__name__}: {e}",
        ))

    # WATCH: setup się kwalifikuje, ale brak konkretnego entry/SL bez ATR
    if verdict.setup_grade in (SetupGrade.A, SetupGrade.B):
        verdict.state = VerdictState.WATCH

    # ─── 5/6. Sizing + Plan (wymaga ATR/spot — guarded) ───
    # TODO commit #5: integracja z EA price feed (spot + ATR z TF1m/5m)
    # Dla READY potrzebujemy entry/SL/TP — bez tego zostajemy w WATCH.

    return verdict
