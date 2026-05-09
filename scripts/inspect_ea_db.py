"""Inspector dla signals_unified.db — odpalamy z PowerShella czystym `python inspect_ea_db.py`,
żeby ominąć escape'y w `python -c "..."`.

Wykrywa schemat głównej tabeli, liczy wiersze, pokazuje sample.
Output kopiujemy i wklejamy do AI — to jest ground truth dla feature_store.py.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path(r"C:\Users\User\Desktop\terminal\signals_unified.db")
EA_ROOT = Path(r"C:\Users\User\Desktop\terminal")


def inspect_db(db_path: Path) -> None:
    print(f"\n=== DB: {db_path} ===")
    if not db_path.exists():
        print(f"  ERROR: not found")
        return

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"  size: {size_mb:.1f} MB")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    # Tabele
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    print(f"  tables ({len(tables)}): {tables}")

    for t in tables:
        print(f"\n  --- TABLE: {t} ---")
        # Schema
        cols = list(cur.execute(f"PRAGMA table_info({t})"))
        print(f"  columns ({len(cols)}):")
        for col in cols:
            # cid, name, type, notnull, dflt_value, pk
            print(f"    {col[1]:30s}  {col[2]:15s}  pk={col[5]}")

        # Row count
        try:
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  rows: {n:,}")
        except Exception as e:
            print(f"  rows: ERROR {e}")
            continue

        if n == 0:
            continue

        # Indeksy
        idx = list(cur.execute(f"PRAGMA index_list({t})"))
        if idx:
            print(f"  indexes: {[i[1] for i in idx]}")

        # Sample: 2 newest rows
        col_names = [c[1] for c in cols]
        try:
            sample = list(cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 2"))
            print(f"  sample (2 newest):")
            for row in sample:
                rec = dict(zip(col_names, row))
                # Skróć długie stringi do 60 znaków, żeby output był czytelny
                rec = {k: (str(v)[:60] + "..." if v and len(str(v)) > 60 else v)
                       for k, v in rec.items()}
                print(f"    {rec}")
        except Exception as e:
            print(f"  sample: ERROR {e}")

    conn.close()


def inspect_json_caches() -> None:
    """Lista i sample z cache'ów forecast modułów (m1-m12) oraz ważnych JSONów."""
    cache_root = Path(r"C:\Users\User\Desktop\forecast\forecast_modules\cache")
    extras = [
        Path(r"C:\Users\User\Desktop\terminal\data\vpin_cache.json"),
        Path(r"C:\Users\User\Desktop\terminal\data\ibkr_options_cache.json"),
        Path(r"C:\Users\User\Desktop\terminal\data\options_history.json"),
        Path(r"C:\Users\User\Desktop\terminal\data\ml_history.json"),
        Path(r"C:\Users\User\Desktop\forecast\snapshot_dump.json"),
    ]
    cache_files = list(cache_root.glob("*.json")) if cache_root.exists() else []

    print(f"\n=== JSON CACHES ({len(cache_files) + len(extras)} files) ===")
    for path in sorted(cache_files) + extras:
        if not path.exists():
            continue
        size_kb = path.stat().st_size / 1024
        print(f"\n  --- {path.name} ({size_kb:.1f} KB) ---")
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                print(f"    type: dict, keys: {list(content.keys())[:20]}")
                # Pokaż 1-poziom shape'u
                for k, v in list(content.items())[:5]:
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        print(f"      {k}: {v}")
                    elif isinstance(v, list):
                        print(f"      {k}: list[{len(v)}] (first: {v[0] if v else 'empty'})")
                    elif isinstance(v, dict):
                        print(f"      {k}: dict, keys={list(v.keys())[:10]}")
                    else:
                        print(f"      {k}: {type(v).__name__}")
            elif isinstance(content, list):
                print(f"    type: list[{len(content)}], first: {content[0] if content else 'empty'}")
            else:
                print(f"    type: {type(content).__name__}, value: {str(content)[:100]}")
        except Exception as e:
            print(f"    ERROR parsing: {e}")


def inspect_other_dbs() -> None:
    others = [
        EA_ROOT / "super_learner.db",
        EA_ROOT / "ml_predictor.db",
        EA_ROOT / "adaptive.db",
        EA_ROOT / "ice_tracker.db",
        EA_ROOT / "ml_bridge.db",
    ]
    for db in others:
        if db.exists():
            inspect_db(db)


if __name__ == "__main__":
    print("=" * 70)
    print("EA TERMINAL — DATABASE INSPECTOR")
    print("=" * 70)

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    inspect_db(db)

    if "--all" in sys.argv:
        inspect_other_dbs()
        inspect_json_caches()

    print("\n" + "=" * 70)
    print("DONE — skopiuj output i wklej do czatu.")
    print("=" * 70)
