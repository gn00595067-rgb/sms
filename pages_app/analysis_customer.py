"""P13 客戶分析 — 誰在養公司、依賴多高、哪個產業在長、誰快掉了。

MEDIA / FINANCE / EXEC 可看全部；SALES 只看自己的客戶。
數字口徑見 core/analysis.py（= tools/mockup_generator.py 樣稿）。
"""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.docs.analysis_customer import build_doc
from core.format import COLORS, axis_wan, money, pct, status_color, wan
from core.ui import feedback_widget, page_header
from reports import export as X

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
is_exec = user["role"] == "EXEC"
page_header("👥 客戶分析", "誰在養公司、依賴多高、哪個產業在長、誰快掉了。")

f = A.filter_bar_analysis("acust", user=user)   # 固定分析口徑（詳細版）；發稿口徑見報表中心的老闆版報表
scope = f["scope"]

# 發稿口徑 / 自訂口徑：改用線層彙總的聚焦排名（避免與分析口徑互動圖表混口徑）
if scope["preset"] != "analysis":
    yf, yt = f["ym_from"], f["ym_to"]
    pf, pt = A.prev_window(yf, yt)
    lines = A.load_lines(yf, yt, scope, f, user)
    cl = A.agg_customers_lines(lines, A.load_lines(pf, pt, scope, f, user))
    st.caption(f"口徑：{('發稿口徑（老闆版）' if scope['preset']=='media' else '自訂')}｜線層彙總（交換併回原業務）。"
               "完整分析（ABC/產業/流失/矩陣）請切回「分析口徑」。")
    if cl.empty:
        st.info("此條件查無資料。"); feedback_widget("analysis_customer"); st.stop()
    tot = float(cl["ext_net"].sum())
    A.kpi_row([
        {"label": "活躍客戶數", "value": f"{len(cl)}"},
        {"label": "除佣實收合計", "value": money(tot)},
        {"label": "前 10 大佔比", "value": pct(float(cl.head(10)['ext_net'].sum())/tot if tot else None)},
        {"label": "帳上毛利率", "value": pct(float(cl['booked_profit'].sum())/tot if tot else None)},
    ])
    _co = f.get("company")
    st.markdown(f"**【{_co}】客戶排名（發稿口徑）**" if _co else "**客戶排名（發稿口徑）**")
    A.show_ranking(cl.head(200), [
        ("rank_in_year", "#", "int", {"width": "small"}), ("customer", "客戶", "text"),
        ("companies_multi", "公司(多)", "text", {"width": "small"}), ("salespeople_multi", "業務(多)", "text"),
        ("ext_net", "除佣實收", "money"),
        ("share", "佔比", "progress", {"max": float(cl["share"].max()) if len(cl) else 1.0}),
        ("net_cp_family", "全家企頻", "money"), ("net_cp_carrefour", "萬家福", "money"),
        ("net_fresh", "新鮮視", "money"), ("net_radio", "廣播", "money"),
        ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
        ("group_margin", "集團利率", "pct"), ("deals", "筆數", "int", {"width": "small"}),
        ("yoy_text", "同期%", "text", {"width": "small"}),
    ], key="cust_rank_scope")
    st.divider()
    X.ui.export_bar(build_doc(f, user), key="acust")
    feedback_widget("analysis_customer"); st.stop()

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
thr = int(st.session_state.get("churn_thr", 300000))
churn = A.churn_list(dp, cust, thr)          # 與下方清單同口徑（P0-4）
mk = A.margin_kpis(dw)                        # 統一毛利率口徑（P0-2）
total = float(cust["ext_net"].sum())
active = len(cust)
active_p = int(dp[dp["ext_net"] > 0]["customer"].nunique()) if not dp.empty else 0
total_p = float(dp[dp["ext_net"] > 0]["ext_net"].sum()) if not dp.empty else 0.0
newc = int((cust["status"] == "新客").sum())
top10 = float(cust.head(10)["ext_net"].sum())
top10_p = float(dp[dp["ext_net"] > 0].groupby("customer")["ext_net"].sum().sort_values(ascending=False).head(10).sum()) if not dp.empty else 0.0
avg_contrib = total / active if active else 0
avg_contrib_p = (total_p / active_p) if active_p else 0

