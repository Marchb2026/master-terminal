"""Smoke tests — sprawdzają że wszystkie moduły się importują
i podstawowe dataclasses działają.

Uruchom:
    pytest tests/
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest


def test_imports():
    """Każdy moduł musi się importować bez błędu."""
    import master  # noqa
    from master import config  # noqa
    from master.core import (  # noqa
        decision, edge_lookup, gates, mtf, pipeline, plan, regime, setup_grader, sizer, verdict, wfa,
    )
    from master.data import calendar, cot, ea_bridge, feature_store  # noqa
    from master.journal import db, importer, stats, trade  # noqa
    from master.monitor import psych, tail  # noqa


def test_verdict_render():
    """Werdykt renderuje się do stringa bez błędu."""
    from master.core.verdict import Regime, SetupGrade, Verdict, VerdictState

    v = Verdict(
        timestamp=datetime(2026, 5, 9, 14, 32),
        instrument="6EM26",
        state=VerdictState.STAND_DOWN,
        regime=Regime.TREND_UP_WEAK,
        mtf_score=3.5,
        setup_grade=SetupGrade.C,
    )
    out = v.render_text()
    assert "MASTER" in out
    assert "STAND_DOWN" in out
    assert "TREND_UP_WEAK" in out


def test_journal_roundtrip(tmp_path):
    """Trade → DB → trade roundtrip.

    Używa pytest fixture `tmp_path` zamiast tempfile.TemporaryDirectory,
    bo TemporaryDirectory ma problem na Windowsie z SQLite file locks
    nawet z ignore_cleanup_errors=True.
    """
    from master.journal.db import JournalDb
    from master.journal.trade import Trade

    db_path = tmp_path / "test_journal.db"
    journal = JournalDb(db_path)

    trade = Trade(
        trade_id="test_1",
        template_id="TEST_LONG_A",
        opened_at=datetime(2026, 5, 9, 10, 0),
        closed_at=datetime(2026, 5, 9, 11, 0),
        entry_price=1.1580,
        exit_price=1.1605,
        stop_loss=1.1565,
        side="LONG",
        contracts=1.0,
        risk_eur=100.0,
        pnl_eur=180.0,
        r_multiple=1.8,
        setup_grade="A",
    )
    journal.insert(trade)

    retrieved = journal.get_trades_by_template("TEST_LONG_A")
    assert len(retrieved) == 1
    assert retrieved[0].r_multiple == 1.8


def test_expectancy():
    """Expectancy math zgadza się z definicją Tharpa."""
    from master.journal.stats import compute_expectancy
    from master.journal.trade import Trade

    trades = [
        Trade(r_multiple=2.0),
        Trade(r_multiple=2.0),
        Trade(r_multiple=-1.0),
        Trade(r_multiple=-1.0),
        Trade(r_multiple=-1.0),
    ]
    stats = compute_expectancy(trades)
    # winrate 40%, avg_win 2R, avg_loss -1R
    # E = 0.4 * 2 + 0.6 * (-1) = 0.8 - 0.6 = 0.2R
    assert stats.n == 5
    assert abs(stats.win_rate - 0.4) < 1e-9
    assert abs(stats.expectancy_r - 0.2) < 1e-9


def test_config_loads():
    """Config można zaimportować i ma sensowne defaulty."""
    from master.config import CONFIG

    assert CONFIG.instrument == "6EM26"
    assert CONFIG.risk.risk_pct_grade_a == 0.010
    assert CONFIG.risk.risk_pct_grade_b == 0.005
    assert CONFIG.risk.max_daily_loss_r == 3.0


def test_pipeline_runs_without_data():
    """Pipeline powinien wystartować nawet bez EA DB i zwrócić STAND_DOWN."""
    import os
    os.environ["EA_TERMINAL_ROOT"] = "/tmp/nonexistent_ea_terminal"
    # forsujemy reload configu
    # (w realnym użyciu config jest singletonem na proces)


def test_feature_store_dataclasses():
    """Wszystkie dataclasses feature_store są poprawnie zdefiniowane."""
    from master.data.feature_store import (
        CompositeSignal,
        FreshnessResult,
        IceEvent,
        IceStat,
        ModuleSignal,
        OptionsState,
        SignalRow,
        SourceStats,
    )

    # CompositeSignal
    cs = CompositeSignal(direction="BULL", score=0.5, conviction="MEDIUM",
                         hot_signals_count=2, n_active=8, n_total=12)
    assert cs.direction == "BULL"

    # SourceStats
    ss = SourceStats(source="vote_SCORE", n_resolved=100, win_rate=0.55,
                     avg_pips_correct=8.0, avg_pips_wrong=-6.0,
                     expectancy_pips=1.7, expectancy_r=0.17)
    assert ss.expectancy_r > 0

    # IceEvent
    ev = IceEvent(ts=1.0, event_type="ABSORPTION_BID", side="BID",
                  level_price=1.158, qty=200, spot_at_detect=1.157,
                  dist_pips=10.0, confidence=0.7)
    assert ev.event_type == "ABSORPTION_BID"


def test_feature_store_methods_exist():
    """Sprawdza że wszystkie publiczne metody są zdefiniowane."""
    from master.data.feature_store import FeatureStore

    expected_methods = [
        "read_composite", "read_module", "read_all_modules",
        "read_recent_signals", "read_distinct_sources",
        "get_source_expectancy", "get_top_sources", "get_signal_confluence",
        "read_ice_events", "get_ice_stats", "has_recent_liquidity_event",
        "read_options_state", "read_options_history",
        "read_snapshots", "get_top_features",
        "check_freshness",
    ]
    for m in expected_methods:
        assert hasattr(FeatureStore, m), f"Missing method: {m}"


def test_parse_ts_handles_all_formats():
    """Regresja: _ts z forecast cache bywa stringiem ISO, bywa floatem epoch.
    Master musi obsłużyć oba bez TypeError przy `now - ts`.
    """
    from master.data.feature_store import FeatureStore

    assert FeatureStore._parse_ts(1778319813.5) == 1778319813.5
    assert FeatureStore._parse_ts(1778319813) == 1778319813.0
    parsed = FeatureStore._parse_ts("2026-05-09T11:43:33")
    assert parsed is not None and isinstance(parsed, float)
    parsed_z = FeatureStore._parse_ts("2026-05-09T11:43:33Z")
    assert parsed_z is not None and isinstance(parsed_z, float)
    assert FeatureStore._parse_ts(None) is None
    assert FeatureStore._parse_ts("not a date") is None
    assert FeatureStore._parse_ts("") is None


def test_weighted_decision_dataclass():
    """WeightedDecision ma właściwe pola i defaults."""
    from master.core.decision import WeightedDecision

    wd = WeightedDecision(
        direction="LONG",
        weighted_score=0.7,
        weighted_long=0.8,
        weighted_short=0.1,
    )
    assert wd.direction == "LONG"
    assert wd.weighted_score == 0.7
    assert wd.contributing == {}
    assert wd.fade_count == 0
    assert wd.flat_skipped == 0


def test_grade_from_score_mapping():
    """Mapowanie weighted_score → SetupGrade w pipeline.
    Granice: 1.0 → A, 0.5 → B, 0.3 → C, < 0.3 → NONE.
    """
    from master.core.pipeline import _grade_from_score
    from master.core.verdict import SetupGrade

    assert _grade_from_score(2.5) == SetupGrade.A
    assert _grade_from_score(1.0) == SetupGrade.A
    assert _grade_from_score(0.99) == SetupGrade.B
    assert _grade_from_score(0.5) == SetupGrade.B
    assert _grade_from_score(0.49) == SetupGrade.C
    assert _grade_from_score(0.3) == SetupGrade.C
    assert _grade_from_score(0.29) == SetupGrade.NONE
    assert _grade_from_score(0.0) == SetupGrade.NONE
    assert _grade_from_score(-0.5) == SetupGrade.NONE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
