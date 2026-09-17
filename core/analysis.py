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
from datetime import date, datetime
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
       "net_cp", "net_fresh", "net_radio", "net_other",
       "net_cp_family", "net_cp_carrefour", "net_clinic"]   # 007：報表平台四欄+健康視
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


def _as_date(v) -> date:
    """把 date / pandas Timestamp / datetime 一律轉成 datetime.date（避免型別不一致比較失敗）。"""
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return pd.Timestamp(v).date()


@st.cache_data(ttl=60)
def as_of() -> dict:
    """分析用截止月：最後一個已結束的月份（本月進行中不算，見 sql/006）。"""
    df = _df("select as_of_ym, as_of_year, as_of_month from v_as_of")
    if df.empty or df.iloc[0]["as_of_ym"] is None:
        today = date.today().replace(day=1)
        return {"as_of_ym": today, "as_of_year": today.year, "as_of_month": today.month}
    r = df.iloc[0]
    return {"as_of_ym": _as_date(r["as_of_ym"]), "as_of_year": int(r["as_of_year"]),
            "as_of_month": int(r["as_of_month"])}


def window_defaults() -> tuple[date, date]:
    """所有分析頁的預設期間 = (今年 1 月, 截止月)。
    「今年」綁日曆當年（date.today）；只有當年尚無任何資料時才退回截止月所在年，避免預設落到空區間。"""
    ao = as_of()
    this_year = date.today().year
    start_year = this_year if ao["as_of_ym"] >= date(this_year, 1, 1) else ao["as_of_year"]
    return date(start_year, 1, 1), ao["as_of_ym"]


def prev_window(ym_from: date, ym_to: date) -> tuple[date, date]:
    """去年同一段月份。"""
    return ym_from - relativedelta(years=1), ym_to - relativedelta(years=1)


@st.cache_data(ttl=60)
def analysis_months() -> list[date]:
    """
    期間下拉的可選月份（新到舊）：只到本月，排除未來的預登月份（如 2027 的預登），
    並統一成 datetime.date（避免與 as_of 的型別不一致，導致預設迄月落到 months[0]）。
    """
    df = _df(
        "select perf_ym from v_months where perf_ym <= date_trunc('month', current_date)::date "
        "order by perf_ym desc")
    return [_as_date(m) for m in df["perf_ym"].tolist()] if not df.empty else []


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
@st.cache_data(ttl=60)
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


# ------------------------------------------------------------------ 口徑（scope）與線層載入（階段 K / TASK_4 §3.5）
# 老闆報表平台的固定欄序
REPORT_PLATFORM_ORDER = ["全家企頻", "萬家福", "新鮮視", "廣播", "健康視", "營運", "其它"]
OWN_MEDIA = ["全家企頻", "萬家福", "新鮮視", "健康視"]          # 自媒體（不含廣播）
MEDIA_PLATFORMS = ["全家企頻", "萬家福", "新鮮視", "廣播", "健康視"]  # 老闆四欄 + 健康視

# 三個口徑的預設旗標（自訂＝可逐項覆寫）
SCOPE_PRESETS: dict[str, dict] = {
    # 分析口徑（現狀、預設）：全部對外線（含製作收入）、全部平台、排除交換、含公司戶、不含轉撥
    "analysis": dict(include_production=True, include_barter=False, include_house=True,
                     include_ops_other=True, merge_ruidi=False),
    # 發稿口徑（老闆版）：只 MEDIA、四平台+健康視、含交換（併回原業務）、含公司戶、不含轉撥
    "media": dict(include_production=False, include_barter=True, include_house=True,
                  include_ops_other=False, merge_ruidi=False),
    # 自訂：預設同發稿口徑，再讓使用者逐項勾
    "custom": dict(include_production=False, include_barter=True, include_house=True,
                   include_ops_other=False, merge_ruidi=False),
}


