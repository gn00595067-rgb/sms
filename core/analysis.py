"""
analysis.py — 分析報表（客戶 / 業務 / 銷售 / 公司）的資料存取與彙總

每個彙總函式都是 tools/mockup_generator.py 對應函式的規格化版本（agg_customers /
agg_sp / band / size_bucket）；頁面與測試都從這裡拿數字，確保與樣稿一致。

口徑（CLAUDE_CODE_TASK_2 §2）：
  - 期間 = 業績年月區間，預設今年 1 月 → v_as_of.as_of_ym。
  - 同期 = 去年同一段月份。
  - KPI / 排名 / 分佈全部從 v_deal_summary（排除交換）在 Python 端彙總。
  - v_customer_year / v_salesperson_year 只用來拿 狀態 / ABC / 距上次交易月數。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect  # noqa: E402

from core.auth import current_user
from core.format import PLATFORM_GROUP_ORDER

# 在 Python 端加總的數值欄（與 generator 的 NUM 一致）
NUM = ["ext_net", "booked_profit", "group_profit", "net_profit",
       "net_cp", "net_fresh", "net_radio", "net_other"]
# 額外需要轉 float 的欄
_FLOAT_EXTRA = ["ext_gross", "booked_cost", "production_cost", "recognized_amount",
                "alloc_fixed_cost", "ic_net", "ic_cost", "purchased_slots", "total_seconds"]

# 業務名稱屬於「公司戶」的清單
HOUSE_NAMES = ("Company", "公司", "東吳", "鉑霖", "聲活", "瑞迪")


# ------------------------------------------------------------------ 低階查詢
def _df(sql: str, params=None) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())


@st.cache_data(ttl=60)
def as_of() -> dict:
    """分析用截止月：有資料且不晚於本月的最大業績年月。"""
    df = _df("select as_of_ym, as_of_year, as_of_month from v_as_of")
    if df.empty or df.iloc[0]["as_of_ym"] is None:
        today = date.today().replace(day=1)
        return {"as_of_ym": today, "as_of_year": today.year, "as_of_month": today.month}
    r = df.iloc[0]
    return {"as_of_ym": r["as_of_ym"], "as_of_year": int(r["as_of_year"]),
            "as_of_month": int(r["as_of_month"])}


def window_defaults() -> tuple[date, date]:
    """(今年 1 月, 截止月)。"""
    ao = as_of()
    return date(ao["as_of_year"], 1, 1), ao["as_of_ym"]


def prev_window(ym_from: date, ym_to: date) -> tuple[date, date]:
    """去年同一段月份。"""
    return ym_from - relativedelta(years=1), ym_to - relativedelta(years=1)


@st.cache_data(ttl=60)
def analysis_months() -> list[date]:
    """有資料的業績年月（新到舊），供期間下拉。"""
    df = _df("select perf_ym from v_months order by perf_ym desc")
    return df["perf_ym"].tolist() if not df.empty else []


def sales_scope_name(user: dict | None) -> str | None:
    """SALES 角色 → 自己的業務名稱（已去除『換』尾）；其他角色 → None。"""
    if not user or user.get("role") != "SALES":
        return None
    sid = user.get("salesperson_id")
    if sid is None:
        return ""  # SALES 但沒綁業務 → 空字串代表「查無」
    df = _df("select name from salesperson where id = %s", (sid,))
    if df.empty:
        return ""
    import re
    return re.sub(r"[-‐]?換$", "", df.iloc[0]["name"] or "")


# ------------------------------------------------------------------ 載入訂單層
def load_deals(ym_from: date, ym_to: date, filters: dict | None = None,
               exclude_barter: bool = True, user: dict | None = None) -> pd.DataFrame:
    """v_deal_summary 期間切片（一列 = 一個合約）。參數化 where。"""
    filters = filters or {}
    where = ["perf_ym between %s and %s"]
    params: list = [ym_from, ym_to]
    if exclude_barter:
        where.append("not is_barter")
    if filters.get("company"):
        where.append("company = %s")
        params.append(filters["company"])
    if filters.get("platform_group"):
        where.append("main_platform_group = %s")
        params.append(filters["platform_group"])
    if filters.get("industry"):
        where.append("industry = %s")
        params.append(filters["industry"])
    if filters.get("salesperson"):
        where.append("salesperson = %s")
        params.append(filters["salesperson"])
    if filters.get("customer"):
        where.append("customer ilike %s")
        params.append(f"%{filters['customer']}%")
    # SALES 只能看自己
    scope = sales_scope_name(user)
    if scope is not None:
        if scope == "":
            where.append("false")
        else:
            where.append("salesperson = %s")
            params.append(scope)
    df = _df(f"select * from v_deal_summary where {' and '.join(where)}", params)
    if df.empty:
        return df
    for c in NUM + _FLOAT_EXTRA:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    if "is_low_margin" in df.columns:
        df["is_low_margin"] = df["is_low_margin"].fillna(False).astype(bool)
    return df


@st.cache_data(ttl=60)
def customer_year(year: int) -> pd.DataFrame:
    """v_customer_year（狀態 / ABC / 距上次交易月數 的來源），index = customer。"""
    df = _df("select * from v_customer_year where perf_year = %s", (year,))
    if df.empty:
        return df
    return df.set_index("customer")


def platform_mix_text(net_cp, net_fresh, net_radio, net_other, top: int = 3) -> str:
    """平台組合 → 可讀文字，如「企頻 63%｜新鮮視 37%」（只列非零、由大到小）。"""
    items = [("企頻", net_cp), ("新鮮視", net_fresh), ("廣播", net_radio), ("其他", net_other)]
    items = [(n, float(v or 0)) for n, v in items if float(v or 0) > 0]
    total = sum(v for _, v in items)
    if total <= 0:
        return ""
    items.sort(key=lambda x: -x[1])
    parts = [f"{n} {round(v / total * 100)}%" for n, v in items[:top]]
    if len(items) > top:
        parts.append("…")
    return "｜".join(parts)


def month_range(ym_from: date, ym_to: date) -> list[date]:
    out, m = [], ym_from
    while m <= ym_to:
        out.append(m)
        m = m + relativedelta(months=1)
    return out


def customer_trends(customers, ym_from: date, ym_to: date) -> tuple[dict, list]:
    """回傳 (dict[customer]->[各月除佣實收], 月清單)。給排名表的月趨勢 sparkline。"""
    months = month_range(ym_from, ym_to)
    customers = list(customers)
    res = {c: [0.0] * len(months) for c in customers}
    if not customers:
        return res, months
    df = _df(
        "select customer, perf_ym, ext_net from v_customer_month "
        "where customer = any(%s) and perf_ym between %s and %s",
        (customers, ym_from, ym_to),
    )
    idx = {m: i for i, m in enumerate(months)}
    for _, r in df.iterrows():
        c, m = r["customer"], r["perf_ym"]
        if c in res and m in idx:
            res[c][idx[m]] = float(r["ext_net"] or 0)
    return res, months


def salesperson_platform(ym_from: date, ym_to: date, filters: dict | None = None,
                         exclude_barter: bool = True, user: dict | None = None,
                         by: str = "platform") -> pd.DataFrame:
    """
    業務 × 平台 的除佣實收總計（line 層，排除內部轉撥）。
    by='platform' → 個別平台（家樂福企頻/健康視…）；by='platform_group' → 平台歸類（企頻/新鮮視…）。
    回傳 pivot：index=業務、欄=各平台、末欄「合計」、末列「（全部業務合計）」。尊重期間 / 公司 / 產業 / 客戶 / SALES 範圍。
    """
    if by not in ("platform", "platform_group"):
        raise ValueError(by)
    filters = filters or {}
    where = ["not is_intercompany", "perf_ym between %s and %s"]
    params: list = [ym_from, ym_to]
    if exclude_barter:
        # 與其他分析一致：排除「整張」交換合約（deal 層 bool_or），非只排交換線
        where.append("contract_no not in (select contract_no from v_line_ext where is_barter)")
    if filters.get("company"):
        where.append("company = %s"); params.append(filters["company"])
    if filters.get("platform_group"):
        where.append("platform_group = %s"); params.append(filters["platform_group"])
    if filters.get("industry"):
        where.append("industry = %s"); params.append(filters["industry"])
    if filters.get("customer"):
        where.append("customer ilike %s"); params.append(f"%{filters['customer']}%")
    scope = sales_scope_name(user)
    if scope is not None:
        if scope == "":
            where.append("false")
        else:
            where.append("salesperson_base = %s"); params.append(scope)
    df = _df(
        f"select salesperson_base as salesperson, {by} as col, sum(net_amount) as net "
        f"from v_line_ext where {' and '.join(where)} and salesperson_base <> '' "
        f"group by 1, 2", params)
    if df.empty:
        return df
    df["net"] = df["net"].astype(float)
    piv = df.pivot_table(index="salesperson", columns="col", values="net", aggfunc="sum").fillna(0.0)
    # 欄依總額由大到小排；加「合計」欄與總計列
    piv = piv[piv.sum(axis=0).sort_values(ascending=False).index]
    piv["合計"] = piv.sum(axis=1)
    piv = piv.sort_values("合計", ascending=False)
    piv.loc["（全部業務合計）"] = piv.sum(numeric_only=True)
    return piv


def query_reasons(deal_ids: list) -> dict:
    """回傳 {deal_id: 低毛利原因}（取該合約任一非空原因）。"""
    if not deal_ids:
        return {}
    df = _df(
        "select deal_id, max(low_margin_reason) as reason from deal_line "
        "where deal_id = any(%s) and low_margin_reason is not null group by deal_id",
        (list(deal_ids),))
    if df.empty:
        return {}
    return {int(r["deal_id"]): r["reason"] for _, r in df.iterrows()}


def load_barter_by(dim: str, ym_from: date, ym_to: date) -> pd.Series:
    """交換金額（is_barter）依 dim（salesperson / company）彙總，回 Series。"""
    if dim not in ("salesperson", "company"):
        raise ValueError(dim)
    df = _df(
        f"select {dim} as k, sum(ext_net) as barter from v_deal_summary "
        f"where is_barter and perf_ym between %s and %s group by 1",
        (ym_from, ym_to),
    )
    if df.empty:
        return pd.Series(dtype=float)
    return df.set_index("k")["barter"].astype(float)


# ------------------------------------------------------------------ 客戶彙總
def _strategy_hint(booked_margin: float, rank: int) -> str:
    if booked_margin is None:
        return "一般"
    if booked_margin >= 0.35 and rank <= 20:
        return "核心：大額高毛利，優先維護"
    if booked_margin < 0.16 and rank <= 20:
        return "大額低毛利：檢討報價/成本"
    if booked_margin >= 0.35:
        return "小額高毛利：可擴大"
    if booked_margin < 0.16:
        return "小額低毛利：評估是否續做"
    return "一般"


def agg_customers(df: pd.DataFrame, prev_df: pd.DataFrame | None = None,
                  cy: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    客戶排名主表（規格 = generator 的 cust）。
    df / prev_df：本期 / 同期 v_deal_summary（已排除交換）。cy：v_customer_year 本年。
    回傳含：ext_net、三層毛利與毛利率、deals、active_months、main_salesperson、
    prev_net、yoy_pct、status、rank_in_year、share、cum_share、abc_tier、avg_deal、
    strategy_hint、industry、months_since_last、平台四欄。
    """
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["ext_net"] > 0]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("customer")
    out = g[NUM].sum()
    out["deals"] = g.size()
    out["active_months"] = g["perf_ym"].nunique()
    out["main_salesperson"] = g.apply(
        lambda x: x.groupby("salesperson")["ext_net"].sum().idxmax())

    # 同期
    if prev_df is not None and not prev_df.empty:
        cp = prev_df[prev_df["ext_net"] > 0].groupby("customer")["ext_net"].sum()
    else:
        cp = pd.Series(dtype=float)
    out["prev_net"] = cp.reindex(out.index)
    out["yoy_pct"] = (out["ext_net"] - out["prev_net"]) / out["prev_net"].abs()

    # 狀態 / 距上次交易 / 產業（來自 v_customer_year）
    if cy is not None and not cy.empty:
        join_cols = [c for c in ("status", "months_since_last", "industry", "customer_category")
                     if c in cy.columns]
        out = out.join(cy[join_cols], how="left")
    out["status"] = out["status"].fillna("既有") if "status" in out.columns else "既有"

    out = out.sort_values("ext_net", ascending=False)
    out["rank_in_year"] = range(1, len(out) + 1)
    total = out["ext_net"].sum()
    out["share"] = out["ext_net"] / total if total else 0.0
    out["cum_share"] = out["share"].cumsum()
    out["abc_tier"] = out["cum_share"].map(lambda s: "A" if s <= 0.8 else ("B" if s <= 0.95 else "C"))
    out["booked_margin"] = out["booked_profit"] / out["ext_net"]
    out["group_margin"] = out["group_profit"] / out["ext_net"]
    out["net_margin"] = out["net_profit"] / out["ext_net"]
    out["avg_deal"] = out["ext_net"] / out["deals"]
    out["strategy_hint"] = out.apply(
        lambda r: _strategy_hint(r["booked_margin"], int(r["rank_in_year"])), axis=1)
    return out.reset_index()


