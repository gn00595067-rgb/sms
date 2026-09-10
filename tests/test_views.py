"""
test_views.py — view 對帳與雙層毛利 / 獎金 / 應收 的關鍵樣本（需要 DB）

對帳目標：docs/reconciliation_targets.csv（只比對有業績年月份的列，
因為空白年月的舊資料不匯入 deal_line）。
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from conftest import requires_db  # noqa: E402
from db import connect  # noqa: E402


def _fetch(sql, params=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


# ------------------------------------------------------------------ 對帳
@requires_db
def test_reconciliation_matches_targets():
    csv = ROOT / "docs" / "reconciliation_targets.csv"
    tgt = pd.read_csv(csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    # 只比對有年月的列
    tgt = tgt[tgt["業績年月份"].str.strip() != ""]

    rows = _fetch(
        """select to_char(perf_ym,'YYYY/MM') as ym, coalesce(company,'') as company,
                  count(*) as rows, sum(gross_amount) as gross, sum(net_amount) as net, sum(cost_amount) as cost
           from v_deal_line_flat group by perf_ym, company"""
    )
    got = {(r["ym"], r["company"]): r for r in rows}

    mismatches = []
    for _, t in tgt.iterrows():
        key = (t["業績年月份"].strip(), t["公司別"].strip())
        g = got.get(key)
        if g is None:
            mismatches.append(f"缺少 {key}")
            continue
        checks = [
            ("rows", float(g["rows"]), float(t["rows"])),
            ("gross", float(g["gross"]), float(t["實收金額"])),
            ("net", float(g["net"]), float(t["除佣實收"])),
            ("cost", float(g["cost"]), float(t["實付金額"])),
        ]
        for name, a, b in checks:
            if abs(a - b) > 1:
                mismatches.append(f"{key} {name}: db={a:,.0f} csv={b:,.0f}")
    assert not mismatches, "對帳不符：\n" + "\n".join(mismatches[:20])


# ------------------------------------------------------------------ 雙層毛利樣本合約
@requires_db
def test_contract_1130825_6_6_two_layer():
    lines = _fetch(
        """select company, business_group, line_type, net_amount, cost_amount
           from v_deal_line_flat where contract_no = %s""",
        ("1130825-6-6",),
    )
    assert lines, "找不到合約 1130825-6-6"
    # 東吳客戶線 net 380,952 / cost 247,619
    dw = [r for r in lines if r["company"] == "東吳" and abs(float(r["net_amount"]) - 380952) <= 1]
    assert dw, "缺東吳客戶線 net≈380,952"
    assert abs(float(dw[0]["cost_amount"]) - 247619) <= 1
    # 聲活-東 轉撥線 net 247,618
    ic = [r for r in lines if r["business_group"] == "聲活-東" and abs(float(r["net_amount"]) - 247618) <= 1]
    assert ic, "缺聲活-東轉撥線 net≈247,618"

    # v_profit_two_layer 2025-01 企頻 應含這兩筆
    tl = _fetch(
        "select layer1_profit, layer2_revenue from v_profit_two_layer where perf_ym = %s and platform_group = %s",
        (date(2025, 1, 1), "企頻"),
    )
    assert tl, "缺 v_profit_two_layer 2025-01 企頻"
    assert float(tl[0]["layer2_revenue"]) >= 247618 - 1


# ------------------------------------------------------------------ 業務獎金樣本
@requires_db
def test_bonus_simple_sample():
    rows = _fetch(
        """select net_amount, bonus_pct, bonus_amount
           from v_bonus_simple
           where perf_ym = %s and salesperson = %s and platform_group = %s and sales_item = %s""",
        (date(2025, 6, 1), "洪佳琪", "廣播", "開發"),
    )
    assert rows, "找不到 v_bonus_simple 2025-06 洪佳琪 廣播 開發"
    r = rows[0]
    assert abs(float(r["net_amount"]) - 670623) <= 1
    assert abs(float(r["bonus_pct"]) - 2) <= 0.001
    assert abs(float(r["bonus_amount"]) - 13412) <= 1


# ------------------------------------------------------------------ 應收：手動結清不變式
@requires_db
def test_ar_settled_manually_invariant():
    rows = _fetch("select outstanding_amount, overdue_days from v_ar_open where settled_manually")
    for r in rows:
        assert float(r["outstanding_amount"]) == 0
        assert int(r["overdue_days"]) == 0
