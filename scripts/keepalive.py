"""keepalive.py — 對資料庫做一次極輕量查詢，避免 Supabase 免費方案因 7 天沒活動而暫停專案。
由 .github/workflows/supabase_keepalive.yml 每天執行；本機也可手動跑。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect  # noqa: E402

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("select count(*) as n from deal_line")
        print("ok, deal_line rows =", cur.fetchone()["n"])