def resolve_scope(scope: dict | str | None) -> dict:
    """把 scope（preset 字串或 dict）正規化成含五個旗標 + preset 的 dict。"""
    if isinstance(scope, str):
        scope = {"preset": scope}
    scope = scope or {}
    preset = scope.get("preset", "analysis")
    out = dict(SCOPE_PRESETS.get(preset, SCOPE_PRESETS["analysis"]))
    for k, v in scope.items():
        if k != "preset":
            out[k] = v
    out["preset"] = preset
    return out


def _scope_where(scope: dict) -> list[str]:
    """由 scope 旗標組出 v_report_line 的 where 片段（轉撥線一律不含）。"""
    s = resolve_scope(scope)
    where = ["not is_intercompany"]
    if not s["include_production"]:
        where.append("line_type <> 'PRODUCTION'")
    if not s["include_ops_other"]:
        where.append("report_platform not in ('營運','其它')")
    if not s["include_barter"]:
        where.append("not is_barter")
    if not s["include_house"]:
        where.append("not is_house")
    return where


# 線層 Python 端要轉 float 的數值欄
_LINE_NUM = ["net_amount", "cost_amount", "booked_profit", "gross_amount",
             "recognized_amount", "total_seconds", "purchased_slots"]


@st.cache_data(ttl=60)
def load_lines(ym_from: date, ym_to: date, scope: dict | str | None = None,
               filters: dict | None = None, user: dict | None = None) -> pd.DataFrame:
    """
    v_report_line 期間切片（一列 = 一條發稿線），依 scope 過濾。交換併回原業務（salesperson_merged）。
    合約層才有的欄位（group_profit / net_profit / size_bucket / is_low_margin）需要時用 deal_id
    從 v_deal_summary 併回，這裡只給線層原生欄。
    """
    filters = filters or {}
    where = ["perf_ym between %s and %s"] + _scope_where(scope)
    params: list = [ym_from, ym_to]
    if filters.get("company"):
        where.append("company = %s"); params.append(filters["company"])
    if filters.get("report_platform"):
        where.append("report_platform = %s"); params.append(filters["report_platform"])
    if filters.get("platform_group"):
        where.append("platform_group = %s"); params.append(filters["platform_group"])
    if filters.get("industry"):
        where.append("industry = %s"); params.append(filters["industry"])
    if filters.get("salesperson"):
        where.append("salesperson_merged = %s"); params.append(filters["salesperson"])
    if filters.get("customer"):
        where.append("customer ilike %s"); params.append(f"%{filters['customer']}%")
    # SALES 只能看自己（用併回後的業務名）
    sc = sales_scope_name(user)
    if sc is not None:
        if sc == "":
            where.append("false")
        else:
            where.append("salesperson_merged = %s"); params.append(sc)
    df = _df(f"select * from v_report_line where {' and '.join(where)}", params)
    if df.empty:
        return df
    for c in _LINE_NUM:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    if resolve_scope(scope)["merge_ruidi"] and "company" in df.columns:
        df["company"] = df["company"].replace({"瑞迪": "東吳"})
    return df


def scope_bridge(ym_from: date, ym_to: date) -> list[tuple[str, float]]:
    """
    分析口徑（線層、排除交換、全部線）→ 發稿口徑 的橋，回傳 [(標籤, 金額), …]，
    最後一項是「發稿口徑」總額。用來回答老闆「為什麼你的數字跟我的不一樣」。
    """
    rows = _df(
        """select
             sum(net_amount) filter (where not is_intercompany and not is_barter)                          as analysis,
             sum(net_amount) filter (where not is_intercompany and not is_barter and line_type='PRODUCTION') as prod,
             sum(net_amount) filter (where not is_intercompany and not is_barter and line_type='MEDIA' and report_platform='營運') as ops,
             sum(net_amount) filter (where not is_intercompany and not is_barter and line_type='MEDIA' and report_platform='其它') as other,
             sum(net_amount) filter (where is_barter and in_media_scope)                                    as barter_media,
             sum(net_amount) filter (where in_media_scope)                                                  as media
           from v_report_line where perf_ym between %s and %s""",
        (ym_from, ym_to))
    if rows.empty:
        return []
    r = rows.iloc[0]
    f = lambda v: float(v or 0)
    return [
        ("分析口徑（線層、排除交換）", f(r["analysis"])),
        ("− 製作收入線", -f(r["prod"])),
        ("− 營運（企頻年度維運）", -f(r["ops"])),
        ("− 其它平台", -f(r["other"])),
        ("＋ 交換（媒體線，併回業績）", f(r["barter_media"])),
        ("＝ 發稿口徑", f(r["media"])),
    ]


