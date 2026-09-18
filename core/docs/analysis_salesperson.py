"""
core/docs/analysis_salesperson.py — 業務分析頁的列印版（不碰 streamlit）

量與質並列（CLAUDE_CODE_TASK_5 §5）：KPI 5 → 業務排名（公司戶灰字/另列）→
業務 × 月熱圖 → 業務 × 報表平台。畫面上的點列進業務頁、平台細度切換留在互動。
"""
from __future__ import annotations

import plotly.express as px

from core import analysis as A
from core.format import money, pct
from reports import export as X

from ._base import EXT_NET, SAME_PERIOD, SHARE, header, open_month_note
from .glossary import annotate


def _scope_preset(f: dict) -> str:
    s = f.get("scope")
    return s.get("preset") if isinstance(s, dict) else (s or "analysis")


def build_doc(f: dict, user: dict | None = None) -> X.Doc:
    yf, yt = f["ym_from"], f["ym_to"]
    pf, pt = A.prev_window(yf, yt)
    preset = _scope_preset(f)
    doc = header("業務分析", subtitle="量與質並列：金額、佔比是量，毛利率、新客、依賴度是質",
                 f=f, user=user, orientation="landscape", as_of_note=open_month_note())

    # ---- 發稿 / 自訂口徑：線層聚焦排名 ----
    if preset != "analysis":
        scope = f.get("scope")
        spl = A.agg_salespeople_lines(A.load_lines(yf, yt, scope, f, user), A.load_lines(pf, pt, scope, f, user))
        if spl.empty:
            doc.text("此條件查無資料。", "callout")
            return annotate(doc)
        nonh = spl[~spl["is_house"]]
        tot = float(nonh["ext_net"].sum())
        doc.kpis([
            {"label": "有業績的業務", "value": f"{len(nonh)} 人"},
            {"label": "除佣實收合計", "value": money(tot)},
            {"label": "帳上毛利率", "value": pct(float(nonh["booked_profit"].sum()) / tot if tot else None)},
        ], per_row=3)
        doc.text(f"口徑：{'發稿口徑（老闆版）' if preset == 'media' else '自訂'}｜線層彙總（交換併回原業務）。"
                 f"{EXT_NET}。完整分析（狀態/同期/熱圖）請切回分析口徑。", "note")
        doc.table("業務排名（發稿口徑）", nonh, X.cols(
            ("rank_in_year", "#", "int"), ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
            X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
            X.Col("share", "佔比", "progress", max=float(nonh["share"].max()) if len(nonh) else 1.0, help=SHARE),
            ("net_cp_family", "全家企頻", "money"), ("net_fresh", "新鮮視", "money"),
            ("net_cp_carrefour", "萬家福", "money"), ("net_radio", "廣播", "money"),
            ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
            ("customers", "客戶數", "int"), X.Col("yoy_text", "同期%", "text", help=SAME_PERIOD)),
            wide=True, note=f"{SAME_PERIOD}；公司戶不列入。")
        house = spl[spl["is_house"]]
        if not house.empty:
            doc.table("公司戶（另列、不排名）", house, X.cols(
                ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
                ("ext_net", "除佣實收", "money"), ("booked_profit", "帳上毛利", "money")),
                note="公司戶＝掛在公司名下（非個人業務）的訂單，不參與業務排名。")
        return annotate(doc)

    # ---- 分析口徑：完整版 ----
    dw = A.load_deals(yf, yt, f, exclude_barter=f["exclude_barter"], user=user)
    if dw.empty:
        doc.text("此條件查無資料。", "callout")
        return annotate(doc)
    dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
    cust = A.agg_customers(dw, dp, A.customer_year(yf.year))
    sp = A.agg_salespeople(dw, dp, A.new_customers_by_salesperson(cust), A.load_barter_by("salesperson", yf, yt))
    nonh = sp[~sp["is_house"]].copy()
    house = sp[sp["is_house"]].copy()
    n = len(nonh)
    tot = float(nonh["ext_net"].sum())
    tot_bp = float(nonh["booked_profit"].sum())

    doc.kpis([
        {"label": "有業績的業務", "value": f"{n} 人", "sub": f"公司戶另計 {money(float(house['ext_net'].sum()))}"},
        {"label": "人均除佣實收", "value": money(tot / n) if n else "–", "sub": f"人均帳上毛利 {money(tot_bp / n) if n else '–'}"},
        {"label": "人均客戶數", "value": f"{nonh['customers'].sum() / n:.1f}" if n else "–",
         "sub": f"人均新客 {nonh['new_customers'].sum() / n:.1f}" if n else "–"},
        {"label": "業務業績合計", "value": money(tot), "sub": f"帳上毛利率 {pct(tot_bp / tot) if tot else '–'}"},
        {"label": "交換（另計）", "value": money(float(sp["barter_net"].sum())), "sub": "不計入排名與毛利"},
    ], per_row=5)
    doc.text(f"**同期比較**：{SAME_PERIOD}。「前3大依賴度」＝該業務前 3 大客戶佔其總業績比重（越高越依賴少數客戶）；"
             "「認定業績」＝交換併回原業務後的業績；公司戶（掛公司名下）另列不排名。", "note")

    doc.heading("業務排名")
    share_max = float(nonh["share"].max()) if n else 1.0
    nonh["mix"] = nonh.apply(lambda r: A.platform_mix_text(r["net_cp"], r["net_fresh"], r["net_radio"], r["net_other"]), axis=1)
    full = X.cols(
        ("rank_in_year", "#", "int"), ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
        ("main_group", "組別", "text"), X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
        X.Col("share", "佔比", "progress", max=share_max, help=SHARE), X.Col("yoy_text", "同期%", "text", help=SAME_PERIOD),
        ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"), ("net_margin", "淨利率", "pct"),
        X.Col("recognized_amount", "認定業績", "money", help="交換併回原業務後的業績"),
        ("customers", "客戶數", "int"), ("new_customers", "新客", "int"), ("deals", "訂單數", "int"),
        ("avg_deal", "平均單筆", "money"),
        X.Col("top3_share", "前3大依賴度", "pct", help="前 3 大客戶佔該業務總業績比重"),
        ("top_customer", "最大客戶", "text"), ("barter_net", "交換", "money"))
    slim = X.cols(
        ("rank_in_year", "#", "int"), ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
        X.Col("ext_net", "除佣實收", "money", help=EXT_NET),
        X.Col("share", "佔比", "progress", max=share_max, help=SHARE), ("yoy_text", "同期%", "text"),
        ("booked_margin", "毛利率", "pct"), ("net_margin", "淨利率", "pct"), ("customers", "客戶數", "int"),
        ("new_customers", "新客", "int"), X.Col("top3_share", "前3大依賴度", "pct", help="前 3 大客戶佔比"))
    doc.table("業務排名", nonh, full, screen_columns=slim, wide=True,
              note=f"{SAME_PERIOD}；{SHARE}。公司戶另列於下。")
    if not house.empty:
        doc.table("公司戶（Company 等，另列、不排名）", house, X.cols(
            ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
            ("ext_net", "除佣實收", "money"), ("booked_profit", "帳上毛利", "money"),
            ("booked_margin", "毛利率", "pct"), ("deals", "訂單數", "int")),
            row_class=lambda r: "muted", note="公司戶＝掛在公司名下（非個人業務）的訂單。")

    # ---- 業務 × 月 熱圖 ----
    doc.heading("時間分布")
    top8 = nonh.head(8)["salesperson"].tolist()
    if top8:
        hm = A.load_deals(yf, yt, f, exclude_barter=True, user=user)
        hm = hm[hm["salesperson"].isin(top8)].copy()
        hm["month"] = hm["perf_ym"].map(lambda d: f"{d.month}月")
        months = [f"{m.month}月" for m in A.month_range(yf, yt)]
        pv = (hm.pivot_table(index="salesperson", columns="month", values="ext_net", aggfunc="sum")
              .reindex(index=top8, columns=months).fillna(0) / 1e4)
        pv["合計"] = pv.sum(axis=1)
        zmax = float(pv[months].values.max()) or 1.0
        fig = px.imshow(pv.values, x=months + ["合計"], y=top8, color_continuous_scale="Blues",
                        aspect="auto", text_auto=",.0f", zmax=zmax, labels=dict(color="萬"))
        fig.update_traces(textfont_size=11)
        fig.update_layout(height=max(240, 36 * len(top8)), coloraxis_showscale=False)
        ex = pv.reset_index().rename(columns={"salesperson": "業務"})
        doc.chart("業務 × 月 熱圖（前 8 名，數字為萬）", fig, height=max(240, 36 * len(top8)),
                  caption="顏色深＝該月金額大；末欄為該業務期間合計（單位：萬）",
                  excel={"type": "matrix", "df": ex[["業務"] + months], "x": "業務", "series": months, "unit": "萬"})

    # ---- 業務 × 報表平台 ----
    doc.heading("平台分布")
    mat = A.salesperson_platform(yf, yt, f, exclude_barter=f["exclude_barter"], user=user, by="report_platform")
    if mat is not None and not mat.empty:
        mat = mat.loc[:, [c for c in mat.columns if mat[c].abs().sum() > 0]]
        disp = mat.round(0).reset_index().rename(columns={"salesperson": "業務"})
        spec = [X.Col("業務", "業務", "text")] + [X.Col(c, c, "money") for c in mat.columns]
        doc.table("業務 × 報表平台（除佣實收）", disp, spec, wide=True,
                  note="數字為除佣實收（對外、已排除內部轉撥" + ("、排除交換" if f["exclude_barter"] else "") +
                       "）；欄依總額由大到小；報表平台＝老闆四欄＋健康視。")

    return annotate(doc)
