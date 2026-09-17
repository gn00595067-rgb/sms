"""
core/docs/analysis_customer.py — 客戶分析頁的列印版（不碰 streamlit）

印出來的是「乾淨靜態版」（CLAUDE_CODE_TASK_5 §5）：畫面上的點選鑽研（ABC/產業長條、
客戶價值矩陣切換、點列進客戶頁）留在畫面互動，這裡只收 KPI / 圖 / 表 / 說明。
月報包（scripts/export_pack.py）直接呼叫本 build_doc。
"""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from core import analysis as A
from core.format import COLORS, money, pct, status_color, wan
from reports import export as X

from ._base import CUM, EXT_NET, SAME_PERIOD, SHARE, header, open_month_note


def _scope_preset(f: dict) -> str:
    s = f.get("scope")
    return s.get("preset") if isinstance(s, dict) else (s or "analysis")


def build_doc(f: dict, user: dict | None = None) -> X.Doc:
    yf, yt = f["ym_from"], f["ym_to"]
    pf, pt = A.prev_window(yf, yt)
    preset = _scope_preset(f)
    doc = header("客戶分析", subtitle="誰在養公司、依賴多高、哪個產業在長、誰快掉了",
                 f=f, user=user, orientation="landscape", as_of_note=open_month_note())

    # ---- 發稿 / 自訂口徑：線層聚焦排名（與畫面一致）----
    if preset != "analysis":
        scope = f.get("scope")
        cl = A.agg_customers_lines(A.load_lines(yf, yt, scope, f, user), A.load_lines(pf, pt, scope, f, user))
        if cl.empty:
            doc.text("此條件查無資料。", "callout")
            return doc
        tot = float(cl["ext_net"].sum())
        doc.kpis([
            {"label": "活躍客戶數", "value": f"{len(cl)}"},
            {"label": "除佣實收合計", "value": money(tot)},
            {"label": "前 10 大佔比", "value": pct(float(cl.head(10)["ext_net"].sum()) / tot if tot else None)},
            {"label": "帳上毛利率", "value": pct(float(cl["booked_profit"].sum()) / tot if tot else None)},
        ], per_row=4)
        doc.text(f"口徑：{'發稿口徑（老闆版）' if preset == 'media' else '自訂'}｜線層彙總（交換併回原業務）。"
                 f"{EXT_NET}。完整分析（ABC/產業/流失/矩陣）請切回分析口徑。", "note")
        doc.table("客戶排名（發稿口徑）", cl.head(200), X.cols(
            ("rank_in_year", "#", "int"), ("customer", "客戶", "text"),
            ("companies_multi", "公司(多)", "text"), ("salespeople_multi", "業務(多)", "text"),
            X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
            X.Col("share", "佔比", "progress", max=float(cl["share"].max()) if len(cl) else 1.0, help=SHARE),
            ("net_cp_family", "全家企頻", "money"), ("net_cp_carrefour", "萬家福", "money"),
            ("net_fresh", "新鮮視", "money"), ("net_radio", "廣播", "money"),
            ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
            X.Col("yoy_text", "同期%", "text", help=SAME_PERIOD)),
            wide=True, note=f"{SAME_PERIOD}；佔比分母＝期間客戶合計。")
        return doc

    # ---- 分析口徑：完整版 ----
    dw = A.load_deals(yf, yt, f, exclude_barter=f["exclude_barter"], user=user)
    if dw.empty:
        doc.text("此條件查無資料。", "callout")
        return doc
    dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
    cust = A.agg_customers(dw, dp, A.customer_year(yf.year))
    total = float(cust["ext_net"].sum())
    active = len(cust)
    active_p = int(dp[dp["ext_net"] > 0]["customer"].nunique()) if not dp.empty else 0
    total_p = float(dp[dp["ext_net"] > 0]["ext_net"].sum()) if not dp.empty else 0.0
    newc = int((cust["status"] == "新客").sum())
    top10 = float(cust.head(10)["ext_net"].sum())
    top10_p = float(dp[dp["ext_net"] > 0].groupby("customer")["ext_net"].sum().sort_values(ascending=False).head(10).sum()) if not dp.empty else 0.0
    avg_c = total / active if active else 0
    avg_cp = (total_p / active_p) if active_p else 0
    thr = 300000
    churn = A.churn_list(dp, cust, thr)
    mk = A.margin_kpis(dw)

    doc.kpis([
        {"label": "活躍客戶數", "value": f"{active}", "sub": f"同期 {active_p} 家",
         "delta": (active - active_p) / active_p if active_p else "同期不可比"},
        {"label": "新客戶", "value": f"{newc}", "sub": "今年第一次有業績"},
        {"label": "流失風險", "value": f"{len(churn)}",
         "sub": f"去年≥{thr // 10000}萬今年無・去年共 {wan(churn['prev_net'].sum()) if len(churn) else '0'}"},
        {"label": "客戶平均貢獻", "value": money(avg_c), "sub": f"同期 {money(avg_cp)}",
         "delta": (avg_c - avg_cp) / avg_cp if avg_cp else "同期不可比"},
        {"label": "前 10 大佔比", "value": pct(top10 / total) if total else "–",
         "sub": f"同期 {pct(top10_p / total_p) if total_p else '–'}"},
        {"label": "帳上毛利率", "value": pct(mk["booked"]), "sub": f"只看有收入客戶 {pct(mk['booked_rev_only'])}"},
    ], per_row=6)
    doc.text(f"**同期比較**：{SAME_PERIOD}。「新客戶」＝今年才第一次有業績；"
             "「流失風險」＝去年同段有業績、今年期間內無業績。", "note")

    # ---- Row：ABC 分級 / 產業別 ----
    doc.heading("客戶結構")
    abc = cust.groupby("abc_tier").agg(n=("customer", "count"), net=("ext_net", "sum")).reindex(["A", "B", "C"]).dropna()
    tier_label = {"A": "A 級", "B": "B 級", "C": "C 級"}
    tier_color = {"A": COLORS["accent"], "B": COLORS["accent2"], "C": COLORS["accent3"]}
    figA = go.Figure()
    for tier in list(abc.index):
        figA.add_bar(y=[tier_label[tier]], x=[float(abc.loc[tier, "net"]) / 1e4], orientation="h",
                     marker_color=tier_color[tier], cliponaxis=False,
                     text=f"{wan(abc.loc[tier, 'net'])}｜{int(abc.loc[tier, 'n'])} 家", textposition="outside")
    figA.update_layout(showlegend=False, height=220, yaxis=dict(autorange="reversed"),
                       xaxis=dict(range=[0, float(abc["net"].max()) / 1e4 * 1.45], ticksuffix="萬", tickformat=",.0f"))
    ind = A.agg_industries(dw, dp)
    top = ind.head(8)[["industry", "ext_net", "customers", "booked_margin"]].copy()
    if len(ind) > 8:
        others = ind.iloc[8:]
        onet = float(others["ext_net"].sum())
        top = pd.concat([top, pd.DataFrame([{"industry": f"其他 {len(others)} 類", "ext_net": onet,
                        "customers": int(others["customers"].sum()),
                        "booked_margin": float(others["booked_profit"].sum()) / onet if onet else 0}])], ignore_index=True)
    figI = go.Figure()
    figI.add_bar(y=top["industry"], x=top["ext_net"] / 1e4, orientation="h", marker_color=COLORS["accent"], cliponaxis=False,
                 text=[f"{wan(n)}｜{int(c)} 家｜{pct(m)}" for n, c, m in zip(top["ext_net"], top["customers"], top["booked_margin"])],
                 textposition="outside")
    figI.update_layout(showlegend=False, height=max(220, 26 * len(top)), yaxis=dict(autorange="reversed"),
                       xaxis=dict(range=[0, float(top["ext_net"].max()) / 1e4 * 1.5], ticksuffix="萬", tickformat=",.0f"))
    doc.row(X.Chart("客戶分級（ABC）：多少客戶貢獻 80% 業績", figA, height=220,
                    caption="A＝累計到 80% 的大客戶、B＝80–95%、C＝最後 5%",
                    excel={"type": "bar", "df": abc.reset_index().assign(級=lambda d: d["abc_tier"]).rename(columns={"net": "除佣實收"})[["級", "除佣實收"]], "x": "級", "series": ["除佣實收"], "unit": "元"}),
            X.Chart("產業別：業績、客戶數、毛利率（前 8 + 其他）", figI, height=max(220, 26 * len(top))))

    # ---- 客戶價值矩陣（散佈）----
    xmax = float(cust["ext_net"].max()) * 1.06
    ticks = [v for v in (250_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000) if v <= xmax]
    figM = go.Figure()
    shape_map = {"既有": "circle", "新客": "diamond", "回流": "square"}
    for stt in ("既有", "新客", "回流"):
        d = cust[cust["status"].fillna("既有").map(lambda s: s if s in shape_map else "既有") == stt]
        if d.empty:
            continue
        figM.add_scatter(x=[math.sqrt(max(v, 0)) for v in d["ext_net"]], y=d["booked_margin"], mode="markers", name=stt,
                         marker=dict(size=[4 + math.sqrt(max(n, 0)) * 3 for n in d["deals"]], color=status_color(stt),
                                     symbol=shape_map[stt], opacity=0.8, line=dict(width=1, color="white")))
    top5 = cust.head(5)
    figM.add_scatter(x=[math.sqrt(max(v, 0)) for v in top5["ext_net"]], y=top5["booked_margin"], mode="text",
                     text=top5["customer"].str.slice(0, 8), textposition="top center", textfont=dict(size=10), showlegend=False)
    figM.add_hline(y=0.16, line_dash="dash", line_color="#cbd3de")
    figM.add_hline(y=0.35, line_dash="dash", line_color="#cbd3de")
    figM.update_xaxes(tickvals=[math.sqrt(v) for v in ticks], ticktext=[f"{v / 1e4:,.0f}萬" for v in ticks], title="除佣實收（平方根刻度）")
    figM.update_yaxes(title="帳上毛利率", tickformat=".0%")
    figM.update_layout(height=380, legend=dict(orientation="h", y=1.08))
    doc.chart("客戶價值矩陣：金額 × 帳上毛利率 × 頻率 × 狀態", figM, height=380,
              caption="泡泡大小＝交易筆數；虛線為毛利率 16% / 35% 參考線；標名字者為前 5 大")

    # ---- 客戶排名表（全部欄，畫面精簡欄）----
    doc.heading("客戶集中度")
    trends, _ = A.customer_trends(cust.head(50)["customer"].tolist(), yf, yt)
    tbl = cust.head(50).copy()
    tbl["mix"] = tbl.apply(lambda r: A.platform_mix_text(r["net_cp"], r["net_fresh"], r["net_radio"], r["net_other"]), axis=1)
    full = X.cols(
        ("rank_in_year", "#", "int"), ("customer", "客戶", "text"), ("industry", "產業", "text"),
        ("companies_multi", "公司(多)", "text"), ("salespeople_multi", "業務(多)", "text"), ("status", "狀態", "text"),
        X.Col("ext_net", "除佣實收", "money", help=EXT_NET), X.Col("yoy_text", "同期%", "text", help=SAME_PERIOD),
        X.Col("share", "佔比", "progress", max=float(cust["share"].max()), help=SHARE),
        X.Col("cum_share", "累計佔比", "pct", help=CUM),
        ("net_cp_family", "全家企頻", "money"), ("net_cp_carrefour", "萬家福", "money"),
        ("net_fresh", "新鮮視", "money"), ("net_radio", "廣播", "money"),
        ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"), ("net_margin", "淨利率", "pct"),
        ("deals", "筆數", "int"), ("months_since_last", "距上次交易(月)", "int"), ("avg_deal", "平均單筆", "money"),
        ("strategy_hint", "策略提示", "text"))
    slim = X.cols(
        ("rank_in_year", "#", "int"), ("customer", "客戶", "text"), ("status", "狀態", "text"),
        X.Col("ext_net", "除佣實收", "money", help=EXT_NET), ("yoy_text", "同期%", "text"),
        X.Col("share", "佔比", "progress", max=float(cust["share"].max()), help=SHARE),
        ("booked_margin", "毛利率", "pct"), ("net_margin", "淨利率", "pct"), ("deals", "筆數", "int"),
        ("strategy_hint", "策略提示", "text"))
    doc.table("客戶排名（前 50）", tbl, full, screen_columns=slim, wide=True,
              note=f"{SAME_PERIOD}；{SHARE}；{CUM}。完整名單請用 Excel 下載。")

    # ---- 流失風險 ----
    doc.page_break()
    doc.heading("流失風險")
    if len(churn):
        disp = pd.DataFrame({
            "customer": churn["customer"],
            "industry": churn["industry"].where(churn["industry"].notna(), "未分類"),
            "salesperson": churn["main_salesperson"].where(churn["main_salesperson"].notna(), ""),
            "prev_net": churn["prev_net"].round(0),
            "msl": churn["months_since_last"]})
        doc.table("⚠ 流失風險（去年同段有業績、今年期間內無業績）", disp, X.cols(
            ("customer", "客戶", "text"), ("industry", "產業", "text"), ("salesperson", "去年業務", "text"),
            X.Col("prev_net", "去年除佣實收", "money", help="去年同段月份的除佣實收"),
            ("msl", "距上次交易(月)", "int")),
            totals={"customer": f"共 {len(churn)} 家", "prev_net": float(churn["prev_net"].sum())},
            note=f"門檻：去年除佣實收 ≥ {thr // 10000} 萬。{SAME_PERIOD}。")
    else:
        doc.text("此門檻下無流失風險客戶。", "note")

    return doc
