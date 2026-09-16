"""
backfill_customer_industry.py — 用「訂單產業/客戶類別眾數」補齊客戶主檔空欄（P0-5）

舊資料很多客戶主檔的 industry_id / customer_category_id 是空的，但每張訂單都有產業，
導致分析頁排名表的「產業」出現大量未分類。此腳本把主檔空的欄位用該客戶訂單的眾數補上。

用法：
  python scripts/backfill_customer_industry.py            # 只顯示會改哪些（dry-run）
  python scripts/backfill_customer_industry.py --apply    # 實際寫入（經 transaction 記稽核）
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, transaction  # noqa: E402

CANDIDATES_SQL = """
select c.id, c.name,
       mode() within group (order by d.industry_id)          filter (where d.industry_id is not null)          as ind,
       mode() within group (order by d.customer_category_id) filter (where d.customer_category_id is not null)  as cat
from customer c
join deal d on d.customer_id = c.id
where c.is_active and (c.industry_id is null or c.customer_category_id is null)
group by c.id, c.name
"""


def main(apply: bool = False) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(CANDIDATES_SQL)
            rows = cur.fetchall()
            cur.execute("select id, industry_id, customer_category_id from customer")
            cur_state = {r["id"]: r for r in cur.fetchall()}

    plan = []
    for r in rows:
        cs = cur_state.get(r["id"], {})
        set_ind = r["ind"] if cs.get("industry_id") is None and r["ind"] is not None else None
        set_cat = r["cat"] if cs.get("customer_category_id") is None and r["cat"] is not None else None
        if set_ind is not None or set_cat is not None:
            plan.append((r["id"], r["name"], set_ind, set_cat))

    print(f"可補齊 {len(plan)} 個客戶：")
    for cid, name, ind, cat in plan[:50]:
        print(f"  #{cid} {name}: industry={ind} category={cat}")
    if len(plan) > 50:
        print(f"  …其餘 {len(plan) - 50} 筆")

    if not apply:
        print("\n（dry-run；加 --apply 實際寫入）")
        return

    n = 0
    with transaction("backfill_industry") as cur:
        for cid, _name, ind, cat in plan:
            sets, params = [], []
            if ind is not None:
                sets.append("industry_id = %s"); params.append(ind)
            if cat is not None:
                sets.append("customer_category_id = %s"); params.append(cat)
            if sets:
                params.append(cid)
                cur.execute(f"update customer set {', '.join(sets)} where id = %s", params)
                n += 1
    print(f"\n已更新 {n} 個客戶（已記稽核）。")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
