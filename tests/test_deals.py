"""
test_deals.py — save_deal + 子公司轉撥線 往返（需要 DB）

依 §10：不動既有 deal，合約編號用 TEST- 前綴，teardown 刪除。
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from conftest import requires_db  # noqa: E402
from db import connect  # noqa: E402
from core import deals as D  # noqa: E402
from core import data  # noqa: E402


def _one(sql, params=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


@requires_db
def test_save_deal_and_intercompany_roundtrip():
    contract = "TEST-0001"
    dongwu = _one("select id from company where name = %s", ("東吳",))
    cust = _one("select id from customer limit 1")
    plat = _one("select id, platform_group from platform where name = %s", ("全家企頻",))
    sp = _one("select id from salesperson limit 1")
    sc = _one("select id from sales_category limit 1")
    assert dongwu and cust and plat and sp, "缺必要主檔（請先跑 ETL）"

    header = {
        "contract_no": contract,
        "company_id": dongwu["id"],
        "customer_id": cust["id"],
        "salesperson_id": sp["id"],
        "sales_category_id": sc["id"] if sc else None,
        "ad_name": "測試廣告",
    }
    line = {
        "line_no": 1, "line_type": "MEDIA", "perf_ym": date(2026, 6, 1),
        "platform_id": plat["id"], "region_codes": ["ALL"],
        "gross_amount": 100000, "rebate_pct": 10, "cash_discount_pct": 0,
        "net_amount": None,  # 自動 = 90,000
        "cost_amount": 0,
        # 供轉撥計算的欄位
        "company": "東吳", "platform_group": plat["platform_group"],
    }
    try:
        deal_id, n = D.save_deal(header, [line], "pytest")
        assert n == 1
        # 重新載入，net 自動 90,000
        hdr, lines = D.load_deal(contract)
        assert hdr is not None
        media = lines[lines["line_type"] == "MEDIA"].iloc[0]
        assert abs(float(media["net_amount"]) - 90000) <= 1

        # 產生轉撥線：58,500，且原線 cost 設為 58,500
        base_line = {
            "line_no": 1, "line_type": "MEDIA", "perf_ym": date(2026, 6, 1),
            "platform_id": plat["id"], "region_codes": ["ALL"],
            "gross_amount": 100000, "rebate_pct": 10, "cash_discount_pct": 0,
            "net_amount": 90000, "cost_amount": 0,
            "company": "東吳", "company_id": dongwu["id"],
            "platform_group": plat["platform_group"], "salesperson_id": sp["id"],
        }
        all_lines, new_ic = D.generate_intercompany([base_line], data.intercompany_rules())
        assert len(new_ic) == 1
        assert new_ic[0]["net_amount"] == 58500
        # generate_intercompany 不改動傳入的 dict，更新後的原線在回傳的 all_lines 裡
        assert all_lines[0]["cost_amount"] == 58500  # 原線實付被設為轉撥金額

        # 存回含轉撥線
        D.save_deal(header, all_lines, "pytest")
        _, lines2 = D.load_deal(contract)
        ic = lines2[lines2["line_type"] == "INTERCOMPANY"]
        assert not ic.empty and abs(float(ic.iloc[0]["net_amount"]) - 58500) <= 1

        # 稽核：至少 deal + 線 有紀錄
        cnt = _one("select count(*) as n from audit_log where new_data->>'contract_no' = %s or row_pk = %s",
                   (contract, str(deal_id)))
        assert int(cnt["n"]) >= 1
    finally:
        D.delete_deal(contract, "pytest")
        assert D.load_deal(contract)[0] is None
