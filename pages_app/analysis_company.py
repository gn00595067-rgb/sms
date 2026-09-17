"""P16 公司分析 — 三家公司加起來到底賺多少（三層毛利橋 + 目標達成）。

MEDIA / FINANCE / EXEC 可看；SALES 通常看不到公司整體，但仍受角色限制。
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.data import query_df
import pandas as pd

from core.format import COLORS, company_color, money, pct, wan, ym_text
from core.uimode import page_available
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "FINANCE", "EXEC")
page_header("🏛️ 公司分析", "三層毛利橋：帳上 → 集團 → 淨利；目標達成用老闆儀表板口徑。")

f = A.filter_bar_analysis("aco", user=user, show_industry=False, show_salesperson=False, show_scope=True)
yf, yt = f["ym_from"], f["ym_to"]
pf, pt = A.prev_window(yf, yt)
scope = f["scope"]

# 線層（口徑感知）：平台總覽與客戶數用它，KPI 三層毛利橋仍用 v_company_month（集團口徑固定）
lines = A.load_lines(yf, yt, scope=scope)
cust_by_co = lines.groupby("company")["customer_id"].nunique() if not lines.empty else pd.Series(dtype=int)
grp_cust = int(lines["customer_id"].nunique()) if not lines.empty else 0


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
        st.caption(f"客戶 {int(cust_by_co.get(name, 0))} 家（不重複）")
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
        st.caption(f"三公司不重複 {grp_cust} 家")

# 口徑差異對照（發稿口徑時顯示「為什麼跟老闆的數字不一樣」）P§3.5
if scope.get("preset") == "media":
    bridge = A.scope_bridge(yf, yt)
    if bridge:
        st.caption("　".join(f"{lab} {money(v)}" for lab, v in bridge))

st.divider()

# ---- 月堆疊柱 / 三層毛利橋 ----
c1, c2 = st.columns(2)
with c1:
    st.markdown("**各公司月業績（除佣實收，對外；單位：萬）**")
    cm = query_df(
        """select company, perf_ym, sum(ext_net) net from v_company_month
           where perf_ym between %s and %s and company = any(%s) group by company, perf_ym order by perf_ym""",
        (yf, yt, main_cos))
    months = A.month_range(yf, yt)
    mlabels = [ym_text(m) for m in months]
    by_co = {}
    for name in main_cos:
        sub = cm[cm["company"] == name] if not cm.empty else cm
        by_co[name] = {r["perf_ym"]: float(r["net"] or 0) for _, r in sub.iterrows()} if not cm.empty else {}
    fig = go.Figure()
    for name in main_cos:
        fig.add_bar(x=mlabels, y=[by_co[name].get(m, 0) / 10000 for m in months], name=name,
                    marker_color=company_color(name), marker_line_width=1, marker_line_color="white")
    totals = [sum(by_co[name].get(m, 0) for name in main_cos) for m in months]
    fig.add_trace(go.Scatter(x=mlabels, y=[t / 10000 for t in totals], mode="text",
                             text=[wan(t) for t in totals], textposition="top center",
                             textfont=dict(size=10), showlegend=False, hoverinfo="skip"))
    fig.update_layout(barmode="stack", height=300, margin=dict(l=8, r=8, t=24, b=8),
                      legend=dict(orientation="h", y=1.12, traceorder="normal"),
                      font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    fig.update_yaxes(ticksuffix="萬", tickformat=",.0f")
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

# ---- 月毛利率趨勢（帳上 / 集團）P1-7 ----
st.markdown("**月毛利率趨勢（帳上 / 集團）**")
gmm = query_df(
    """select perf_ym, booked_margin, group_margin from v_group_month
       where perf_ym between %s and %s order by perf_ym""", (yf, yt))
if not gmm.empty:
    gmap_b = {r["perf_ym"]: (float(r["booked_margin"]) if r["booked_margin"] is not None else None) for _, r in gmm.iterrows()}
    gmap_g = {r["perf_ym"]: (float(r["group_margin"]) if r["group_margin"] is not None else None) for _, r in gmm.iterrows()}
    figm = go.Figure()
    figm.add_trace(go.Scatter(x=mlabels, y=[gmap_b.get(m) for m in months], mode="lines+markers",
                              name="帳上毛利率", line=dict(color=COLORS["accent"])))
    figm.add_trace(go.Scatter(x=mlabels, y=[gmap_g.get(m) for m in months], mode="lines+markers",
                              name="集團毛利率", line=dict(color=COLORS["company"]["東吳"])))
    figm.update_yaxes(tickformat=".0%")
    figm.update_layout(height=260, margin=dict(l=8, r=8, t=8, b=8),
                       legend=dict(orientation="h", y=1.12), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(figm, use_container_width=True)
    if f.get("includes_open"):
        st.caption("⚠ 區間含進行中月份，末月毛利率偏低多因當月尚未登打完整，非真的下滑。")

# ---- 目標達成 ----
st.markdown("**目標達成**（口徑：企頻＋新鮮視、不含公司戶、不含交換）")
tgt = query_df(
    """select company, period_label, target_amount, actual, remaining, achieved_pct,
              months_left, required_monthly, forecast_amount, achieved_pct_with_forecast, year, period_no, period_type
       from v_target_progress order by company, year, period_no""")
if not tgt.empty:
    has_forecast = float(tgt["forecast_amount"].fillna(0).astype(float).sum()) > 0
    # 集團合計列（同期別加總）
    grp_rows = []
    for (pt_, pn, yr, plabel), sub in tgt.groupby(["period_type", "period_no", "year", "period_label"]):
        ta = float(sub["target_amount"].sum()); ac = float(sub["actual"].sum())
        grp_rows.append({"company": "集團合計", "period_label": plabel, "target_amount": ta,
                         "actual": ac, "remaining": ta - ac,
                         "achieved_pct": ac / ta if ta else None,
                         "months_left": sub["months_left"].max(),
                         "required_monthly": float(sub["required_monthly"].fillna(0).astype(float).sum()) or None,
                         "achieved_pct_with_forecast": None})
    tshow = pd.concat([tgt, pd.DataFrame(grp_rows)], ignore_index=True)
    cols_spec = [
        ("company", "公司", "text"), ("period_label", "期間", "text"),
        ("target_amount", "目標", "money"), ("actual", "進單", "money"),
        ("remaining", "待追", "money"),
        ("achieved_pct", "達成率", "progress", {"max": 1.0}),
        ("months_left", "剩餘月份", "int", {"width": "small"}), ("required_monthly", "每月需達", "money"),
    ]
    if has_forecast:
        cols_spec.append(("achieved_pct_with_forecast", "加預估後達成率", "pct"))
    A.show_ranking(tshow, cols_spec, height=None, key="co_tgt")
    # 下一季 / 年度目標提示
    yr_now = A.as_of()["as_of_year"]
    has_future = not tgt[(tgt["year"] >= yr_now) & (tgt["period_no"] >= ((A.as_of()["as_of_month"] - 1)//3 + 2))].empty
    if not has_future:
        st.caption("尚未設定下一季 / 年度目標。")
        if page_available("masters"):
            st.page_link("pages_app/masters.py", label="→ 去主檔維護設定目標", icon="🗂️")
else:
    st.caption("尚未設定目標（主檔維護 → 目標）。")

# ---- 平台總計總覽（老闆版：公司 × 報表平台 × 指標）§3.1 ----
st.markdown("**平台總計總覽**（公司 × 報表平台；老闆四欄 + 健康視）")
oc = st.columns([3, 2])
metric = oc[0].radio("指標", ["除佣實收", "成本", "帳上毛利", "帳上利率", "集團毛利", "集團利率"],
                     horizontal=True, key="co_metric")
prange = oc[1].segmented_control("平台範圍", ["全部", "自媒體（不含廣播）", "只看廣播"],
                                 default="全部", key="co_prange")
if lines.empty:
    st.info("查無資料")
else:
    lt = lines.copy()
    if prange == "自媒體（不含廣播）":
        lt = lt[lt["report_platform"].isin(A.OWN_MEDIA)]
    elif prange == "只看廣播":
        lt = lt[lt["report_platform"] == "廣播"]
    lt = lt.copy()
    lt["_gp"] = A.line_group_profit(lt)
    is_ratio = metric in ("帳上利率", "集團利率")
    numer = {"除佣實收": "net_amount", "成本": "cost_amount", "帳上毛利": "booked_profit",
             "帳上利率": "booked_profit", "集團毛利": "_gp", "集團利率": "_gp"}[metric]
    plats = [p for p in A.REPORT_PLATFORM_ORDER if p in set(lt["report_platform"])]
    net_by = lt.pivot_table(index="company", columns="report_platform", values="net_amount",
                            aggfunc="sum", fill_value=0.0)
    num_by = lt.pivot_table(index="company", columns="report_platform", values=numer,
                            aggfunc="sum", fill_value=0.0)
    cust_by = lt.groupby("company")["customer_id"].nunique()
    order = [c for c in ("聲活", "東吳", "鉑霖", "瑞迪") if c in num_by.index]
    grand_net = float(lt["net_amount"].sum())
    disp_rows = []
    for name in order + ["三公司合計"]:
        if name == "三公司合計":
            n_net = net_by.reindex(order).sum()
            n_num = num_by.reindex(order).sum()
            row_net = grand_net
            cust = int(lt["customer_id"].nunique())
        else:
            n_net = net_by.loc[name] if name in net_by.index else None
            n_num = num_by.loc[name] if name in num_by.index else None
            row_net = float(lt[lt["company"] == name]["net_amount"].sum())
            cust = int(cust_by.get(name, 0))
        row = {"company": name}
        tot_num = 0.0
        for p in plats:
            v_num = float(n_num[p]) if n_num is not None and p in n_num.index else 0.0
            v_net = float(n_net[p]) if n_net is not None and p in n_net.index else 0.0
            tot_num += v_num
            row[p] = (v_num / v_net if v_net else None) if is_ratio else v_num
        row["合計"] = (tot_num / row_net if row_net else None) if is_ratio else tot_num
        row["客戶數"] = cust
        row["佔比"] = (row_net / grand_net) if grand_net else 0.0
        disp_rows.append(row)
    odf = pd.DataFrame(disp_rows)
    kind = "pct" if is_ratio else "money"
    spec = [("company", "公司", "text")]
    spec += [(p, p, kind) for p in plats]
    spec += [("合計", f"合計（{metric}）", kind), ("客戶數", "客戶數", "int"),
             ("佔比", "佔比", "progress", {"max": 1.0})]
    A.show_ranking(odf, spec, height=None, key="co_overview")
    st.caption(f"口徑：{scope.get('preset')}｜{prange}；利率＝Σ毛利 ÷ Σ除佣（非平均）。"
               "營運／其它平台在發稿口徑下不列入；分析口徑會另成欄。")

# ---- 進單 + 預估（公司 × 月，每家三列：進單/預估/合計）P1-5 ----
st.markdown("**進單 + 預估（公司 × 月，單位：萬）**")
bvf = query_df(
    """select company, perf_ym, perf_ym_text, booked_net, forecast_amount
       from v_booked_vs_forecast where perf_ym between %s and %s order by perf_ym""", (yf, yt))
if bvf.empty or bvf[["booked_net", "forecast_amount"]].astype(float).abs().to_numpy().sum() == 0:
    st.caption("尚無進單 / 預估資料。")
else:
    mcols = [ym_text(m) for m in months]
    m_by_text = {ym_text(m): m for m in months}
    has_fc = float(bvf["forecast_amount"].fillna(0).astype(float).sum()) > 0
    # 只留有數字的公司（去掉瑞迪 / 錄音室等整列 0）
    keep = (bvf.assign(v=bvf["booked_net"].astype(float).abs() + bvf["forecast_amount"].astype(float).abs())
            .groupby("company")["v"].sum())
    companies = [c for c in keep[keep > 0].index]
    order = {"聲活": 0, "東吳": 1, "鉑霖": 2}
    companies.sort(key=lambda c: order.get(c, 9))
    rows = []
    for co in companies:
        sub = bvf[bvf["company"] == co]
        bk = {ym_text(r["perf_ym"]): float(r["booked_net"] or 0) for _, r in sub.iterrows()}
        fc = {ym_text(r["perf_ym"]): float(r["forecast_amount"] or 0) for _, r in sub.iterrows()}
        row_bk = {"公司": co, "類型": "進單", **{mc: bk.get(mc, 0) / 10000 for mc in mcols}}
        row_bk["合計"] = sum(bk.values()) / 10000
        rows.append(row_bk)
        if has_fc:
            row_fc = {"公司": co, "類型": "預估", **{mc: fc.get(mc, 0) / 10000 for mc in mcols}}
            row_fc["合計"] = sum(fc.values()) / 10000
            row_tt = {"公司": co, "類型": "合計", **{mc: (bk.get(mc, 0) + fc.get(mc, 0)) / 10000 for mc in mcols}}
            row_tt["合計"] = (sum(bk.values()) + sum(fc.values())) / 10000
            rows.append(row_fc)
            rows.append(row_tt)
    tbl = pd.DataFrame(rows)
    cfg = {mc: st.column_config.NumberColumn(mc, format="%.0f", width="small") for mc in mcols + ["合計"]}
    cfg["公司"] = st.column_config.TextColumn("公司", width="small")
    cfg["類型"] = st.column_config.TextColumn("類型", width="small")
    st.dataframe(tbl, column_config=cfg, hide_index=True, use_container_width=True)
    if not has_fc:
        st.caption("目前只有進單；預估資料需在主檔維護 → 預估 輸入後才會出現「預估 / 合計」列。")

feedback_widget("analysis_company")
