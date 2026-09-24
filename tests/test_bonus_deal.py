"""test_bonus_deal.py — 業務獎金逐案分攤（純 Python，不用 DB）"""
from __future__ import annotations

from datetime import date

import pandas as pd

from reports.bonus_deal import _alloc_int, allocate_bonus_by_deal

YM = date(2026, 9, 1)


def _bucket(sp, grp, pg, item, net, bonus, pct):
    return dict(perf_ym=YM, salesperson=sp, business_group=grp, platform_group=pg, sales_item=item,
                net_amount=net, bonus_amount=bonus, bonus_pct=pct, threshold_amount=0)


def _line(sp, grp, pg, item, cno, cust, net):
    return dict(perf_ym=YM, perf_ym_text="2026/09", salesperson=sp, business_group=grp,
                platform_group=pg, sales_item=item, contract_no=cno, customer=cust, net_amount=net)


def test_alloc_int_sums_exactly():
    # 最大餘數法：和恰為 total，且盡量依權重
    assert sum(_alloc_int([1, 1, 1], 10)) == 10
    assert _alloc_int([1, 1, 1], 10) == [4, 3, 3]           # 餘 1 給第一位
    assert _alloc_int([700, 200, 100], 1000) == [700, 200, 100]
    assert sum(_alloc_int([333, 333, 334], 100)) == 100
    assert _alloc_int([5, 0, 0], 7) == [7, 0, 0]            # 只有一格有權重全給它
    assert _alloc_int([0, 0], 0) == [0, 0]


def test_allocation_equals_monthly_bonus():
    # 一格：月獎金 13,412 分攤到三個合約（依除佣佔比），逐案加總 == 月獎金
    bucket = pd.DataFrame([_bucket("洪佳琪", "東吳組", "廣播", "開發", 670623, 13412, 2)])
    contract = pd.DataFrame([
        _line("洪佳琪", "東吳組", "廣播", "開發", "C1", "客A", 400000),
        _line("洪佳琪", "東吳組", "廣播", "開發", "C2", "客B", 200000),
        _line("洪佳琪", "東吳組", "廣播", "開發", "C3", "客C", 70623),
    ])
    out = allocate_bonus_by_deal(bucket, contract)
    assert round(out["bonus_amount"].sum()) == 13412           # 100% 對得上月獎金
    assert round(out["net_amount"].sum()) == 670623
    assert set(out["contract_no"]) == {"C1", "C2", "C3"}
    assert (out["rule_status"] == "").all()


def test_threshold_not_met_zero():
    # 月獎金 = 0（未達門檻）→ 逐案全部 0
    bucket = pd.DataFrame([_bucket("A", "東吳組", "企頻", "開發", 100000, 0, 3)])
    contract = pd.DataFrame([
        _line("A", "東吳組", "企頻", "開發", "C1", "客A", 60000),
        _line("A", "東吳組", "企頻", "開發", "C2", "客B", 40000),
    ])
    out = allocate_bonus_by_deal(bucket, contract)
    assert out["bonus_amount"].sum() == 0


def test_contract_spanning_two_buckets_merges():
    # 同一合約跨兩個平台歸類（兩格）→ 逐合約合併成一列、獎金加總
    bucket = pd.DataFrame([
        _bucket("A", "東吳組", "企頻", "開發", 100000, 3000, 3),
        _bucket("A", "東吳組", "廣播", "開發", 50000, 1000, 2),
    ])
    contract = pd.DataFrame([
        _line("A", "東吳組", "企頻", "開發", "C1", "客A", 100000),
        _line("A", "東吳組", "廣播", "開發", "C1", "客A", 50000),
    ])
    out = allocate_bonus_by_deal(bucket, contract)
    assert len(out) == 1                                        # 一合約一列
    r = out.iloc[0]
    assert r["contract_no"] == "C1"
    assert round(r["net_amount"]) == 150000
    assert round(r["bonus_amount"]) == 4000                     # 3000 + 1000
    assert r["platform_group"] == "企頻／廣播"                  # 兩平台歸類都列
    assert r["rule_status"] == "混合%"                          # 2% 與 3% 不同 → 混合


def test_no_rule_marked():
    # 該格沒有規則（bonus_amount 為 None）→ 標「未設定規則」、獎金 0
    bucket = pd.DataFrame([_bucket("A", "東吳組", "數位", "直客", 80000, None, None)])
    contract = pd.DataFrame([_line("A", "東吳組", "數位", "直客", "C9", "客Z", 80000)])
    out = allocate_bonus_by_deal(bucket, contract)
    assert out.iloc[0]["bonus_amount"] == 0
    assert out.iloc[0]["rule_status"] == "未設定規則"


def test_empty_contract_returns_empty():
    out = allocate_bonus_by_deal(pd.DataFrame(), pd.DataFrame())
    assert out.empty