A.kpi_row([
    {"label": "活躍客戶數", "value": f"{active}", "sub": f"同期 {active_p}",
     "delta": (active - active_p) / active_p if active_p else None},
    {"label": "新客戶", "value": f"{newc}", "sub": "今年第一次有業績"},
    {"label": "流失風險", "value": f"{len(churn)}",
     "sub": f"去年≥{thr//10000}萬今年無・去年共 {wan(churn['prev_net'].sum()) if len(churn) else '0'}"},
    {"label": "客戶平均貢獻", "value": money(avg_contrib), "sub": f"同期 {money(avg_contrib_p)}",
     "delta": (avg_contrib - avg_contrib_p) / avg_contrib_p if avg_contrib_p else None},
    {"label": "前 10 大佔比", "value": pct(top10 / total) if total else "–",
     "sub": f"同期 {pct(top10_p / total_p) if total_p else '–'}"},
    {"label": "帳上毛利率", "value": pct(mk["booked"]),
     "sub": f"只看有收入客戶 {pct(mk['booked_rev_only'])}"},
])

st.divider()

# ---- 兩張圖：ABC 分級 / 產業別（單位：萬）----
# ---- 兩張圖交叉連動：點 ABC 級別 → 產業圖只算該級客戶；點產業 → ABC 圖只算該產業客戶 ----
sel_tier = st.session_state.get("abc_focus")
sel_ind = st.session_state.get("ind_focus")

# 產業聚合（若選了 ABC 級別，只算該級客戶的訂單）
_tier_custs = set(cust[cust["abc_tier"] == sel_tier]["customer"]) if sel_tier else None
dw_ind = dw[dw["customer"].isin(_tier_custs)] if sel_tier else dw
ind = A.agg_industries(dw_ind, dp)
top = ind.head(8)[["industry", "ext_net", "customers", "booked_margin"]].copy()
other_label, other_inds = None, []
if len(ind) > 8:
    others = ind.iloc[8:]
    other_inds = others["industry"].tolist()
    other_label = f"其他 {len(others)} 類"
    onet = float(others["ext_net"].sum())
    top = pd.concat([top, pd.DataFrame([{
        "industry": other_label, "ext_net": onet,
        "customers": int(others["customers"].sum()),
        "booked_margin": float(others["booked_profit"].sum()) / onet if onet else 0,
    }])], ignore_index=True)

# ABC 聚合（若選了產業，只算該產業的客戶）
if sel_ind:
    _ind_custs = set(dw[dw["industry"].isin(other_inds if sel_ind == other_label else [sel_ind])]["customer"])
    cust_abc = cust[cust["customer"].isin(_ind_custs)]
else:
    cust_abc = cust

