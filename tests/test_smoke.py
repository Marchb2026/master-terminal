"""Smoke tests."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pytest


def test_imports():
    import master  # noqa
    from master import config  # noqa
    from master.core import (  # noqa
        edge_lookup, gates, mtf, pipeline, plan, regime, setup_grader, sizer, verdict, wfa,
    )
    fr
# === ZASTOSUJ AKTUALIZACJE ===
$proj = "$env:USERPROFILE\Desktop\master_terminal"
$desk = "$env:USERPROFILE\Desktop"

# 1. Sprawdź feature_store.py na Desktopie
$fs_src = "$desk\feature_store.py"
if (-not (Test-Path $fs_src)) { Write-Host "BRAK $fs_src" -ForegroundColor Red; return }
$size = (Get-Item $fs_src).Length
Write-Host "feature_store.py na Desktopie: $size bajtów" -ForegroundColor Yellow
if ($size -lt 15000) { Write-Host "ZA MAŁY - download niekompletny, kliknij download jeszcze raz" -ForegroundColor Red; return }

# 2. Kopiuj feature_store.py do projektu
Copy-Item $fs_src "$proj\master\data\feature_store.py" -Force
Write-Host "  feature_store.py wgrany ($size B)" -ForegroundColor Green

# 3. Napisz świeży test_smoke.py inline (Windows-safe wersja z tmp_path)
@'
"""Smoke tests."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pytest


def test_imports():
    import master  # noqa
    from master import config  # noqa
    from master.core import (  # noqa
        edge_lookup, gates, mtf, pipeline, plan, regime, setup_grader, sizer, verdict, wfa,
    )
    from master.data import calendar, cot, ea_bridge, feature_store  # noqa
    from master.journal import db, importer, stats, trade  # noqa
    from master.monitor import psych, tail  # noqa


def test_verdict_render():
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


def test_journal_roundtrip(tmp_path):
    """Uzywa tmp_path bo TemporaryDirectory ma issue na Windows z SQLite locks."""
    from master.journal.db import JournalDb
    from master.journal.trade import Trade

    db_path = tmp_path / "test_journal.db"
    journal = JournalDb(db_path)
    trade = Trade(
        trade_id="test_1", template_id="TEST_LONG_A",
        opened_at=datetime(2026, 5, 9, 10, 0),
        closed_at=datetime(2026, 5, 9, 11, 0),
        entry_price=1.1580, exit_price=1.1605, stop_loss=1.1565,
        side="LONG", contracts=1.0, risk_eur=100.0, pnl_eur=180.0,
        r_multiple=1.8, setup_grade="A",
    )
    journal.insert(trade)
    retrieved = journal.get_trades_by_template("TEST_LONG_A")
    assert len(retrieved) == 1
    assert retrieved[0].r_multiple == 1.8


def test_expectancy():
    from master.journal.stats import compute_expectancy
    from master.journal.trade import Trade
    trades = [
        Trade(r_multiple=2.0), Trade(r_multiple=2.0),
        Trade(r_multiple=-1.0), Trade(r_multiple=-1.0), Trade(r_multiple=-1.0),
    ]
    stats = compute_expectancy(trades)
    assert stats.n == 5
    assert abs(stats.win_rate - 0.4) < 1e-9
    assert abs(stats.expectancy_r - 0.2) < 1e-9


def test_config_loads():
    from master.config import CONFIG
    assert CONFIG.instrument == "6EM26"
    assert CONFIG.risk.risk_pct_grade_a == 0.010
    assert CONFIG.risk.max_daily_loss_r == 3.0


def test_pipeline_runs_without_data():
    import os
    os.environ["EA_TERMINAL_ROOT"] = "/tmp/nonexistent_ea_terminal"


def test_feature_store_dataclasses():
    from master.data.feature_store import (
        CompositeSignal, FreshnessResult, IceEvent, IceStat,
        ModuleSignal, OptionsState, SignalRow, SourceStats,
    )
    cs = CompositeSignal(direction="BULL", score=0.5, conviction="MEDIUM",
                         hot_signals_count=2, n_active=8, n_total=12)
    assert cs.direction == "BULL"
    ss = SourceStats(source="vote_SCORE", n_resolved=100, win_rate=0.55,
                     avg_pips_correct=8.0, avg_pips_wrong=-6.0,
                     expectancy_pips=1.7, expectancy_r=0.17)
    assert ss.expectancy_r > 0
    ev = IceEvent(ts=1.0, event_type="ABSORPTION_BID", side="BID",
                  level_price=1.158, qty=200, spot_at_detect=1.157,
                  dist_pips=10.0, confidence=0.7)
    assert ev.event_type == "ABSORPTION_BID"


def test_feature_store_methods_exist():
    from master.data.feature_store import FeatureStore
    expected = [
        "read_composite", "read_module", "read_all_modules",
        "read_recent_signals", "read_distinct_sources",
        "get_source_expectancy", "get_top_sources", "get_signal_confluence",
        "read_ice_events", "get_ice_stats", "has_recent_liquidity_event",
        "read_options_state", "read_options_history",
        "read_snapshots", "get_top_features", "check_freshness",
    ]
    for m in expected:
        assert hasattr(FeatureStore, m), f"Missing method: {m}"
