"""
data.py — 主檔快取與常用查詢

主檔讀取全部 @st.cache_data(ttl=60)；任何寫入主檔後呼叫 clear_cache()。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect  # noqa: E402


def _df(sql: str, params=None) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def clear_cache() -> None:
    """寫入主檔後呼叫，讓下拉選單立即反映。"""
    st.cache_data.clear()


def query_df(sql: str, params=None) -> pd.DataFrame:
    """給頁面做臨時唯讀查詢用（不快取）。"""
    return _df(sql, params)


# ------------------------------------------------------------------ 主檔清單
@st.cache_data(ttl=60)
def companies() -> pd.DataFrame:
    return _df("select id, name, is_parent, sort_order, is_active from company order by sort_order, name")


@st.cache_data(ttl=60)
def business_groups() -> pd.DataFrame:
    return _df("select id, name, company_id, is_intercompany, sort_order, is_active from business_group order by sort_order, name")


@st.cache_data(ttl=60)
def salespersons() -> pd.DataFrame:
    return _df("select id, name, group_id, manager_name, is_active from salesperson order by name")


@st.cache_data(ttl=60)
def staff() -> pd.DataFrame:
    return _df("select id, name, roles, is_active from staff order by name")


@st.cache_data(ttl=60)
def industries() -> pd.DataFrame:
    return _df("select id, name from industry order by name")


@st.cache_data(ttl=60)
def customer_categories() -> pd.DataFrame:
    return _df("select id, name from customer_category order by name")


@st.cache_data(ttl=60)
def sales_categories() -> pd.DataFrame:
    return _df("select id, name, parent_category, recognition_ratio, is_active from sales_category order by name")


@st.cache_data(ttl=60)
def platforms() -> pd.DataFrame:
    return _df("select id, name, platform_group, default_region, sort_order, is_active from platform order by sort_order, name")


@st.cache_data(ttl=60)
def platform_groups() -> list[str]:
    df = _df("select distinct platform_group from platform where platform_group is not null order by platform_group")
    return df["platform_group"].tolist() if not df.empty else []


@st.cache_data(ttl=60)
def media_channels() -> pd.DataFrame:
    return _df("select id, name, channel_type, is_designated, tax_rate, sort_order, is_active from media_channel order by sort_order, name")


@st.cache_data(ttl=60)
def programs() -> pd.DataFrame:
    return _df("select id, name, media_channel_id from program order by name")


@st.cache_data(ttl=60)
def regions() -> pd.DataFrame:
    return _df("select code, name, sort_order from region order by sort_order")


@st.cache_data(ttl=60)
def customers() -> pd.DataFrame:
    return _df(
        """select id, name, customer_category_id, industry_id, tax_id, contact_person,
                  phone, email, is_new_case, is_top1000, notes, is_active
           from customer order by name"""
    )


@st.cache_data(ttl=60)
def months() -> list[date]:
    """有資料的業績年月（新到舊）。"""
    df = _df("select perf_ym from v_months order by perf_ym desc")
    return df["perf_ym"].tolist() if not df.empty else []


@st.cache_data(ttl=60)
def fixed_cost_rules() -> pd.DataFrame:
    return _df(
        """select r.id, r.platform_group, r.platform_id, p.name as platform, r.media_channel_id,
                  mc.name as media_channel, r.company_id, c.name as company,
                  r.ym_from, r.ym_to, r.monthly_amount, r.note
           from fixed_cost_rule r
           left join platform p on p.id = r.platform_id
           left join media_channel mc on mc.id = r.media_channel_id
           left join company c on c.id = r.company_id
           order by r.ym_from desc, r.id"""
    )


@st.cache_data(ttl=60)
def intercompany_rules() -> pd.DataFrame:
    return _df(
        """select r.id, r.from_company_id, cf.name as from_company, r.to_company_id, ct.name as to_company,
                  r.platform_group, r.rate, r.ym_from, r.ym_to, r.note
           from intercompany_rule r
           join company cf on cf.id = r.from_company_id
           join company ct on ct.id = r.to_company_id
           order by r.ym_from desc, r.id"""
    )


@st.cache_data(ttl=60)
def bonus_rules() -> pd.DataFrame:
    return _df(
        """select r.id, r.salesperson_id, sp.name as salesperson, r.platform_group, r.sales_item,
                  r.ym_from, r.ym_to, r.bonus_pct, r.threshold_amount, r.note
           from bonus_rule r
           left join salesperson sp on sp.id = r.salesperson_id
           order by r.ym_from desc, r.id"""
    )


# ------------------------------------------------------------------ selectbox helper
def options(table: str, *, active_only: bool = True) -> list[tuple]:
    """回傳 [(id, name), ...] 供 selectbox。region 用 code 當 id。"""
    getter = {
        "company": companies, "business_group": business_groups, "salesperson": salespersons,
        "staff": staff, "industry": industries, "customer_category": customer_categories,
        "sales_category": sales_categories, "platform": platforms, "media_channel": media_channels,
        "program": programs, "customer": customers, "region": regions,
    }.get(table)
    if getter is None:
        raise ValueError(f"未知主檔：{table}")
    df = getter()
    if df.empty:
        return []
    key = "code" if table == "region" else "id"
    if active_only and "is_active" in df.columns:
        df = df[df["is_active"] != False]  # noqa: E712
    return list(zip(df[key], df["name"]))


# ------------------------------------------------------------------ 客戶搜尋（登打帶出舊資料）
def customer_lookup(text: str, limit: int = 20) -> pd.DataFrame:
    """name ilike 或 別名 ilike，回傳前 N 筆。"""
    text = (text or "").strip()
    if not text:
        return pd.DataFrame(columns=["id", "name"])
    like = f"%{text}%"
    return _df(
        """select distinct c.id, c.name, c.customer_category_id, c.industry_id
           from customer c
           left join customer_alias a on a.customer_id = c.id
           where c.name ilike %s or a.alias ilike %s
           order by c.name
           limit %s""",
        (like, like, limit),
    )