c1, c2 = st.columns(2)
with c1:
    st.markdown("**客戶分級（ABC）：多少客戶貢獻 80% 業績**"
                + (f"　·　僅「{sel_ind}」的客戶" if sel_ind else "　·　點長條看該級公司"))
    abc = cust_abc.groupby("abc_tier").agg(n=("customer", "count"), net=("ext_net", "sum")).reindex(["A", "B", "C"]).dropna()
    tier_label = {"A": "A 級（累計 80%）", "B": "B 級（80–95%）", "C": "C 級（最後 5%）"}
    tier_color = {"A": COLORS["accent"], "B": COLORS["accent2"], "C": COLORS["accent3"]}
    tiers = list(abc.index)
    if abc.empty:
        st.caption("此產業無客戶。")
    else:
        fig = go.Figure()
        for tier in tiers:
            dim = sel_tier is not None and tier != sel_tier
            fig.add_bar(y=[tier_label[tier]], x=[float(abc.loc[tier, "net"]) / 10000], orientation="h",
                        marker_color=tier_color[tier], name=tier, cliponaxis=False,
                        customdata=[tier], opacity=0.35 if dim else 1.0,
                        text=f"{wan(abc.loc[tier, 'net'])}｜{int(abc.loc[tier, 'n'])} 家",
                        textposition="outside", hovertemplate="%{text}　（點選）<extra></extra>")
        fig.update_layout(showlegend=False, height=220, margin=dict(l=8, r=8, t=8, b=8),
                          yaxis=dict(autorange="reversed"), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
        fig.update_xaxes(range=[0, float(abc["net"].max()) / 10000 * 1.45], ticksuffix="萬", tickformat=",.0f")
        abc_ev = st.plotly_chart(fig, use_container_width=True, key="abc_chart", on_select="rerun")
        # 點選 ABC → 設定分級焦點、清掉產業焦點（一次一個作用中）
        if abc_ev and getattr(abc_ev, "selection", None) and abc_ev.selection.get("points"):
            p = abc_ev.selection["points"][0]
            cd = p.get("customdata")
            picked = (cd[0] if isinstance(cd, (list, tuple)) and cd else cd) if cd else None
            if picked is None and p.get("curve_number") is not None and p["curve_number"] < len(tiers):
                picked = tiers[p["curve_number"]]
            if picked and picked != sel_tier:
                st.session_state["abc_focus"] = picked
                st.session_state.pop("ind_focus", None)
                st.rerun()
    if sel_tier or sel_ind:
        if st.button("← 顯示全部（清除連動篩選）", key="abc_clear"):
            st.session_state.pop("abc_focus", None)
            st.session_state.pop("ind_focus", None)
            st.rerun()
with c2:
    st.markdown("**產業別：業績、客戶數、毛利率（前 8 + 其他）**"
                + (f"　·　僅 {sel_tier} 級客戶" if sel_tier else "　·　點長條看該產業公司"))
    bar_colors = [COLORS["accent"] if (sel_ind is None or lbl == sel_ind) else "#cbd5e1"
                  for lbl in top["industry"]]
    fig2 = go.Figure()
    fig2.add_bar(y=top["industry"], x=top["ext_net"] / 10000, orientation="h",
                 marker_color=bar_colors, cliponaxis=False,
                 customdata=[[lbl] for lbl in top["industry"]],
                 text=[f"{wan(n)}｜{int(c)} 家｜{pct(m)}" for n, c, m in
                       zip(top["ext_net"], top["customers"], top["booked_margin"])],
                 textposition="outside", hovertemplate="%{y}: %{text}　（點選）<extra></extra>")
    fig2.update_layout(showlegend=False, height=max(220, 26 * len(top)), margin=dict(l=8, r=8, t=8, b=8),
                       yaxis=dict(autorange="reversed"), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    fig2.update_xaxes(range=[0, float(top["ext_net"].max()) / 10000 * 1.5] if len(top) else [0, 1],
                      ticksuffix="萬", tickformat=",.0f")
    ind_ev = st.plotly_chart(fig2, use_container_width=True, key="ind_chart", on_select="rerun")
    # 點選產業 → 設定產業焦點、清掉分級焦點
    if ind_ev and getattr(ind_ev, "selection", None) and ind_ev.selection.get("points"):
        p = ind_ev.selection["points"][0]
        cd = p.get("customdata")
        picked = (cd[0] if isinstance(cd, (list, tuple)) and cd else cd) if cd else None
        if picked is None and p.get("point_index") is not None and p["point_index"] < len(top):
            picked = top["industry"].iloc[p["point_index"]]
        if picked and picked != sel_ind:
            st.session_state["ind_focus"] = picked
            st.session_state.pop("abc_focus", None)
            st.rerun()

# ---- 點選 ABC 長條 → 動態列出該級公司 ----
if sel_tier and sel_tier in tier_label:
    sub = cust[cust["abc_tier"] == sel_tier].copy()
    st.markdown(
        f"**{tier_label[sel_tier]}：{len(sub)} 家・合計 {wan(sub['ext_net'].sum())}"
        f"（佔全體 {pct(sub['ext_net'].sum() / total) if total else '–'}）**　·　點一列 → 客戶頁")
    tier_cols = [
        ("rank_in_year", "#", "int", {"width": "small", "pin": True}),
        ("customer", "客戶", "text", {"pin": True}),
        ("industry", "產業", "text", {"width": "small"}),
        ("main_salesperson", "主要業務", "text", {"width": "small"}),
        ("status", "狀態", "text", {"width": "small"}),
        ("ext_net", "除佣實收", "money"),
        ("yoy_text", "同期%", "text", {"width": "small"}),
        ("share", "佔比", "progress", {"max": float(cust["share"].max())}),
        ("cum_share", "累計佔比", "pct", {"width": "small"}),
        ("booked_margin", "毛利率", "pct", {"width": "small"}),
        ("net_margin", "淨利率", "pct", {"width": "small"}),
        ("deals", "筆數", "int", {"width": "small"}),
    ]
    tev = A.show_ranking(sub, tier_cols, key="abc_tier_rank", on_select="rerun",
                         height=min(460, 40 + 36 * len(sub)))
    if tev and getattr(tev, "selection", None) and tev.selection.get("rows"):
        st.session_state["customer_focus"] = sub.iloc[tev.selection["rows"][0]]["customer"]
        st.switch_page("pages_app/customer_detail.py")

# ---- 點選產業長條 → 動態列出該產業公司 ----
# 產業記在「每筆訂單」上，同一客戶可跨多個產業。這裡的金額/毛利/筆數只算「該產業的訂單」，
# 合計 = 長條的數字（與 agg_industries 同口徑）；「主力產業」欄另標客戶主檔產業供參考。
sel_ind = st.session_state.get("ind_focus")
if sel_ind:
    dwc = dw[dw["ext_net"] > 0].copy()
    dwc["industry"] = dwc["industry"].fillna("(未分類)")
    if sel_ind == other_label:
        dsel = dwc[dwc["industry"].isin(other_inds)]
        title_ind = f"其他 {len(other_inds)} 類產業"
    else:
        dsel = dwc[dwc["industry"] == sel_ind]
        title_ind = sel_ind
    if dsel.empty:
        st.info(f"「{title_ind}」查無訂單。")
    else:
        g = dsel.groupby("customer").agg(
            ext_net=("ext_net", "sum"), booked_profit=("booked_profit", "sum"),
            net_profit=("net_profit", "sum"), deals=("deal_id", "count")).reset_index()
        nz = g["ext_net"].where(g["ext_net"] != 0)
        g["booked_margin"] = g["booked_profit"] / nz
        g["net_margin"] = g["net_profit"] / nz
        itot = float(g["ext_net"].sum())
        g["share"] = g["ext_net"] / itot if itot else 0.0
        cmap = cust.set_index("customer")
        for col in ("status", "main_salesperson", "abc_tier"):
            g[col] = g["customer"].map(cmap[col])
        g["main_industry"] = g["customer"].map(cmap["industry"]).fillna("(未分類)")
        # 標記跨產業：主力產業不屬於目前篩選的產業（其他類則看是否落在該群產業內）
        inset = set(other_inds) if sel_ind == other_label else {sel_ind}
        cross = ~g["main_industry"].isin(inset)
        n_cross = int(cross.sum())
        g["main_industry"] = ["〔跨〕" + mi if x else mi for mi, x in zip(g["main_industry"], cross)]
        g = g.sort_values("ext_net", ascending=False).reset_index(drop=True)
        g["rank_in_year"] = range(1, len(g) + 1)
        cross_note = f"　·　其中 {n_cross} 家為跨產業客戶（主力產業標「〔跨〕」，金額只算該產業那部分）" if n_cross else ""
        st.markdown(
            f"**產業「{title_ind}」：{len(g)} 家・該產業合計 {wan(itot)}"
            f"（佔全體 {pct(itot / total) if total else '–'}）**　·　"
            "金額/毛利/筆數只算該產業訂單　·　點一列 → 客戶頁" + cross_note)
        ind_cols = [
            ("rank_in_year", "#", "int", {"width": "small", "pin": True}),
            ("customer", "客戶", "text", {"pin": True}),
            ("main_industry", "主力產業", "text", {"width": "small"}),
            ("main_salesperson", "主要業務", "text", {"width": "small"}),
            ("status", "狀態", "text", {"width": "small"}),
            ("abc_tier", "分級", "text", {"width": "small"}),
            ("ext_net", "該產業除佣實收", "money"),
            ("share", "佔該產業%", "progress", {"max": float(g["share"].max())}),
            ("booked_margin", "毛利率", "pct", {"width": "small"}),
            ("net_margin", "淨利率", "pct", {"width": "small"}),
            ("deals", "筆數", "int", {"width": "small"}),
        ]
        iev = A.show_ranking(g, ind_cols, key="ind_tier_rank", on_select="rerun",
                             height=min(460, 40 + 36 * len(g)))
        if iev and getattr(iev, "selection", None) and iev.selection.get("rows"):
            st.session_state["customer_focus"] = g.iloc[iev.selection["rows"][0]]["customer"]
            st.switch_page("pages_app/customer_detail.py")

# ---- 客戶價值矩陣（散佈圖，x 平方根刻度；可切毛利率口徑 P2-1）----
st.markdown("**客戶價值矩陣：金額 × 毛利率 × 頻率 × 狀態**")
y_opt = st.radio("毛利率口徑", ["帳上毛利率", "集團淨利率"], index=(1 if is_exec else 0),
                 horizontal=True, key="scatter_ycol")
ycol = "net_margin" if y_opt == "集團淨利率" else "booked_margin"
xmax = float(cust["ext_net"].max()) * 1.06
tickvals_orig = [v for v in (250_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000) if v <= xmax]
fig3 = go.Figure()
shape_map = {"既有": "circle", "新客": "diamond", "回流": "square"}
for status in ("既有", "新客", "回流"):
    d = cust[cust["status"].fillna("既有").map(lambda s: s if s in shape_map else "既有") == status]
    if d.empty:
        continue
    fig3.add_trace(go.Scatter(
        x=[math.sqrt(max(v, 0)) for v in d["ext_net"]], y=d[ycol],
        mode="markers", name=status,
        marker=dict(size=[4 + math.sqrt(max(n, 0)) * 3 for n in d["deals"]],
                    color=status_color(status), symbol=shape_map[status], opacity=0.8,
                    line=dict(width=1, color="white")),
        customdata=list(zip(d["customer"], d["ext_net"], d["deals"])),
        hovertemplate="%{customdata[0]}<br>除佣 %{customdata[1]:,.0f}<br>" + y_opt + " %{y:.1%}<br>%{customdata[2]} 筆<extra></extra>",
    ))
# 前 5 大直接標名字（P2-1）
top5 = cust.head(5)
fig3.add_trace(go.Scatter(
    x=[math.sqrt(max(v, 0)) for v in top5["ext_net"]], y=top5[ycol],
    mode="text", text=top5["customer"].str.slice(0, 8), textposition="top center",
    textfont=dict(size=10), showlegend=False, hoverinfo="skip"))
fig3.add_hline(y=0.16, line_dash="dash", line_color="#cbd3de")
fig3.add_hline(y=0.35, line_dash="dash", line_color="#cbd3de")
fig3.update_xaxes(tickvals=[math.sqrt(v) for v in tickvals_orig],
                  ticktext=[f"{v/10000:,.0f}萬" for v in tickvals_orig], title="除佣實收（平方根刻度）")
fig3.update_yaxes(title=y_opt, tickformat=".0%")
fig3.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8),
                   legend=dict(orientation="h", y=1.08),
                   font=dict(family="Noto Sans TC, Microsoft JhengHei"))