def agg_industries(df: pd.DataFrame, prev_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """產業別彙總（規格 = generator 的 ind）。"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["ext_net"] > 0].copy()
    d["industry"] = d["industry"].fillna("(未分類)")
    ig = d.groupby("industry").agg(
        customers=("customer", "nunique"), deals=("deal_id", "count"),
        ext_net=("ext_net", "sum"), booked_profit=("booked_profit", "sum")).reset_index()
    ig["booked_margin"] = ig["booked_profit"] / ig["ext_net"]
    ig["share"] = ig["ext_net"] / ig["ext_net"].sum()
    if prev_df is not None and not prev_df.empty:
        p = prev_df[prev_df["ext_net"] > 0].copy()
        p["industry"] = p["industry"].fillna("(未分類)")
        prev = p.groupby("industry")["ext_net"].sum()
        ig["prev"] = ig["industry"].map(prev)
        ig["yoy_pct"] = (ig["ext_net"] - ig["prev"]) / ig["prev"].abs()
    ig = ig.sort_values("ext_net", ascending=False).reset_index(drop=True)
    ig["rank_in_year"] = range(1, len(ig) + 1)
    return ig


# ------------------------------------------------------------------ 業務彙總
def new_customers_by_salesperson(cust_df: pd.DataFrame) -> pd.Series:
    """由 cust 表算「該業務帶進的新客數」（generator：cw[status=='新客'].groupby(main_salesperson)）。"""
    if cust_df is None or cust_df.empty or "status" not in cust_df.columns:
        return pd.Series(dtype=int)
    return cust_df[cust_df["status"] == "新客"].groupby("main_salesperson").size()


def agg_salespeople(df: pd.DataFrame, prev_df: pd.DataFrame | None = None,
                    new_by_sp: pd.Series | None = None,
                    barter_by_sp: pd.Series | None = None) -> pd.DataFrame:
    """
    業務排名主表（規格 = generator 的 sp）。公司戶（is_house）另排、列在最後。
    """
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["ext_net"] > 0]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("salesperson")
    cols = NUM + (["recognized_amount"] if "recognized_amount" in d.columns else [])
    out = g[cols].sum()
    out["deals"] = g.size()
    out["customers"] = g["customer"].nunique()
    out["main_company"] = g.apply(lambda x: x.groupby("company")["ext_net"].sum().idxmax())
    out["main_group"] = g.apply(lambda x: x.groupby("business_group")["ext_net"].sum().idxmax())
    out["is_house"] = g["is_house"].any()

    def _top3(x):
        s = x.groupby("customer")["ext_net"].sum().sort_values(ascending=False)
        return pd.Series({"top3_net": s.head(3).sum(),
                          "top1_net": s.iloc[0] if len(s) else 0.0,
                          "top_customer": s.index[0] if len(s) else None})
    out = out.join(g.apply(_top3))

    if prev_df is not None and not prev_df.empty:
        sp = prev_df[prev_df["ext_net"] > 0].groupby("salesperson")["ext_net"].sum()
    else:
        sp = pd.Series(dtype=float)
    out["prev_net"] = sp.reindex(out.index)
    out["yoy_pct"] = (out["ext_net"] - out["prev_net"]) / out["prev_net"].abs()

    if new_by_sp is not None:
        out["new_customers"] = new_by_sp.reindex(out.index).fillna(0).astype(int)
    else:
        out["new_customers"] = 0
    if barter_by_sp is not None:
        out["barter_net"] = barter_by_sp.reindex(out.index).fillna(0).astype(float)
    else:
        out["barter_net"] = 0.0

    out["booked_margin"] = out["booked_profit"] / out["ext_net"]
    out["group_margin"] = out["group_profit"] / out["ext_net"]
    out["net_margin"] = out["net_profit"] / out["ext_net"]
    out["avg_deal"] = out["ext_net"] / out["deals"]
    out["top3_share"] = out["top3_net"] / out["ext_net"]
    out["top1_share"] = out["top1_net"] / out["ext_net"]
    out = out.sort_values(["is_house", "ext_net"], ascending=[True, False]).reset_index()
    out["rank_in_year"] = out.groupby("is_house").cumcount() + 1
    out["share"] = out["ext_net"] / out["ext_net"].sum()
    return out


# ------------------------------------------------------------------ 銷售（訂單）分佈
def size_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """訂單金額級距（有收入訂單）：筆數、金額、帳上毛利、毛利率。"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["ext_net"] > 0]
    if d.empty:
        return pd.DataFrame()
    sb = d.groupby("size_bucket").agg(
        n=("deal_id", "count"), net=("ext_net", "sum"),
        gp=("booked_profit", "sum")).reset_index().sort_values("size_bucket")
    sb["booked_margin"] = sb["gp"] / sb["net"]
    return sb


def margin_band(m) -> str:
    m = float(m or 0)
    if m < 0:
        return "1. <0%（虧損）"
    if m < 0.16:
        return "2. 0–16%（低毛利）"
    if m < 0.35:
        return "3. 16–35%"
    if m < 0.5:
        return "4. 35–50%"
    return "5. >50%"


def margin_bands(df: pd.DataFrame) -> pd.DataFrame:
    """毛利率分佈（有收入訂單）：筆數、金額。"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["ext_net"] > 0].copy()
    if d.empty:
        return pd.DataFrame()
    d["band"] = d["booked_margin"].map(margin_band)
    mb = d.groupby("band").agg(
        n=("deal_id", "count"), net=("ext_net", "sum")).reset_index().sort_values("band")
    return mb


# ------------------------------------------------------------------ UI 元件
def kpi_row(items: list[dict]) -> None:
    """一列 KPI 卡。item：{label, value, sub?, delta?}（delta 為同期比率，會顯示成 chip）。"""
    from core.format import pct
    cols = st.columns(len(items) or 1)
    for col, it in zip(cols, items):
        with col:
            delta = it.get("delta")
            delta_txt = None
            if delta is not None and not (isinstance(delta, float) and pd.isna(delta)):
                delta_txt = f"{pct(delta, already_ratio=True)} 同期"
            st.metric(it["label"], it["value"], delta=delta_txt)
            if it.get("sub"):
                st.caption(it["sub"])


def filter_bar_analysis(key: str, *, user: dict | None = None,
                        show_industry: bool = True, show_salesperson: bool = True,
                        show_house_toggle: bool = False) -> dict:
    """
    分析頁共用篩選列。回傳 dict：ym_from, ym_to, company, platform_group, industry,
    salesperson, customer, exclude_barter, include_house。
    期間預設 今年 1 月 → 截止月。SALES 角色隱藏業務篩選（自動限縮）。
    """
    from core.format import ym_text
    from core import data as _data

    user = user or current_user()
    is_sales = bool(user and user.get("role") == "SALES")
    months = analysis_months()
    def_from, def_to = window_defaults()
    out: dict = {}

    c1, c2 = st.columns(2)
    if months:
        labels = {m: ym_text(m) for m in months}
        # 期間起：預設今年 1 月（不在清單就取最接近）
        from_default = def_from if def_from in months else min(months, key=lambda m: abs((m - def_from).days))
        to_default = def_to if def_to in months else months[0]
        out["ym_from"] = c1.selectbox("期間（起）", months, index=months.index(from_default),
                                      format_func=lambda m: labels[m], key=f"{key}_ymf")
        out["ym_to"] = c2.selectbox("期間（迄）", months, index=months.index(to_default),
                                    format_func=lambda m: labels[m], key=f"{key}_ymt")
    else:
        out["ym_from"], out["ym_to"] = def_from, def_to

    row = st.columns(4)
    with row[0]:
        comps = [None] + [o[1] for o in _data.options("company")]
        out["company"] = st.selectbox("公司別", comps,
                                      format_func=lambda v: "全部" if v is None else v, key=f"{key}_co")
    with row[1]:
        pgs = [None] + _data.platform_groups()
        out["platform_group"] = st.selectbox("平台歸類", pgs,
                                              format_func=lambda v: "全部" if v is None else v, key=f"{key}_pg")
    with row[2]:
        if show_industry:
            inds = [None] + [o[1] for o in _data.options("industry")]
            out["industry"] = st.selectbox("產業別", inds,
                                           format_func=lambda v: "全部" if v is None else v, key=f"{key}_ind")
        else:
            out["industry"] = None
    with row[3]:
        if show_salesperson and not is_sales:
            sps = [None] + [o[1] for o in _data.options("salesperson")]
            out["salesperson"] = st.selectbox("業務", sps,
                                              format_func=lambda v: "全部" if v is None else v, key=f"{key}_sp")
        else:
            out["salesperson"] = None

    row2 = st.columns([2, 1, 1])
    with row2[0]:
        out["customer"] = st.text_input("客戶（模糊）", key=f"{key}_cust")
    with row2[1]:
        out["exclude_barter"] = st.checkbox("排除交換", value=True, key=f"{key}_barter")
    with row2[2]:
        if show_house_toggle:
            out["include_house"] = st.checkbox("含公司戶", value=True, key=f"{key}_house")
        else:
            out["include_house"] = True
    return out


def show_ranking(df: pd.DataFrame, columns: list, *, height: int | None = 460,
                 key: str | None = None, on_select=None, selection_mode="single-row"):
    """
    統一的排名表渲染。columns：list of (col, header, kind[, opts])。
    kind：text / money / int / pct / progress / bar / line。
    money 用千分位（localized）、pct 百分比、progress 佔比長條、bar 平台組合、line 月趨勢。
    """
    if df is None or df.empty:
        st.info("查無資料")
        return None
    disp = pd.DataFrame(index=df.index)
    cfg: dict = {}
    order: list[str] = []
    for spec in columns:
        col, header, kind = spec[0], spec[1], spec[2]
        opts = spec[3] if len(spec) > 3 else {}
        order.append(header)
        if kind in ("money", "int"):
            disp[header] = pd.to_numeric(df[col], errors="coerce").round(0)
            cfg[header] = st.column_config.NumberColumn(header, format="localized")
        elif kind == "pct":
            disp[header] = pd.to_numeric(df[col], errors="coerce")
            cfg[header] = st.column_config.NumberColumn(header, format="percent")
        elif kind == "progress":
            v = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            disp[header] = v
            mx = opts.get("max")
            if not mx or mx <= 0:
                mx = float(v.max()) if len(v) and float(v.max()) > 0 else 1.0
            cfg[header] = st.column_config.ProgressColumn(
                header, format="percent", min_value=0.0, max_value=float(mx))
        elif kind == "bar":
            disp[header] = df[col].values
            cfg[header] = st.column_config.BarChartColumn(header, help=opts.get("help"))
        elif kind == "line":
            disp[header] = df[col].values
            cfg[header] = st.column_config.LineChartColumn(header, help=opts.get("help"))
        else:  # text
            disp[header] = df[col].astype(object)
            cfg[header] = st.column_config.TextColumn(header)
    kwargs = dict(column_config=cfg, hide_index=True, use_container_width=True, key=key)
    if isinstance(height, int) and height > 0:
        kwargs["height"] = height   # None → 讓 Streamlit 自動高度（1.63 不接受 height=None）
    if on_select is not None:
        kwargs["on_select"] = on_select
        kwargs["selection_mode"] = selection_mode
    return st.dataframe(disp[order], **kwargs)


def filter_text(f: dict) -> str:
    """篩選條件 → Excel 副標。"""
    from core.format import ym_text
    parts = [f"{ym_text(f['ym_from'])}–{ym_text(f['ym_to'])}"]
    for k, lab in (("company", "公司"), ("platform_group", "平台歸類"),
                   ("industry", "產業"), ("salesperson", "業務"), ("customer", "客戶")):
        if f.get(k):
            parts.append(f"{lab}={f[k]}")
    if f.get("exclude_barter"):
        parts.append("排除交換")
    return "　".join(parts)
