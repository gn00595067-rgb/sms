"""
build_boss_workbook.py — 從資料庫產生「老闆工作簿」Excel（值）

用法：
    python tools/build_boss_workbook.py --year 2025 --out samples/常用分析_2025.xlsx
    python tools/build_boss_workbook.py --ym-from 2026-01 --ym-to 2026-08 --out pack/常用分析_2026_1-8.xlsx
需要 sql/009_boss_workbook.sql 已套用（v_boss_line）。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from reports.boss_workbook import compute as C  # noqa: E402
from reports.boss_workbook.xlsx import build_bytes  # noqa: E402


def _connect(db_url: str | None):
    """有 --db 用它，否則走專案 db.connect()（讀 .streamlit/secrets.toml 的 Supabase）。"""
    if db_url:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(db_url, row_factory=dict_row)
    from db import connect
    return connect()


def load_raw(conn, ym_from: date, ym_to: date) -> pd.DataFrame:
    rows = conn.execute("select * from v_boss_line where perf_ym between %s and %s order by perf_ym, \"合約編號\"", (ym_from, ym_to)).fetchall()
    return pd.DataFrame(rows)


def load_counts(conn, ym_from: date, ym_to: date) -> tuple[int, int, float]:
    r = conn.execute("""select count(*) n, count(*) filter (where line_type='PRODUCTION') np,
                               coalesce(sum(cost_amount) filter (where line_type='PRODUCTION'),0) pc
                        from v_line_ext where not is_intercompany and perf_ym between %s and %s""", (ym_from, ym_to)).fetchone()
    return int(r["n"]), int(r["np"]), float(r["pc"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--ym-from")
    ap.add_argument("--ym-to")
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    a = ap.parse_args()
    if a.year:
        ym_from, ym_to, label = date(a.year, 1, 1), date(a.year, 12, 1), f"{a.year}年度"
    else:
        ym_from, ym_to = date.fromisoformat(a.ym_from + "-01"), date.fromisoformat(a.ym_to + "-01")
        label = f"{ym_from:%Y/%m}–{ym_to:%Y/%m}"
    with _connect(a.db) as conn:
        raw = load_raw(conn, ym_from, ym_to)
        n, np_, pc = load_counts(conn, ym_from, ym_to)
    notes = C.notes(raw, n, np_, pc, label)
    Path(a.out).write_bytes(build_bytes(raw, year_label=label, notes_lines=notes))
    print("ok", a.out, len(raw), "lines")


if __name__ == "__main__":
    main()
