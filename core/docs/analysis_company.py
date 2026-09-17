"""
core/docs/analysis_company.py — 公司分析頁的「印出來的樣子」（不碰 streamlit）

區塊順序（= 印出來的順序，CLAUDE_CODE_TASK_5 §5）：
  KPI 4（三家 + 集團）→ Row(月堆疊, 三層毛利橋) → 月毛利率折線
  → 目標達成 → 公司 × 報表平台（當前指標）→ 進單 + 預估

互動（口徑切換、平台總覽的「指標 / 平台範圍」）在頁面端讀好值後，用 kwargs 傳進來重組 Doc。
每個容易看不懂的欄位 / 數字都在 Col.help（滑鼠移上去看）與表下 note 說明，畫面 / PDF / Excel 三處一致。
"""
from __future__ import annotations

import plotly.graph_objects as go

from core import analysis as A
from core.data import query_df
from core.format import COLORS, company_color, money, pct, wan, ym_text
from reports import export as X
from reports.export.theme import COMPANY, PLATFORM

from ._base import GROUP_MARGIN, NET_PROFIT, SAME_PERIOD, header, open_month_note
from .glossary import annotate

_MAIN = ("聲活", "東吳", "鉑霖")
_MEDIA_FONT = dict(family="Noto Sans TC, Microsoft JhengHei")


def _company_agg(a, b) -> dict:
    df = query_df(
        """select company, sum(ext_net) en, sum(booked_profit) bp, sum(ic_out) io, sum(ic_in) ii,
                  sum(fixed_cost) fc from v_company_month
           where perf_ym between %s and %s group by company""", (a, b))
    return {r["company"]: r for _, r in df.iterrows()} if not df.empty else {}


def _group_agg(a, b):
    df = query_df(
        """select sum(ext_net) en, sum(booked_profit) bp, sum(ic_add_back) ic, sum(group_profit) gp,
                  sum(fixed_cost) fc, sum(net_profit) np from v_group_month
           where perf_ym between %s and %s""", (a, b))
    return df.iloc[0] if not df.empty else None


def _yoy(en: float, pen: float):
    """同期成長率；公司別重整（2024 業績登在瑞迪）或分母 0 時回不可比字串，避免顯示 33313% 這種假數字。"""
    if not pen or pen <= 0:
        return "同期不可比"
    r = (en - pen) / pen
    return r if abs(r) <= 2.0 else "同期不可比（公司別重整）"


