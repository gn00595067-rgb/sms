"""
html.py — layout.py 的 HTML 寫入端：畫面（st.html）與 PDF（Chromium 列印）共用

一張工作表 = 一個 <table class="bw">，列與 Excel 一一對應（標題列 colspan、空列 <tr class="gap">、合併表頭 rowspan/colspan），
顏色、粗體、數字格式和 Excel 版一致。CSS 內含列印規則：A4 橫向、表頭每頁重複（逐筆明細的三列表頭放 <thead>）、列不切頁。
"""
from __future__ import annotations

import html as _h

import pandas as pd

from . import layout as L

FONT_STACK = '"Noto Sans CJK TC","Noto Sans TC","Microsoft JhengHei","微軟正黑體","PingFang TC",sans-serif'
TOTAL_LABELS = ("合計", "三公司合計", "前10大合計", "除佣實收總計")

CSS = f"""
.bw-wrap {{ font-family: {FONT_STACK}; color: #1d2733; font-size: 12px; }}
table.bw {{ border-collapse: collapse; width: max-content; min-width: 60%; font-variant-numeric: tabular-nums; }}
table.bw td, table.bw th {{ border: 1px solid #000; padding: 3px 7px; white-space: nowrap; vertical-align: middle; }}
.bw-wrap .ttl {{ font-weight: 700; padding: 8px 0 3px; break-after: avoid; page-break-after: avoid; }}
.bw-wrap .ttl.big {{ font-size: 15px; color: #203864; }}
.bw-wrap .ttl.mid {{ font-size: 13px; color: #203864; }}
.bw-wrap .block {{ display: inline-block; min-width: 60%; background: #8EA9DB; font-weight: 700; border: 1px solid #000; padding: 3px 7px; margin-top: 6px; break-after: avoid; page-break-after: avoid; }}
.bw-wrap table.bw.raw td {{ font-size: 10px; padding: 2px 5px; }}
table.bw th {{ background: #2F5496; color: #fff; font-weight: 700; text-align: center; white-space: normal; }}
table.bw th.green {{ background: #548235; }}
table.bw th.plain {{ background: #fff; color: #1d2733; font-weight: 400; }}
table.bw td.num {{ text-align: right; }}
table.bw td.ctr {{ text-align: center; }}
table.bw td.neg {{ color: #c00000; }}
table.bw tr.total td {{ background: #FFFF00; font-weight: 700; }}
table.bw tr.sub td {{ background: #D9E2F3; font-weight: 700; }}
table.bw td.b {{ font-weight: 700; }}
table.bw td.detail-title {{ border: none; font-size: 14px; padding: 4px 0 10px; }}
@media print {{
  @page {{ size: A4 landscape; margin: 12mm 10mm; }}
  .bw-wrap {{ font-size: 10.5px; }}
  table.bw {{ width: 100%; }}
  table.bw tr {{ break-inside: avoid; page-break-inside: avoid; }}
  table.bw thead {{ display: table-header-group; }}
  .noprint {{ display: none !important; }}
}}
"""


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def fmt(v, kind: str, pct: str = L.PCT2) -> tuple[str, str]:
    """回傳 (文字, td class)。"""
    if _missing(v):
        return "", ""
    if kind == "money":
        x = float(v)
        return (f"(${abs(x):,.0f})", "num neg") if x < 0 else (f"${x:,.0f}", "num")
    if kind == "count":
        x = int(v)
        return ("-" if x == 0 else f"{x:,}"), "num"
    if kind == "pct":
        d = 1 if pct == L.PCT1 else 2
        return f"{float(v) * 100:.{d}f}%", "num"
    if kind == "int":
        return (str(int(v)) if not isinstance(v, str) else _h.escape(v)), "ctr"
    return _h.escape(str(v)), ""


