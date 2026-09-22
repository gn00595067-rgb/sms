"""
grid.py — Access 報表版型的中間格式：一張報表 = 一串 Row，一列 = 一串 Cell（可跨欄／跨列、填色、粗體、數字格式）

同一份 Grid 交給 to_html() 畫畫面／PDF（Chromium 列印），交給 to_xlsx() 寫 Excel，數字、顏色、粗體三處一致。
不用 reports/export/doc.py 的 Table（那是「一張 DataFrame 一張表」的模型），因為舊 Access 報表是
「明細 + 三層小計 + 方塊 + 表單」自由排版，用列/格描述最直接。
"""
from __future__ import annotations

import html as _h
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

FONT_STACK = '"Noto Sans CJK TC","Noto Sans TC","Microsoft JhengHei","微軟正黑體","PingFang TC",sans-serif'

# 舊報表用到的填色（Excel 標準色）
C = {
    "grey": "D9D9D9", "yellow": "FFFF00", "lyellow": "FFFF99", "cyan": "CCFFFF", "teal": "99FFFF", "purple": "CC99FF",
    "orange": "F4B084", "lorange": "F8CBAD", "lblue": "BDD7EE", "blue": "9BC2E6", "green": "C6E0B4", "lgreen": "E2EFDA",
    "pink": "FF99CC", "lpink": "FFCCFF", "gold": "FFE699", "lavender": "E4DFEC", "white": "FFFFFF",
}


@dataclass
class Cell:
    v: object = ""
    kind: str = "text"          # text | money | money2 | int | pct | pct1 | pct2 | date | ym
    span: int = 1               # colspan
    rowspan: int = 1
    cls: str = ""               # 空白分隔：b（粗體）ctr / left / right（對齊）red / blue / grey（字色）small / big（字級）noborder box
    fill: str | None = None     # 'yellow' 等 C 的鍵，或 6 碼 hex
    ul: bool = False            # 底線（簽名欄）


@dataclass
class Row:
    cells: list[Cell]
    cls: str = ""               # head（表頭：列印每頁重複）title / gap / sub / total / kwn（keep-with-next）
    height: float | None = None


@dataclass
class Grid:
    name: str                   # 工作表名 / 段落 id
    rows: list[Row] = field(default_factory=list)
    widths: list[float] = field(default_factory=list)   # Excel 字元寬；HTML 依比例
    header_rows: int = 0        # 前 n 列是表頭（PDF 每頁重複、Excel 列印標題列）
    landscape: bool = True
    paper: str = "A4"           # A4 / A3（業務發稿統計）
    font_size: float = 10
    page_break_before: bool = False
    footer_left: str = ""       # 頁尾左（日期）；PDF 由 CSS 頁尾印
    footer_center: str = ""

    # ---- 便利方法 ----
    def add(self, cells: list, cls: str = "", height: float | None = None) -> "Row":
        r = Row([c if isinstance(c, Cell) else Cell(c) for c in cells], cls, height)
        self.rows.append(r)
        return r

    def gap(self, n: int = 1) -> None:
        for _ in range(n):
            self.rows.append(Row([Cell("")], "gap"))

    def title(self, text: str, span: int, *, size: str = "big", cls: str = "left") -> None:
        self.add([Cell(text, span=span, cls=f"b {size} {cls} noborder")], "title")

    @property
    def ncol(self) -> int:
        return max((sum(c.span for c in r.cells) for r in self.rows), default=1)


# ---------------------------------------------------------------- 格式
def _missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return False


def fmt(v, kind: str) -> str:
    if _missing(v):
        return ""
    if kind == "text":
        return _h.escape(str(v))
    if kind in ("money", "int"):
        x = float(v)
        return f"{x:,.0f}"
    if kind == "money2":
        return f"{float(v):,.2f}"
    if kind == "pct":       # 整數 %
        return f"{float(v) * 100:.0f}%"
    if kind == "pct1":
        return f"{float(v) * 100:.1f}%"
    if kind == "pct2":
        return f"{float(v) * 100:.2f}%"
    if kind == "date":
        if isinstance(v, (date, datetime)):
            return f"{v.year}/{v.month:02d}/{v.day:02d}"
        return _h.escape(str(v))
    if kind == "md":
        if isinstance(v, (date, datetime)):
            return f"{v.month:02d}/{v.day:02d}"
        return _h.escape(str(v))
    return _h.escape(str(v))


def _neg(v) -> bool:
    try:
        return float(v) < 0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- HTML
