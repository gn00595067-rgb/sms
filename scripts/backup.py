"""
backup.py — 把所有非 legacy 表 COPY 成 CSV 打包成 backup_YYYYMMDD.zip

用法：
  python scripts/backup.py                 # 產生 backup_<今天>.zip
  python scripts/backup.py --out mydir      # 指定輸出資料夾
排除 legacy_* 原樣表（資料量大且可由 CSV 重匯）。
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys
import zipfile
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect  # noqa: E402


def dump_tables(out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"backup_{date.today():%Y%m%d}.zip"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select table_name from information_schema.tables
                   where table_schema = 'public' and table_type = 'BASE TABLE'
                     and table_name not like 'legacy_%'
                   order by table_name"""
            )
            tables = [r["table_name"] for r in cur.fetchall()]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for t in tables:
                chunks: list[bytes] = []
                with conn.cursor() as cur:
                    with cur.copy(f'copy "{t}" to stdout with csv header') as cp:
                        while True:
                            data = cp.read()
                            if not data:
                                break
                            chunks.append(bytes(data))
                zf.writestr(f"{t}.csv", b"".join(chunks).decode("utf-8"))
                print(f"  {t}")
    print(f"完成：{zip_path}")
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    dump_tables(pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