def line_group_profit(lines: pd.DataFrame) -> pd.Series:
    """
    把每條線依合約比例分回「集團毛利」（§4.1）：line.net / deal.ext_net × deal.group_profit。
    回傳與 lines 對齊的 Series。轉撥線或 ext_net=0 的合約給 0。
    """
    empty = pd.Series(0.0, index=(lines.index if lines is not None else None), dtype=float)
    if lines is None or lines.empty or "deal_id" not in lines.columns:
        return empty
    ids = [int(x) for x in lines["deal_id"].dropna().unique().tolist()]
    if not ids:
        return empty
    ds = _df("select deal_id, ext_net, group_profit from v_deal_summary where deal_id = any(%s)", (ids,))
    if ds.empty:
        return empty
    ds = ds.set_index("deal_id")
    en = pd.to_numeric(ds["ext_net"], errors="coerce")
    gp = pd.to_numeric(ds["group_profit"], errors="coerce")
    margin = (gp / en.where(en != 0)).fillna(0.0)   # 每合約集團毛利率
    return (lines["net_amount"] * lines["deal_id"].map(margin)).fillna(0.0).astype(float)


def _plat_cols(lines: pd.DataFrame, index_col: str) -> pd.DataFrame:
    """把線層 df 依 index_col × report_platform 樞紐出四平台欄（全家企頻/萬家福/新鮮視/廣播）。"""
    piv = lines.pivot_table(index=index_col, columns="report_platform", values="net_amount",
                            aggfunc="sum", fill_value=0.0)
    ren = {"全家企頻": "net_cp_family", "萬家福": "net_cp_carrefour", "新鮮視": "net_fresh", "廣播": "net_radio"}
    for k, v in ren.items():
        piv[v] = piv[k] if k in piv.columns else 0.0
    return piv[list(ren.values())]


