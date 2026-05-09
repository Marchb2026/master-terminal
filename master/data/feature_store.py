"""Feature Store — adapter do CAŁEGO ekosystemu EA Terminal.

Read-only. Master nigdy nie pisze do plików EA.

Źródła (na podstawie inspekcji 2026-05-09):
- signals_unified.db.signals  (74,556 wierszy: per-source sygnały + resolved outcomes)
- super_learner.db.snapshots  (1,281: feature snapshots + 15/60/240 outcomes)
- super_learner.db.feature_importance  (30: corr/hit_rate per feature per horizon)
- adaptive.db.cat_votes  (7,913: per-category votes + outcomes)
- ice_tracker.db.ice_events  (172: ICEBERG/ABSORPTION/BIG_ORDER + outcomes)
- ice_tracker.db.ice_stats  (hit_rate per kategoria)
- forecast/cache/composite.json  (meta-aggregator)
- forecast/cache/m{1..12}.json  (per-module composite score + direction)
- terminal/data/ibkr_options_cache.json  (gex, flip_level, top_strikes)
- terminal/data/options_history.json  (historical options state)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from master.config import MasterConfig

log = logging.getLogger(__name__)


# ─────────── Dataclasses ───────────

@dataclass
class FreshnessResult:
    is_fresh: bool
    reason: str = ""
    latest_ts: datetime | None = None
    per_source: dict[str, float] = field(default_factory=dict)  # source -> age_seconds


@dataclass
class SignalRow:
    """Wiersz z signals_unified.db.signals."""
    id: int
    ts: float
    ts_str: str
    source: str
    direction: str        # LONG / SHORT / FLAT
    strength: float
    confidence: float
    spot: float
    horizon_min: int
    resolved: bool
    pips: float | None = None
    correct: bool | None = None


@dataclass
class CompositeSignal:
    """forecast/cache/composite.json."""
    direction: str            # BULL / BEAR / NEUT
    score: float
    conviction: str           # LOW / MEDIUM / HIGH
    hot_signals_count: int
    n_active: int
    n_total: int
    votes: dict[str, int] = field(default_factory=dict)
    ts: float | None = None


@dataclass
class ModuleSignal:
    """forecast/cache/m{N}.json — pojedynczy moduł."""
    module: str
    ok: bool
    direction: str            # BULL / BEAR / NEUT
    score: float
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IceEvent:
    """ice_tracker.db.ice_events — liquidity events."""
    ts: float
    event_type: str           # BIG_ORDER / ICEBERG / ABSORPTION_ASK / ABSORPTION_BID
    side: str                 # BID / ASK
    level_price: float
    qty: int
    spot_at_detect: float
    dist_pips: float
    confidence: float
    outcome_5: str | None = None
    outcome_15: str | None = None
    outcome_60: str | None = None


@dataclass
class IceStat:
    """ice_tracker.db.ice_stats."""
    key: str
    hit_rate: float
    n_samples: int
    avg_pnl: float
    sharpe: float


@dataclass
class OptionsState:
    """ibkr_options_cache.json."""
    spot: float
    gex: float
    gex_direction: str        # POSITIVE / NEGATIVE / NEUTRAL
    flip_level: float | None
    vanna: float | None
    charm: float | None
    top_strikes: list[Any] = field(default_factory=list)
    n_contracts: int = 0
    connected: bool = False
    ts: float | None = None


@dataclass
class SourceStats:
    """Edge per signal source (z signals_unified.db.signals)."""
    source: str
    n_resolved: int
    win_rate: float
    avg_pips_correct: float
    avg_pips_wrong: float
    expectancy_pips: float
    expectancy_r: float       # E w R-multiples (1R = ASSUMED_R_PIPS pips)


# Konwersja pips → R-multiples (placeholder: 10 pips = 1R)
ASSUMED_R_PIPS = 10.0


# ─────────── FeatureStore ───────────

class FeatureStore:
    """Read-only adapter do całego ekosystemu EA Terminal."""

    def __init__(self, cfg: MasterConfig):
        self.cfg = cfg
        self._ea_root: Path = cfg.ea_signals_db.parent
        self._desktop = self._ea_root.parent
        self._forecast_cache = self._desktop / "forecast" / "forecast_modules" / "cache"

    # ─────────── Connection helpers ───────────

    def _connect_ro(self, db_path: Path) -> sqlite3.Connection:
        if not db_path.exists():
            raise FileNotFoundError(f"DB not found: {db_path}")
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_json(self, path: Path) -> dict | list | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("JSON read failed %s: %s", path.name, e)
            return None

    @staticmethod
    def _parse_ts(val) -> float | None:
        """Parse timestamp z dowolnego formatu: float epoch, int epoch, ISO string.

        EA czasem zapisuje `_ts` jako string '2026-05-09T11:43:33', czasem jako
        epoch. Master jest defensywny.
        """
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                return None
        return None

    # ─────────── LIVE: composite + modules (forecast cache) ───────────

    def read_composite(self) -> CompositeSignal | None:
        """forecast/cache/composite.json — meta-aggregator wszystkich m1-m12."""
        data = self._read_json(self._forecast_cache / "composite.json")
        if not isinstance(data, dict):
            return None
        return CompositeSignal(
            direction=str(data.get("composite_direction", "NEUT")),
            score=float(data.get("composite_score", 0.0)),
            conviction=str(data.get("conviction", "LOW")),
            hot_signals_count=int(data.get("hot_signals_count", 0)),
            n_active=int(data.get("n_active", 0)),
            n_total=int(data.get("n_total", 0)),
            votes=dict(data.get("votes", {})),
            ts=self._parse_ts(data.get("_ts")),
        )

    def read_module(self, module_id: str) -> ModuleSignal | None:
        """Pojedynczy moduł forecast: m1_etf_flow ... m12_microstructure."""
        data = self._read_json(self._forecast_cache / f"{module_id}.json")
        if not isinstance(data, dict):
            return None
        return ModuleSignal(
            module=str(data.get("module", module_id)),
            ok=bool(data.get("ok", False)),
            direction=str(data.get("composite_direction", "NEUT")),
            score=float(data.get("composite_score", 0.0)),
            error=data.get("error"),
            raw=data,
        )

    def read_all_modules(self) -> dict[str, ModuleSignal]:
        modules = [
            "m1_etf_flow", "m2_kalman_flow", "m3_fix_window", "m4_hawkes",
            "m5_vecm_residual", "m6_rough_vol", "m7_mtf_trend",
            "m9_gex", "m10_orderflow", "m11_dom_walls", "m12_microstructure",
        ]
        result: dict[str, ModuleSignal] = {}
        for m in modules:
            sig = self.read_module(m)
            if sig:
                result[m] = sig
        return result

    # ─────────── LIVE: signals_unified.db ───────────

    def read_recent_signals(
        self,
        since_minutes: int = 30,
        source: str | None = None,
        only_unresolved: bool = False,
        limit: int = 2000,
    ) -> list[SignalRow]:
        cutoff_ts = time.time() - since_minutes * 60
        sql = "SELECT * FROM signals WHERE ts >= ?"
        params: list = [cutoff_ts]
        if source:
            sql += " AND source = ?"
            params.append(source)
        if only_unresolved:
            sql += " AND resolved = 0"
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        try:
            with self._connect_ro(self.cfg.ea_signals_db) as conn:
                rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            log.warning("read_recent_signals failed: %s", e)
            return []

        return [self._row_to_signal(r) for r in rows]

    def read_distinct_sources(self) -> list[str]:
        try:
            with self._connect_ro(self.cfg.ea_signals_db) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT source FROM signals ORDER BY source"
                ).fetchall()
            return [r["source"] for r in rows]
        except Exception as e:
            log.warning("read_distinct_sources failed: %s", e)
            return []

    def get_source_expectancy(
        self,
        source: str,
        lookback_days: int = 30,
        horizon_min: int = 60,
    ) -> SourceStats | None:
        """Liczy edge dla danego source na podstawie resolved outcomes."""
        cutoff = time.time() - lookback_days * 86400
        sql = """
            SELECT direction, pips, correct
            FROM signals
            WHERE source = ? AND resolved = 1
              AND horizon_min = ? AND ts >= ?
              AND pips IS NOT NULL
        """
        try:
            with self._connect_ro(self.cfg.ea_signals_db) as conn:
                rows = list(conn.execute(sql, (source, horizon_min, cutoff)))
        except Exception as e:
            log.warning("get_source_expectancy failed for %s: %s", source, e)
            return None

        if not rows:
            return None

        n = len(rows)
        wins = [r for r in rows if r["correct"] == 1]
        losses = [r for r in rows if r["correct"] == 0]

        win_rate = len(wins) / n if n else 0.0
        avg_pips_win = sum(abs(r["pips"]) for r in wins) / len(wins) if wins else 0.0
        avg_pips_loss = -sum(abs(r["pips"]) for r in losses) / len(losses) if losses else 0.0

        e_pips = (win_rate * avg_pips_win) + ((1 - win_rate) * avg_pips_loss)
        e_r = e_pips / ASSUMED_R_PIPS

        return SourceStats(
            source=source,
            n_resolved=n,
            win_rate=win_rate,
            avg_pips_correct=avg_pips_win,
            avg_pips_wrong=avg_pips_loss,
            expectancy_pips=e_pips,
            expectancy_r=e_r,
        )

    def get_top_sources(
        self,
        lookback_days: int = 30,
        horizon_min: int = 60,
        min_samples: int = 30,
    ) -> list[SourceStats]:
        """Wszystkie sources z min_samples, posortowane po expectancy."""
        results: list[SourceStats] = []
        for src in self.read_distinct_sources():
            stats = self.get_source_expectancy(src, lookback_days, horizon_min)
            if stats and stats.n_resolved >= min_samples:
                results.append(stats)
        return sorted(results, key=lambda s: s.expectancy_r, reverse=True)

    def get_signal_confluence(
        self,
        since_minutes: int = 15,
        min_confidence: float = 0.5,
    ) -> dict[str, int]:
        """Ile niezależnych source potwierdza każdy kierunek w ostatnich X min."""
        recent = self.read_recent_signals(since_minutes=since_minutes)
        result = {"LONG": 0, "SHORT": 0, "FLAT": 0}
        seen: dict[str, set[str]] = {"LONG": set(), "SHORT": set(), "FLAT": set()}
        for s in recent:
            if s.confidence < min_confidence:
                continue
            d = s.direction if s.direction in result else "FLAT"
            if s.source not in seen[d]:
                seen[d].add(s.source)
                result[d] += 1
        return result

    # ─────────── LIVE: ice_tracker (LIQUIDITY) ───────────

    def read_ice_events(self, since_minutes: int = 60) -> list[IceEvent]:
        """Liquidity events: ICEBERG / ABSORPTION_BID / ABSORPTION_ASK / BIG_ORDER."""
        ice_db = self._ea_root / "ice_tracker.db"
        cutoff = time.time() - since_minutes * 60
        try:
            with self._connect_ro(ice_db) as conn:
                rows = list(conn.execute(
                    "SELECT * FROM ice_events WHERE ts >= ? ORDER BY ts DESC",
                    (cutoff,),
                ))
        except Exception as e:
            log.warning("read_ice_events failed: %s", e)
            return []

        return [
            IceEvent(
                ts=r["ts"],
                event_type=r["event_type"],
                side=r["side"] or "",
                level_price=r["level_price"] or 0.0,
                qty=r["qty"] or 0,
                spot_at_detect=r["spot_at_detect"] or 0.0,
                dist_pips=r["dist_pips"] or 0.0,
                confidence=r["confidence"] or 0.0,
                outcome_5=r["outcome_5"],
                outcome_15=r["outcome_15"],
                outcome_60=r["outcome_60"],
            )
            for r in rows
        ]

    def get_ice_stats(self) -> dict[str, IceStat]:
        ice_db = self._ea_root / "ice_tracker.db"
        try:
            with self._connect_ro(ice_db) as conn:
                rows = list(conn.execute("SELECT * FROM ice_stats"))
        except Exception as e:
            log.warning("get_ice_stats failed: %s", e)
            return {}

        return {
            r["key"]: IceStat(
                key=r["key"],
                hit_rate=r["hit_rate"] or 0.0,
                n_samples=r["n_samples"] or 0,
                avg_pnl=r["avg_pnl"] or 0.0,
                sharpe=r["sharpe"] or 0.0,
            )
            for r in rows
        }

    def has_recent_liquidity_event(
        self,
        since_minutes: int = 30,
        event_types: tuple[str, ...] = ("ICEBERG", "ABSORPTION_BID", "ABSORPTION_ASK"),
    ) -> IceEvent | None:
        """Czy w ostatnich X min był event płynnościowy istotnego typu."""
        events = self.read_ice_events(since_minutes=since_minutes)
        for ev in events:
            if ev.event_type in event_types:
                return ev
        return None

    # ─────────── LIVE: options ───────────

    def read_options_state(self) -> OptionsState | None:
        """ibkr_options_cache.json — gex, flip_level, top_strikes."""
        path = self._ea_root / "data" / "ibkr_options_cache.json"
        data = self._read_json(path)
        if not isinstance(data, dict):
            return None
        return OptionsState(
            spot=float(data.get("spot", 0.0)),
            gex=float(data.get("gex", 0.0)),
            gex_direction=str(data.get("gex_direction", "NEUTRAL")),
            flip_level=data.get("flip_level"),
            vanna=data.get("vanna"),
            charm=data.get("charm"),
            top_strikes=data.get("top_strikes", []) or [],
            n_contracts=int(data.get("n_contracts", 0) or 0),
            connected=bool(data.get("connected", False)),
            ts=self._parse_ts(data.get("ts")),
        )

    def read_options_history(self, n: int = 20) -> list[dict]:
        """Ostatnie N snapshotów options (cw, pw, flip, mp, gex)."""
        path = self._ea_root / "data" / "options_history.json"
        data = self._read_json(path)
        if not isinstance(data, list):
            return []
        return data[-n:]

    # ─────────── HISTORICAL: super_learner snapshots ───────────

    def read_snapshots(self, n: int = 100, resolved_only: bool = True) -> list[dict]:
        """super_learner.db.snapshots — feature snapshots z 15/60/240 outcomes."""
        sl_db = self._ea_root / "super_learner.db"
        sql = "SELECT * FROM snapshots"
        if resolved_only:
            sql += " WHERE resolved_60 = 1"
        sql += " ORDER BY ts DESC LIMIT ?"
        try:
            with self._connect_ro(sl_db) as conn:
                rows = list(conn.execute(sql, (n,)))
        except Exception as e:
            log.warning("read_snapshots failed: %s", e)
            return []
        return [dict(r) for r in rows]

    def get_top_features(self, horizon: int = 60, top_n: int = 20) -> list[dict]:
        """super_learner.db.feature_importance — top features dla danego horyzontu."""
        sl_db = self._ea_root / "super_learner.db"
        col = f"hit_rate_{horizon}" if horizon in (15, 60, 240) else "hit_rate_60"
        try:
            with self._connect_ro(sl_db) as conn:
                rows = list(conn.execute(
                    f"SELECT feature, {col} as hit_rate, n_samples FROM feature_importance "
                    f"WHERE n_samples > 100 ORDER BY {col} DESC LIMIT ?",
                    (top_n,),
                ))
        except Exception as e:
            log.warning("get_top_features failed: %s", e)
            return []
        return [dict(r) for r in rows]

    # ─────────── Freshness ───────────

    def check_freshness(self, max_age_seconds: int = 120) -> FreshnessResult:
        """Czy wszystkie kluczowe źródła są świeże."""
        per_source: dict[str, float] = {}
        now = time.time()
        problems: list[str] = []

        # signals_unified.db — max(ts)
        try:
            with self._connect_ro(self.cfg.ea_signals_db) as conn:
                row = conn.execute("SELECT MAX(ts) AS mx FROM signals").fetchone()
            mx = row["mx"] if row and row["mx"] else 0
            age = now - mx if mx else 9_999_999
            per_source["signals_unified"] = age
            if age > max_age_seconds:
                problems.append(f"signals stale ({int(age)}s)")
        except Exception as e:
            problems.append(f"signals unreachable: {e}")
            per_source["signals_unified"] = 9_999_999

        # composite.json
        comp = self.read_composite()
        if comp and comp.ts:
            age = now - comp.ts
            per_source["composite"] = age
            if age > max_age_seconds:
                problems.append(f"composite stale ({int(age)}s)")
        else:
            per_source["composite"] = 9_999_999
            problems.append("composite missing")

        # ibkr_options_cache.json — opcje aktualizują rzadziej (10 min OK)
        opts = self.read_options_state()
        if opts and opts.ts:
            age = now - opts.ts
            per_source["options"] = age
            if age > max_age_seconds * 5:
                problems.append(f"options stale ({int(age)}s)")
        elif opts is None:
            per_source["options"] = 9_999_999

        latest = (
            datetime.fromtimestamp(now - min(per_source.values()))
            if per_source else None
        )

        return FreshnessResult(
            is_fresh=len(problems) == 0,
            reason="; ".join(problems) if problems else "all fresh",
            latest_ts=latest,
            per_source=per_source,
        )

    # ─────────── Internal helpers ───────────

    @staticmethod
    def _row_to_signal(r: sqlite3.Row) -> SignalRow:
        return SignalRow(
            id=r["id"],
            ts=r["ts"],
            ts_str=r["ts_str"] or "",
            source=r["source"] or "",
            direction=r["direction"] or "FLAT",
            strength=r["strength"] or 0.0,
            confidence=r["confidence"] or 0.0,
            spot=r["spot"] or 0.0,
            horizon_min=r["horizon_min"] or 60,
            resolved=bool(r["resolved"]),
            pips=r["pips"],
            correct=bool(r["correct"]) if r["correct"] is not None else None,
        )
