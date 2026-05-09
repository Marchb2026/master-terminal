"""Importer — EA signal_log.csv → Master journal.

EA już prowadzi proto-journal w `logs/signal_log.csv` z kolumnami:
    ts, tf, signal, score, strength, ofi, cd50, dxy_bias, vix,
    price_at_signal, price_1h_later, price_4h_later,
    outcome_1h, outcome_4h, r_pips_1h, r_pips_4h, correct_1h,
    supporting, opposing, agreement

Z tego wyciągamy historyczne trade'y do bootstrapu expectancy DB.

UWAGA: signal_log.csv ma "outcome" mierzone w pipsach, nie w R.
Konwertujemy do R przyjmując założony stop. Ponieważ EA nie loguje
zamierzonego SL, używamy proxy: r_per_trade = założone 10 pips SL,
a wynik 1h jako r_pips_1h / 10. To jest hack — w przyszłości EA
powinien logować SL bezpośrednio.

Importer można uruchomić wielokrotnie — używa INSERT OR REPLACE
po unikalnym trade_id (timestamp-based).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from master.config import CONFIG, ensure_dirs
from master.journal.db import JournalDb
from master.journal.trade import Trade

log = logging.getLogger(__name__)


# Założenia bootstrapu (do późniejszej rewizji)
ASSUMED_SL_PIPS = 10.0    # 1R = 10 pipsów (proxy bo EA nie loguje SL)


def import_signal_log(
    csv_path: Path,
    journal: JournalDb,
    horizon: str = "4h",
    instrument: str = "6EM26",
    skip_if_inconclusive: bool = True,
) -> tuple[int, int]:
    """Importuje signal_log.csv jako trade'y do journal'a.

    horizon: "1h" lub "4h" — który outcome bierzemy jako wynik trade'a.
    Zwraca: (imported, skipped).
    """
    if not csv_path.exists():
        log.error("CSV not found: %s", csv_path)
        return 0, 0

    df = pd.read_csv(csv_path)
    log.info("Loaded %d rows from %s", len(df), csv_path)

    outcome_col = f"outcome_{horizon}"
    r_pips_col = f"r_pips_{horizon}"

    if outcome_col not in df.columns:
        log.error("Column %s not in CSV", outcome_col)
        return 0, 0

    imported = 0
    skipped = 0

    trades_to_insert: list[Trade] = []
    for _, row in df.iterrows():
        outcome = str(row.get(outcome_col, "")).upper()
        if skip_if_inconclusive and outcome not in ("WIN", "LOSS"):
            skipped += 1
            continue

        # Konwersja r_pips -> r_multiple
        try:
            r_pips = float(row.get(r_pips_col, 0))
        except (ValueError, TypeError):
            skipped += 1
            continue

        # WIN: r_pips dodatnie; LOSS: ujemne (lub abs i znak z outcome)
        sign = 1.0 if outcome == "WIN" else -1.0
        r_multiple = sign * abs(r_pips) / ASSUMED_SL_PIPS

        try:
            ts = datetime.fromisoformat(str(row["ts"]))
        except (ValueError, KeyError):
            skipped += 1
            continue

        signal = str(row.get("signal", "")).upper()
        side = "LONG" if signal == "LONG" else "SHORT" if signal == "SHORT" else "LONG"

        # Template ID — póki nie znamy regime/grade z EA, używamy TF + side
        tf_val = row.get("tf", "")
        template_id = f"EA_TF{tf_val}_{side}"

        trade = Trade(
            trade_id=f"ea_{ts.strftime('%Y%m%d_%H%M%S')}_{tf_val}_{side}",
            template_id=template_id,
            instrument=instrument,
            opened_at=ts,
            closed_at=ts,    # EA loguje wynik 1h/4h później ale ts jest z momentu sygnału
            entry_price=float(row.get("price_at_signal", 0)) or None,
            exit_price=(float(row.get(f"price_{horizon}_later", 0)) or None),
            side=side,
            contracts=1.0,
            risk_eur=ASSUMED_SL_PIPS,    # placeholder — 1R = ASSUMED_SL_PIPS jednostek
            pnl_eur=r_multiple * ASSUMED_SL_PIPS,
            r_multiple=r_multiple,
            regime="UNKNOWN",
            mtf_score=0.0,
            setup_grade="?",
            source="ea_signal_log",
            notes=f"score={row.get('score', '')}, strength={row.get('strength', '')}, "
                  f"agreement={row.get('agreement', '')}",
            tags=[
                t.strip() for t in str(row.get("supporting", "")).split(",")
                if t.strip()
            ],
        )
        trades_to_insert.append(trade)
        imported += 1

    journal.insert_many(trades_to_insert)
    log.info("Imported %d trades, skipped %d", imported, skipped)
    return imported, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Import EA signal_log.csv to Master journal")
    parser.add_argument("--csv", type=Path, default=CONFIG.ea_signal_log_csv)
    parser.add_argument("--horizon", choices=["1h", "4h"], default="4h")
    parser.add_argument("--instrument", default=CONFIG.instrument)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    ensure_dirs()
    journal = JournalDb(CONFIG.journal_db)
    imp, skp = import_signal_log(
        args.csv, journal,
        horizon=args.horizon,
        instrument=args.instrument,
    )
    print(f"Imported: {imp}, Skipped: {skp}, Total in journal: {journal.count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
