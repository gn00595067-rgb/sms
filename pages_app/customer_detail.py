"""客戶頁（3.6）— 單一客戶的 24 個月趨勢、歷年同期、訂單清單、平台/業務變化。

由 P13 客戶分析點列帶入（st.session_state["customer_focus"]），也可自行選客戶。
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st
from dateutil.relativedelta import relativedelta

from core import analysis as A
from core.auth import require_role
from core.data import query_df
from core.format import COLORS, money, pct, ym_text
from core.ui import feedback_widget, page_header, show_df

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("🏢 客戶頁", "單一客戶的長期趨勢與訂單明細。")

scope = A.sales_scope_name(user)
scope_sql, scope_params = "", []
if scope == "":
    st.info("你的帳號尚未綁定業務，無法檢視客戶頁。")
    st.stop()
elif scope:
    scope_sql = " and salesperson = %s"
    scope_params = [scope]

# 客戶清單
clist = query_df(
    f"select distinct customer from v_deal_summary where customer is not null{scope_sql} order by customer",
    scope_params or None)
customers = clist["customer"].tolist() if not clist.empty else []
if not customers:
    st.info("查無客戶資料。")
    st.stop()

focus = st.session_state.get("customer_focus")
idx = customers.index(focus) if focus in customers else 0
customer = st.selectbox("客戶", customers, index=idx, key="cd_customer")
st.session_state["customer_focus"] = customer

ao = A.as_of()
year = ao["as_of_year"]
yf, yt = date(year, 1, 1), ao["as_of_ym"]
pf, pt = A.prev_window(yf, yt)

# ---- KPI：期間 / 去年同段 / 歷年 ----
def _sum(ym_from, ym_to):
    r = query_df(
        """select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp
           from v_deal_summary where customer=%s and not is_barter and perf_ym between %s and %s""",
        (customer, ym_from, ym_to))
    return (float(r.iloc[0]["net"]), float(r.iloc[0]["bp"])) if not r.empty else (0.0, 0.0)

cur_net, cur_bp = _sum(yf, yt)
prev_net, prev_bp = _sum(pf, pt)
allr = query_df(
    "select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp from v_deal_summary where customer=%s and not is_barter",
    (customer,))
all_net = float(allr.iloc[0]["net"]) if not allr.empty else 0.0
all_bp = float(allr.iloc[0]["bp"]) if not allr.empty else 0.0

A.kpi_row([
    {"label": f"本期 {year}/01–{ym_text(yt)}", "value": money(cur_net),
     "sub": f"帳上毛利 {money(cur_bp)}（{pct(cur_bp/cur_net) if cur_net else '–'}）",
     "delta": (cur_net - prev_net) / prev_net if prev_net else None},
    {"label": "去年同段", "value": money(prev_net),
     "sub": f"帳上毛利 {money(prev_bp)}"},
    {"label": "歷年累計", "value": money(all_net),
     "sub": f"帳上毛利 {money(all_bp)}（{pct(all_bp/all_net) if all_net else '–'}）"},
])

st.divider()

# ---- 24 個月 除佣實收 / 帳上毛利（兩張小圖並排，單軸） ----
start24 = (ao["as_of_ym"] - relativedelta(months=23))
mrows = query_df(
    """select perf_ym, coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp
       from v_customer_month where customer=%s and perf_ym between %s and %s
       group by perf_ym order by perf_ym""",
    (customer, start24, ao["as_of_ym"]))
months = A.month_range(start24, ao["as_of_ym"])
mlabels = [ym_text(m) for m in months]
net_by = {r["perf_ym"]: float(r["net"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
bp_by = {r["perf_ym"]: float(r["bp"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
c1, c2 = st.columns(2)
with c1:
    st.markdown("**近 24 個月 除佣實收**")
    fig = go.Figure(go.Bar(x=mlabels, y=[net_by.get(m, 0) for m in months], marker_color=COLORS["accent"]))
    fig.update_layout(height=260, margin=dict(l=8, r=8, t=8, b=8),
                      font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.markdown("**近 24 個月 帳上毛利**")
    fig2 = go.Figure(go.Scatter(x=mlabels, y=[bp_by.get(m, 0) for m in months], mode="lines+markers",
                                line=dict(color=COLORS["company"]["東吳"])))
    fig2.update_layout(height=260, margin=dict(l=8, r=8, t=8, b=8),
                       font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig2, use_container_width=True)

# ---- 歷年同期比較 ----
st.markdown("**歷年同期比較**（今年到目前 vs 各年同一段月份）")
yrows = query_df(
    """select perf_year, ext_net, ext_net_same_period, booked_profit, booked_margin, yoy_pct, main_salesperson
       from v_customer_year where customer=%s order by perf_year""",
    (customer,))
if not yrows.empty:
    A.show_ranking(yrows, [
        ("perf_year", "年", "int"),
        ("ext_net", "全年除佣實收", "money"),
        ("ext_net_same_period", "同段除佣實收", "money"),
        ("yoy_pct", "同期%", "pct"),
        ("booked_profit", "帳上毛利", "money"),
        ("booked_margin", "毛利率", "pct"),
        ("main_salesperson", "主要業務", "text"),
    ], height=None, key="cd_year")

# ---- 訂單清單（三個毛利率） ----
st.markdown("**訂單清單**（三層毛利率並列）")
orders = query_df(
    """select perf_ym_text, contract_no, ad_name, company, salesperson, platform_groups,
              ext_net, booked_cost, booked_profit, booked_margin, group_margin, net_margin
       from v_deal_summary where customer=%s and not is_barter order by perf_ym desc, ext_net desc""",
    (customer,))
show_df(orders)

# ---- 平台組合變化 / 經手業務 ----
c3, c4 = st.columns(2)
with c3:
    st.markdown("**平台組合變化（年 × 平台歸類）**")
    plat = query_df(
        """select perf_year, sum(net_cp) 企頻, sum(net_fresh) 新鮮視, sum(net_radio) 廣播, sum(net_other) 其他
           from v_deal_summary where customer=%s and not is_barter group by perf_year order by perf_year""",
        (customer,))
    if not plat.empty:
        figp = go.Figure()
        for pgname in ("企頻", "新鮮視", "廣播", "其他"):
            figp.add_bar(x=plat["perf_year"].astype(str), y=plat[pgname], name=pgname,
                         marker_color=COLORS["platform_group"][pgname], marker_line_width=1, marker_line_color="white")
        figp.update_layout(barmode="stack", height=280, margin=dict(l=8, r=8, t=8, b=8),
                           legend=dict(orientation="h", y=1.08),
                           font=dict(family="Noto Sans TC, Microsoft JhengHei"))
        st.plotly_chart(figp, use_container_width=True)
with c4:
    st.markdown("**經手業務（年 × 業務金額）**")
    spy = query_df(
        """select perf_year, salesperson, sum(ext_net) net from v_deal_summary
           where customer=%s and not is_barter group by perf_year, salesperson order by perf_year""",
        (customer,))
    if not spy.empty:
        pivot = spy.pivot_table(index="perf_year", columns="salesperson", values="net", aggfunc="sum").fillna(0)
        figs = go.Figure()
        for sp in pivot.columns:
            figs.add_bar(x=pivot.index.astype(str), y=pivot[sp], name=str(sp),
                         marker_line_width=1, marker_line_color="white")
        figs.update_layout(barmode="stack", height=280, margin=dict(l=8, r=8, t=8, b=8),
                           legend=dict(orientation="h", y=1.08),
                           font=dict(family="Noto Sans TC, Microsoft JhengHei"))
        st.plotly_chart(figs, use_container_width=True)

feedback_widget("customer_detail")
