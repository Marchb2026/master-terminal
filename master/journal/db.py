"""Journal DB — SQLite storage dla trade'ów Mastera.

Read-write (jedyne miejsce w Master gdzie piszemy). Używamy stdlib sqlite3,
bez sqlalchemy — schemat jest prosty, trade to jedna tabela.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from master.journal.trade import Trade

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id            TEXT PRIMARY KEY,
    template_id         TEXT NOT NULL,
    instrument          TEXT NOT NULL,
    opened_at           TEXT,
    closed_at           TEXT,
    entry_price         REAL,
    exit_price          REAL,
    stop_loss           REAL,
    take_profit         REAL,
    side                TEXT,
    contracts           REAL,
    risk_eur            REAL,
    pnl_eur             REAL,
    r_multiple          REAL,
    regime              TEXT,
    mtf_score           REAL,
    setup_grade         TEXT,
    expected_r_at_entry REAL,
    source              TEXT,
    notes               TEXT,
    tags                TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_template ON trades(template_id);
CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_at);
CREATE INDEX IF NOT EXISTS idx_trades_source ON trades(source);
"""


class JournalDb:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def insert(self, trade: Trade) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades VALUES (
                    :trade_id, :template_id, :instrument,
                    :opened_at, :closed_at,
                    :entry_price, :exit_price, :stop_loss, :take_profit,
                    :side, :contracts, :risk_eur, :pnl_eur, :r_multiple,
                    :regime, :mtf_score, :setup_grade, :expected_r_at_entry,
                    :source, :notes, :tags
                )
                """,
                {
                    "trade_id": trade.trade_id,
                    "template_id": trade.template_id,
                    "instrument": trade.instrument,
                    "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
                    "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "stop_loss": trade.stop_loss,
                    "take_profit": trade.take_profit,
                    "side": trade.side,
                    "contracts": trade.contracts,
                    "risk_eur": trade.risk_eur,
                    "pnl_eur": trade.pnl_eur,
                    "r_multiple": trade.r_multiple,
                    "regime": trade.regime,
                    "mtf_score": trade.mtf_score,
                    "setup_grade": trade.setup_grade,
                    "expected_r_at_entry": trade.expected_r_at_entry,
                    "source": trade.source,
                    "notes": trade.notes,
                    "tags": ",".join(trade.tags) if trade.tags else "",
                },
            )
            conn.commit()

    def insert_many(self, trades: list[Trade]) -> int:
        for t in trades:
            self.insert(t)
        return len(trades)

    def get_trades_by_template(
        self,
        template_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Trade]:
        """Pobiera trade'y dla danego templatu, opcjonalnie z filtrem czasu."""
        sql = "SELECT * FROM trades WHERE template_id = ? AND closed_at IS NOT NULL"
        params: list = [template_id]
        if start is not None:
            sql += " AND closed_at >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND closed_at <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY closed_at DESC"

        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_trade(r) for r in rows]

    def get_session_pnl_r(self, session_start: datetime) -> tuple[float, int, int]:
        """Zwraca (sum_r, n_trades, consecutive_losses) dla bieżącej sesji."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT r_multiple FROM trades
                WHERE closed_at >= ?
                ORDER BY closed_at ASC
                """,
                (session_start.isoformat(),),
            ).fetchall()

        if not rows:
            return 0.0, 0, 0

        rs = [r["r_multiple"] for r in rows]
        total = sum(rs)
        # consecutive losses od końca
        cl = 0
        for r in reversed(rs):
            if r < 0:
                cl += 1
            else:
                break
        return total, len(rs), cl

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> Trade:
        d = dict(row)
        return Trade(
            trade_id=d["trade_id"],
            template_id=d["template_id"],
            instrument=d["instrument"],
            opened_at=datetime.fromisoformat(d["opened_at"]) if d["opened_at"] else None,
            closed_at=datetime.fromisoformat(d["closed_at"]) if d["closed_at"] else None,
            entry_price=d["entry_price"],
            exit_price=d["exit_price"],
            stop_loss=d["stop_loss"],
            take_profit=d["take_profit"],
            side=d["side"] or "LONG",
            contracts=d["contracts"] or 0.0,
            risk_eur=d["risk_eur"] or 0.0,
            pnl_eur=d["pnl_eur"] or 0.0,
            r_multiple=d["r_multiple"] or 0.0,
            regime=d["regime"] or "UNKNOWN",
            mtf_score=d["mtf_score"] or 0.0,
            setup_grade=d["setup_grade"] or "C",
            expected_r_at_entry=d["expected_r_at_entry"],
            source=d["source"] or "master",
            notes=d["notes"] or "",
            tags=(d["tags"] or "").split(",") if d["tags"] else [],
        )

    def count(self) -> int:
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
