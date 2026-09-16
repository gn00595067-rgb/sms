"""業務頁（3.7）— 單一業務的月趨勢、客戶組合、目標達成、預估 pipeline。"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.data import query_df
from core.format import COLORS, money, pct, ym_text
from core.ui import feedback_widget, page_header, show_df

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("🧑‍💼 業務頁", "單一業務的趨勢、客戶組合、目標與預估。")

scope = A.sales_scope_name(user)
if scope == "":
    st.info("你的帳號尚未綁定業務，無法檢視業務頁。")
    st.stop()

if scope:
    salespeople = [scope]
else:
    sl = query_df("select distinct salesperson from v_deal_summary where salesperson is not null and not is_house order by salesperson")
    salespeople = sl["salesperson"].tolist() if not sl.empty else []
if not salespeople:
    st.info("查無業務資料。")
    st.stop()

focus = st.session_state.get("salesperson_focus")
idx = salespeople.index(focus) if focus in salespeople else 0
sp = st.selectbox("業務", salespeople, index=idx, key="spd_sp")
st.session_state["salesperson_focus"] = sp

ao = A.as_of()
year = ao["as_of_year"]
yf, yt = date(year, 1, 1), ao["as_of_ym"]
pf, pt = A.prev_window(yf, yt)

# ---- KPI ----
cur = query_df(
    """select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp,
              count(distinct customer) cust, count(*) deals
       from v_deal_summary where salesperson=%s and not is_barter and perf_ym between %s and %s""",
    (sp, yf, yt)).iloc[0]
prev = query_df(
    "select coalesce(sum(ext_net),0) net from v_deal_summary where salesperson=%s and not is_barter and perf_ym between %s and %s",
    (sp, pf, pt)).iloc[0]
cur_net = float(cur["net"]); prev_net = float(prev["net"])
A.kpi_row([
    {"label": f"本期 {year}/01–{ym_text(yt)}", "value": money(cur_net),
     "delta": (cur_net - prev_net) / prev_net if prev_net else None,
     "sub": f"帳上毛利 {money(float(cur['bp']))}（{pct(float(cur['bp'])/cur_net) if cur_net else '–'}）"},
    {"label": "客戶數", "value": f"{int(cur['cust'])}"},
    {"label": "訂單數", "value": f"{int(cur['deals'])}", "sub": f"平均單筆 {money(cur_net/int(cur['deals'])) if int(cur['deals']) else '–'}"},
])

st.divider()

# ---- 月趨勢 ----
st.markdown("**月趨勢（期間內除佣實收）**")
mrows = query_df(
    """select perf_ym, coalesce(sum(ext_net),0) net from v_salesperson_month
       where salesperson=%s and perf_ym between %s and %s group by perf_ym order by perf_ym""",
    (sp, yf, yt))
months = A.month_range(yf, yt)
net_by = {r["perf_ym"]: float(r["net"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
fig = go.Figure(go.Bar(x=[ym_text(m) for m in months], y=[net_by.get(m, 0) for m in months], marker_color=COLORS["accent"]))
fig.update_layout(height=260, margin=dict(l=8, r=8, t=8, b=8), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
st.plotly_chart(fig, use_container_width=True)

# ---- 客戶組合（前 10 大） ----
st.markdown("**客戶組合（前 10 大：金額、同期%、佔該業務%）**")
cur_c = query_df(
    """select customer, sum(ext_net) net from v_deal_summary
       where salesperson=%s and not is_barter and perf_ym between %s and %s group by customer""",
    (sp, yf, yt))
prev_c = query_df(
    """select customer, sum(ext_net) net from v_deal_summary
       where salesperson=%s and not is_barter and perf_ym between %s and %s group by customer""",
    (sp, pf, pt))
if not cur_c.empty:
    cur_c["net"] = cur_c["net"].astype(float)
    prevmap = {r["customer"]: float(r["net"]) for _, r in prev_c.iterrows()} if not prev_c.empty else {}
    cur_c = cur_c.sort_values("net", ascending=False).head(10)
    total = float(cur_c["net"].sum()) or 1
    cur_c["同期%"] = cur_c.apply(lambda r: (r["net"] - prevmap.get(r["customer"], 0)) / prevmap[r["customer"]] if prevmap.get(r["customer"]) else None, axis=1)
    cur_c["佔該業務%"] = cur_c["net"] / total
    A.show_ranking(cur_c, [
        ("customer", "客戶", "text"), ("net", "除佣實收", "money"),
        ("同期%", "同期%", "pct"), ("佔該業務%", "佔該業務%", "progress", {"max": float(cur_c["佔該業務%"].max())}),
    ], height=None, key="spd_cust")

# ---- 新客與流失風險 ----
c1, c2 = st.columns(2)
with c1:
    st.markdown("**新客（今年第一次有業績、由本業務帶進）**")
    cy = A.customer_year(year)
    if not cy.empty and "main_salesperson" in cy.columns:
        newc = cy[(cy["status"] == "新客") & (cy["main_salesperson"] == sp)]
        if not newc.empty:
            show_df(newc.reset_index()[["customer", "ext_net", "booked_margin"]])
        else:
            st.caption("本期無新客。")
with c2:
    st.markdown("**流失風險（去年有、今年到目前無）**")
    if not cy.empty and "main_salesperson" in cy.columns:
        lost = cy[(cy["status"] == "流失風險") & (cy["main_salesperson"] == sp)]
        if not lost.empty:
            show_df(lost.reset_index()[["customer", "months_since_last"]])
        else:
            st.caption("本期無流失風險客戶。")

# ---- 目標達成 ----
st.markdown("**目標達成**")
tgt = query_df(
    """select period_label, target_amount, actual, remaining, achieved_pct, months_left, required_monthly
       from v_target_progress where salesperson=%s order by year, period_no""", (sp,))
if not tgt.empty:
    A.show_ranking(tgt, [
        ("period_label", "期間", "text"), ("target_amount", "目標", "money"),
        ("actual", "進單", "money"), ("remaining", "待追", "money"),
        ("achieved_pct", "達成率", "progress", {"max": 1.0}),
        ("months_left", "剩餘月份", "int"), ("required_monthly", "每月需達", "money"),
    ], height=None, key="spd_tgt")
else:
    st.caption("尚未設定此業務的目標（主檔維護 → 目標）。")

# ---- 預估 pipeline ----
st.markdown("**預估（OPEN pipeline）**")
fc = query_df(
    """select f.perf_ym, c.name company, cu.name customer, f.customer_text, f.ad_name,
              f.platform_group, f.amount, f.probability, f.status
       from forecast f
       left join company c on c.id=f.company_id
       left join customer cu on cu.id=f.customer_id
       left join salesperson s on s.id=f.salesperson_id
       where s.name=%s and f.status='OPEN' order by f.perf_ym""", (sp,))
if not fc.empty:
    fc["客戶"] = fc.apply(lambda r: r["customer"] or r["customer_text"] or "", axis=1)
    fc["prob_ratio"] = fc["probability"].astype(float) / 100.0
    A.show_ranking(fc, [
        ("perf_ym", "業績年月", "text"), ("company", "公司", "text"), ("客戶", "客戶", "text"),
        ("ad_name", "廣告", "text"), ("platform_group", "平台歸類", "text"),
        ("amount", "預估", "money"), ("prob_ratio", "機率%", "pct"),
    ], height=None, key="spd_fc")
else:
    st.caption("尚無預估資料（主檔維護 → 預估）。")

# ---- 連結 ----
st.divider()
c1, c2 = st.columns(2)
with c1:
    st.page_link("pages_app/reports.py", label="→ 月業績認定表（報表中心）", icon="📈")
with c2:
    st.page_link("pages_app/bonus.py", label="→ 業務獎金試算", icon="🎯")

feedback_widget("salesperson_detail")