st.plotly_chart(fig3, use_container_width=True)

# ---- 客戶排名表（精簡欄，可展開全部）----
# §3.4：公司篩選時標題標公司，佔比分母 = 該公司合計（dw 已被 load_deals 依公司篩選）
_co = f.get("company")
_rank_title = (f"**【{_co}】客戶排名**（佔比＝佔該公司總計；點一列 → 客戶頁）" if _co
               else "**客戶排名**（點一列 → 客戶頁；下載 Excel 為完整名單）")
st.markdown(_rank_title)
show_all = st.toggle("顯示全部欄位", value=True, key="cust_allcols")
trends, _months = A.customer_trends(cust.head(50)["customer"].tolist(), f["ym_from"], f["ym_to"])
tbl = cust.head(50).copy()
tbl["mix"] = tbl.apply(lambda r: A.platform_mix_text(r["net_cp"], r["net_fresh"], r["net_radio"], r["net_other"]), axis=1)
tbl["trend"] = tbl["customer"].map(lambda c: trends.get(c, []))

slim = [
    ("rank_in_year", "#", "int", {"width": "small", "pin": True}),
    ("customer", "客戶", "text", {"pin": True}),
    ("status", "狀態", "text", {"width": "small"}),
    ("ext_net", "除佣實收", "money"),
    ("yoy_text", "同期%", "text", {"width": "small"}),
    ("share", "佔比", "progress", {"max": float(cust["share"].max())}),
    ("booked_margin", "毛利率", "pct", {"width": "small"}),
    ("net_margin", "淨利率", "pct", {"width": "small"}),
    ("deals", "筆數", "int", {"width": "small"}),
    ("trend", "月趨勢", "line"),
    ("strategy_hint", "策略提示", "text"),
]
full = [
    ("rank_in_year", "#", "int", {"width": "small", "pin": True}),
    ("customer", "客戶", "text", {"pin": True}),
    ("industry", "產業", "text"),
    ("companies_multi", "公司(多)", "text", {"width": "small"}),
    ("salespeople_multi", "業務(多)", "text"),
    ("status", "狀態", "text", {"width": "small"}),
    ("ext_net", "除佣實收", "money"),
    ("yoy_text", "同期%", "text", {"width": "small"}),
    ("share", "佔比", "progress", {"max": float(cust["share"].max())}),
    ("cum_share", "累計佔比", "pct"),
    ("net_cp_family", "全家企頻", "money"),
    ("net_cp_carrefour", "萬家福", "money"),
    ("net_fresh", "新鮮視", "money"),
    ("net_radio", "廣播", "money"),
    ("booked_profit", "帳上毛利", "money"),
    ("booked_margin", "毛利率", "pct"),
    ("net_margin", "淨利率", "pct"),
    ("deals", "筆數", "int", {"width": "small"}),
    ("months_since_last", "距上次交易", "int", {"width": "small"}),
    ("avg_deal", "平均單筆", "money"),
    ("trend", "月趨勢", "line"),
    ("strategy_hint", "策略提示", "text"),
]
event = A.show_ranking(tbl, full if show_all else slim, key="cust_rank", on_select="rerun")

