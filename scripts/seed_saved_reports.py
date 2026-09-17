"""
seed_saved_reports.py — 種子：老闆工作簿六張表的自訂報表定義（CLAUDE_CODE_TASK_4 §5.5）

owner = 系統帳號（第一個 EXEC）、is_shared = true，讓同仁一登入就能重跑。
用法：python scripts/seed_saved_reports.py [year]   （預設 2025）
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, transaction  # noqa: E402


def definitions(year: int) -> list[dict]:
    period = {"from": f"{year}-01-01", "to": f"{year}-12-01", "yoy": False}
    media = {"preset": "media"}
    base_meas = ["net_amount", "cost_amount", "booked_profit", "booked_margin"]
    return [
        {"v": 1, "name": "平台總計總覽（含廣播）", "period": period, "scope": media,
         "filters": {}, "rows": ["company"], "col": "report_platform",
         "measures": base_meas + ["customers"],
         "show": {"total": True, "share": True, "sort": ["net_amount", "desc"]}},
        {"v": 1, "name": "平台總計總覽（不含廣播）", "period": period, "scope": media,
         "filters": {"report_platform": ["全家企頻", "萬家福", "新鮮視", "健康視"]},
         "rows": ["company"], "col": "report_platform", "measures": base_meas + ["customers"],
         "show": {"total": True, "share": True, "sort": ["net_amount", "desc"]}},
        {"v": 1, "name": "各業務分平台總計", "period": period, "scope": media,
         "filters": {}, "rows": ["salesperson", "company"], "col": "report_platform",
         "measures": base_meas, "show": {"total": True, "share": True, "sort": ["net_amount", "desc"]}},
        {"v": 1, "name": "各公司前 10 大客戶", "period": period, "scope": media,
         "filters": {}, "rows": ["company", "customer"], "col": "report_platform",
         "measures": base_meas, "show": {"total": False, "share": True, "top_n": 10, "sort": ["net_amount", "desc"]}},
        {"v": 1, "name": "三公司客戶排名", "period": period, "scope": media,
         "filters": {}, "rows": ["customer"], "col": "report_platform",
         "measures": base_meas, "show": {"total": False, "share": True, "sort": ["net_amount", "desc"]}},
        {"v": 1, "name": "業務 × 客戶 × 平台", "period": period, "scope": media,
         "filters": {}, "rows": ["salesperson", "customer"], "col": "report_platform",
         "measures": ["net_amount", "booked_profit", "booked_margin"],
         "show": {"total": False, "share": True, "sort": ["net_amount", "desc"]}},
    ]


def main(year: int = 2025) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id, username from app_user where role='EXEC' order by id limit 1")
            row = cur.fetchone()
    if not row:
        print("找不到 EXEC 帳號，無法設 owner。"); return
    owner_id, uname = row["id"], row["username"]
    n = 0
    with transaction(uname) as cur:
        for d in definitions(year):
            cur.execute(
                "insert into saved_report(name, owner_id, is_shared, definition, updated_by) "
                "values (%s,%s,true,%s::jsonb,%s) "
                "on conflict (owner_id, name) do update set definition=excluded.definition, "
                "is_shared=true, updated_by=excluded.updated_by",
                (d["name"], owner_id, json.dumps(d, ensure_ascii=False), uname))
            n += 1
    print(f"已寫入 {n} 個共用報表定義（owner={uname}, year={year}）。")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2025)
