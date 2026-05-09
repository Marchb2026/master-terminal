"""EA Bridge — pomocnicze read-only adaptery dla różnych plików EA.

`feature_store.py` obsługuje główny kanał (signals_unified.db).
Tu jest reszta: signal_log.csv, ml_predictor.db, super_learner.db,
opcjonalnie inne stale.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from master.config import MasterConfig

log = logging.getLogger(__name__)


@dataclass
class SignalLogRow:
    """Wiersz z logs/signal_log.csv — schemat z audytu EA."""

    ts: str
    tf: int
    signal: str               # LONG / SHORT
    score: float
    strength: float
    ofi: float
    cd50: float
    dxy_bias: str
    vix: float
    price_at_signal: float
    price_1h_later: float
    price_4h_later: float
    outcome_1h: str           # WIN / LOSS / FLAT
    outcome_4h: str
    r_pips_1h: float
    r_pips_4h: float
    correct_1h: int
    supporting: str           # comma-separated factors
    opposing: str
    agreement: int            # %


def read_signal_log(path: Path | None = None) -> pd.DataFrame:
    """Czyta signal_log.csv z EA i zwraca pełny DataFrame.

    Domyślna ścieżka z config.MasterConfig.ea_signal_log_csv.
    """
    cfg = MasterConfig()
    p = path or cfg.ea_signal_log_csv
    if not p.exists():
        log.warning("signal_log.csv not found at %s", p)
        return pd.DataFrame()

    df = pd.read_csv(p)
    log.info("read_signal_log: %d rows from %s", len(df), p.name)
    return df


def query_super_learner(query: str, params: tuple = ()) -> pd.DataFrame:
    """Read-only query do super_learner.db (5.1 MB, content TBI po introspekcji)."""
    cfg = MasterConfig()
    p = cfg.ea_signals_db.parent / "super_learner.db"
    if not p.exists():
        return pd.DataFrame()

    uri = f"file:{p}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        return pd.read_sql_query(query, conn, params=params)


def list_ea_databases() -> dict[str, Path]:
    """Zwraca dostępne pliki .db w katalogu EA — przydatne do introspekcji."""
    cfg = MasterConfig()
    root = cfg.ea_signals_db.parent
    return {
        "signals_unified": root / "signals_unified.db",
        "super_learner": root / "super_learner.db",
        "ml_predictor": root / "ml_predictor.db",
        "adaptive": root / "adaptive.db",
        "ice_tracker": root / "ice_tracker.db",
        "ml_bridge": root / "ml_bridge.db",
    }