def agg_customers_lines(lines: pd.DataFrame, prev_lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    發稿口徑/自訂口徑用的客戶排名（線層彙總）。欄位：ext_net/cost/booked_profit/group_profit 與毛利率、
    deals、客戶跨公司/業務、四平台、佔比、排名、同期%。不含 status/ABC/strategy（那是分析口徑概念）。
    """
    if lines is None or lines.empty:
        return pd.DataFrame()
    d = lines.copy()
    d["_gp"] = line_group_profit(d)
    g = d.groupby("customer")
    out = pd.DataFrame(index=g.size().index)
    out["ext_net"] = g["net_amount"].sum()
    out["cost"] = g["cost_amount"].sum()
    out["booked_profit"] = out["ext_net"] - out["cost"]
    out["group_profit"] = g["_gp"].sum()
    out["deals"] = g["deal_id"].nunique()
    out["main_salesperson"] = g.apply(lambda x: x.groupby("salesperson_merged")["net_amount"].sum().idxmax())
    out["companies_multi"] = g.apply(lambda x: "、".join(x.groupby("company")["net_amount"].sum().sort_values(ascending=False).index))
    out["salespeople_multi"] = g.apply(lambda x: "、".join(x.groupby("salesperson_merged")["net_amount"].sum().sort_values(ascending=False).index[:5]))
    out = out.join(_plat_cols(d, "customer"))
    out = out[out["ext_net"] != 0].sort_values("ext_net", ascending=False)
    total = out["ext_net"].sum()
    out["share"] = out["ext_net"] / total if total else 0.0
    out["cum_share"] = out["share"].cumsum()
    out["booked_margin"] = out["booked_profit"] / out["ext_net"].where(out["ext_net"] != 0)
    out["group_margin"] = out["group_profit"] / out["ext_net"].where(out["ext_net"] != 0)
    out["rank_in_year"] = range(1, len(out) + 1)
    if prev_lines is not None and not prev_lines.empty:
        pv = prev_lines.groupby("customer")["net_amount"].sum()
        out["prev_net"] = pv.reindex(out.index)
        out["yoy_pct"] = (out["ext_net"] - out["prev_net"]) / out["prev_net"].abs()
        from core.format import pct as _pct
        out["yoy_text"] = out.apply(lambda r: "新" if pd.isna(r["prev_net"]) or r["prev_net"] == 0 else _pct(r["yoy_pct"]), axis=1)
    else:
        out["yoy_text"] = ""
    return out.reset_index()


def agg_salespeople_lines(lines: pd.DataFrame, prev_lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """發稿口徑/自訂口徑用的業務排名（線層）。公司戶（is_house）另排、列最後。"""
    if lines is None or lines.empty:
        return pd.DataFrame()
    d = lines.copy()
    d["_gp"] = line_group_profit(d)
    g = d.groupby("salesperson_merged")
    out = pd.DataFrame(index=g.size().index)
    out["ext_net"] = g["net_amount"].sum()
    out["cost"] = g["cost_amount"].sum()
    out["booked_profit"] = out["ext_net"] - out["cost"]
    out["group_profit"] = g["_gp"].sum()
    out["deals"] = g["deal_id"].nunique()
    out["customers"] = g["customer_id"].nunique()
    out["main_company"] = g.apply(lambda x: x.groupby("company")["net_amount"].sum().idxmax())
    out["is_house"] = g.apply(lambda x: bool(x["is_house"].any()))
    out = out.join(_plat_cols(d, "salesperson_merged"))
    out = out[out["ext_net"] != 0]
    out["booked_margin"] = out["booked_profit"] / out["ext_net"].where(out["ext_net"] != 0)
    out["group_margin"] = out["group_profit"] / out["ext_net"].where(out["ext_net"] != 0)
    out = out.reset_index().rename(columns={"salesperson_merged": "salesperson"})
    out = out.sort_values(["is_house", "ext_net"], ascending=[True, False]).reset_index(drop=True)
    out["rank_in_year"] = out.groupby("is_house").cumcount() + 1
    tot = out["ext_net"].sum()
    out["share"] = out["ext_net"] / tot if tot else 0.0
    if prev_lines is not None and not prev_lines.empty:
        pv = prev_lines.groupby("salesperson_merged")["net_amount"].sum()
        out["prev_net"] = out["salesperson"].map(pv)
        out["yoy_pct"] = (out["ext_net"] - out["prev_net"]) / out["prev_net"].abs()
        from core.format import pct as _pct
        out["yoy_text"] = out.apply(lambda r: "新" if pd.isna(r["prev_net"]) or r["prev_net"] == 0 else _pct(r["yoy_pct"]), axis=1)
    else:
        out["yoy_text"] = ""
    return out


def open_month() -> dict | None:
    """本月（進行中）概況：perf_ym / deals / ext_net / last_entry。無資料回 None。"""
    df = _df("select perf_ym, deals, ext_net, last_entry from v_open_month")
    if df.empty or df.iloc[0]["deals"] in (0, None):
        return None
    r = df.iloc[0]
    return {"perf_ym": r["perf_ym"], "deals": int(r["deals"]),
            "ext_net": float(r["ext_net"] or 0), "last_entry": r["last_entry"]}


def margin_kpis(dw: pd.DataFrame) -> dict:
    """
    統一的毛利率口徑（P0-2）：以期間內全部非交換訂單（含零收入成本單）計算。
    回傳 booked/group/net（三層毛利率）與 booked_rev_only（只看有收入訂單的帳上毛利率）。
    """
    if dw is None or dw.empty:
        return {"ext_net": 0.0, "booked": None, "group": None, "net": None, "booked_rev_only": None}
    en = float(dw["ext_net"].sum())
    bp = float(dw["booked_profit"].sum())
    gp = float(dw["group_profit"].sum())
    npf = float(dw["net_profit"].sum())
    d = dw[dw["ext_net"] > 0]
    en_r = float(d["ext_net"].sum())
    bp_r = float(d["booked_profit"].sum())
    return {"ext_net": en,
            "booked": bp / en if en else None,
            "group": gp / en if en else None,
            "net": npf / en if en else None,
            "booked_rev_only": bp_r / en_r if en_r else None}


def churn_list(prev_df: pd.DataFrame, cur_df: pd.DataFrame, threshold: float = 300000):
    """
    流失風險（P0-4，KPI 與清單同口徑）：去年同段 ≥ threshold 且本期無收入的客戶。
    回傳 DataFrame：customer、prev_net、last_txn（去年同段最後交易月）、months_since_last、main_salesperson、industry。
    """
    cols = ["customer", "prev_net", "last_txn", "months_since_last", "main_salesperson", "industry"]
    if prev_df is None or prev_df.empty:
        return pd.DataFrame(columns=cols)
    p = prev_df[prev_df["ext_net"] > 0]
    prev_net = p.groupby("customer")["ext_net"].sum()
    cur_set = set(cur_df["customer"]) if cur_df is not None and not cur_df.empty else set()
    cand = prev_net[(prev_net >= threshold) & (~prev_net.index.isin(cur_set))].sort_values(ascending=False)
    if cand.empty:
        return pd.DataFrame(columns=cols)
    ao = as_of()
    last_txn = p.groupby("customer")["perf_ym"].max()
    # 去年同段內金額最大的業務
    sp = (p.groupby(["customer", "salesperson"])["ext_net"].sum()
          .reset_index().sort_values("ext_net", ascending=False)
          .drop_duplicates("customer").set_index("customer")["salesperson"])
    ind = (p.groupby(["customer", "industry"])["ext_net"].sum()
           .reset_index().sort_values("ext_net", ascending=False)
           .drop_duplicates("customer").set_index("customer")["industry"])
    rows = []
    for c, v in cand.items():
        lt = last_txn.get(c)
        msl = None
        if lt is not None:
            msl = (ao["as_of_year"] - lt.year) * 12 + (ao["as_of_month"] - lt.month)
        rows.append({"customer": c, "prev_net": float(v),
                     "last_txn": lt, "months_since_last": msl,
                     "main_salesperson": sp.get(c), "industry": ind.get(c)})
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(ttl=60)
def active_salespeople(user: dict | None = None) -> list[str]:
    """可下鑽的業務清單（排除停用、單字垃圾名、公司戶），供業務頁預設。"""
    scope = sales_scope_name(user)
    if scope == "":
        return []
    if scope:
        return [scope]
    df = _df(
        "select distinct s.name from salesperson s join v_deal_summary d on d.salesperson_id = s.id "
        "where s.is_active and length(btrim(s.name)) > 1 and not d.is_house order by s.name")
    return df["name"].tolist() if not df.empty else []


@st.cache_data(ttl=120)
def data_quality_summary() -> dict:
    """資料品質面板（P2-3）：主檔缺產業的活躍客戶、異常業務名、疑似同一客戶異名。"""
    no_ind = _df(
        "select c.name from customer c where c.is_active and c.industry_id is null "
        "and exists (select 1 from deal d where d.customer_id = c.id) order by c.name")
    bad_sp = _df("select name from salesperson where name is not null and length(btrim(name)) <= 1")
    # 疑似異名：去掉常見尾綴後相同
    dup = _df(
        """with n as (
             select id, name,
                    btrim(regexp_replace(name, '(股份有限公司|有限公司|集團|企業社|company|co\\.?,? ?ltd\\.?)', '', 'gi')) as base
             from customer where is_active
           )
           select base, string_agg(name, ' / ' order by name) as names, count(*) c
           from n where base <> '' group by base having count(*) > 1 order by c desc limit 30""")
    return {
        "no_industry_n": len(no_ind), "no_industry": no_ind["name"].tolist() if not no_ind.empty else [],
        "bad_salesperson": bad_sp["name"].tolist() if not bad_sp.empty else [],
        "dup_groups": dup.to_dict("records") if not dup.empty else [],
    }


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


@st.cache_data(ttl=60)
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
    if by not in ("platform", "platform_group", "report_platform"):
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
    # 欄排序：報表平台用固定欄序（老闆版），其餘依總額由大到小
    if by == "report_platform":
        piv = piv[[p for p in REPORT_PLATFORM_ORDER if p in piv.columns]
                  + [c for c in piv.columns if c not in REPORT_PLATFORM_ORDER]]
    else:
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
    out["last_txn"] = g["perf_ym"].max()
    out["main_salesperson"] = g.apply(
        lambda x: x.groupby("salesperson")["ext_net"].sum().idxmax())
    # 跨公司 / 跨業務（§3.4：喬商是東吳、聲活、鉑霖都在做）——依金額由大到小
    out["companies_multi"] = g.apply(
        lambda x: "、".join(x.groupby("company")["ext_net"].sum().sort_values(ascending=False).index))
    out["salespeople_multi"] = g.apply(
        lambda x: "、".join(x.groupby("salesperson")["ext_net"].sum().sort_values(ascending=False).index[:5]))
    # 產業：優先用「訂單產業眾數」（deal.industry 幾乎都有），主檔為空才 fallback（P0-5）
    if "industry" in d.columns:
        out["industry_orders"] = g["industry"].agg(
            lambda s: s.mode().iat[0] if s.notna().any() else None)

    # 距上次交易（月，以訂單 max(perf_ym) 為準，不依賴 v_customer_year）
    ao = as_of()
    out["months_since_last"] = out["last_txn"].map(
        lambda d0: None if pd.isna(d0) else (ao["as_of_year"] - d0.year) * 12 + (ao["as_of_month"] - d0.month))

    # 同期
    if prev_df is not None and not prev_df.empty:
        cp = prev_df[prev_df["ext_net"] > 0].groupby("customer")["ext_net"].sum()
    else:
        cp = pd.Series(dtype=float)
    out["prev_net"] = cp.reindex(out.index)
    out["yoy_pct"] = (out["ext_net"] - out["prev_net"]) / out["prev_net"].abs()

    # 狀態 / 產業（狀態來自 v_customer_year；產業以訂單眾數為主、主檔補）
    if cy is not None and not cy.empty:
        join_cols = [c for c in ("status", "customer_category") if c in cy.columns]
        if "industry" in cy.columns:
            out = out.join(cy[join_cols + ["industry"]].rename(columns={"industry": "industry_master"}), how="left")
        else:
            out = out.join(cy[join_cols], how="left")
    out["status"] = out["status"].fillna("既有") if "status" in out.columns else "既有"
    # 合併產業：訂單眾數 → 主檔
    io = out["industry_orders"] if "industry_orders" in out.columns else pd.Series(index=out.index, dtype=object)
    im = out["industry_master"] if "industry_master" in out.columns else pd.Series(index=out.index, dtype=object)
    out["industry"] = io.where(io.notna(), im)
    out = out.drop(columns=[c for c in ("industry_orders", "industry_master") if c in out.columns])

    # 同期文字（新客顯示「新」）
    from core.format import pct as _pct
    out["yoy_text"] = out.apply(
        lambda r: "新" if pd.isna(r["prev_net"]) or r["prev_net"] == 0 else _pct(r["yoy_pct"]), axis=1)

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
    from core.format import pct as _pct
    out["yoy_text"] = out.apply(
        lambda r: "新" if pd.isna(r["prev_net"]) or r["prev_net"] == 0 else _pct(r["yoy_pct"]), axis=1)

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
            if isinstance(delta, str):
                delta_txt = delta                       # 已是文字（例：「同期不可比」）直接顯示
            elif delta is not None and not (isinstance(delta, float) and pd.isna(delta)):
                delta_txt = f"{pct(delta, already_ratio=True)} 同期"
            st.metric(it["label"], it["value"], delta=delta_txt, delta_color="off" if isinstance(delta, str) else "normal")
            if it.get("sub"):
                st.caption(it["sub"])


def _nearest_month(target: date, months: list[date]) -> date:
    """把 target 對到 months（有資料的月）中最接近的一個。"""
    return min(months, key=lambda m: abs((m - target).days)) if months else target


def scope_bar(key: str) -> dict:
    """
    口徑切換元件（TASK_4 §3.5）：分析口徑 / 發稿口徑（老闆版）/ 自訂。
    回傳 resolve_scope 後的 dict（含五個旗標與 preset）。自訂展開五個勾選。
    """
    # 用 st.radio（各版本皆有；st.segmented_control 需 1.40+，Streamlit Cloud 版本會飄）
    label = st.radio(
        "口徑", ["分析口徑", "發稿口徑（老闆版）", "自訂"], horizontal=True,
        key=f"{key}_scope", help=(
            "分析口徑＝全部對外線、排除交換（系統預設）；"
            "發稿口徑＝老闆年度表：只算媒體上稿線、四平台+健康視、交換併回原業務；"
            "自訂＝自己勾。轉撥線一律不算。"))
    preset = {"分析口徑": "analysis", "發稿口徑（老闆版）": "media", "自訂": "custom"}.get(label, "analysis")
    scope: dict = {"preset": preset}
    if preset == "custom":
        base = resolve_scope("custom")
        with st.expander("自訂口徑", expanded=True):
            c = st.columns(5)
            scope["include_production"] = c[0].checkbox("含製作費線", value=base["include_production"], key=f"{key}_sc_prod")
            scope["include_barter"] = c[1].checkbox("含交換", value=base["include_barter"], key=f"{key}_sc_bar")
            scope["include_house"] = c[2].checkbox("含公司戶", value=base["include_house"], key=f"{key}_sc_house")
            scope["include_ops_other"] = c[3].checkbox("含營運與其它平台", value=base["include_ops_other"], key=f"{key}_sc_ops")
            scope["merge_ruidi"] = c[4].checkbox("瑞迪併入東吳", value=base["merge_ruidi"], key=f"{key}_sc_ruidi")
    return resolve_scope(scope)


def filter_bar_analysis(key: str, *, user: dict | None = None,
                        show_industry: bool = True, show_salesperson: bool = True,
                        show_house_toggle: bool = False, show_scope: bool = False) -> dict:
    """
    分析頁共用篩選列（跨頁保留：所有 widget 用共用 key）。回傳 dict：ym_from, ym_to,
    company, platform_group, industry, salesperson, customer, exclude_barter,
    include_house, includes_open（迄月是否含進行中月份）, scope（口徑 dict）。
    期間預設 今年 1 月 → 截止月（= 最後已結束的月，P0-3）。SALES 角色隱藏業務篩選。
    show_scope=True 時在最上方顯示口徑切換（§3.5）。
    """
    from core.format import ym_text
    from core import data as _data

    user = user or current_user()
    is_sales = bool(user and user.get("role") == "SALES")
    months = analysis_months()          # 新到舊
    ao = as_of()
    def_from, def_to = window_defaults()
    ss = st.session_state
    out: dict = {}
    out["scope"] = scope_bar(key) if show_scope else resolve_scope("analysis")

    if not months:
        out.update(ym_from=def_from, ym_to=def_to, company=None, platform_group=None,
                   industry=None, salesperson=None, customer="", exclude_barter=True,
                   include_house=True, includes_open=False)
        return out

    # 初始化共用狀態（只在第一次）
    if "af_ymf" not in ss:
        ss.af_ymf = _nearest_month(def_from, months)
    if "af_ymt" not in ss:
        ss.af_ymt = def_to if def_to in months else months[0]

    # 快捷區間鈕（在 selectbox 之前設定 session，selectbox 直接讀）
    labels = {m: ym_text(m) for m in months}
    q = st.columns(4)
    if q[0].button("上月", use_container_width=True, key=f"{key}_q_last"):
        ss.af_ymf = ss.af_ymt = ao["as_of_ym"]
    if q[1].button("本季", use_container_width=True, key=f"{key}_q_qtr"):
        qm = (ao["as_of_month"] - 1) // 3 * 3 + 1
        ss.af_ymf = _nearest_month(date(ao["as_of_year"], qm, 1), months)
        ss.af_ymt = ao["as_of_ym"]
    if q[2].button("今年至今", use_container_width=True, key=f"{key}_q_ytd"):
        ss.af_ymf = _nearest_month(date(ao["as_of_year"], 1, 1), months)
        ss.af_ymt = ao["as_of_ym"]
    if q[3].button("近 12 個月", use_container_width=True, key=f"{key}_q_12"):
        ss.af_ymf = _nearest_month(ao["as_of_ym"] - relativedelta(months=11), months)
        ss.af_ymt = ao["as_of_ym"]

    c1, c2 = st.columns(2)
    out["ym_from"] = c1.selectbox("期間（起）", months, format_func=lambda m: labels[m], key="af_ymf")
    out["ym_to"] = c2.selectbox("期間（迄）", months, format_func=lambda m: labels[m], key="af_ymt")

    row = st.columns(4)
    with row[0]:
        comps = [None] + [o[1] for o in _data.options("company") if o[1] != "瑞迪"]
        out["company"] = st.selectbox("公司別", comps,
                                      format_func=lambda v: "全部" if v is None else v, key="af_co")
    with row[1]:
        pgs = [None] + _data.platform_groups()
        out["platform_group"] = st.selectbox("平台歸類", pgs,
                                              format_func=lambda v: "全部" if v is None else v, key="af_pg")
    with row[2]:
        if show_industry:
            inds = [None] + [o[1] for o in _data.options("industry")]
            out["industry"] = st.selectbox("產業別", inds,
                                           format_func=lambda v: "全部" if v is None else v, key="af_ind")
        else:
            out["industry"] = None
    with row[3]:
        if show_salesperson and not is_sales:
            sps = [None] + [o[1] for o in _data.options("salesperson")]
            out["salesperson"] = st.selectbox("業務", sps,
                                              format_func=lambda v: "全部" if v is None else v, key="af_sp")
        else:
            out["salesperson"] = None

    row2 = st.columns([2, 1, 1])
    with row2[0]:
        out["customer"] = st.text_input("客戶（模糊）", key="af_cust")
    with row2[1]:
        out["exclude_barter"] = st.checkbox("排除交換", value=True, key="af_barter")
    with row2[2]:
        if show_house_toggle:
            out["include_house"] = st.checkbox("含公司戶", value=True, key="af_house")
        else:
            out["include_house"] = True

    # 進行中月份提示（P0-3）
    om = open_month()
    if om:
        out["includes_open"] = out["ym_to"] >= om["perf_ym"]
        from core.format import money as _money, date_text as _dt
        st.caption(f"ℹ️ {ym_text(om['perf_ym'])} 進行中（已登 {om['deals']} 筆、{_money(om['ext_net'])}；"
                   f"最後登打 {_dt(om['last_entry'])[5:] if om['last_entry'] else '—'}），未納入預設區間"
                   + ("　⚠ 目前區間含未結月，同期比較會偏低" if out["includes_open"] else ""))
    else:
        out["includes_open"] = False
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
            cfg[header] = st.column_config.NumberColumn(header, format="localized", width=opts.get("width"))
        elif kind == "pct":
            disp[header] = pd.to_numeric(df[col], errors="coerce")
            cfg[header] = st.column_config.NumberColumn(header, format="percent", width=opts.get("width"))
        elif kind == "progress":
            v = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            disp[header] = v
            mx = opts.get("max")
            if not mx or mx <= 0:
                mx = float(v.max()) if len(v) and float(v.max()) > 0 else 1.0
            cfg[header] = st.column_config.ProgressColumn(
                header, format=opts.get("format", "percent"), min_value=0.0, max_value=float(mx))
        elif kind == "bar":
            disp[header] = df[col].values
            cfg[header] = st.column_config.BarChartColumn(header, help=opts.get("help"))
        elif kind == "line":
            disp[header] = df[col].values
            cfg[header] = st.column_config.LineChartColumn(header, help=opts.get("help"))
        else:  # text（NaN/None 顯示空白，不印 'None'）
            s = df[col]
            disp[header] = s.where(s.notna(), "").astype(object)
            cfg[header] = st.column_config.TextColumn(header, width=opts.get("width"))
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
