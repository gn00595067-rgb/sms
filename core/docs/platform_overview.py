"""
core/docs/platform_overview.py — 平台總計總覽（老闆版）的列印版（不碰 streamlit）

老闆工作簿「平台總計總覽」八區塊（除佣／成本／帳上毛利／利率 × 含廣播／不含廣播）
＋集團毛利＋客戶數（含／不含廣播），公司 × 報表平台矩陣。發稿口徑。
資料計算沿用 reports.platform_overview。Excel 用 xlsx_layout="single"（區塊往下排）。
"""
from __future__ import annotations

from reports import export as X
from reports import platform_overview as PO

from ._base import header
from .glossary import annotate


def build_doc(f: dict, user: dict | None = None) -> X.Doc:
    year = (f.get("ym_to").year if f and f.get("ym_to") else None)
    if year is None:
        from core import analysis as A
        year = A.as_of()["as_of_year"]
    df = PO._base(year, "media", user)
    doc = header(f"平台總計總覽 — {year}",
                 subtitle="老闆版：公司 × 報表平台，八區塊（除佣／成本／毛利／利率 × 含廣播／不含廣播）＋集團毛利＋客戶數",
                 f={"ym_from": f.get("ym_from"), "ym_to": f.get("ym_to"), "scope": "media", "exclude_barter": False},
                 user=user, orientation="landscape")
    doc.xlsx_layout = "single"
    doc.filter_text = f"{year} 全年・發稿口徑"
    if df.empty:
        doc.text(f"{year} 查無資料。", "callout")
        return annotate(doc)

    for title, metric, own in PO.BLOCKS:
        blk = PO._block(df, metric, own)
        if blk.empty:
            continue
        plats = PO._present(df, own)
        kind = "pct" if metric == "margin" else ("int" if metric == "customers" else "money")
        body, totrow = blk.iloc[:-1], blk.iloc[-1]
        cols = X.cols(("公司", "公司", "text")) + [X.Col(p, p, kind) for p in plats] + \
            [X.Col("合計", "合計", kind)]
        tot = {"公司": totrow.get("公司"), "合計": totrow.get("合計"), **{p: totrow.get(p) for p in plats}}
        doc.heading(title)
        doc.table(title, body, cols, totals=tot)
    doc.text("利率＝Σ帳上毛利 ÷ Σ除佣實收（非各平台平均）；客戶數為不重複；"
             "不含廣播＝只算自媒體（全家企頻／萬家福／新鮮視／健康視）。", "note")
    return annotate(doc)
