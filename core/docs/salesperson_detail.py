"""
core/docs/salesperson_detail.py — 業務頁的列印版（不碰 streamlit）

單一業務的趨勢、客戶組合、目標與預估（CLAUDE_CODE_TASK_5 §5）：
KPI → 月趨勢 → 客戶組合（前 10）→ 新客 / 流失 → 目標達成 → 預估 pipeline。
畫面上的選業務下拉留在互動；build_doc 收 salesperson 參數。
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from core import analysis as A
from core.data import query_df
from core.format import COLORS, money, pct, ym_text
from reports import export as X

from ._base import EXT_NET, SAME_PERIOD, SHARE, header


def build_doc(f: dict | None = None, user: dict | None = None, *, salesperson: str) -> X.Doc:
    ao = A.as_of()
    year = ao["as_of_year"]
    yf, yt = date(year, 1, 1), ao["as_of_ym"]
    pf, pt = A.prev_window(yf, yt)
    sp = salesperson
    hf = {"ym_from": yf, "ym_to": yt, "scope": "analysis", "exclude_barter": True,
          "company": None, "platform_group": None, "industry": None, "salesperson": sp, "customer": None}
    doc = header(f"業務頁 — {sp}", subtitle="單一業務的趨勢、客戶組合、目標與預估",
                 f=hf, user=user, orientation="landscape")

    cur = query_df(
        """select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp,
                  count(distinct customer) cust, count(*) deals
           from v_deal_summary where salesperson=%s and not is_barter and perf_ym between %s and %s""",
        (sp, yf, yt)).iloc[0]
    prev = query_df(
        "select coalesce(sum(ext_net),0) net from v_deal_summary where salesperson=%s and not is_barter and perf_ym between %s and %s",
        (sp, pf, pt)).iloc[0]
    cur_net, prev_net = float(cur["net"]), float(prev["net"])

    doc.kpis([
        {"label": f"本期 {year}/01–{ym_text(yt)}", "value": money(cur_net),
         "delta": (cur_net - prev_net) / prev_net if prev_net else "同期不可比",
         "sub": f"帳上毛利 {money(float(cur['bp']))}（{pct(float(cur['bp']) / cur_net) if cur_net else '–'}）"},
        {"label": "去年同段", "value": money(prev_net)},
        {"label": "差異", "value": money(cur_net - prev_net), "sub": f"{pct((cur_net - prev_net) / prev_net) if prev_net else '新'}"},
        {"label": "客戶數", "value": f"{int(cur['cust'])}"},
        {"label": "訂單數", "value": f"{int(cur['deals'])}",
         "sub": f"平均單筆 {money(cur_net / int(cur['deals'])) if int(cur['deals']) else '–'}"},
    ], per_row=5)
    doc.text(f"**同期比較**：{SAME_PERIOD}（本期＝今年 1 月到目前）。{EXT_NET}。", "note")

    # ---- 月趨勢 ----
    doc.heading("月趨勢")
    mrows = query_df(
        """select perf_ym, coalesce(sum(ext_net),0) net from v_salesperson_month
           where salesperson=%s and perf_ym between %s and %s group by perf_ym order by perf_ym""", (sp, yf, yt))
    months = A.month_range(yf, yt)
    net_by = {r["perf_ym"]: float(r["net"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
    fig = go.Figure(go.Bar(x=[ym_text(m) for m in months], y=[net_by.get(m, 0) / 1e4 for m in months], marker_color=COLORS["accent"]))
    fig.update_layout(height=260, yaxis=dict(ticksuffix="萬", tickformat=",.0f"))
    doc.chart("月趨勢（期間內除佣實收，萬）", fig, height=260, caption="看該業務逐月進單節奏")

    # ---- 客戶組合（前 10）----
    doc.heading("客戶組合")
    cur_c = query_df(
        """select customer, sum(ext_net) net from v_deal_summary
           where salesperson=%s and not is_barter and perf_ym between %s and %s group by customer""", (sp, yf, yt))
    prev_c = query_df(
        """select customer, sum(ext_net) net from v_deal_summary
           where salesperson=%s and not is_barter and perf_ym between %s and %s group by customer""", (sp, pf, pt))
    if not cur_c.empty:
        cur_c = cur_c.copy()
        cur_c["net"] = cur_c["net"].astype(float)
        prevmap = {r["customer"]: float(r["net"]) for _, r in prev_c.iterrows()} if not prev_c.empty else {}
        cur_c = cur_c.sort_values("net", ascending=False).head(10)
        total = float(cur_c["net"].sum()) or 1
        cur_c["yoy"] = cur_c.apply(lambda r: (r["net"] - prevmap.get(r["customer"], 0)) / prevmap[r["customer"]] if prevmap.get(r["customer"]) else None, axis=1)
        cur_c["share"] = cur_c["net"] / total
        doc.table("客戶組合（前 10 大）", cur_c, X.cols(
            ("customer", "客戶", "text"), X.Col("net", "除佣實收", "money", help=EXT_NET),
            X.Col("yoy", "同期%", "pct", help=SAME_PERIOD),
            X.Col("share", "佔該業務%", "progress", max=float(cur_c["share"].max()), help="該客戶佔此業務前 10 大合計比重")),
            note=f"{SAME_PERIOD}；佔比分母＝該業務前 10 大合計。")

    # ---- 新客 / 流失 ----
    cy = A.customer_year(year)
    if not cy.empty and "main_salesperson" in cy.columns:
        newc = cy[(cy["status"] == "新客") & (cy["main_salesperson"] == sp)]
        if not newc.empty:
            doc.table("新客（今年第一次有業績、由本業務帶進）", newc.reset_index()[["customer", "ext_net", "booked_margin"]],
                      X.cols(("customer", "客戶", "text"), X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
                             ("booked_margin", "毛利率", "pct")),
                      sheet_name="新客", note="新客＝今年才第一次有業績的客戶。")
        lost = cy[(cy["status"] == "流失風險") & (cy["main_salesperson"] == sp)]
        if not lost.empty:
            doc.table("流失風險（去年有、今年到目前無）", lost.reset_index()[["customer", "months_since_last"]],
                      X.cols(("customer", "客戶", "text"), X.Col("months_since_last", "距上次交易(月)", "int", help="離最近一次交易幾個月")),
                      sheet_name="流失風險", note="流失風險＝去年有業績、今年到目前尚無業績的客戶。")

    # ---- 目標達成 ----
    doc.heading("目標與預估")
    tgt = query_df(
        """select period_label, target_amount, actual, remaining, achieved_pct, months_left, required_monthly
           from v_target_progress where salesperson=%s order by year, period_no""", (sp,))
    if not tgt.empty:
        doc.table("目標達成", tgt, X.cols(
            ("period_label", "期間", "text"), ("target_amount", "目標", "money"),
            X.Col("actual", "進單", "money", help="期間內已成立的除佣實收"),
            X.Col("remaining", "待追", "money", help="目標 − 進單"),
            X.Col("achieved_pct", "達成率", "progress", max=1.0, help="進單 ÷ 目標"),
            ("months_left", "剩餘月份", "int"),
            X.Col("required_monthly", "每月需達", "money", help="待追 ÷ 剩餘月份")),
            note="目標由主檔維護設定。")

    # ---- 預估 pipeline ----
    fc = query_df(
        """select f.perf_ym, c.name company, cu.name customer, f.customer_text, f.ad_name,
                  f.platform_group, f.amount, f.probability
           from forecast f
           left join company c on c.id=f.company_id
           left join customer cu on cu.id=f.customer_id
           left join salesperson s on s.id=f.salesperson_id
           where s.name=%s and f.status='OPEN' order by f.perf_ym""", (sp,))
    if not fc.empty:
        fc = fc.copy()
        fc["cust"] = fc.apply(lambda r: r["customer"] or r["customer_text"] or "", axis=1)
        fc["prob_ratio"] = fc["probability"].astype(float) / 100.0
        doc.table("預估（OPEN pipeline）", fc, X.cols(
            ("perf_ym", "業績年月", "text"), ("company", "公司", "text"), ("cust", "客戶", "text"),
            ("ad_name", "廣告", "text"), ("platform_group", "平台歸類", "text"),
            X.Col("amount", "預估", "money", help="尚未成立、預估中的金額"),
            X.Col("prob_ratio", "機率%", "pct", help="成交機率（業務自評）")),
            sheet_name="預估pipeline", note="預估＝OPEN 狀態、尚未成立的 pipeline；成交機率為業務自評。")

    return doc
