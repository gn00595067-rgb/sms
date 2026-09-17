"""
core/docs/analysis_sales.py — 銷售分析頁的列印版（不碰 streamlit）

分佈比平均重要（CLAUDE_CODE_TASK_5 §5）：KPI 6 → Row(金額分佈, 毛利率分佈) →
產業 × 平台歸類熱圖 → 訂單排名 → 低毛利清單（唯讀，含原因欄）。
畫面上的排序切換、點列改單、低毛利原因回填留在互動。
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core import analysis as A
from core.format import COLORS, money, pct, wan
from reports import export as X

from ._base import EXT_NET, SAME_PERIOD, header, open_month_note
from .glossary import annotate

_LOW_MARGIN = "低毛利＝帳上毛利率 < 16%（可能報價偏低或成本偏高，需檢視）"


def build_doc(f: dict, user: dict | None = None, *, sort_opt: str = "除佣實收") -> X.Doc:
    yf, yt = f["ym_from"], f["ym_to"]
    pf, pt = A.prev_window(yf, yt)
    doc = header("銷售分析", subtitle="分佈比平均重要：錢集中在哪個級距、有多少業績在低毛利下做的",
                 f=f, user=user, orientation="landscape", as_of_note=open_month_note())

    d_all = A.load_deals(yf, yt, f, exclude_barter=f["exclude_barter"], user=user)
    if d_all.empty:
        doc.text("此條件查無資料。", "callout")
        return annotate(doc)
    d = d_all[d_all["ext_net"] > 0].copy()
    zero = d_all[d_all["ext_net"] <= 0].copy()
    dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
    deals_p = int((dp["ext_net"] > 0).sum()) if not dp.empty else 0
    net_sum = float(d["ext_net"].sum())

    doc.kpis([
        {"label": "有收入的訂單", "value": f"{len(d)}", "sub": f"同期 {deals_p} 筆"},
        {"label": "平均單筆", "value": money(d["ext_net"].mean()), "sub": f"中位數 {money(d['ext_net'].median())}"},
        {"label": "大單（≥100 萬）", "value": f"{int((d['ext_net'] >= 1_000_000).sum())} 筆",
         "sub": f"佔業績 {pct(float(d[d['ext_net'] >= 1_000_000]['ext_net'].sum()) / net_sum) if net_sum else '–'}"},
        {"label": "低毛利（<16%）", "value": f"{int(d['is_low_margin'].sum())} 筆",
         "sub": f"佔業績 {pct(float(d[d['is_low_margin']]['ext_net'].sum()) / net_sum) if net_sum else '–'}"},
        {"label": "零收入成本單", "value": f"{len(zero)} 筆", "sub": f"成本 {money(float(zero['booked_cost'].sum()))}"},
        {"label": "帳上毛利率（含成本單）",
         "value": pct(float(d_all['booked_profit'].sum()) / float(d_all['ext_net'].sum())) if float(d_all['ext_net'].sum()) else "–",
         "sub": f"只看有收入 {pct(float(d['booked_profit'].sum()) / net_sum) if net_sum else '–'}"},
    ], per_row=6)
    doc.text(f"**同期比較**：{SAME_PERIOD}。{_LOW_MARGIN}；「零收入成本單」＝只有成本、沒有對外收入的內部單（如製作、營運）。", "note")

    # ---- Row：金額分佈 / 毛利率分佈 ----
    doc.heading("分佈")
    sb = A.size_buckets(d)
    figA = go.Figure(go.Bar(y=[s[3:] for s in sb["size_bucket"]], x=sb["net"] / 1e4, orientation="h",
                            marker_color=COLORS["accent"], cliponaxis=False,
                            text=[f"{wan(n)}｜{int(c)} 筆｜{pct(m)}" for n, c, m in zip(sb["net"], sb["n"], sb["booked_margin"])],
                            textposition="outside"))
    figA.update_layout(showlegend=False, height=260, yaxis=dict(autorange="reversed"),
                       xaxis=dict(range=[0, float(sb["net"].max()) / 1e4 * 1.5], ticksuffix="萬", tickformat=",.0f"))
    mb = A.margin_bands(d)

    def _c(b):
        return COLORS["alert"]["red"] if b.startswith("<0") else (COLORS["alert"]["yellow"] if b.startswith("0–16") else COLORS["accent"])
    figB = go.Figure(go.Bar(y=[s[3:] for s in mb["band"]], x=mb["net"] / 1e4, orientation="h",
                            marker_color=[_c(s[3:]) for s in mb["band"]], cliponaxis=False,
                            text=[f"{wan(n)}｜{int(c)} 筆" for n, c in zip(mb["net"], mb["n"])], textposition="outside"))
    figB.update_layout(showlegend=False, height=260, yaxis=dict(autorange="reversed"),
                       xaxis=dict(range=[0, float(mb["net"].max()) / 1e4 * 1.5], ticksuffix="萬", tickformat=",.0f"))
    sb_ex = sb.assign(級距=lambda x: [s[3:] for s in x["size_bucket"]], 萬=lambda x: (x["net"] / 1e4).round(0))
    doc.row(X.Chart("訂單金額分佈（單位：萬）", figA, height=260, caption="每個金額級距的業績、筆數、毛利率",
                    excel={"type": "bar", "df": sb_ex[["級距", "萬"]], "x": "級距", "series": ["萬"], "unit": "萬"}),
            X.Chart("毛利率分佈（單位：萬）", figB, height=260, caption="紅＝虧損、黃＝低毛利(0–16%)、藍＝健康"))

    # ---- 產業 × 平台歸類熱圖 ----
    dd = d.copy()
    dd["ind"] = dd["industry"].fillna("(未分類)")
    dd["pg"] = dd["main_platform_group"].map(lambda p: p if p in ("企頻", "新鮮視", "廣播") else "其他")
    top9 = dd.groupby("ind")["ext_net"].sum().sort_values(ascending=False).head(9).index.tolist()
    if top9:
        pv = dd[dd["ind"].isin(top9)].pivot_table(index="ind", columns="pg", values="ext_net", aggfunc="sum")
        pv = (pv.reindex(index=top9, columns=["企頻", "新鮮視", "廣播", "其他"]).fillna(0) / 1e4)
        pv["合計"] = pv.sum(axis=1)
        zmax = float(pv[["企頻", "新鮮視", "廣播", "其他"]].values.max()) or 1.0
        fig3 = px.imshow(pv.values, x=list(pv.columns), y=top9, color_continuous_scale="Blues", aspect="auto",
                         text_auto=",.0f", zmax=zmax, labels=dict(color="萬"))
        fig3.update_traces(textfont_size=11)
        fig3.update_layout(height=max(280, 38 * len(top9)), coloraxis_showscale=False)
        ex = pv.reset_index().rename(columns={"ind": "產業"})
        doc.chart("產業 × 平台歸類（除佣實收，前 9 產業，數字為萬）", fig3, height=max(280, 38 * len(top9)),
                  caption="顏色深＝金額大；末欄為該產業合計",
                  excel={"type": "matrix", "df": ex[["產業", "企頻", "新鮮視", "廣播", "其他"]],
                         "x": "產業", "series": ["企頻", "新鮮視", "廣播", "其他"], "unit": "萬"})

    # ---- 訂單排名 ----
    doc.heading("訂單排名")
    sort_col = {"除佣實收": "ext_net", "帳上毛利": "booked_profit", "毛利率": "booked_margin", "集團淨利率": "net_margin"}.get(sort_opt, "ext_net")
    top = d.sort_values(sort_col, ascending=False).head(300)
    doc.table(f"訂單排名（前 300，依{sort_opt}）", top, X.cols(
        ("contract_no", "合約", "text"), ("ad_name", "廣告", "text"), ("customer", "客戶", "text"),
        ("industry", "產業", "text"), ("salesperson", "業務", "text"), ("company", "公司", "text"),
        ("platform_groups", "平台歸類", "text"), ("perf_ym_text", "年月", "text"),
        X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
        X.Col("booked_cost", "實付", "money", help="實際付給媒體/通路的成本"),
        ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
        X.Col("net_margin", "集團淨利率", "pct", help="轉撥加回、扣固定成本後的淨利率"),
        ("production_cost", "製作費", "money")),
        wide=True, note="完整訂單清單請用 Excel 下載（可超過 300 筆）。")

    # ---- 低毛利清單 ----
    doc.heading("待處理低毛利訂單")
    low = d[(d["ext_net"] >= 100000) & (d["main_platform_group"] != "營運")].sort_values("booked_margin").head(20).copy()
    if not low.empty:
        reasons = A.query_reasons(low["deal_id"].tolist()) if hasattr(A, "query_reasons") else {}
        disp = pd.DataFrame({
            "contract_no": low["contract_no"], "ad_name": low["ad_name"], "customer": low["customer"],
            "salesperson": low["salesperson"], "ext_net": low["ext_net"].round(0),
            "booked_margin": low["booked_margin"], "reason": [reasons.get(x, "") for x in low["deal_id"]]})
        doc.table("⚠ 待處理低毛利訂單（≥10 萬、毛利率最低 20 筆）", disp, X.cols(
            ("contract_no", "合約", "text"), ("ad_name", "廣告", "text"), ("customer", "客戶", "text"),
            ("salesperson", "業務", "text"), X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
            X.Col("booked_margin", "毛利率", "pct", help=_LOW_MARGIN),
            X.Col("reason", "低毛利原因", "text", help="業務/主管在畫面上回填的說明")),
            note=f"{_LOW_MARGIN}。已排除營運（固定成本）單。原因欄請在畫面上回填後儲存。")
    else:
        doc.text("此條件下無低毛利訂單。", "note")

    return annotate(doc)