class HtmlSheet:
    """
    實作 layout.py 的介面。每個「表頭」開一張新的 <table>（表頭放 <thead>，列印時每頁重複）；
    標題／空列／區塊標題是表與表之間的 <div>。r 只用來對齊 Excel 的列號（layout 用 mark()）。
    """

    def __init__(self, size=10):
        self.chunks: list[str] = []
        self.r = 1
        self.size = size
        self._open = False

    def mark(self) -> int:
        return self.r

    def _close(self):
        if self._open:
            self.chunks.append("</tbody></table>")
            self._open = False

    def _open_table(self, thead_rows: list[str], cls: str = "bw"):
        self._close()
        self.chunks.append(f'<table class="{cls}"><thead>{"".join(thead_rows)}</thead><tbody>')
        self._open = True

    def _add(self, tr: str):
        if not self._open:
            self._open_table([])
        self.chunks.append(tr)
        self.r += 1

    def title(self, text, *, size=13, bold=True, color=L.TITLE_INK, merge_to=None, center=False):
        self._close()
        cls = "ttl big" if size >= 13 else ("ttl mid" if size >= 12 else "ttl")
        style = "" if bold else ' style="font-weight:400"'
        self.chunks.append(f'<div class="{cls}"{style}>{_h.escape(text)}</div>')
        self.r += 1

    def blank(self, n=1):
        self._close()
        self.chunks.append(f'<div class="gap" style="height:{8 * n}px"></div>')
        self.r += n

    def block_title(self, text, ncol):
        self._close()
        self.chunks.append(f'<div class="block">{_h.escape(text)}</div>')
        self.r += 1

    def header(self, labels, *, fill=L.BLUE, size=None, height=None):
        cls = ' class="green"' if fill == L.GREEN else ""
        self._open_table(["<tr>" + "".join(f"<th{cls}>{_h.escape(str(x))}</th>" for x in labels) + "</tr>"])
        self.r += 1

    def table(self, df: pd.DataFrame, fmts: dict, *, pct=L.PCT2, bold_cols=("總計", "總計(除佣實收)"), bold_first=True,
              size=None, first_col_bold_rows=True):
        cols = list(df.columns)
        for _, row in df.iterrows():
            first = row[cols[0]]
            is_total = isinstance(first, str) and first in TOTAL_LABELS
            is_sub = isinstance(first, str) and first.endswith(" 小計")
            tds = []
            for j, col in enumerate(cols, start=1):
                text, cls = fmt(row[col], fmts.get(col, "text"), pct)
                if (col in bold_cols) or (j == 1 and first_col_bold_rows and bold_first):
                    cls = (cls + " b").strip()
                tds.append(f'<td class="{cls}">{text}</td>' if cls else f"<td>{text}</td>")
            trc = ' class="total"' if is_total else (' class="sub"' if is_sub else "")
            self._add(f"<tr{trc}>" + "".join(tds) + "</tr>")

    # ---- 年度發稿明細 ----
    def detail_title(self, company, year_label, ncol):
        self._add(f'<tr><td class="detail-title" colspan="{ncol}">{_h.escape(f"{company}-{year_label}發稿")}</td></tr>')
        self.blank()
        self.r = 3

    def section3_header(self, plats):
        n = len(plats)
        r1 = ('<tr><th class="plain" rowspan="3">業務</th><th class="plain" rowspan="3">客戶名稱</th>'
              '<th class="plain" rowspan="3">實收</th><th class="plain" rowspan="3">執行走期</th>'
              f'<th class="plain" colspan="{n}">平台</th><th class="plain" rowspan="3">成本<br>(實付金額)</th>'
              '<th class="plain" rowspan="3">毛利</th><th class="plain" rowspan="3">利率(%)</th><th class="plain" rowspan="3">發稿佔比</th></tr>')
        r2 = "<tr>" + "".join(f'<th class="plain">{_h.escape(p)}</th>' for p in plats) + "</tr>"
        r3 = f'<tr><th class="plain" colspan="{n}">除佣實收</th></tr>'
        self._open_table([r1, r2, r3])   # thead：列印時每頁重複
        self.r += 3

    def section3_rows(self, df: pd.DataFrame, plats):
        for _, row in df.iterrows():
            tds = [f"<td>{_h.escape(str(row['業務']))}</td>", f"<td>{_h.escape(str(row['客戶名稱']))}</td>"]
            t, c = fmt(row["實收"], "money"); tds.append(f'<td class="ctr {c}">{t}</td>')
            tds.append(f'<td class="ctr">{_h.escape(str(row["執行走期"]))}</td>')
            for p in plats:
                t, c = fmt(row[p], "money"); tds.append(f'<td class="ctr {c}">{t}</td>')
            for key, kind in (("成本", "money"), ("毛利", "money"), ("利率", "pct"), ("發稿佔比", "pct")):
                t, c = fmt(row[key], kind); tds.append(f'<td class="ctr {c}">{t}</td>')
            self._add("<tr>" + "".join(tds) + "</tr>")

    def section3_totals(self, t: dict, plats):
        n = len(plats)
        cells = [f'<td class="ctr" colspan="2">各平台除佣實收小計</td>', f'<td class="ctr">{fmt(t["實收"], "money")[0]}</td>', "<td></td>"]
        cells += [f'<td class="ctr">{fmt(t[p], "money")[0]}</td>' for p in plats]
        cells += [f'<td class="ctr">{fmt(t["成本"], "money")[0]}</td>', f'<td class="ctr">{fmt(t["毛利"], "money")[0]}</td>',
                  f'<td class="ctr">{fmt(t["利率"], "pct")[0]}</td>', f'<td class="ctr">{fmt(t["發稿佔比"], "pct")[0]}</td>']
        self._add('<tr class="total">' + "".join(cells) + "</tr>")
        cells = [f'<td class="ctr" colspan="2">除佣實收總計</td>', "<td></td>", "<td></td>",
                 f'<td class="ctr" colspan="{n}">{fmt(t["總計"], "money")[0]}</td>',
                 f'<td class="ctr">{fmt(t["成本"], "money")[0]}</td>', f'<td class="ctr">{fmt(t["毛利"], "money")[0]}</td>',
                 f'<td class="ctr">{fmt(t["利率"], "pct")[0]}</td>', f'<td class="ctr">{fmt(t["發稿佔比"], "pct")[0]}</td>']
        self._add('<tr class="total">' + "".join(cells) + "</tr>")

    def raw_table(self, raw: pd.DataFrame, cols):
        self._open_table(["<tr>" + "".join(f"<th>{_h.escape(c)}</th>" for c in cols) + "</tr>"], cls="bw raw")
        num = {"實收金額", "除佣實收", "實付金額", "購買檔次", "搭贈檔次", "搭贈金額", "編播贈檔"}
        for _, row in raw[cols].iterrows():
            tds = []
            for c in cols:
                v = row[c]
                if _missing(v):
                    tds.append("<td></td>")
                elif c in num:
                    tds.append(f'<td class="num">{float(v):,.0f}</td>')
                else:
                    tds.append(f"<td>{_h.escape(str(v))}</td>")
            self._add("<tr>" + "".join(tds) + "</tr>")

    # ---- 工作表層（HTML 不需要）----
    def widths(self, spec): ...
    def freeze(self, cell): ...
    def print_setup(self, *, landscape=True, repeat_rows=None): ...

    def render(self) -> str:
        self._close()
        return "".join(self.chunks)


