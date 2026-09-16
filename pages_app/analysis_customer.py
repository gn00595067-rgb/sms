"""P13 客戶分析 — 誰在養公司、依賴多高、哪個產業在長、誰快掉了。

MEDIA / FINANCE / EXEC 可看全部；SALES 只看自己的客戶。
數字口徑見 core/analysis.py（= tools/mockup_generator.py 樣稿）。
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.format import COLORS, money, pct, status_color
from core.ui import feedback_widget, page_header
from reports.render_excel import build_excel

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("👥 客戶分析", "誰在養公司、依賴多高、哪個產業在長、誰快掉了。")

f = A.filter_bar_analysis("acust", user=user)
dw = A.load_deals(f["ym_from"], f["ym_to"], f, exclude_barter=f["exclude_barter"], user=user)
if dw.empty:
    st.info("此條件查無資料。")
    feedback_widget("analysis_customer")
    st.stop()

pf, pt = A.prev_window(f["ym_from"], f["ym_to"])
dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
cy = A.customer_year(f["ym_from"].year)
cust = A.agg_customers(dw, dp, cy)

# ---- KPI ----
total = float(cust["ext_net"].sum())
active = len(cust)
active_p = int((dp[dp["ext_net"] > 0]["customer"].nunique())) if not dp.empty else 0
total_p = float(dp[dp["ext_net"] > 0]["ext_net"].sum()) if not dp.empty else 0.0
newc = int((cust["status"] == "新客").sum())
# 流失風險：整年口徑（v_customer_year），SALES 範圍下只算自己客戶
if not cy.empty and "status" in cy.columns:
    lost_idx = cy[cy["status"] == "流失風險"].index
    if A.sales_scope_name(user):
        lost_idx = [c for c in lost_idx if c in set(dp["customer"])] if not dp.empty else []
    lost = len(lost_idx)
else:
    lost = 0
top10 = float(cust.head(10)["ext_net"].sum())
top10_p = float(dp[dp["ext_net"] > 0].groupby("customer")["ext_net"].sum().sort_values(ascending=False).head(10).sum()) if not dp.empty else 0.0
booked_margin = float(cust["booked_profit"].sum()) / total if total else 0
group_margin = float(cust["group_profit"].sum()) / total if total else 0
avg_contrib = total / active if active else 0
avg_contrib_p = (total_p / active_p) if active_p else 0

A.kpi_row([
    {"label": "活躍客戶數", "value": f"{active}", "sub": f"同期 {active_p}",
     "delta": (active - active_p) / active_p if active_p else None},
    {"label": "新客戶", "value": f"{newc}", "sub": "今年第一次有業績"},
    {"label": "流失風險", "value": f"{lost}", "sub": "去年有、今年尚無"},
    {"label": "客戶平均貢獻", "value": money(avg_contrib), "sub": f"同期 {money(avg_contrib_p)}",
     "delta": (avg_contrib - avg_contrib_p) / avg_contrib_p if avg_contrib_p else None},
    {"label": "前 10 大佔比", "value": pct(top10 / total) if total else "–",
     "sub": f"同期 {pct(top10_p / total_p) if total_p else '–'}"},
    {"label": "帳上毛利率", "value": pct(booked_margin), "sub": f"集團毛利率 {pct(group_margin)}"},
])

st.divider()

# ---- 兩張圖：ABC 分級 / 產業別 ----
c1, c2 = st.columns(2)
with c1:
    st.markdown("**客戶分級（ABC）：多少客戶貢獻 80% 業績**")
    abc = cust.groupby("abc_tier").agg(n=("customer", "count"), net=("ext_net", "sum")).reindex(["A", "B", "C"]).dropna()
    tier_label = {"A": "A 級（累計 80%）", "B": "B 級（80–95%）", "C": "C 級（最後 5%）"}
    tier_color = {"A": COLORS["accent"], "B": COLORS["accent2"], "C": COLORS["accent3"]}
    fig = go.Figure()
    for tier in abc.index:
        fig.add_bar(y=[tier_label[tier]], x=[float(abc.loc[tier, "net"])], orientation="h",
                    marker_color=tier_color[tier], name=tier,
                    text=f"{money(abc.loc[tier, 'net'])}｜{int(abc.loc[tier, 'n'])} 家",
                    textposition="outside", hovertemplate="%{text}<extra></extra>")
    fig.update_layout(showlegend=False, height=220, margin=dict(l=8, r=8, t=8, b=8),
                      xaxis_title=None, yaxis=dict(autorange="reversed"),
                      font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.markdown("**產業別：業績、客戶數、毛利率（前 8 + 其他）**")
    import pandas as pd
    ind = A.agg_industries(dw, dp)
    top = ind.head(8)[["industry", "ext_net", "customers", "booked_margin"]].copy()
    if len(ind) > 8:
        others = ind.iloc[8:]
        onet = float(others["ext_net"].sum())
        top = pd.concat([top, pd.DataFrame([{
            "industry": f"其他 {len(others)} 類", "ext_net": onet,
            "customers": int(others["customers"].sum()),
            "booked_margin": float(others["booked_profit"].sum()) / onet if onet else 0,
        }])], ignore_index=True)
    fig2 = go.Figure()
    fig2.add_bar(y=top["industry"], x=top["ext_net"], orientation="h", marker_color=COLORS["accent"],
                 text=[f"{money(n)}｜{int(c)} 家｜{pct(m)}" for n, c, m in
                       zip(top["ext_net"], top["customers"], top["booked_margin"])],
                 textposition="outside", hovertemplate="%{y}: %{text}<extra></extra>")
    fig2.update_layout(showlegend=False, height=max(220, 26 * len(top)), margin=dict(l=8, r=8, t=8, b=8),
                       yaxis=dict(autorange="reversed"), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig2, use_container_width=True)

# ---- 客戶價值矩陣（散佈圖，x 平方根刻度） ----
st.markdown("**客戶價值矩陣：金額 × 毛利率 × 頻率 × 狀態**（滑鼠移上去看名字）")
import math
xmax = float(cust["ext_net"].max()) * 1.06
tickvals_orig = [v for v in (250_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000) if v <= xmax]
fig3 = go.Figure()
shape_map = {"既有": "circle", "新客": "diamond", "回流": "square"}
for status in ("既有", "新客", "回流"):
    d = cust[cust["status"].fillna("既有").map(lambda s: s if s in shape_map else "既有") == status]
    if d.empty:
        continue
    fig3.add_trace(go.Scatter(
        x=[math.sqrt(max(v, 0)) for v in d["ext_net"]], y=d["booked_margin"],
        mode="markers", name=status,
        marker=dict(size=[4 + math.sqrt(max(n, 0)) * 3 for n in d["deals"]],
                    color=status_color(status), symbol=shape_map[status], opacity=0.8,
                    line=dict(width=1, color="white")),
        customdata=list(zip(d["customer"], d["ext_net"], d["deals"])),
        hovertemplate="%{customdata[0]}<br>除佣 %{customdata[1]:,.0f}<br>毛利率 %{y:.1%}<br>%{customdata[2]} 筆<extra></extra>",
    ))
fig3.add_hline(y=0.16, line_dash="dash", line_color="#cbd3de")
fig3.add_hline(y=0.35, line_dash="dash", line_color="#cbd3de")
fig3.update_xaxes(tickvals=[math.sqrt(v) for v in tickvals_orig],
                  ticktext=[f"{v/10000:,.0f}萬" for v in tickvals_orig], title="除佣實收（平方根刻度）")
fig3.update_yaxes(title="帳上毛利率", tickformat=".0%")
fig3.update_layout(height=420, margin=dict(l=8, r=8, t=8, b=8),
                   legend=dict(orientation="h", y=1.08),
                   font=dict(family="Noto Sans TC, Microsoft JhengHei"))
st.plotly_chart(fig3, use_container_width=True)

# ---- 客戶排名表 ----
st.markdown("**客戶排名**（點一列 → 客戶頁；下載 Excel 為完整名單）")
trends, _months = A.customer_trends(cust.head(50)["customer"].tolist(), f["ym_from"], f["ym_to"])
tbl = cust.head(50).copy()
tbl["mix"] = tbl.apply(lambda r: [float(r["net_cp"]), float(r["net_fresh"]), float(r["net_radio"]), float(r["net_other"])], axis=1)
tbl["trend"] = tbl["customer"].map(lambda c: trends.get(c, []))
tbl["industry"] = tbl.get("industry", "").fillna("未分類") if "industry" in tbl.columns else "未分類"

event = A.show_ranking(tbl, [
    ("rank_in_year", "#", "int"),
    ("customer", "客戶", "text"),
    ("industry", "產業", "text"),
    ("main_salesperson", "主要業務", "text"),
    ("status", "狀態", "text"),
    ("ext_net", "除佣實收", "money"),
    ("yoy_pct", "同期%", "pct"),
    ("share", "佔比", "progress", {"max": float(cust["share"].max())}),
    ("cum_share", "累計佔比", "pct"),
    ("booked_profit", "帳上毛利", "money"),
    ("booked_margin", "毛利率", "pct"),
    ("net_margin", "集團淨利率", "pct"),
    ("deals", "筆數", "int"),
    ("active_months", "活躍月數", "int"),
    ("avg_deal", "平均單筆", "money"),
    ("mix", "平台組合", "bar", {"help": "企頻/新鮮視/廣播/其他"}),
    ("trend", "月趨勢", "line"),
    ("strategy_hint", "策略提示", "text"),
], key="cust_rank", on_select="rerun")

if event and getattr(event, "selection", None) and event.selection.get("rows"):
    idx = event.selection["rows"][0]
    st.session_state["customer_focus"] = tbl.iloc[idx]["customer"]
    st.switch_page("pages_app/customer_detail.py")

xcols = ["rank_in_year", "customer", "industry", "main_salesperson", "status", "ext_net",
         "yoy_pct", "share", "cum_share", "booked_profit", "booked_margin", "net_margin",
         "deals", "active_months", "avg_deal", "strategy_hint"]
st.download_button("⬇ 下載 Excel（完整名單）",
                   data=build_excel(cust[xcols], "客戶分析", A.filter_text(f), columns=xcols),
                   file_name="analysis_customer.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- 流失風險清單 ----
st.divider()
st.markdown("**⚠ 流失風險**：去年同段有業績、今年期間內無業績")
thr = st.number_input("門檻（去年除佣實收 ≥）", min_value=0, value=300000, step=50000, key="churn_thr")
if not dp.empty:
    prev_net = dp[dp["ext_net"] > 0].groupby("customer")["ext_net"].sum()
    cur_set = set(cust["customer"])
    churn = prev_net[(prev_net >= thr) & (~prev_net.index.isin(cur_set))].sort_values(ascending=False)
    if len(churn):
        rows = []
        for c, v in churn.items():
            msl = int(cy.loc[c, "months_since_last"]) if (not cy.empty and c in cy.index and cy.loc[c, "months_since_last"] is not None) else None
            sp = cy.loc[c, "main_salesperson"] if (not cy.empty and c in cy.index and "main_salesperson" in cy.columns) else None
            ind_ = cy.loc[c, "industry"] if (not cy.empty and c in cy.index and "industry" in cy.columns) else None
            rows.append({"客戶": c, "產業": ind_ or "未分類", "去年業務": sp or "",
                         "去年除佣實收": money(v), "距上次交易": f"{msl} 個月" if msl is not None else ""})
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("此門檻下無流失風險客戶。")

feedback_widget("analysis_customer")
