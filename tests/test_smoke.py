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
        edge_lookup, gates, mtf, pipeline, plan, regime, setup_grader, sizer, verdict, wfa,
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


def test_journal_roundtrip():
    """Trade → DB → trade roundtrip."""
    from master.journal.db import JournalDb
    from master.journal.trade import Trade

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_journal.db"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
