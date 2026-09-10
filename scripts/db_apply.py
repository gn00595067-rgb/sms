"""
db_apply.py — 依檔名順序套用 sql/*.sql（不需要 supabase CLI）

用法：
  python scripts/db_apply.py            # 套用尚未套用過的檔案
  python scripts/db_apply.py --force    # 全部重跑（所有 SQL 都是 idempotent，可安全重跑）

每個檔案在一個交易內執行；成功後記錄到 schema_migrations。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect  # noqa: E402

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent / "sql"


def main(force: bool = False) -> None:
    files = sorted(SQL_DIR.glob("*.sql"))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "create table if not exists schema_migrations (filename text primary key, applied_at timestamptz not null default now())"
            )
            conn.commit()
            cur.execute("select filename from schema_migrations")
            done = {r["filename"] for r in cur.fetchall()}
        for f in files:
            if f.name in done and not force:
                print(f"skip   {f.name}")
                continue
            sql = f.read_text(encoding="utf-8")
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "insert into schema_migrations(filename) values (%s) on conflict (filename) do update set applied_at = now()",
                        (f.name,),
                    )
            print(f"applied {f.name}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
