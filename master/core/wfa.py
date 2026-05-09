"""Walk-forward analysis — Pardo (*Evaluation and Optimization of Trading Strategies*).

Cel: comiesięczna sanity-check edge'ów per template setupu.
Czy A-setupy wciąż mają E > 0.5R w ostatnim oknie out-of-sample?
Jeśli nie — alert, że reżim się zmienił, system przestał działać.

Bez WFA każdy backtest jest curve-fittingiem. Pardo: "the only test that
matters is the one performed on data the system never saw during design".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from master.journal.db import JournalDb
from master.journal.stats import compute_expectancy

log = logging.getLogger(__name__)


@dataclass
class WfaWindow:
    template_id: str
    window_start: datetime
    window_end: datetime
    sample_size: int
    expectancy_r: float
    win_rate: float
    profit_factor: float
    decay_alert: bool = False


@dataclass
class WfaReport:
    windows: list[WfaWindow]
    alerts: list[str]


def run_wfa(
    journal: JournalDb,
    template_ids: list[str],
    window_days: int = 30,
    n_windows: int = 6,
    alert_threshold_r: float = 0.0,
) -> WfaReport:
    """Liczy expectancy w n_windows kolejnych okien po window_days.

    Alert gdy najnowsze okno ma E poniżej alert_threshold_r LUB gdy
    monotoniczny spadek E przez >= 3 ostatnie okna (edge decay).
    """
    now = datetime.now()
    windows: list[WfaWindow] = []
    alerts: list[str] = []

    for template in template_ids:
        per_template_windows: list[WfaWindow] = []

        for i in range(n_windows):
            end = now - timedelta(days=i * window_days)
            start = end - timedelta(days=window_days)

            trades = journal.get_trades_by_template(
                template,
                start=start,
                end=end,
            )
            if not trades:
                continue

            stats = compute_expectancy(trades)
            w = WfaWindow(
                template_id=template,
                window_start=start,
                window_end=end,
                sample_size=len(trades),
                expectancy_r=stats.expectancy_r,
                win_rate=stats.win_rate,
                profit_factor=stats.profit_factor,
            )
            per_template_windows.append(w)
            windows.append(w)

        # Edge decay detection
        if per_template_windows:
            latest = per_template_windows[0]
            if latest.expectancy_r < alert_threshold_r:
                latest.decay_alert = True
                alerts.append(
                    f"{template}: latest E={latest.expectancy_r:+.2f}R "
                    f"below threshold {alert_threshold_r:+.2f}R"
                )

            if len(per_template_windows) >= 3:
                last3 = per_template_windows[:3]
                if all(last3[j].expectancy_r > last3[j + 1].expectancy_r for j in range(2)):
                    alerts.append(
                        f"{template}: monotonic E decay over last 3 windows"
                    )

    return WfaReport(windows=windows, alerts=alerts)
