"""Master Terminal — konfiguracja.

Jedno źródło prawdy dla ścieżek, progów i parametrów.
Nie hardkoduj nigdzie indziej.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# ─────────── Ścieżki ───────────

EA_TERMINAL_ROOT = Path(os.environ.get(
    "EA_TERMINAL_ROOT",
    r"C:\Users\User\Desktop\terminal",
))

EA_SIGNALS_DB = EA_TERMINAL_ROOT / "signals_unified.db"
EA_SIGNAL_LOG_CSV = EA_TERMINAL_ROOT / "logs" / "signal_log.csv"
EA_SUPER_LEARNER_DB = EA_TERMINAL_ROOT / "super_learner.db"
EA_ML_PREDICTOR_DB = EA_TERMINAL_ROOT / "ml_predictor.db"
EA_ADAPTIVE_DB = EA_TERMINAL_ROOT / "adaptive.db"

MASTER_ROOT = Path(__file__).resolve().parent.parent
MASTER_DATA = MASTER_ROOT / "data"
MASTER_JOURNAL_DB = MASTER_DATA / "journal.db"
MASTER_CACHE = MASTER_DATA / "cache"
MASTER_LOGS = MASTER_ROOT / "logs"


# ─────────── Instrument ───────────

INSTRUMENT = "6EM26"
TIMEZONE_OFFSET_HOURS = 2  # jak w EA
MAGNET_RANGE = 0.020       # jak w EA


# ─────────── Risk parameters (Tharp) ───────────

@dataclass
class RiskConfig:
    """Tharp's R-multiples i caps sesyjne."""

    # account
    account_size_eur: float = 10_000.0  # placeholder, podmień

    # ryzyko per trade
    risk_pct_grade_a: float = 0.010   # 1% dla A-setup
    risk_pct_grade_b: float = 0.005   # 0.5% dla B-setup
    risk_pct_grade_c: float = 0.0     # C nie tradujemy

    # caps sesyjne (Douglas, Elder)
    max_daily_loss_r: float = 3.0           # po -3R stop sesji
    max_consecutive_losses: int = 3         # po 3 stratach z rzędu pauza
    max_trades_per_session: int = 10        # twardy cap (przeciw revenge tradingowi)

    # SL
    sl_atr_multiplier: float = 1.5          # min SL = 1.5×ATR
    min_rr_ratio: float = 1.5               # min reward/risk = 1.5


# ─────────── Regime classifier ───────────

@dataclass
class RegimeConfig:
    """Clenow + Komar — progi klasyfikacji reżimu."""

    adx_trend_threshold: float = 25.0
    adx_range_threshold: float = 18.0
    ema_fast: int = 20
    ema_slow: int = 50
    ema_filter: int = 200       # Clenow: nad MA200 = bull regime
    chaos_atr_pct_threshold: float = 0.005  # ATR > 0.5% mid → chaos


# ─────────── MTF alignment ───────────

@dataclass
class MtfConfig:
    """Elder — multi-timeframe alignment.

    9 TF z EA: TF5, TF10, TF15, TF30, TF60, TF120, TF240, TF480, TF1440.
    Wyższe TF dostają większą wagę (definiują kierunek).
    """

    timeframes: list[str] = field(default_factory=lambda: [
        "TF5", "TF10", "TF15", "TF30", "TF60",
        "TF120", "TF240", "TF480", "TF1440",
    ])
    weights: dict[str, float] = field(default_factory=lambda: {
        "TF5": 0.5, "TF10": 0.7, "TF15": 0.8, "TF30": 1.0, "TF60": 1.2,
        "TF120": 1.4, "TF240": 1.6, "TF480": 1.8, "TF1440": 2.0,
    })
    strong_align_threshold: float = 7.0    # weighted score >= 7 → strong
    no_trade_threshold: float = 4.0        # < 4 → no trade


# ─────────── Setup grader ───────────

@dataclass
class GraderConfig:
    """Komar + Murphy — A/B/C grading."""

    a_grade_min_factors: int = 5    # 5/5: regime, MTF≥7, magnet, flow, macro
    b_grade_min_factors: int = 3    # 3/5
    magnet_proximity_atr: float = 1.5


# ─────────── Edge lookup ───────────

@dataclass
class EdgeConfig:
    """Tharp — minimum expected R per template."""

    min_e_for_a: float = 0.4        # A-setup wymaga E ≥ 0.4R
    min_e_for_b: float = 0.2        # B-setup wymaga E ≥ 0.2R
    min_sample_size: int = 30       # mniej niż 30 trade'ów → tryb eksploracji (½ size)


# ─────────── Tail risk / blackout ───────────

@dataclass
class TailConfig:
    """Taleb + Zaremba — eventy i blackout windows."""

    blackout_minutes_before_event: int = 30
    blackout_minutes_after_event: int = 15
    high_impact_events: tuple[str, ...] = (
        "FOMC", "ECB", "NFP", "CPI", "PCE", "GDP",
    )


# ─────────── Cała konfiguracja ───────────

@dataclass
class MasterConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    mtf: MtfConfig = field(default_factory=MtfConfig)
    grader: GraderConfig = field(default_factory=GraderConfig)
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    tail: TailConfig = field(default_factory=TailConfig)

    instrument: str = INSTRUMENT
    tz_offset_hours: int = TIMEZONE_OFFSET_HOURS

    # ścieżki
    ea_signals_db: Path = EA_SIGNALS_DB
    ea_signal_log_csv: Path = EA_SIGNAL_LOG_CSV
    journal_db: Path = MASTER_JOURNAL_DB

    # UI
    ui_port: int = 8052
    ui_refresh_seconds: int = 60   # Master odświeża się raz na minutę


CONFIG = MasterConfig()


def ensure_dirs() -> None:
    """Tworzy katalogi danych Mastera (idempotentne)."""
    for p in (MASTER_DATA, MASTER_CACHE, MASTER_LOGS):
        p.mkdir(parents=True, exist_ok=True)