def build_doc(f: dict, user: dict | None = None, *, metric: str = "除佣實收", prange: str = "全部") -> X.Doc:
    yf, yt = f["ym_from"], f["ym_to"]
    pf, pt = A.prev_window(yf, yt)
    scope = f.get("scope")

    lines = A.load_lines(yf, yt, scope=scope)
    cust_by_co = lines.groupby("company")["customer_id"].nunique() if not lines.empty else {}
    grp_cust = int(lines["customer_id"].nunique()) if not lines.empty else 0

    cur, prev = _company_agg(yf, yt), _company_agg(pf, pt)
    g, gp = _group_agg(yf, yt), _group_agg(pf, pt)
    main_cos = [c for c in _MAIN if c in cur]

    doc = header("公司分析", subtitle="三家公司加起來到底賺多少：平台結構、目標達成、三層毛利橋",
                 f=f, user=user, orientation="landscape", as_of_note=open_month_note())

    # ---- KPI：三家 + 集團（delta = 同期 = 去年同段月份）----
    items = []
    for name in main_cos:
        r = cur[name]
        en, bp = float(r["en"] or 0), float(r["bp"] or 0)
        pen = float(prev[name]["en"]) if name in prev and prev[name]["en"] is not None else 0
        io, ii, fc = float(r["io"] or 0), float(r["ii"] or 0), float(r["fc"] or 0)
        extra = f"・轉撥給聲活 {money(io)}" if io > 0 else (f"・收到轉撥 {money(ii)}" if ii > 0 else "")
        n_cust = int(cust_by_co.get(name, 0)) if hasattr(cust_by_co, "get") else 0
        items.append({"label": f"{name} 除佣實收", "color": company_color(name),
                      "value": money(en), "delta": _yoy(en, pen),
                      "sub": f"帳上毛利 {money(bp)}（{pct(bp / en) if en else '–'}）・客戶 {n_cust} 家{extra}"})
    fc_zero = False
    if g is not None:
        gen, ggp, gnp = float(g["en"] or 0), float(g["gp"] or 0), float(g["np"] or 0)
        gfc = float(g["fc"] or 0)
        fc_zero = gfc == 0
        pgen = float(gp["en"]) if gp is not None and gp["en"] is not None else 0
        net_txt = f"淨利 {money(gnp)}" + ("（＝集團毛利，固定成本未設）" if fc_zero else "")
        items.append({"label": "集團合併", "color": "#1d2733",
                      "value": money(gen), "delta": _yoy(gen, pgen),
                      "sub": f"集團毛利 {money(ggp)}（{pct(ggp / gen) if gen else '–'}）・{net_txt}・不重複客戶 {grp_cust} 家"})
    doc.kpis(items, per_row=4)
    _net_note = NET_PROFIT + ("（2025 固定成本規則尚未設定，故淨利暫等於集團毛利）" if fc_zero else "")
    doc.text(f"**同期比較**：{SAME_PERIOD}。{GROUP_MARGIN}；{_net_note}。"
             "集團合併＝三公司加總全部口徑；下方平台總覽為發稿口徑，兩者合計不同屬正常。", "note")

    scope_preset = scope.get("preset") if isinstance(scope, dict) else scope
    if scope_preset == "media":
        bridge = A.scope_bridge(yf, yt)
        if bridge:
            doc.text("**發稿口徑橋**（為什麼跟老闆數字一致）：" + "　".join(f"{lab} {money(v)}" for lab, v in bridge), "note")

    # ---- Row：各公司月業績堆疊 / 三層毛利橋 ----
    doc.heading("業績結構")
    months = A.month_range(yf, yt)
    mlabels = [ym_text(m) for m in months]
    cm = query_df(
        """select company, perf_ym, sum(ext_net) net from v_company_month
           where perf_ym between %s and %s and company = any(%s) group by company, perf_ym""",
        (yf, yt, main_cos))
    by_co = {name: {r["perf_ym"]: float(r["net"] or 0) for _, r in cm[cm["company"] == name].iterrows()}
             for name in main_cos} if not cm.empty else {name: {} for name in main_cos}
    fig1 = go.Figure()
    for name in main_cos:
        fig1.add_bar(x=mlabels, y=[by_co[name].get(m, 0) / 1e4 for m in months], name=name,
                     marker_color=company_color(name), marker_line_width=1, marker_line_color="white")
    tot = [sum(by_co[name].get(m, 0) for name in main_cos) / 1e4 for m in months]
    fig1.add_scatter(x=mlabels, y=tot, mode="text", text=[f"{v:,.0f}" for v in tot],
                     textposition="top center", textfont=dict(size=10, color="#66717f"),
                     showlegend=False, cliponaxis=False)
    fig1.update_layout(barmode="stack", height=300, legend=dict(orientation="h", y=1.12, traceorder="normal"),
                       font=_MEDIA_FONT,
                       yaxis=dict(ticksuffix="萬", tickformat=",.0f", gridcolor="#e9edf2",
                                  range=[0, (max(tot) if tot else 1) * 1.18]))
    import pandas as pd
    m_excel = pd.DataFrame({"月": mlabels, **{name: [round(by_co[name].get(m, 0) / 1e4) for m in months] for name in main_cos}})

    fig2 = None
    if g is not None:
        bp, ic, gpf = float(g["bp"] or 0), float(g["ic"] or 0), float(g["gp"] or 0)
        fc, np_ = float(g["fc"] or 0), float(g["np"] or 0)
        fig2 = go.Figure(go.Waterfall(
            orientation="v", measure=["absolute", "relative", "total", "relative", "total"],
            x=["帳上毛利", "＋轉撥加回", "集團毛利", "－固定成本", "集團淨利"], y=[bp, ic, gpf, -fc, np_],
            text=[money(bp), f"+{money(ic)}", money(gpf), f"−{money(fc)}", money(np_)],
            textposition="outside", connector=dict(line=dict(color="#cbd3de")),
            increasing=dict(marker_color=COLORS["alert"]["green"]),
            decreasing=dict(marker_color=COLORS["alert"]["red"]), totals=dict(marker_color=COLORS["accent"])))
        fig2.update_layout(height=300, font=_MEDIA_FONT, margin=dict(t=28),
                           yaxis=dict(range=[0, max(bp, gpf) * 1.25]))
    ch1 = X.Chart("各公司月業績（除佣實收，萬）", fig1, height=300, caption="柱頂數字為三公司當月合計",
                  excel={"type": "stacked", "df": m_excel, "x": "月", "series": list(main_cos), "unit": "萬"})
    if fig2 is not None:
        doc.row(ch1, X.Chart("三層毛利橋：帳上 → 集團 → 淨利", fig2, height=300,
                             caption="轉撥加回＝母子公司互開的內部交易還原；固定成本＝人事租金等"))
    else:
        doc.add(ch1)

    # ---- 月毛利率折線 ----
    gmm = query_df(
        """select perf_ym, booked_margin, group_margin from v_group_month
           where perf_ym between %s and %s order by perf_ym""", (yf, yt))
    if not gmm.empty:
        mb = {r["perf_ym"]: (float(r["booked_margin"]) if r["booked_margin"] is not None else None) for _, r in gmm.iterrows()}
        mg = {r["perf_ym"]: (float(r["group_margin"]) if r["group_margin"] is not None else None) for _, r in gmm.iterrows()}
        figm = go.Figure()
        figm.add_scatter(x=mlabels, y=[mb.get(m) for m in months], mode="lines+markers",
                         name="帳上毛利率", line=dict(color=COLORS["accent"]))
        figm.add_scatter(x=mlabels, y=[mg.get(m) for m in months], mode="lines+markers",
                         name="集團毛利率", line=dict(color=COLORS["company"]["東吳"]))
        figm.update_layout(height=260, font=_MEDIA_FONT, legend=dict(orientation="h", y=1.12),
                           yaxis=dict(tickformat=".0%"))
        cap = "帳上毛利率＝各公司自認毛利率；集團毛利率＝轉撥加回後合併毛利率"
        if f.get("includes_open"):
            cap += "。末月偏低多因當月尚未登打完整，非真的下滑"
        doc.chart("月毛利率趨勢（帳上 / 集團）", figm, height=260, caption=cap)

    # ---- 目標達成 ----
    tgt = query_df(
        """select company, period_label, target_amount, actual, remaining, achieved_pct,
                  months_left, required_monthly, forecast_amount, achieved_pct_with_forecast,
                  period_type, period_no, year
           from v_target_progress order by company, year, period_no""")
    if not tgt.empty:
        import pandas as pd
        grp_rows = []
        for (ptp, pno, yr, plabel), sub in tgt.groupby(["period_type", "period_no", "year", "period_label"]):
            ta, ac = float(sub["target_amount"].sum()), float(sub["actual"].sum())
            grp_rows.append({"company": "集團合計", "period_label": plabel, "target_amount": ta,
                             "actual": ac, "remaining": ta - ac, "achieved_pct": ac / ta if ta else None,
                             "months_left": sub["months_left"].max(),
                             "required_monthly": float(sub["required_monthly"].fillna(0).astype(float).sum()) or None})
        tshow = pd.concat([tgt, pd.DataFrame(grp_rows)], ignore_index=True)
        doc.heading("目標達成")
        doc.table("目標達成", tshow, X.cols(
            ("company", "公司", "text"), ("period_label", "期間", "text"),
            X.Col("target_amount", "目標", "money", help="主檔維護設定的業績目標"),
            X.Col("actual", "進單", "money", help="期間內已成立的除佣實收（不含預估）"),
            X.Col("remaining", "待追", "money", help="目標 − 進單，還差多少"),
            X.Col("achieved_pct", "達成率", "progress", max=1.0, help="進單 ÷ 目標"),
            X.Col("months_left", "剩餘月份", "int", help="到期間結束還剩幾個月"),
            X.Col("required_monthly", "每月需達", "money", help="待追 ÷ 剩餘月份，平均每月要進多少才達標")),
            note="口徑：企頻＋新鮮視、不含公司戶、不含交換；目標由主檔維護設定。")

    # ---- 公司 × 報表平台（當前指標）----
    if not lines.empty:
        doc.heading("平台總覽")
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
        net_by = lt.pivot_table(index="company", columns="report_platform", values="net_amount", aggfunc="sum", fill_value=0.0)
        num_by = lt.pivot_table(index="company", columns="report_platform", values=numer, aggfunc="sum", fill_value=0.0)
        cust_by = lt.groupby("company")["customer_id"].nunique()
        order = [c for c in ("聲活", "東吳", "鉑霖", "瑞迪") if c in num_by.index]
        grand_net = float(lt["net_amount"].sum())
        rows = []
        for name in order + ["三公司合計"]:
            if name == "三公司合計":
                n_net, n_num = net_by.reindex(order).sum(), num_by.reindex(order).sum()
                row_net, cust = grand_net, int(lt["customer_id"].nunique())
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
            row["客戶數"], row["佔比"] = cust, (row_net / grand_net) if grand_net else 0.0
            rows.append(row)
        odf = pd.DataFrame(rows)
        kind = "pct" if is_ratio else "money"
        spec = [X.Col("company", "公司", "text")]
        spec += [X.Col(p, p, kind, help="報表平台：老闆版四欄（全家企頻/萬家福/新鮮視/廣播）＋健康視") for p in plats]
        spec += [X.Col("合計", f"合計（{metric}）", kind),
                 X.Col("客戶數", "客戶數", "int", help="該公司不重複客戶數"),
                 X.Col("佔比", "佔比", "progress", max=1.0, help="該公司除佣實收 ÷ 三公司合計")]
        doc.table("公司 × 報表平台", odf, spec,
                  col_groups=[("", 1), (f"報表平台（{metric}）", len(plats)), ("", 3)],
                  note=f"當前指標：{metric}｜平台範圍：{prange}；利率＝Σ毛利 ÷ Σ除佣（非各月平均）。"
                       "營運／其它平台在發稿口徑下不列入。")

    # ---- 進單 + 預估（公司 × 月，萬）----
    bvf = query_df(
        """select company, perf_ym, booked_net, forecast_amount from v_booked_vs_forecast
           where perf_ym between %s and %s order by perf_ym""", (yf, yt))
    if not bvf.empty and bvf[["booked_net", "forecast_amount"]].astype(float).abs().to_numpy().sum() > 0:
        import pandas as pd
        has_fc = float(bvf["forecast_amount"].fillna(0).astype(float).sum()) > 0
        keep = (bvf.assign(v=bvf["booked_net"].astype(float).abs() + bvf["forecast_amount"].astype(float).abs())
                .groupby("company")["v"].sum())
        _order = {"聲活": 0, "東吳": 1, "鉑霖": 2}
        companies = sorted([c for c in keep[keep > 0].index], key=lambda c: _order.get(c, 9))
        rows = []
        for co in companies:
            sub = bvf[bvf["company"] == co]
            bk = {ym_text(r["perf_ym"]): float(r["booked_net"] or 0) for _, r in sub.iterrows()}
            fc = {ym_text(r["perf_ym"]): float(r["forecast_amount"] or 0) for _, r in sub.iterrows()}
            rows.append({"公司": co, "類型": "進單", **{mc: bk.get(mc, 0) / 1e4 for mc in mlabels}, "合計": sum(bk.values()) / 1e4})
            if has_fc:
                rows.append({"公司": co, "類型": "預估", **{mc: fc.get(mc, 0) / 1e4 for mc in mlabels}, "合計": sum(fc.values()) / 1e4})
                rows.append({"公司": co, "類型": "合計", **{mc: (bk.get(mc, 0) + fc.get(mc, 0)) / 1e4 for mc in mlabels},
                             "合計": (sum(bk.values()) + sum(fc.values())) / 1e4})
        tbl = pd.DataFrame(rows)
        doc.heading("進單 + 預估")
        spec = [X.Col("公司", "公司", "text"), X.Col("類型", "類型", "text",
                help="進單＝已成立；預估＝主檔輸入的預估；合計＝兩者相加")]
        spec += [X.Col(mc, mc, "int") for mc in mlabels] + [X.Col("合計", "合計", "int")]
        doc.table("進單 + 預估（單位：萬）", tbl, spec, sheet_name="進單預估",
                  wide=True, freeze_cols=2, max_cols_pdf=16,
                  note="單位：萬元（非元）。進單＝期間內已成立的除佣實收；預估需在主檔維護 → 預估 輸入後才出現。")

    return annotate(doc)