CSS = f"""
.fg-wrap {{ font-family: {FONT_STACK}; color: #000; font-variant-numeric: tabular-nums; }}
.fg-wrap table.fg {{ border-collapse: collapse; table-layout: fixed; margin-bottom: 4px; }}
.fg-wrap table.fg td {{ border: 1px solid #000; padding: 2px 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; line-height: 1.35; }}
.fg-wrap table.fg tr.gap td {{ border: none; height: 10px; padding: 0; }}
.fg-wrap table.fg tr.title td {{ border: none; padding: 6px 0 4px; }}
.fg-wrap td.num {{ text-align: right; }}
.fg-wrap td.ctr {{ text-align: center; }}
.fg-wrap td.left {{ text-align: left; }}
.fg-wrap td.right {{ text-align: right; }}
.fg-wrap td.b {{ font-weight: 700; }}
.fg-wrap td.red {{ color: #c00000; }}
.fg-wrap td.blue {{ color: #0000ff; }}
.fg-wrap td.grey {{ color: #7f7f7f; }}
.fg-wrap td.magenta {{ color: #ff00ff; }}
.fg-wrap td.green {{ color: #00b050; }}
.fg-wrap td.teal {{ color: #00b0f0; }}
.fg-wrap td.orange {{ color: #ff9900; }}
.fg-wrap td.neg {{ color: #c00000; }}
.fg-wrap td.small {{ font-size: 85%; }}
.fg-wrap td.big {{ font-size: 170%; }}
.fg-wrap td.mid {{ font-size: 125%; }}
.fg-wrap table.fg td.noborder {{ border: none; }}
.fg-wrap table.fg td.ul {{ border: none; border-bottom: 1px solid #000; }}
.fg-wrap table.fg td.wrap {{ white-space: normal; }}
.fg-wrap .fg-page.brk {{ page-break-before: always; break-before: page; }}
@media print {{
  .fg-wrap table.fg tr {{ break-inside: avoid; page-break-inside: avoid; }}
  .fg-wrap table.fg thead {{ display: table-header-group; }}
  .fg-wrap table.fg tr.kwn {{ break-after: avoid; page-break-after: avoid; }}
}}
"""


def _td(c: Cell, fs: float) -> str:
    classes = []
    kind = c.kind
    if kind in ("money", "money2", "int", "pct", "pct1", "pct2") and "left" not in c.cls and "ctr" not in c.cls:
        classes.append("num")
    if kind in ("date", "md", "ym") and "left" not in c.cls:
        classes.append("ctr")
    classes.extend(x for x in c.cls.split() if x)
    if kind in ("money", "money2", "int") and _neg(c.v) and "blue" not in c.cls:
        classes.append("neg")
    if c.ul:
        classes.append("ul")
    style = ""
    if c.fill:
        style = f' style="background:#{C.get(c.fill, c.fill)}"'
    attrs = f' colspan="{c.span}"' if c.span > 1 else ""
    attrs += f' rowspan="{c.rowspan}"' if c.rowspan > 1 else ""
    cls = f' class="{" ".join(classes)}"' if classes else ""
    return f"<td{attrs}{cls}{style}>{fmt(c.v, kind).replace(chr(10), '<br>')}</td>"


def grid_html(g: Grid) -> str:
    total = sum(g.widths) or g.ncol * 10
    colgroup = "".join(f'<col style="width:{w / total * 100:.2f}%">' for w in g.widths) if g.widths else ""
    fs = g.font_size
    head, body = [], []
    for i, r in enumerate(g.rows):
        cls = f' class="{r.cls}"' if r.cls else ""
        h = f' style="height:{r.height}px"' if r.height else ""
        tr = f"<tr{cls}{h}>" + "".join(_td(c, fs) for c in r.cells) + "</tr>"
        (head if i < g.header_rows else body).append(tr)
    thead = f"<thead>{''.join(head)}</thead>" if head else ""
    brk = " brk" if g.page_break_before else ""
    return (f'<div class="fg-page{brk}" data-name="{_h.escape(g.name)}">'
            f'<table class="fg" style="font-size:{fs}pt;width:100%"><colgroup>{colgroup}</colgroup>{thead}<tbody>{"".join(body)}</tbody></table></div>')


