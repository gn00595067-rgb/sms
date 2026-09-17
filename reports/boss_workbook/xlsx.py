"""
xlsx.py — layout.py 的 Excel 寫入端（openpyxl；寫值不寫公式）

樣式全部照 2025年度_三公司發稿明細分析-0917.xlsx 量的：
  表頭：深藍 2F5496 白字粗體置中（三公司彙總表頭用綠 548235）；合計列：黃 FFFF00 粗體；
  區塊標題【業務】：淺藍 8EA9DB 粗體、合併整列；小計列：淡藍 D9E2F3 粗體；
  金額：$#,##0_);[Red]($#,##0)；筆數：#,##0;(#,##0);-；利率：0.0%（平台總計總覽）/ 0.00%（其餘）；
  全部細框線；字型統一微軟正黑體（原檔混用 Noto Sans CJK，是產生機器的字型，不是設計）。
比原檔多的：欄寬夠寬（原檔預設寬會顯示 ###）、列印設定（A4 橫向一頁寬、頁尾頁碼、逐筆明細表頭每頁重複）。
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.properties import PageSetupProperties

from . import layout as L

FONT = "微軟正黑體"
MONEY = '\\$#,##0_);[Red]"($"#,##0\\)'
COUNT = "#,##0;\\(#,##0\\);\\-"
_thin = Side(style="thin", color="000000")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFTC = Alignment(horizontal="left", vertical="center")
TOTAL_LABELS = ("合計", "三公司合計", "前10大合計", "除佣實收總計")


def _font(size=10, bold=False, color=None):
    return Font(name=FONT, size=size, bold=bold, color=color)


def _fill(rgb):
    return PatternFill("solid", fgColor=rgb)


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


class Sheet:
    """逐列往下寫；r 是下一個可用列。實作 layout.py 要求的介面。"""

    def __init__(self, ws, size=10):
        self.ws, self.r, self.size = ws, 1, size

    def mark(self) -> int:
        return self.r

    def title(self, text, *, size=13, bold=True, color=L.TITLE_INK, merge_to=None, center=False):
        c = self.ws.cell(self.r, 1, text)
        c.font = _font(size, bold, color)
        if merge_to:
            self.ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=merge_to)
        if center:
            c.alignment = CENTER
        self.r += 1

    def blank(self, n=1):
        self.r += n

    def block_title(self, text, ncol):
        c = self.ws.cell(self.r, 1, text)
        c.font, c.fill, c.border, c.alignment = _font(self.size, True), _fill(L.LBLUE), BORDER, LEFTC
        for j in range(2, ncol + 1):
            self.ws.cell(self.r, j).border = BORDER
        self.ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=ncol)
        self.r += 1

    def header(self, labels, *, fill=L.BLUE, size=None, height=None):
        for j, lab in enumerate(labels, start=1):
            c = self.ws.cell(self.r, j, lab)
            c.font, c.fill, c.border, c.alignment = _font(size or self.size, True, "FFFFFF"), _fill(fill), BORDER, CENTER
        if height:
            self.ws.row_dimensions[self.r].height = height
        self.r += 1

    def table(self, df: pd.DataFrame, fmts: dict, *, pct=L.PCT2, bold_cols=("總計", "總計(除佣實收)"), bold_first=True,
              size=None, first_col_bold_rows=True):
        size = size or self.size
        cols = list(df.columns)
        for _, row in df.iterrows():
            first = row[cols[0]]
            is_total = isinstance(first, str) and first in TOTAL_LABELS
            is_sub = isinstance(first, str) and first.endswith(" 小計")
            for j, col in enumerate(cols, start=1):
                v = row[col]
                c = self.ws.cell(self.r, j)
                kind = fmts.get(col, "text")
                if _missing(v):
                    c.value = None
                elif kind == "money":
                    c.value, c.number_format = float(v), MONEY
                elif kind == "count":
                    c.value, c.number_format = int(v), COUNT
                elif kind == "pct":
                    c.value, c.number_format = float(v), pct
                elif kind == "int" and not isinstance(v, str):
                    c.value = int(v)
                else:
                    c.value = str(v)
                bold = is_total or is_sub or (col in bold_cols) or (j == 1 and first_col_bold_rows and bold_first)
                c.font, c.border = _font(size, bold), BORDER
                if is_total:
                    c.fill = _fill(L.YELLOW)
                elif is_sub:
                    c.fill = _fill(L.SUBTOT)
            self.r += 1

    # ---- 年度發稿明細專用 ----
    def detail_title(self, company, year_label, ncol):
        ws = self.ws
        ws.cell(1, 1, f"{company}-{year_label}發稿").font = _font(12)
        c = ws.cell(1, 2, f"{company}-{year_label}發稿")
        c.font, c.alignment = _font(12), CENTER
        ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=ncol)
        ws.row_dimensions[1].height = 19.5
        self.r = 3

    def section3_header(self, plats):
        ws, r0, n = self.ws, self.r, len(plats)
        heads = {1: "業務", 2: "客戶名稱", 3: " 實收", 4: "執行走期", 5 + n: "成本\n(實付金額)", 6 + n: "毛利", 7 + n: "利率(%)", 8 + n: "發稿佔比"}
        for j, lab in heads.items():
            ws.cell(r0, j, lab)
            ws.merge_cells(start_row=r0, start_column=j, end_row=r0 + 2, end_column=j)
        ws.cell(r0, 5, "平台")
        ws.merge_cells(start_row=r0, start_column=5, end_row=r0, end_column=4 + n)
        for k, p in enumerate(plats):
            ws.cell(r0 + 1, 5 + k, p)
        ws.cell(r0 + 2, 5, "除佣實收")
        ws.merge_cells(start_row=r0 + 2, start_column=5, end_row=r0 + 2, end_column=4 + n)
        for rr in (r0, r0 + 1, r0 + 2):
            for j in range(1, 9 + n):
                c = ws.cell(rr, j)
                c.font, c.border, c.alignment = _font(12), BORDER, CENTER
        ws.row_dimensions[r0].height, ws.row_dimensions[r0 + 1].height, ws.row_dimensions[r0 + 2].height = 19.5, 15.5, 19.5
        self.r = r0 + 3

    def section3_rows(self, df: pd.DataFrame, plats):
        n = len(plats)
        for _, row in df.iterrows():
            vals = [row["業務"], row["客戶名稱"], row["實收"], row["執行走期"]] + [row[p] for p in plats] + [row["成本"], row["毛利"], row["利率"], row["發稿佔比"]]
            for j, v in enumerate(vals, start=1):
                c = self.ws.cell(self.r, j)
                if _missing(v):
                    c.value = None
                elif j in (1, 2, 4):
                    c.value = str(v)
                elif j in (7 + n, 8 + n):
                    c.value, c.number_format = float(v), L.PCT2
                else:
                    c.value, c.number_format = float(v), MONEY
                c.font, c.border = _font(12), BORDER
                c.alignment = Alignment(horizontal=None if j in (1, 2) else "center", vertical="center")
            self.r += 1

    def section3_totals(self, t: dict, plats):
        ws, n = self.ws, len(plats)
        ncol = 8 + n
        ws.cell(self.r, 1, "各平台除佣實收小計")
        ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=2)
        vals = {3: t["實收"], **{5 + k: t[p] for k, p in enumerate(plats)}, 5 + n: t["成本"], 6 + n: t["毛利"]}
        for j in range(1, ncol + 1):
            c = ws.cell(self.r, j)
            if j in vals:
                c.value, c.number_format = float(vals[j]), MONEY
            elif j == 7 + n:
                c.value, c.number_format = t["利率"], L.PCT2
            elif j == 8 + n:
                c.value, c.number_format = t["發稿佔比"], L.PCT2
            c.font, c.fill, c.border, c.alignment = _font(12, True), _fill(L.YELLOW), BORDER, CENTER
        self.r += 1
        ws.cell(self.r, 1, "除佣實收總計")
        ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=2)
        ws.merge_cells(start_row=self.r, start_column=5, end_row=self.r, end_column=4 + n)
        for j in range(1, ncol + 1):
            c = ws.cell(self.r, j)
            if j == 5:
                c.value, c.number_format = t["總計"], MONEY
            elif j == 5 + n:
                c.value, c.number_format = t["成本"], MONEY
            elif j == 6 + n:
                c.value, c.number_format = t["毛利"], MONEY
            elif j == 7 + n:
                c.value, c.number_format = t["利率"], L.PCT2
            elif j == 8 + n:
                c.value, c.number_format = t["發稿佔比"], L.PCT2
            c.font, c.fill, c.border, c.alignment = _font(12, True), _fill(L.YELLOW), BORDER, CENTER
        self.r += 1

    def raw_table(self, raw: pd.DataFrame, cols):
        ws = self.ws
        for j, col in enumerate(cols, start=1):
            c = ws.cell(1, j, col)
            c.font, c.fill, c.border, c.alignment = _font(10, True, "FFFFFF"), _fill(L.BLUE), BORDER, CENTER
        num = {"實收金額", "除佣實收", "實付金額", "購買檔次", "搭贈檔次", "搭贈金額", "編播贈檔"}
        for i, (_, row) in enumerate(raw[cols].iterrows(), start=2):
            for j, col in enumerate(cols, start=1):
                v = row[col]
                if _missing(v):
                    continue
                c = ws.cell(i, j)
                if col in num:
                    c.value, c.number_format = float(v), COUNT
                else:
                    c.value = str(v)
                c.font = _font(10)
        for j, col in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(j)].width = 12 if col not in ("客戶名稱", "廣告名稱", "電台", "備註") else 26
        self.r = len(raw) + 2

    # ---- 工作表層 ----
    def widths(self, spec: dict):
        for k, w in spec.items():
            self.ws.column_dimensions[k].width = w

    def freeze(self, cell: str):
        self.ws.freeze_panes = cell

    def print_setup(self, *, landscape: bool, repeat_rows: str | None = None):
        ws = self.ws
        ws.page_setup.orientation = "landscape" if landscape else "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.print_options.horizontalCentered = True
        ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.6, bottom=0.6, header=0.3, footer=0.3)
        if repeat_rows:
            ws.print_title_rows = repeat_rows
        ws.oddFooter.right.text = f'&"{FONT}"第 &P / &N 頁'
        ws.oddFooter.left.text = f'&"{FONT}"&A'


def build_workbook(raw: pd.DataFrame, *, year_label: str, notes_lines: list[str], sheets: list[str] | None = None) -> Workbook:
    """raw = v_boss_line 的期間切片（欄名同工作簿）。year_label 例「2025年度」或「2026/01–2026/08」。"""
    raw, plats = L.prepare(raw)
    wb = Workbook()
    wb.remove(wb.active)
    for name in (sheets or L.SHEETS):
        ws = wb.create_sheet(name)
        s = Sheet(ws, 12 if name.endswith("_年度發稿明細") else 10)
        L.layout_sheet(s, name, raw, plats, year_label=year_label, notes_lines=notes_lines)
    return wb


def build_bytes(raw: pd.DataFrame, *, year_label: str, notes_lines: list[str], sheets: list[str] | None = None) -> bytes:
    buf = io.BytesIO()
    build_workbook(raw, year_label=year_label, notes_lines=notes_lines, sheets=sheets).save(buf)
    return buf.getvalue()
