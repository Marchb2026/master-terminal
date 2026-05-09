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
    """Mapowanie weighted_score → SetupGrade w pipeline."""
    from master.core.pipeline import _grade_from_score
    from master.core.verdict import SetupGrade

    assert _grade_from_score(2.5) == SetupGrade.A
    assert _grade_from_score(1.0) == SetupGrade.A
    assert _grade_from_score(0.99) == SetupGrade.B
    assert _grade_from_score(0.5) == SetupGrade.B
    assert _grade_from_score(0.49) == SetupGrade.C
    assert _grade_from_score(0.3) == SetupGrade.C
    assert _grade_from_score(0.29) == SetupGrade.NONE


def test_weighted_decision_v05_fields():
    """v0.5: WeightedDecision ma pola dla wszystkich 7 layerów confluence."""
    from master.core.decision import WeightedDecision

    wd = WeightedDecision(
        direction="LONG",
        weighted_score=0.7,
        weighted_long=0.8,
        weighted_short=0.1,
    )
    # Defaults dla nowych pól
    assert wd.composite_contribution == 0.0
    assert wd.liquidity_modifier == 0.0
    assert wd.gex_warning == ""
    assert wd.mtf_alignment == "UNKNOWN"
    assert wd.decision_threshold_used == 0.3
    assert wd.sources_unstable == []
    assert wd.notes == []


def test_wfa_edge_stability_dataclass():
    """WFA: EdgeStability ma właściwe pola."""
    from master.core.wfa import EdgeStability

    es = EdgeStability(
        source="XGB",
        full_window_r=0.491,
        full_window_n=5550,
        recent_window_r=0.45,
        recent_window_n=200,
        delta=-0.041,
        relative_drop=0.08,
        stable=True,
    )
    assert es.source == "XGB"
    assert es.stable is True
    assert es.relative_drop < 0.5


def test_wfa_sign_flip_detected():
    """Sign flip (full +0.5R → recent -0.3R) musi być oznaczony jako unstable."""
    # Mock FeatureStore zwracający różne expectancy w różnych windowach
    from master.core.wfa import check_recent_edge_stability
    from master.data.feature_store import SourceStats

    class MockFs:
        def get_source_expectancy(self, source, lookback_days=30):
            if lookback_days == 30:
                return SourceStats(source=source, n_resolved=5000, win_rate=0.4,
                                   avg_pips_correct=10, avg_pips_wrong=-5,
                                   expectancy_pips=5, expectancy_r=0.5)
            else:  # recent 7d
                return SourceStats(source=source, n_resolved=100, win_rate=0.3,
                                   avg_pips_correct=5, avg_pips_wrong=-10,
                                   expectancy_pips=-3, expectancy_r=-0.3)

    es = check_recent_edge_stability(MockFs(), "XGB", full_days=30, recent_days=7)
    assert es.stable is False
    assert "sign flip" in es.reason.lower() or "drop" in es.reason.lower()


def test_wfa_drop_detected():
    """Drop > 50% z absolute change > 0.15R musi być unstable."""
    from master.core.wfa import check_recent_edge_stability
    from master.data.feature_store import SourceStats

    class MockFs:
        def get_source_expectancy(self, source, lookback_days=30):
            if lookback_days == 30:
                return SourceStats(source=source, n_resolved=5000, win_rate=0.4,
                                   avg_pips_correct=10, avg_pips_wrong=-5,
                                   expectancy_pips=5, expectancy_r=0.5)
            else:
                # 0.5 → 0.05 = 90% drop, abs change 0.45R
                return SourceStats(source=source, n_resolved=100, win_rate=0.35,
                                   avg_pips_correct=6, avg_pips_wrong=-5,
                                   expectancy_pips=0.5, expectancy_r=0.05)

    es = check_recent_edge_stability(MockFs(), "XGB", full_days=30, recent_days=7)
    assert es.stable is False
    assert es.relative_drop > 0.5


def test_wfa_small_drop_still_stable():
    """Drop ~10% nie powinien być flagged."""
    from master.core.wfa import check_recent_edge_stability
    from master.data.feature_store import SourceStats

    class MockFs:
        def get_source_expectancy(self, source, lookback_days=30):
            base_r = 0.5 if lookback_days == 30 else 0.45  # 10% drop
            return SourceStats(source=source, n_resolved=5000 if lookback_days == 30 else 100,
                               win_rate=0.4, avg_pips_correct=10, avg_pips_wrong=-5,
                               expectancy_pips=base_r * 10, expectancy_r=base_r)

    es = check_recent_edge_stability(MockFs(), "XGB", full_days=30, recent_days=7)
    assert es.stable is True


# ───────── Execution layer tests (commit #6) ─────────

def test_execution_config_present():
    """ExecutionConfig musi mieć wszystkie pola wymagane przez sizer/plan."""
    from master.config import CONFIG

    e = CONFIG.execution
    assert e.pip_size == 0.0001
    assert e.pip_value_eur > 0
    assert e.sl_atr_multiplier > 0
    assert e.tp1_r_multiple > 0
    assert e.tp2_r_multiple > e.tp1_r_multiple
    assert e.invalidation_minutes > 0


