"""
core/docs/customer_detail.py — 客戶頁的列印版（不碰 streamlit）

單一客戶的長期趨勢與訂單明細（CLAUDE_CODE_TASK_5 §5）：
KPI → 近月趨勢（除佣實收 / 帳上毛利）→ 歷年同期比較 → 平台組合 → 經手業務 → 訂單清單。
畫面上的選客戶下拉留在互動；build_doc 收 customer 參數。
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta

from core import analysis as A
from core.data import query_df
from core.format import COLORS, money, pct, ym_text
from reports import export as X

from ._base import EXT_NET, SAME_PERIOD, header


def build_doc(f: dict | None = None, user: dict | None = None, *, customer: str) -> X.Doc:
    ao = A.as_of()
    year = ao["as_of_year"]
    yf, yt = date(year, 1, 1), ao["as_of_ym"]
    pf, pt = A.prev_window(yf, yt)
    hf = {"ym_from": yf, "ym_to": yt, "scope": "analysis", "exclude_barter": True,
          "company": None, "platform_group": None, "industry": None, "salesperson": None, "customer": customer}
    doc = header(f"客戶頁 — {customer}", subtitle="單一客戶的長期趨勢與訂單明細",
                 f=hf, user=user, orientation="landscape")

    txn = query_df(
        "select distinct perf_ym from v_deal_summary where customer=%s and not is_barter and ext_net>0 order by perf_ym",
        (customer,))
    all_months = txn["perf_ym"].tolist() if not txn.empty else []
    # 「最近一次交易」只看已實際發生（≤ 截止月）的月份；未來的預登單另計，避免顯示「距今 -8 個月」
    txn_months = [m for m in all_months if m <= yt]
    future_months = [m for m in all_months if m > yt]
    last_txn = txn_months[-1] if txn_months else None
    months_since = ((ao["as_of_year"] - last_txn.year) * 12 + (ao["as_of_month"] - last_txn.month)) if last_txn else None
    avg_gap = None
    if len(txn_months) >= 2:
        span = (txn_months[-1].year - txn_months[0].year) * 12 + (txn_months[-1].month - txn_months[0].month)
        avg_gap = span / (len(txn_months) - 1)

    def _sum(a, b):
        r = query_df(
            """select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp
               from v_deal_summary where customer=%s and not is_barter and perf_ym between %s and %s""",
            (customer, a, b))
        return (float(r.iloc[0]["net"]), float(r.iloc[0]["bp"])) if not r.empty else (0.0, 0.0)

    cur_net, cur_bp = _sum(yf, yt)
    prev_net, prev_bp = _sum(pf, pt)
    allr = query_df(
        "select coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp from v_deal_summary where customer=%s and not is_barter",
        (customer,))
    all_net = float(allr.iloc[0]["net"]) if not allr.empty else 0.0
    all_bp = float(allr.iloc[0]["bp"]) if not allr.empty else 0.0

    doc.kpis([
        {"label": f"本期 {year}/01–{ym_text(yt)}", "value": money(cur_net),
         "sub": f"帳上毛利 {money(cur_bp)}（{pct(cur_bp / cur_net) if cur_net else '–'}）",
         "delta": (cur_net - prev_net) / prev_net if prev_net else "同期不可比"},
        {"label": "去年同段", "value": money(prev_net), "sub": f"帳上毛利 {money(prev_bp)}"},
        {"label": "歷年累計", "value": money(all_net),
         "sub": f"帳上毛利 {money(all_bp)}（{pct(all_bp / all_net) if all_net else '–'}）"},
        {"label": "最近一次交易", "value": (ym_text(last_txn) if last_txn else "—"),
         "sub": (f"距今 {months_since} 個月" if months_since is not None else "尚無實際交易")
                + (f"・另有 {len(future_months)} 個月預登單" if future_months else "")},
        {"label": "平均回購間隔", "value": (f"{avg_gap:.1f} 個月" if avg_gap is not None else "—"),
         "sub": f"歷年實際交易 {len(txn_months)} 個月"},
    ], per_row=5)
    doc.text(f"**同期比較**：{SAME_PERIOD}（本期＝今年 1 月到目前）。{EXT_NET}。"
             "平均回購間隔＝歷年交易月份的平均間隔月數，可看客戶回購節奏。", "note")

    # ---- 近月趨勢 ----
    if txn_months:
        start_win = min(txn_months[0], ao["as_of_ym"] - relativedelta(months=11))
        start_win = max(start_win, ao["as_of_ym"] - relativedelta(months=23))
    else:
        start_win = ao["as_of_ym"] - relativedelta(months=11)
    mrows = query_df(
        """select perf_ym, coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp
           from v_customer_month where customer=%s and perf_ym between %s and %s
           group by perf_ym order by perf_ym""", (customer, start_win, ao["as_of_ym"]))
    months = A.month_range(start_win, ao["as_of_ym"])
    mlabels = [ym_text(m) for m in months]
    net_by = {r["perf_ym"]: float(r["net"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
    bp_by = {r["perf_ym"]: float(r["bp"] or 0) for _, r in mrows.iterrows()} if not mrows.empty else {}
    doc.heading("長期趨勢")
    figN = go.Figure(go.Bar(x=mlabels, y=[net_by.get(m, 0) / 1e4 for m in months], marker_color=COLORS["accent"]))
    figN.update_layout(height=260, yaxis=dict(ticksuffix="萬", tickformat=",.0f"))
    figB = go.Figure(go.Scatter(x=mlabels, y=[bp_by.get(m, 0) / 1e4 for m in months], mode="lines+markers",
                                line=dict(color=COLORS["company"]["東吳"])))
    figB.update_layout(height=260, yaxis=dict(ticksuffix="萬", tickformat=",.0f"))
    doc.row(X.Chart(f"近 {len(months)} 個月 除佣實收（萬）", figN, height=260),
            X.Chart(f"近 {len(months)} 個月 帳上毛利（萬）", figB, height=260))

    # ---- 歷年同期比較 ----
    yrows = query_df(
        """select perf_year, ext_net, ext_net_same_period, booked_profit, booked_margin, yoy_pct, main_salesperson
           from v_customer_year where customer=%s and perf_year <= %s order by perf_year""", (customer, year))
    if not yrows.empty:
        yrows = yrows.copy()
        yrows["perf_year"] = yrows["perf_year"].astype(str)
        doc.table("歷年同期比較（今年到目前 vs 各年同一段月份）", yrows, X.cols(
            ("perf_year", "年", "text"),
            X.Col("ext_net", "全年除佣實收", "money", help="該年一整年的除佣實收"),
            X.Col("ext_net_same_period", "同段除佣實收", "money", help="該年 1 月到今年同月份的除佣實收（可跨年公平比較）"),
            X.Col("yoy_pct", "同期%", "pct", help=SAME_PERIOD),
            ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
            ("main_salesperson", "主要業務", "text")),
            note=f"「同段除佣實收」讓不同年份用相同月份區間比較（{SAME_PERIOD}）。")

    # ---- 平台組合 / 經手業務 ----
    doc.heading("結構變化")
    plat = query_df(
        """select perf_year, sum(net_cp) 企頻, sum(net_fresh) 新鮮視, sum(net_radio) 廣播, sum(net_other) 其他
           from v_deal_summary where customer=%s and not is_barter group by perf_year order by perf_year""", (customer,))
    if not plat.empty:
        figP = go.Figure()
        for pg in ("企頻", "新鮮視", "廣播", "其他"):
            figP.add_bar(x=plat["perf_year"].astype(str), y=plat[pg], name=pg,
                         marker_color=COLORS["platform_group"][pg], marker_line_width=1, marker_line_color="white")
        figP.update_layout(barmode="stack", height=280, legend=dict(orientation="h", y=1.08),
                           yaxis=dict(tickformat=",.0f"))
        ex = plat.copy()
        ex["perf_year"] = ex["perf_year"].astype(str)
        doc.chart("平台組合變化（年 × 平台歸類，除佣實收）", figP, height=280,
                  caption="看客戶逐年在企頻/新鮮視/廣播的配置變化",
                  excel={"type": "stacked", "df": ex.rename(columns={"perf_year": "年"}), "x": "年",
                         "series": ["企頻", "新鮮視", "廣播", "其他"], "unit": "元"})
    spy = query_df(
        """select perf_year, salesperson, sum(ext_net) net from v_deal_summary
           where customer=%s and not is_barter group by perf_year, salesperson order by perf_year""", (customer,))
    if not spy.empty:
        pivot = spy.pivot_table(index="perf_year", columns="salesperson", values="net", aggfunc="sum").fillna(0)
        disp = pivot.round(0).reset_index()
        disp["perf_year"] = disp["perf_year"].astype(str)
        spec = [X.Col("perf_year", "年", "text")] + [X.Col(str(c), str(c), "money") for c in pivot.columns]
        doc.table("經手業務（年 × 業務金額）", disp, spec, sheet_name="經手業務",
                  note="看客戶歷年由哪些業務經手、有無交接。金額為除佣實收。")

    # ---- 訂單清單 ----
    doc.page_break()
    doc.heading("訂單清單")
    orders = query_df(
        """select perf_ym_text, contract_no, ad_name, company, salesperson, platform_groups,
                  ext_net, booked_cost, booked_profit, booked_margin, group_margin, net_margin
           from v_deal_summary where customer=%s and not is_barter order by perf_ym desc, ext_net desc""", (customer,))
    if not orders.empty:
        doc.table("訂單清單（三層毛利率並列）", orders, X.cols(
            ("perf_ym_text", "年月", "text"), ("contract_no", "合約", "text"), ("ad_name", "廣告", "text"),
            ("company", "公司", "text"), ("salesperson", "業務", "text"), ("platform_groups", "平台歸類", "text"),
            X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
            X.Col("booked_cost", "實付", "money", help="實際付給媒體/通路的成本"),
            ("booked_profit", "帳上毛利", "money"),
            X.Col("booked_margin", "帳上利率", "pct", help="帳上毛利 ÷ 除佣實收"),
            X.Col("group_margin", "集團利率", "pct", help="轉撥加回後的集團毛利率"),
            X.Col("net_margin", "淨利率", "pct", help="再扣固定成本後的淨利率")),
            wide=True, max_rows_pdf=300, note="三層毛利率：帳上（自認）→ 集團（轉撥加回）→ 淨利（再扣固定成本）。")

    return doc
