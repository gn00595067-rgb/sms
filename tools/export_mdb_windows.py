"""
export_mdb_windows.py — 在 Windows 上把 Access .mdb / .accdb 的所有資料表匯出成 UTF-8 CSV。

用途：之後拿到往年的業績系統檔案（例如 2023 版、2025 版）時，用這支把它們轉成
legacy_csv/ 同樣格式的 CSV，再跑 scripts/etl_legacy.py 匯入。

需求：
  pip install pyodbc pandas
  Windows 需安裝 Microsoft Access Database Engine（若電腦已裝 64 位元 Office 通常已有）。
  注意 Python 與 Access 驅動的位元數要一致（64 位元 Python 需要 64 位元驅動）。
  下載：https://www.microsoft.com/en-us/download/details.aspx?id=54920

用法：
  python tools/export_mdb_windows.py "C:\\path\\舊系統2025.mdb" out_dir
"""
import sys
import os
import pyodbc
import pandas as pd

SKIP_PASSWORD_COLUMNS = {"密碼"}  # 舊系統密碼為明文，絕對不匯出


def main(mdb_path: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={mdb_path};"
    )
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    tables = [
        r.table_name
        for r in cur.tables(tableType="TABLE")
        if not r.table_name.startswith("MSys")
    ]
    print(f"{len(tables)} tables")
    for t in tables:
        try:
            df = pd.read_sql(f"SELECT * FROM [{t}]", conn)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {t}: {e}")
            continue
        drop = [c for c in df.columns if c in SKIP_PASSWORD_COLUMNS]
        if drop:
            df = df.drop(columns=drop)
        # 日期欄轉成 YYYY-MM-DD，與 legacy_csv/ 一致
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
        out = os.path.join(out_dir, f"{t}.csv")
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"  {len(df):6d}  {t}")
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