if event and getattr(event, "selection", None) and event.selection.get("rows"):
    idx = event.selection["rows"][0]
    st.session_state["customer_focus"] = tbl.iloc[idx]["customer"]
    st.switch_page("pages_app/customer_detail.py")

# ---- 流失風險清單（與 KPI 同口徑）----
st.divider()
st.markdown("**⚠ 流失風險**：去年同段有業績、今年期間內無業績")
st.number_input("門檻（去年除佣實收 ≥）", min_value=0, value=thr, step=50000, key="churn_thr")
if len(churn):
    disp = pd.DataFrame({
        "客戶": churn["customer"],
        "產業": churn["industry"].where(churn["industry"].notna(), "未分類"),
        "去年業務": churn["main_salesperson"].where(churn["main_salesperson"].notna(), ""),
        "去年除佣實收": churn["prev_net"].round(0),
        "距上次交易(月)": churn["months_since_last"],
    })
    st.dataframe(disp, hide_index=True, use_container_width=True, column_config={
        "去年除佣實收": st.column_config.NumberColumn("去年除佣實收", format="localized"),
        "距上次交易(月)": st.column_config.NumberColumn("距上次交易(月)", format="%d"),
    })
    st.caption(f"共 {len(churn)} 家、去年同段合計 {money(churn['prev_net'].sum())}（與上方 KPI 同口徑）")
