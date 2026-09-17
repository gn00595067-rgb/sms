"""
test_analysis.py — 分析報表資料層驗收（需要 DB）

對 2026/01–09 視窗，比對 core/analysis.py 的彙總與 §7 驗收數字（= tools/mockup_generator.py）。
數字若有差異代表資料層或彙總邏輯與樣稿不一致，必須先修好再動畫面。
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

YF, YT = date(2026, 1, 1), date(2026, 9, 1)
PF, PT = date(2025, 1, 1), date(2025, 9, 1)


def _fetch(sql, params=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


# ------------------------------------------------------------------ 集團三層毛利（v_group_month 期間加總）
@requires_db
def test_group_month_totals_match_acceptance():
    r = _fetch(
        """select sum(ext_net) en, sum(booked_profit) bp, sum(ic_add_back) ic, sum(ic_transfer_gross) icg,
                  sum(group_profit) gp, sum(fixed_cost) fc, sum(net_profit) np
           from v_group_month where perf_year=2026 and perf_month<=9""")[0]
    assert abs(float(r["en"]) - 87_443_295) <= 1
    assert abs(float(r["bp"]) - 24_090_256) <= 1
    # 007 §2.4：集團毛利橋一定收斂（帳上毛利 + 加回 = 集團毛利）
    assert abs(float(r["bp"]) + float(r["ic"]) - float(r["gp"])) <= 1
    # 加回 = 集團毛利 − 帳上毛利（≈ 2,333 萬）；轉撥收入總額（明細）= 2,468 萬
    assert abs(float(r["ic"]) - 23_331_605) <= 1
    assert abs(float(r["icg"]) - 24_681_545) <= 1
    assert abs(float(r["gp"]) - 47_421_861) <= 1
    assert abs(float(r["fc"]) - 14_250_000) <= 1
    assert abs(float(r["np"]) - 33_171_861) <= 1


@requires_db
def test_company_ext_net_match_acceptance():
    got = {r["company"]: float(r["en"]) for r in _fetch(
        """select company, sum(ext_net) en from v_company_month
           where perf_year=2026 and perf_month<=9 group by company""")}
    assert abs(got["聲活"] - 51_116_900) <= 1
    assert abs(got["東吳"] - 23_651_990) <= 1
    assert abs(got["鉑霖"] - 12_674_406) <= 1


@requires_db
def test_barter_total():
    r = _fetch("select sum(ext_net) b from v_deal_summary where is_barter and perf_ym between %s and %s", (YF, YT))[0]
    assert abs(float(r["b"]) - 2_504_378) <= 1


# ------------------------------------------------------------------ 客戶彙總（agg_customers）
@requires_db
def test_agg_customers_match_acceptance():
    from core import analysis as A
    dw = A.load_deals(YF, YT)
    dp = A.load_deals(PF, PT)
    cy = A.customer_year(2026)
    cust = A.agg_customers(dw, dp, cy)
    assert len(cust) == 172                                   # 活躍客戶數
    assert int((cust["status"] == "新客").sum()) == 89        # 新客（期間口徑）
    top10 = float(cust.head(10)["ext_net"].sum()) / float(cust["ext_net"].sum())
    assert abs(top10 - 0.533) <= 0.001                        # 前 10 大佔比
    # 客戶第 1 名（期間口徑）
    assert cust.iloc[0]["customer"] == "全家便利商店股份有限公司"
    assert abs(float(cust.iloc[0]["ext_net"]) - 16_492_236) <= 1


@requires_db
def test_customer_year_abc_counts():
    got = {r["abc_tier"]: int(r["n"]) for r in _fetch(
        "select abc_tier, count(*) n from v_customer_year where perf_year=2026 and ext_net>0 group by abc_tier")}
    assert got["A"] == 39 and got["B"] == 61 and got["C"] == 76   # 年度口徑


# ------------------------------------------------------------------ 業務彙總（agg_salespeople）
@requires_db
def test_agg_salespeople_match_acceptance():
    from core import analysis as A
    dw = A.load_deals(YF, YT)
    dp = A.load_deals(PF, PT)
    cy = A.customer_year(2026)
    cust = A.agg_customers(dw, dp, cy)
    sp = A.agg_salespeople(dw, dp, A.new_customers_by_salesperson(cust),
                           A.load_barter_by("salesperson", YF, YT))
    nonh = sp[~sp["is_house"]]
    assert len(nonh) == 14                                    # 有業績業務（非公司戶）
    per_capita = float(nonh["ext_net"].sum()) / len(nonh) / 10000
    assert abs(per_capita - 448) <= 1                         # 人均約 448 萬
    assert list(nonh.head(3)["salesperson"]) == ["洪佳琪", "陳絜心", "許雅婷"]


# ------------------------------------------------------------------ 銷售分佈
@requires_db
def test_sales_distribution_match_acceptance():
    from core import analysis as A
    d_all = A.load_deals(YF, YT)
    d = d_all[d_all["ext_net"] > 0]
    zero = d_all[d_all["ext_net"] <= 0]
    assert len(d) == 486
    assert len(zero) == 97
    assert int((d["ext_net"] >= 1_000_000).sum()) == 10
    assert int(d["is_low_margin"].sum()) == 47


# ------------------------------------------------------------------ 目標達成（Q3 三家）
@requires_db
def test_target_progress_q3_actuals():
    got = {r["company"]: float(r["actual"]) for r in _fetch(
        "select company, actual from v_target_progress where period_type='Q' and period_no=3 and year=2026")}
    assert abs(got["聲活"] - 3_329_960) <= 1
    assert abs(got["東吳"] - 8_568_577) <= 1
    assert abs(got["鉑霖"] - 4_765_370) <= 1


# ------------------------------------------------------------------ P0-3：截止月 = 最後已結束的月
@requires_db
def test_as_of_is_last_completed_month():
    r = _fetch("select as_of_ym from v_as_of")[0]
    m = _fetch("select date_trunc('month', current_date)::date as m")[0]
    assert r["as_of_ym"] < m["m"], "v_as_of 應為最後一個已結束的月份（本月進行中不算）"


# ------------------------------------------------------------------ P0-2：統一毛利率口徑
@requires_db
def test_margin_kpis_matches_group_month():
    """margin_kpis（含成本單）的帳上毛利率 = v_group_month 同區間的 booked_margin。"""
    from core import analysis as A
    dw = A.load_deals(YF, YT)
    mk = A.margin_kpis(dw)
    r = _fetch("select case when sum(ext_net)<>0 then sum(booked_profit)/sum(ext_net) end bm "
               "from v_group_month where perf_year=2026 and perf_month<=9")[0]
    assert abs(mk["booked"] - float(r["bm"])) <= 0.001
    assert mk["booked_rev_only"] > mk["booked"]      # 只看有收入客戶會較高（含成本單會拉低）


# ------------------------------------------------------------------ P0-4：流失風險 KPI 與清單同口徑、無空業務
@requires_db
def test_churn_list_same_scope_and_no_null_salesperson():
    from core import analysis as A
    dw = A.load_deals(YF, YT)
    dp = A.load_deals(PF, PT)
    cust = A.agg_customers(dw, dp, A.customer_year(2026))
    churn = A.churn_list(dp, cust, 300000)
    # 清單每一家去年同段金額都 ≥ 門檻、且本期不在客戶清單
    cur_set = set(cust["customer"])
    assert (churn["prev_net"] >= 300000).all()
    assert not churn["customer"].isin(cur_set).any()
    assert churn["main_salesperson"].notna().all(), "去年業務不應有空值"


# ------------------------------------------------------------------ P0-5：客戶產業以訂單眾數補齊，前 20 名無未分類
@requires_db
def test_top_customers_have_industry():
    from core import analysis as A
    dw = A.load_deals(YF, YT)
    cust = A.agg_customers(dw, A.load_deals(PF, PT), A.customer_year(2026))
    top20 = cust.head(20)
    missing = top20[top20["industry"].isna() | (top20["industry"] == "(未分類)")]
    assert len(missing) == 0, f"前 20 名仍有未分類：{list(missing['customer'])}"


# ------------------------------------------------------------------ 007 §2.6：老闆工作簿 2025 發稿口徑黃金數字
@requires_db
def test_boss_workbook_2025():
    """對過老闆工作簿的固定值（發稿口徑）：ETL 重跑後仍須相等。"""
    # 各公司除佣實收 / 成本 / 客戶數（發稿口徑，線層）
    rows = {r["company"]: r for r in _fetch(
        """select company, round(sum(net_amount)) net, round(sum(cost_amount)) cost,
                  count(distinct customer_id) customers
           from v_report_line where perf_year=2025 and in_media_scope group by 1""")}
    assert abs(float(rows["聲活"]["net"]) - 71_533_523) <= 1
    assert abs(float(rows["聲活"]["cost"]) - 29_157_710) <= 1
    assert abs(float(rows["東吳"]["net"]) - 50_325_792) <= 1
    assert abs(float(rows["瑞迪"]["net"]) - 536_190) <= 1
    assert abs(float(rows["鉑霖"]["net"]) - 11_907_516) <= 1
    assert abs(float(rows["鉑霖"]["cost"]) - 6_932_238) <= 1
    # 三公司合計 + 帳上毛利 + 不重複客戶數
    tot = _fetch(
        """select round(sum(net_amount)) net, round(sum(net_amount)-sum(cost_amount)) profit,
                  count(distinct customer_id) customers
           from v_report_line where perf_year=2025 and in_media_scope""")[0]
    assert abs(float(tot["net"]) - 134_303_021) <= 1
    assert abs(float(tot["profit"]) - 67_416_333) <= 1
    assert int(tot["customers"]) == 265
    # 不含廣播（自媒體）
    own = _fetch(
        """select round(sum(net_amount)) net, count(distinct customer_id) customers
           from v_report_line where perf_year=2025 and in_media_scope and is_own_media""")[0]
    assert abs(float(own["net"]) - 98_408_698) <= 1
    assert int(own["customers"]) == 259
    # 東吳+瑞迪 分報表平台（= 老闆工作簿東吳列）
    rp = {r["report_platform"]: float(r["net"]) for r in _fetch(
        """select report_platform, round(sum(net_amount)) net from v_report_line
           where perf_year=2025 and in_media_scope and company in ('東吳','瑞迪') group by 1""")}
    assert abs(rp["全家企頻"] - 32_378_519) <= 1
    assert abs(rp["萬家福"] - 5_630_860) <= 1
    assert abs(rp["新鮮視"] - 9_535_360) <= 1
    assert abs(rp["廣播"] - 3_317_243) <= 1


# ------------------------------------------------------------------ 純函式（免 DB）：毛利率分段
def test_margin_band_boundaries():
    from core.analysis import margin_band
    assert margin_band(-0.1).startswith("1.")
    assert margin_band(0.0).startswith("2.")
    assert margin_band(0.15).startswith("2.")
    assert margin_band(0.16).startswith("3.")
    assert margin_band(0.34).startswith("3.")
    assert margin_band(0.35).startswith("4.")
    assert margin_band(0.5).startswith("5.")