def sheet_html(name: str, raw: pd.DataFrame, plats: list[str], *, year_label: str, notes_lines: list[str],
               max_raw_rows: int | None = None, sections: tuple[int, ...] = (1, 2, 3)) -> str:
    """一張工作表的 HTML 片段（不含 <html>）。畫面用 st.html(CSS + 片段)；年度發稿明細可用 sections 只畫部分段。"""
    s = HtmlSheet(12 if name.endswith("_年度發稿明細") else 10)
    src = raw if (max_raw_rows is None or name != "原始資料_發稿分析") else raw.head(max_raw_rows)
    L.layout_sheet(s, name, src, plats, year_label=year_label, notes_lines=notes_lines, sections=sections)
    return f'<div class="bw-wrap">{s.render()}</div>'


def page_html(names: list[str], raw: pd.DataFrame, *, year_label: str, notes_lines: list[str], title: str = "常用分析") -> str:
    """整份（多張工作表）的可列印 HTML：每張工作表從新的一頁開始。給 reports.export.pdf.html_to_pdf 或瀏覽器 Ctrl+P。"""
    raw, plats = L.prepare(raw)
    parts = []
    for i, n in enumerate(names):
        frag = sheet_html(n, raw, plats, year_label=year_label, notes_lines=notes_lines)
        pb = ' style="break-before:page;page-break-before:always"' if i else ""
        parts.append(f'<section{pb}><h2 style="font-family:{FONT_STACK};font-size:14px;margin:0 0 6px">{_h.escape(n)}</h2>{frag}</section>')
    return (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{_h.escape(title)}</title>'
            f"<style>{CSS} body{{margin:16px}} h2{{break-after:avoid}}</style></head><body>{''.join(parts)}</body></html>")