def to_html(grids: list[Grid], *, title: str, footer_left: str = "", footer_center: str = "") -> str:
    """整份列印版 HTML：A4 橫／直向依第一張 grid；每張 grid 一頁段（page-break）。"""
    landscape = grids[0].landscape if grids else True
    paper = grids[0].paper if grids else "A4"
    size = f"{paper} landscape" if landscape else f"{paper} portrait"
    body = "".join(grid_html(g) for g in grids)
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{_h.escape(title)}</title>
<style>{CSS}
@page {{ size: {size}; margin: 12mm 10mm 14mm 10mm; }}
body {{ margin: 0; padding: 8px; }}
</style></head><body><div class="fg-wrap">{body}</div></body></html>"""


# ---------------------------------------------------------------- Excel
def to_xlsx(grids: list[Grid], *, title: str = "", footer_left: str = "", footer_center: str = "") -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    NUMFMT = {"money": '#,##0;[Red]-#,##0', "int": '#,##0;[Red]-#,##0', "money2": '#,##0.00;[Red]-#,##0.00',
              "pct": '0%', "pct1": '0.0%', "pct2": '0.00%', "date": 'yyyy/mm/dd', "md": 'mm/dd'}
    used = set()
    for g in grids:
        name = g.name[:31] or "報表"
        i = 2
        base = name
        while name in used:
            name = f"{base[:28]}({i})"
            i += 1
        used.add(name)
        ws = wb.create_sheet(name)
        need: dict[int, float] = {}          # 每欄需要的字元寬（粗體數字會顯示 ###，所以照內容量）
        r = 1
        occupied: dict[tuple[int, int], bool] = {}
        for row in g.rows:
            if row.cls == "gap":
                ws.row_dimensions[r].height = 8
                r += 1
                continue
            col = 1
            for c in row.cells:
                while occupied.get((r, col)):
                    col += 1
                cell = ws.cell(row=r, column=col)
                v = c.v
                if _missing(v):
                    v = None
                elif c.kind in ("money", "money2", "int", "pct", "pct1", "pct2"):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        v = str(v)
                elif c.kind in ("date", "md") and isinstance(v, (date, datetime)):
                    v = v
                else:
                    v = str(v)
                cell.value = v
                if c.kind in NUMFMT and not isinstance(v, str):
                    cell.number_format = NUMFMT[c.kind]
                sz = g.font_size
                if "big" in c.cls:
                    sz = g.font_size * 1.7
                elif "mid" in c.cls:
                    sz = g.font_size * 1.25
                elif "small" in c.cls:
                    sz = g.font_size * 0.85
                cl = c.cls.split()
                color = "000000"
                for k, v in (("red", "C00000"), ("blue", "0000FF"), ("grey", "7F7F7F"), ("magenta", "FF00FF"), ("green", "00B050"),
                             ("teal", "00B0F0"), ("orange", "FF9900")):
                    if k in cl:
                        color = v
                if c.kind in ("money", "money2", "int") and _neg(c.v) and color == "000000":
                    color = "C00000"
                cell.font = Font(name="Microsoft JhengHei", size=sz, bold=("b" in c.cls.split()), color=color, underline="single" if c.ul else None)
                if "ctr" in c.cls:
                    hz = "center"
                elif "left" in c.cls:
                    hz = "left"
                elif "right" in c.cls:
                    hz = "right"
                elif c.kind in ("money", "money2", "int", "pct", "pct1", "pct2"):
                    hz = "right"
                elif c.kind in ("date", "md", "ym"):
                    hz = "center"
                else:
                    hz = "left"
                cell.alignment = Alignment(horizontal=hz, vertical="center", wrap_text=("wrap" in c.cls))
                if "noborder" not in c.cls and row.cls not in ("title",) and not c.ul:
                    cell.border = border
                if c.ul:
                    cell.border = Border(bottom=thin)
                if c.fill:
                    cell.fill = PatternFill("solid", fgColor=C.get(c.fill, c.fill))
                if c.span == 1 and "noborder" not in c.cls and row.cls != "title":
                    txt = fmt(c.v, c.kind)
                    w = sum(2 if ord(ch) > 0x2E7F else 1 for ch in txt) * (1.15 if "b" in c.cls.split() else 1.0) + 1.5
                    if "small" in c.cls:
                        w *= 0.85
                    need[col] = max(need.get(col, 0), w)
                if c.span > 1 or c.rowspan > 1:
                    ws.merge_cells(start_row=r, start_column=col, end_row=r + c.rowspan - 1, end_column=col + c.span - 1)
                    for rr in range(r, r + c.rowspan):
                        for cc in range(col, col + c.span):
                            occupied[(rr, cc)] = True
                            if "noborder" not in c.cls and row.cls != "title":
                                ws.cell(row=rr, column=cc).border = border
                col += c.span
            if row.height:
                ws.row_dimensions[r].height = row.height * 0.75
            r += 1
        for j, w in enumerate(g.widths, start=1):
            ws.column_dimensions[get_column_letter(j)].width = max(w, min(need.get(j, 0), 60))
        # 列印設定
        ws.page_setup.orientation = "landscape" if g.landscape else "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A3 if g.paper == "A3" else ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.page_margins.left = ws.page_margins.right = 0.4
        ws.page_margins.top, ws.page_margins.bottom = 0.5, 0.6
        if g.header_rows:
            ws.print_title_rows = f"1:{g.header_rows}"
            ws.freeze_panes = ws.cell(row=g.header_rows + 1, column=1)
        ws.oddFooter.left.text = footer_left or g.footer_left
        ws.oddFooter.center.text = footer_center or g.footer_center
        ws.oddFooter.right.text = "頁 &P 之 &N"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
