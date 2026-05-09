"""Feature Store — adapter do danych EA Terminal.

Czyta z `signals_unified.db` (główny hub EA, 11.5 MB SQLite na dzień
audytu). Master nie pisze do tego pliku — tylko select.

Klasa robi lazy introspection schema'y przy pierwszym dostępie i loguje
co znalazła, żebyśmy mieli ground truth schemy przed pełną implementacją
funkcji domain-specific (get_bars, get_atr, get_compute_sig, ...).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from master.config import MasterConfig

log = logging.getLogger(__name__)


@dataclass
class FreshnessResult:
    is_fresh: bool
    reason: str = ""
    latest_ts: datetime | None = None


class FeatureStore:
    """Read-only adapter do EA's signals_unified.db i innych źródeł.

    Lazy introspection: przy pierwszym dostępie loguje listę tabel
    i kolumn, żeby kontrakt danych był jawny.
    """

    def __init__(self, cfg: MasterConfig):
        self.cfg = cfg
        self._db_path: Path = cfg.ea_signals_db
        self._schema_introspected = False
        self._tables: dict[str, list[str]] = {}

    # ─────────── Connection ───────────

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"EA signals_unified.db not found at {self._db_path}. "
                f"Set EA_TERMINAL_ROOT env var or update master/config.py."
            )
        # read-only via URI, w razie czego EA może mieć otwarte uchwyty
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=2.0)

    def introspect(self) -> dict[str, list[str]]:
        """Zwraca dict {table_name: [columns]}. Loguje przy pierwszym wywołaniu."""
        if self._schema_introspected:
            return self._tables

        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                table_names = [row[0] for row in cur.fetchall()]
                for tname in table_names:
                    cur.execute(f"PRAGMA table_info({tname})")
                    cols = [row[1] for row in cur.fetchall()]
                    self._tables[tname] = cols
            self._schema_introspected = True
            log.info("FeatureStore: introspected %d tables in %s",
                     len(self._tables), self._db_path.name)
            for t, cols in self._tables.items():
                log.debug("  %s: %s", t, ", ".join(cols))
        except Exception as e:
            log.error("FeatureStore introspection failed: %s", e)
            self._schema_introspected = True
            self._tables = {}
        return self._tables

    # ─────────── Public API (high-level) ───────────

    def check_freshness(self, max_age_minutes: int = 5) -> FreshnessResult:
        """Czy najnowszy timestamp w głównej tabeli sygnałów jest świeży."""
        # TODO: implement po introspekcji — wybierz najnowszy MAX(ts)
        # z najbardziej aktywnej tabeli (prawdopodobnie 'signals' lub
        # podobna). Na razie zakładamy fresh, żeby pipeline szedł.
        try:
            self.introspect()
        except Exception as e:
            return FreshnessResult(False, reason=f"introspection failed: {e}")

        if not self._tables:
            return FreshnessResult(False, reason="no tables found in DB")

        # placeholder — TBI po znajomości realnych tabel
        return FreshnessResult(True, reason="placeholder OK", latest_ts=datetime.now())

    def get_bars(self, timeframe: str, n: int = 200) -> pd.DataFrame | None:
        """Pobiera ostatnie n barów dla danego TF.

        TODO: implement po introspekcji — w EA bary mogą siedzieć w
        tabelach typu 'bars_TF5', 'bars_TF60' itp., albo w jednej tabeli
        z kolumną 'tf'.
        """
        log.debug("get_bars(%s, n=%d) — TBI", timeframe, n)
        return None

    def get_atr(self, timeframe: str = "TF15", period: int = 14) -> float | None:
        """ATR(period) na danym TF. Liczone z bars albo z gotowej kolumny."""
        df = self.get_bars(timeframe, n=period + 50)
        if df is None or df.empty:
            return None
        # TODO: True Range + EMA
        return None

    def get_latest_signal(self, timeframe: str | None = None) -> dict | None:
        """Najnowszy sygnał z EA dla danego TF (lub wszystkich)."""
        # TODO: implement po introspekcji
        return None

    def get_magnets(self) -> list[float]:
        """Aktualne magnety (kluczowe poziomy) z EA."""
        # TODO: implement — magnety są w EA z RANGE=0.020
        return []

    def is_near_magnet(self, atr_multiplier: float = 1.5) -> bool:
        """Czy aktualna cena jest w odległości ≤ multi×ATR od magnetu."""
        magnets = self.get_magnets()
        atr = self.get_atr()
        if not magnets or atr is None:
            return False
        # TODO: po dostępie do live price z self.get_latest_price()
        return False

    def get_compute_sig(self) -> dict | None:
        """Najnowszy compute_sig z EA (FRED + GEX bias)."""
        # TODO
        return None

    def flow_aggression_side(self) -> str | None:
        """Czy footprint pokazuje przewagę bid czy ask aggression."""
        # TODO: czyta z tabeli footprint w signals_unified.db
        return None

    def bankradar_status(self) -> dict | None:
        """Aktualny stan bankradar (świeżość ważna — znany problem stale data)."""
        # TODO
        return None
