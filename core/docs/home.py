"""
core/docs/home.py — 首頁「老闆一頁」的列印版（不碰 streamlit）

月報包（scripts/export_pack.py）的第一頁：本月一頁看完（CLAUDE_CODE_TASK_5 §5）：
KPI 4（本月除佣 / 同期 / 集團毛利率 / 當季目標達成）→ 各公司本月 vs 目標 →
近 12 月堆疊 → 待處理提醒（低毛利 / 逾期 / 流失風險）。

「本月」＝ f['ym_to']（月報包指定的截止月）。同期＝去年同一個月。
"""
from __future__ import annotations

import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta

from core import analysis as A
from core.data import query_df
from core.format import COLORS, company_color, money, pct, ym_text
from reports import export as X

from ._base import header, open_month_note
from .glossary import annotate

_MAIN = ("聲活", "東吳", "鉑霖")


def _month_row(view: str, col_sql: str, ym) -> dict:
    df = query_df(f"select {col_sql} from {view} where perf_ym = %s", (ym,))
    return df.iloc[0].to_dict() if not df.empty else {}


def build_doc(f: dict, user: dict | None = None) -> X.Doc:
    ref = f.get("ym_to") or A.as_of()["as_of_ym"]
    prevm = ref - relativedelta(months=1)
    prevy = ref - relativedelta(months=12)
    q = (ref.month - 1) // 3 + 1
    doc = header("首頁 — 老闆一頁", subtitle=f"{ym_text(ref)} 本月一頁看完：業績、目標、待處理",
                 f={**f, "ym_from": ref}, user=user, orientation="portrait", as_of_note=open_month_note())
    doc.period_text = ym_text(ref)

    g = _month_row("v_group_month", "coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp,"
                   "coalesce(sum(group_profit),0) gp, coalesce(sum(net_profit),0) np,"
                   "max(group_margin) gm", ref)
    g_pm = _month_row("v_group_month", "coalesce(sum(ext_net),0) net", prevm)
    g_py = _month_row("v_group_month", "coalesce(sum(ext_net),0) net", prevy)
    net = float(g.get("net") or 0)
    pm = float(g_pm.get("net") or 0)
    py = float(g_py.get("net") or 0)

    # 當季目標（集團合計）
    tq = query_df(
        """select coalesce(sum(target_amount),0) tgt, coalesce(sum(actual),0) act
           from v_target_progress where period_type='Q' and year=%s and period_no=%s""", (ref.year, q))
    tgt = float(tq.iloc[0]["tgt"]) if not tq.empty else 0.0
    act = float(tq.iloc[0]["act"]) if not tq.empty else 0.0

    doc.kpis([
        {"label": "本月除佣實收（集團）", "value": money(net), "color": "#1d2733",
         "delta": (net - pm) / pm if pm else "上月不可比", "sub": f"上月 {money(pm)}"},
        {"label": "同期（去年同月）", "value": money(py),
         "sub": f"年增 {pct((net - py) / py) if py else '–'}"},
        {"label": "集團毛利率", "value": pct(g.get("gm")), "sub": f"集團毛利 {money(g.get('gp'))}・淨利 {money(g.get('np'))}"},
        {"label": f"當季目標達成（Q{q}）", "value": pct(act / tgt) if tgt else "未設目標",
         "sub": f"進單 {money(act)} / 目標 {money(tgt)}"},
    ], per_row=4)
    doc.text("**同期＝去年的同一個月**（例：本月 2026/08，同期為 2025/08）。集團＝三公司合併全部口徑。", "note")

    # ---- 各公司本月 vs 當季目標 ----
    import pandas as pd
    comp = query_df(
        """select company, coalesce(sum(ext_net),0) net, coalesce(sum(booked_profit),0) bp,
                  case when sum(ext_net)<>0 then sum(booked_profit)/sum(ext_net) end margin
           from v_company_month where perf_ym=%s group by company""", (ref,))
    tgt_by = query_df(
        """select company, coalesce(sum(target_amount),0) tgt, coalesce(sum(actual),0) act,
                  max(achieved_pct) ap, max(required_monthly) rm, max(months_left) ml
           from v_target_progress where period_type='Q' and year=%s and period_no=%s group by company""",
        (ref.year, q))
    tmap = {r["company"]: r for _, r in tgt_by.iterrows()} if not tgt_by.empty else {}
    rows = []
    for co in [c for c in _MAIN if c in set(comp["company"])] if not comp.empty else []:
        cr = comp[comp["company"] == co].iloc[0]
        tr = tmap.get(co, {})
        rows.append({"company": co, "net": float(cr["net"] or 0), "bp": float(cr["bp"] or 0),
                     "margin": float(cr["margin"]) if cr["margin"] is not None else None,
                     "tgt": float(tr.get("tgt") or 0) if tr is not None else 0,
                     "ap": float(tr["ap"]) if tr is not None and tr.get("ap") is not None else None,
                     "rm": float(tr.get("rm") or 0) if tr is not None else 0})
    if rows:
        doc.heading("各公司本月 vs 當季目標")
        doc.table(f"各公司本月（{ym_text(ref)}）與當季目標", pd.DataFrame(rows), X.cols(
            ("company", "公司", "text"),
            X.Col("net", "本月除佣實收", "money", help="該公司本月對外實收（除佣、非牌價）"),
            ("bp", "本月帳上毛利", "money"), ("margin", "毛利率", "pct"),
            X.Col("tgt", "當季目標", "money", help=f"{ref.year} Q{q} 目標"),
            X.Col("ap", "當季達成率", "progress", max=1.0, help="當季進單 ÷ 當季目標"),
            X.Col("rm", "每月需達", "money", help="達標還需的每月平均進單")),
            note="目標為當季（Q）口徑；達成率＝當季累計進單 ÷ 當季目標。")

    # ---- 近 12 月堆疊 ----
    doc.heading("近 12 個月業績趨勢")
    start = ref - relativedelta(months=11)
    months = A.month_range(start, ref)
    mlabels = [ym_text(m) for m in months]
    cm = query_df(
        """select company, perf_ym, coalesce(sum(ext_net),0) net from v_company_month
           where perf_ym between %s and %s and company = any(%s) group by company, perf_ym""",
        (start, ref, list(_MAIN)))
    by_co = {co: {r["perf_ym"]: float(r["net"] or 0) for _, r in cm[cm["company"] == co].iterrows()}
             for co in _MAIN} if not cm.empty else {co: {} for co in _MAIN}
    fig = go.Figure()
    for co in _MAIN:
        fig.add_bar(x=mlabels, y=[by_co[co].get(m, 0) / 1e4 for m in months], name=co,
                    marker_color=company_color(co), marker_line_width=1, marker_line_color="white")
    tot = [sum(by_co[co].get(m, 0) for co in _MAIN) / 1e4 for m in months]
    fig.add_scatter(x=mlabels, y=tot, mode="text", text=[f"{v:,.0f}" for v in tot],
                    textposition="top center", textfont=dict(size=9, color="#66717f"), showlegend=False, cliponaxis=False)
    fig.update_layout(barmode="stack", height=300, legend=dict(orientation="h", y=1.12, traceorder="normal"),
                      font=dict(family="Noto Sans TC, Microsoft JhengHei"),
                      yaxis=dict(ticksuffix="萬", tickformat=",.0f", range=[0, (max(tot) if tot else 1) * 1.18]))
    m_excel = pd.DataFrame({"月": mlabels, **{co: [round(by_co[co].get(m, 0) / 1e4) for m in months] for co in _MAIN}})
    doc.chart("各公司月業績（除佣實收，萬）", fig, height=300, caption="柱頂為三公司當月合計",
              excel={"type": "stacked", "df": m_excel, "x": "月", "series": list(_MAIN), "unit": "萬"})

    # ---- 待處理提醒 ----
    doc.heading("待處理提醒")
    lm = query_df(
        """select count(*) n, coalesce(sum(net_amount),0) amt from v_report_line
           where perf_ym=%s and not is_intercompany and not is_barter and net_amount>=100000
             and coalesce(cost_amount,0) > net_amount*0.84 and report_platform<>'營運'""", (ref,))
    lm_n = int(lm.iloc[0]["n"]) if not lm.empty else 0
    lm_amt = float(lm.iloc[0]["amt"]) if not lm.empty else 0.0
    # 逾期未收：舊帳的銷帳幾乎沒登錄（v_ar_open 有 2021 年起、甚至髒日期），故只是「帳列未收」，
    # 不是真實逾期；濾掉離譜日期，並在說明明講「僅供參考、含未登銷帳」。
    ar = query_df(
        """select coalesce(sum(outstanding_amount),0) amt, count(*) n from v_ar_open
           where coalesce(overdue_days,0) > 0
             and (invoice_issued_on is null or invoice_issued_on <= current_date)""")
    ar_amt = float(ar.iloc[0]["amt"]) if not ar.empty else 0.0
    ar_n = int(ar.iloc[0]["n"]) if not ar.empty else 0
    ch = query_df("select count(*) n from v_customer_year where perf_year=%s and status='流失'", (ref.year,))
    ch_n = int(ch.iloc[0]["n"]) if not ch.empty else 0
    doc.kpis([
        {"label": "本月低毛利訂單", "value": f"{lm_n} 筆", "color": COLORS["alert"]["yellow"],
         "sub": f"金額 {money(lm_amt)}・毛利率<16%（≥10 萬、不含營運）"},
        {"label": "帳列未收（未銷帳）", "value": money(ar_amt), "color": COLORS["alert"]["yellow"],
         "sub": f"{ar_n} 張・含多年舊帳、銷帳多未登錄，僅供參考"},
        {"label": f"本年流失客戶（{ref.year}）", "value": f"{ch_n} 家", "color": COLORS["alert"]["red"],
         "sub": "當年有交易但已轉為流失狀態"},
    ], per_row=3)
    doc.text("低毛利＝帳上毛利率<16% 的大單（可能報價偏低）；**帳列未收**＝發票未收金額合計，"
             "但舊資料的銷帳（收款）多半沒登錄，故此數字偏高、僅供參考，需以實際收款為準；"
             "流失＝該年度狀態為「流失」的客戶。", "note")
    return annotate(doc)
