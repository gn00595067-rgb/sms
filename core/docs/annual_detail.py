"""
core/docs/annual_detail.py — 年度發稿明細（喬商版型）的列印版（不碰 streamlit）

一家公司一份 Doc，三段往下排（CLAUDE_CODE_TASK_5 §4.1 / §5）：
  第一段 各業務客戶數與發稿總計
  第二段 各業務每客戶總計（分平台）
  第三段 逐筆明細
Excel 用 xlsx_layout="single"（三段同一張工作表，喬商習慣）。資料計算沿用 reports.annual_detail。
"""
from __future__ import annotations

import pandas as pd

from reports import annual_detail as AD
from reports import export as X

from ._base import header
from .glossary import annotate

_PLAT_HELP = "報表平台：全家企頻／萬家福／新鮮視／廣播／健康視（發稿口徑五欄）"


def _plat_cols(plats):
    return [X.Col(p, p, "money", help=_PLAT_HELP) for p in plats]


def build_doc(f: dict, user: dict | None = None, *, company: str) -> X.Doc:
    year = (f.get("ym_to").year if f and f.get("ym_to") else None)
    if year is None:
        from core import analysis as A
        year = A.as_of()["as_of_year"]
    df = AD.load(year, company, "media", user)
    doc = header(f"年度發稿明細 — {company} {year}",
                 subtitle="發稿口徑（老闆版）：只算媒體上稿線、交換併回原業務、四平台＋健康視、帳上毛利",
                 f={"ym_from": f.get("ym_from"), "ym_to": f.get("ym_to"), "scope": "media",
                    "company": company, "exclude_barter": False},
                 user=user, orientation="landscape")
    doc.xlsx_layout = "single"
    doc.filter_text = f"公司={company}　{year} 全年"
    if df.empty:
        doc.text(f"{company} {year} 查無資料。", "callout")
        return annotate(doc)
    plats = AD._present_platforms(df)
    ctot = float(df["net_amount"].sum())

    # ---- 第一段 ----
    doc.heading("第一段：各業務客戶數與發稿總計")
    s1 = AD.section1(df, ctot, plats)
    body1, tot1row = s1.iloc[:-1], s1.iloc[-1]
    cols1 = X.cols(("業務", "業務", "text"), X.Col("customers", "客戶數", "int", help="該業務不重複客戶數")) \
        + _plat_cols(plats) + X.cols(
        X.Col("總計", "總計（除佣實收）", "money", help="該業務發稿口徑除佣實收"),
        ("帳上毛利", "帳上毛利", "money"), X.Col("利率", "利率", "pct", help="帳上毛利 ÷ 除佣實收"),
        X.Col("發稿佔比", "發稿佔比", "pct", help="該業務 ÷ 公司發稿總額"))
    tot1 = {k: tot1row.get(k) for k in ("業務", "customers", "總計", "帳上毛利", "利率", "發稿佔比", *plats)}
    doc.table("各業務發稿總計", body1, cols1, totals=tot1,
              note="發稿佔比分母＝該公司發稿口徑除佣實收合計。")

    # ---- 第二段 ----
    doc.heading("第二段：各業務每客戶總計（分平台）")
    cols2 = X.cols(("客戶", "客戶", "text")) + _plat_cols(plats) + X.cols(
        X.Col("總計", "總計", "money", help="該客戶在此業務的除佣實收"),
        ("帳上毛利", "帳上毛利", "money"), ("利率", "利率", "pct"),
        X.Col("佔該業務", "佔該業務", "pct", help="該客戶 ÷ 該業務總額"))
    for sp, b in AD.section2(df, plats):
        doc.heading(f"【{sp}】", level=3)
        doc.table(f"{sp} — 客戶明細", b, cols2)

    # ---- 第三段 ----
    doc.page_break()
    doc.heading("第三段：逐筆明細")
    s3 = AD.section3(df, plats)
    cols3 = X.cols(("業務", "業務", "text"), ("客戶", "客戶", "text"),
                   X.Col("實收", "實收", "money", help="該筆除佣實收"), ("走期", "執行走期", "text")) \
        + _plat_cols(plats) + X.cols(
        X.Col("成本", "成本", "money", help="實付媒體/通路"), ("帳上毛利", "帳上毛利", "money"),
        ("利率", "利率", "pct"), X.Col("佔比", "佔比", "pct", help="該筆 ÷ 公司發稿總額"))
    tl = AD.totals_line(df, plats)
    tl_tot = {"業務": tl.get("業務"), "實收": tl.get("實收"), "成本": tl.get("成本"),
              "帳上毛利": tl.get("帳上毛利"), **{p: tl.get(p) for p in plats}}
    doc.table("逐筆明細", s3, cols3, totals=tl_tot, wide=True, max_rows_pdf=400,
              note="末列為除佣實收總計與各平台小計；完整逐筆請用 Excel。")
    return annotate(doc)