else:
    st.caption("此門檻下無流失風險客戶。")

# ---- 資料品質面板（EXEC，P2-3）----
if is_exec:
    dq = A.data_quality_summary()
    with st.expander(f"🧹 資料品質（缺產業 {dq['no_industry_n']} 家・異常業務名 {len(dq['bad_salesperson'])}・疑似異名 {len(dq['dup_groups'])} 組）"):
        st.caption("主檔沒產業的活躍客戶（排名表產業改用訂單眾數已補顯示，但主檔仍建議補齊）：")
        st.write("、".join(dq["no_industry"][:40]) + ("…" if dq["no_industry_n"] > 40 else "") or "（無）")
        if dq["bad_salesperson"]:
            st.caption(f"異常業務名（已停用）：{'、'.join(dq['bad_salesperson'])}")
        if dq["dup_groups"]:
            st.caption("疑似同一客戶的異名（去掉公司後綴後相同）：")
            st.dataframe(pd.DataFrame(dq["dup_groups"])[["names", "c"]].rename(columns={"names": "名稱", "c": "筆數"}),
                         hide_index=True, use_container_width=True)
        from core.uimode import page_available
        if page_available("masters"):
            st.page_link("pages_app/masters.py", label="→ 去主檔維護補產業", icon="🗂️")

st.divider()
X.ui.export_bar(build_doc(f, user), key="acust")
feedback_widget("analysis_customer")