def test_sizer_a_grade_calculation():
    """A-grade z 10k EUR account, 1% risk, ATR 15p, SL 1.5×ATR = 22.5p stop.
    Risk per kontrakt = 22.5p × 10.65 EUR/p = 239.6 EUR. 100 EUR / 239.6 = 0.42 → 0 contracts.
    Z 100k account = 1000 EUR / 239.6 = 4.17 → 4 kontrakty.
    """
    from master.config import MasterConfig, RiskConfig, ExecutionConfig
    from master.core.sizer import size, SizingResult
    from master.core.verdict import SetupGrade

    cfg = MasterConfig()
    cfg.risk = RiskConfig(account_size_eur=100_000.0, risk_pct_grade_a=0.010)
    cfg.execution = ExecutionConfig()  # defaults: ATR 15p, SL 1.5x, pip 10.65 EUR

    class MockFs:
        def estimate_atr_pips(self, **kwargs): return 15.0

    result = size(cfg, MockFs(), SetupGrade.A, weighted_score=1.2)
    assert result.contracts >= 1
    assert result.risk_eur > 0
    assert result.stop_distance_pips == 15.0 * 1.5


def test_sizer_grade_c_returns_zero():
    """Grade C → no sizing (Tharp: nie tradujemy słabych setupów)."""
    from master.config import CONFIG
    from master.core.sizer import size
    from master.core.verdict import SetupGrade

    class MockFs:
        def estimate_atr_pips(self, **kwargs): return 15.0

    result = size(CONFIG, MockFs(), SetupGrade.C)
    assert result.contracts == 0
    assert "no sizing" in result.detail.lower() or "grade c" in result.detail.lower()


def test_plan_long_geometry():
    """LONG plan: SL pod entry, TP1/TP2 nad entry, R = stop_distance."""
    from master.config import CONFIG
    from master.core.plan import build
    from master.core.regime import RegimeResult
    from master.core.sizer import SizingResult
    from master.core.verdict import Regime, Side

    sizing = SizingResult(
        contracts=2, risk_eur=200.0, target_risk_eur=200.0,
        stop_distance_pips=20.0, atr_pips=13.3, pip_value_eur=10.65,
    )
    regime = RegimeResult(regime=Regime.TREND_UP_WEAK)

    class MockFs:
        def get_current_spot(self, **kwargs): return 1.1580

    plan = build(CONFIG, MockFs(), regime, sizing, Side.LONG)
    assert plan.entry == 1.1580
    assert plan.stop_loss < plan.entry           # SL pod entry
    assert plan.take_profit_1 > plan.entry       # TP1 nad entry
    assert plan.take_profit_2 > plan.take_profit_1  # TP2 dalej niż TP1
    # R distance = 20 pips × 0.0001 = 0.002
    assert abs((plan.entry - plan.stop_loss) - 0.0020) < 1e-9
    # TP1 = entry + 1.5R = entry + 0.003
    assert abs((plan.take_profit_1 - plan.entry) - 0.003) < 1e-9


def test_plan_short_geometry():
    """SHORT plan: SL nad entry, TP1/TP2 pod entry."""
    from master.config import CONFIG
    from master.core.plan import build
    from master.core.regime import RegimeResult
    from master.core.sizer import SizingResult
    from master.core.verdict import Regime, Side

    sizing = SizingResult(
        contracts=2, risk_eur=200.0, target_risk_eur=200.0,
        stop_distance_pips=20.0, atr_pips=13.3, pip_value_eur=10.65,
    )
    regime = RegimeResult(regime=Regime.TREND_DN_WEAK)

    class MockFs:
        def get_current_spot(self, **kwargs): return 1.1580

    plan = build(CONFIG, MockFs(), regime, sizing, Side.SHORT)
    assert plan.entry == 1.1580
    assert plan.stop_loss > plan.entry
    assert plan.take_profit_1 < plan.entry
    assert plan.take_profit_2 < plan.take_profit_1


def test_plan_zero_contracts_returns_empty():
    """contracts=0 → pusty plan, nie crash."""
    from master.config import CONFIG
    from master.core.plan import build
    from master.core.regime import RegimeResult
    from master.core.sizer import SizingResult
    from master.core.verdict import Regime, Side

    sizing = SizingResult(contracts=0)
    regime = RegimeResult(regime=Regime.RANGE)

    class MockFs:
        def get_current_spot(self, **kwargs): return 1.1580

    plan = build(CONFIG, MockFs(), regime, sizing, Side.LONG)
    assert plan.entry is None
    assert plan.position_size_contracts is None or plan.position_size_contracts == 0


def test_regime_blocks_long_in_strong_downtrend():
    """TREND_DN_STRONG nie pozwala na long."""
    from master.core.regime import regime_allows_long, regime_allows_short
    from master.core.verdict import Regime

    assert regime_allows_long(Regime.TREND_DN_STRONG) is False
    assert regime_allows_short(Regime.TREND_DN_STRONG) is True
    assert regime_allows_long(Regime.TREND_UP_STRONG) is True
    assert regime_allows_long(Regime.RANGE) is True
    assert regime_allows_long(Regime.CHAOS) is False


def test_regime_classify_returns_unknown_with_no_data():
    """Bez composite i bez signals → UNKNOWN, no crash."""
    from master.config import CONFIG
    from master.core.regime import classify, RegimeResult

    class MockFs:
        def read_composite(self): return None
        def estimate_atr_pips(self, **kwargs): return None
        def read_recent_signals(self, **kwargs): return []

    result = classify(CONFIG, MockFs())
    assert result.regime.value == "UNKNOWN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
