"""P16 公司分析 — 三家公司加起來到底賺多少（三層毛利橋 + 目標達成）。

MEDIA / FINANCE / EXEC 可看；SALES 通常看不到公司整體，但仍受角色限制。
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.data import query_df
from core.format import COLORS, company_color, money, pct, ym_text
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "FINANCE", "EXEC")
page_header("🏛️ 公司分析", "三層毛利橋：帳上 → 集團 → 淨利；目標達成用老闆儀表板口徑。")

f = A.filter_bar_analysis("aco", user=user, show_industry=False, show_salesperson=False)
yf, yt = f["ym_from"], f["ym_to"]
pf, pt = A.prev_window(yf, yt)


def _company_agg(a, b):
    df = query_df(
        """select company, sum(ext_net) en, sum(booked_profit) bp, sum(ic_out) io, sum(ic_in) ii,
                  sum(fixed_cost) fc, max(active_salespeople) sp,
                  sum(net_cp) cp, sum(net_fresh) fr, sum(net_radio) rd, sum(net_other) ot, sum(barter_net) bt
           from v_company_month where perf_ym between %s and %s group by company""", (a, b))
    return {r["company"]: r for _, r in df.iterrows()} if not df.empty else {}


def _group_agg(a, b):
    df = query_df(
        """select sum(ext_net) en, sum(booked_profit) bp, sum(ic_add_back) ic, sum(group_profit) gp,
                  sum(fixed_cost) fc, sum(net_profit) np, sum(barter_net) bt
           from v_group_month where perf_ym between %s and %s""", (a, b))
    return df.iloc[0] if not df.empty else None


cur = _company_agg(yf, yt)
prev = _company_agg(pf, pt)
g = _group_agg(yf, yt)
gp = _group_agg(pf, pt)

# 期間內有業績的公司（決定是否顯示瑞迪）
show_cos = [c for c in ("聲活", "東吳", "鉑霖", "瑞迪") if c in cur and float(cur[c]["en"] or 0) > 0]
main_cos = [c for c in ("聲活", "東吳", "鉑霖") if c in cur]

# ---- KPI 四卡（三家 + 集團） ----
cols = st.columns(len(main_cos) + 1)
for col, name in zip(cols, main_cos):
    r = cur[name]
    en = float(r["en"] or 0); bp = float(r["bp"] or 0)
    pen = float(prev[name]["en"]) if name in prev else 0
    io = float(r["io"] or 0); ii = float(r["ii"] or 0); fc = float(r["fc"] or 0)
    with col:
        st.markdown(f"<span style='color:{company_color(name)};font-weight:700'>● {name}</span>", unsafe_allow_html=True)
        st.metric("除佣實收", money(en), delta=f"{pct((en-pen)/pen) if pen else '–'} 同期")
        extra = f"轉撥給聲活 {money(io)}" if io > 0 else (f"收到轉撥 {money(ii)}・固定成本 {money(fc)}" if ii > 0 else "")
        st.caption(f"帳上毛利 {money(bp)}（{pct(bp/en) if en else '–'}）")
        if extra:
            st.caption(extra)
if g is not None:
    gen = float(g["en"] or 0); ggp = float(g["gp"] or 0); gnp = float(g["np"] or 0)
    pgen = float(gp["en"]) if gp is not None and gp["en"] is not None else 0
    with cols[-1]:
        st.markdown("**集團合併**")
        st.metric("除佣實收", money(gen), delta=f"{pct((gen-pgen)/pgen) if pgen else '–'} 同期")
        st.caption(f"集團毛利 {money(ggp)}（{pct(ggp/gen) if gen else '–'}）")
        st.caption(f"扣固定成本後淨利 {money(gnp)}（{pct(gnp/gen) if gen else '–'}）")

st.divider()

# ---- 月堆疊柱 / 三層毛利橋 ----
c1, c2 = st.columns(2)
with c1:
    st.markdown("**各公司月業績（除佣實收，對外）**")
    cm = query_df(
        """select company, perf_ym, sum(ext_net) net from v_company_month
           where perf_ym between %s and %s and company = any(%s) group by company, perf_ym order by perf_ym""",
        (yf, yt, main_cos))
    months = A.month_range(yf, yt)
    mlabels = [ym_text(m) for m in months]
    fig = go.Figure()
    for name in main_cos:
        sub = cm[cm["company"] == name] if not cm.empty else cm
        by = {r["perf_ym"]: float(r["net"] or 0) for _, r in sub.iterrows()} if not cm.empty else {}
        fig.add_bar(x=mlabels, y=[by.get(m, 0) for m in months], name=name,
                    marker_color=company_color(name), marker_line_width=1, marker_line_color="white")
    fig.update_layout(barmode="stack", height=300, margin=dict(l=8, r=8, t=8, b=8),
                      legend=dict(orientation="h", y=1.08), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.markdown("**三層毛利橋：帳上 → 集團 → 淨利**")
    if g is not None:
        bp = float(g["bp"] or 0); ic = float(g["ic"] or 0); gpf = float(g["gp"] or 0)
        fc = float(g["fc"] or 0); np_ = float(g["np"] or 0)
        fig2 = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total", "relative", "total"],
            x=["帳上毛利合計", "＋轉撥加回", "集團毛利", "－固定成本", "集團淨利"],
            y=[bp, ic, gpf, -fc, np_],
            text=[money(bp), f"+{money(ic)}", money(gpf), f"−{money(fc)}", money(np_)],
            textposition="outside",
            connector=dict(line=dict(color="#cbd3de")),
            increasing=dict(marker_color=COLORS["alert"]["green"]),
            decreasing=dict(marker_color=COLORS["alert"]["red"]),
            totals=dict(marker_color=COLORS["accent"])))
        fig2.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8),
                           font=dict(family="Noto Sans TC, Microsoft JhengHei"))
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("2025 尚未設定固定成本規則，淨利同期比較待規則補齊後顯示。")

# ---- 目標達成 ----
st.markdown("**目標達成**（口徑：企頻＋新鮮視、不含公司戶、不含交換）")
tgt = query_df(
    """select company, period_label, target_amount, actual, remaining, achieved_pct,
              months_left, required_monthly, achieved_pct_with_forecast
       from v_target_progress order by company, year, period_no""")
if not tgt.empty:
    A.show_ranking(tgt, [
        ("company", "公司", "text"), ("period_label", "期間", "text"),
        ("target_amount", "目標", "money"), ("actual", "進單", "money"),
        ("remaining", "待追", "money"),
        ("achieved_pct", "達成率", "progress", {"max": 1.0}),
        ("months_left", "剩餘月份", "int"), ("required_monthly", "每月需達", "money"),
        ("achieved_pct_with_forecast", "加預估後達成率", "pct"),
    ], height=None, key="co_tgt")
else:
    st.caption("尚未設定目標（主檔維護 → 目標）。")

# ---- 公司 × 平台歸類 ----
st.markdown("**公司 × 平台歸類：業績結構與人均產值**")
import pandas as pd
rows = []
for name in main_cos:
    r = cur[name]
    en = float(r["en"] or 0); spn = int(r["sp"] or 0)
    rows.append({"company": name, "net_cp": float(r["cp"] or 0), "net_fresh": float(r["fr"] or 0),
                 "net_radio": float(r["rd"] or 0), "net_other": float(r["ot"] or 0), "total": en,
                 "mix": [float(r["cp"] or 0), float(r["fr"] or 0), float(r["rd"] or 0), float(r["ot"] or 0)],
                 "booked_margin": float(r["bp"] or 0) / en if en else 0,
                 "sp": spn, "per_sp": en / spn if spn else 0})
pgdf = pd.DataFrame(rows)
if not pgdf.empty:
    A.show_ranking(pgdf, [
        ("company", "公司", "text"), ("net_cp", "企頻", "money"), ("net_fresh", "新鮮視", "money"),
        ("net_radio", "廣播", "money"), ("net_other", "其他", "money"), ("total", "合計", "money"),
        ("mix", "組合", "bar", {"help": "企頻/新鮮視/廣播/其他"}),
        ("booked_margin", "帳上毛利率", "pct"), ("sp", "業務人數", "int"), ("per_sp", "人均產值", "money"),
    ], height=None, key="co_pg")

# ---- 進單 + 預估 ----
st.markdown("**進單 + 預估（公司 × 月）**")
bvf = query_df(
    """select company, perf_ym_text, booked_net, barter_net, forecast_amount, booked_plus_forecast
       from v_booked_vs_forecast where perf_ym between %s and %s order by perf_ym_text, company""",
    (yf, yt))
if not bvf.empty and bvf["booked_plus_forecast"].astype(float).abs().sum() > 0:
    pv = bvf.pivot_table(index="company", columns="perf_ym_text", values="booked_plus_forecast", aggfunc="sum").fillna(0)
    from core.ui import show_df
    show_df(pv.reset_index())
    st.caption("數字 = 進單 + 預估；預估資料需在主檔維護 → 預估 輸入後才有意義。")
else:
    st.caption("尚無預估資料；進單明細見上方各表。")

feedback_widget("analysis_company")
