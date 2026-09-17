"""
doc.py — 報表文件模型（每一頁「印出來的樣子」的中間格式）

頁面在畫畫面的同時，把 KPI / 表格 / 圖 / 說明「記」進一個 Doc；
之後 html.py / pdf.py / xlsx.py 各自把同一個 Doc 渲染成列印版 HTML、PDF、Excel。
畫面怎麼排跟匯出怎麼排是兩件事：Doc 只描述內容與順序，版面由各 renderer 的 theme 決定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

import pandas as pd

Kind = Literal["text", "money", "int", "pct", "progress", "ym", "date"]


@dataclass
class Col:
    """一欄的顯示規格。kind 決定對齊、格式與 Excel number_format。"""
    key: str
    label: str
    kind: Kind = "text"
    max: float | None = None        # progress 的分母（None = 取該欄最大值）
    width: str | None = None        # HTML 欄寬提示：'narrow' / 'wide' / None
    help: str | None = None         # Excel 表頭註解 / HTML title


@dataclass
class Heading:
    text: str
    level: int = 2                  # 2 = 節、3 = 小節


@dataclass
class Text:
    text: str                       # 純文字，可用 \n 分段；**粗體** 支援
    style: Literal["note", "body", "callout"] = "body"


@dataclass
class Kpis:
    items: list[dict]               # {label, value, delta?, sub?, color?}；value 已是顯示字串
    per_row: int = 4
    title: str | None = None


@dataclass
class Table:
    title: str
    df: pd.DataFrame
    columns: list[Col]
    totals: dict | None = None      # {key: value}；None = 不印合計列
    note: str | None = None         # 表下方小字（口徑、單位）
    col_groups: list[tuple[str, int]] | None = None   # 兩層表頭：[("平台", 4), ("獲利", 3)]
    max_rows_pdf: int = 300         # PDF 最多列數（超過只印前 N 列並註明）
    wide: bool = False              # 欄位多：字級縮小一級
    row_class: Callable[[pd.Series], str | None] | None = None   # 例：公司戶 → "muted"
    sheet_name: str | None = None   # Excel 工作表名（None = title）
    freeze_cols: int = 1            # Excel 凍結前幾欄；PDF 拆欄時重複前幾欄
    max_cols_pdf: int = 14          # PDF 一張表最多幾欄，超過自動拆成「（續）」表，前 freeze_cols 欄重複
    screen_columns: list[Col] | None = None   # 畫面精簡欄（P1-4）；None = 與 columns 相同
    key: str | None = None          # 畫面上 st.dataframe 的 key（要支援點選下鑽時給）


@dataclass
class Chart:
    title: str
    fig: Any                        # plotly Figure
    height: int = 320
    width: Literal["full", "half"] = "full"
    caption: str | None = None
    excel: dict | None = None       # {"type": "bar"|"stacked"|"line", "df": DataFrame, "x": col, "series": [cols], "unit": "萬"}


@dataclass
class Row:
    """並排（最多 2 個）：兩張半寬圖或 一圖一小表。"""
    blocks: list[Any]


@dataclass
class PageBreak:
    pass


Block = Heading | Text | Kpis | Table | Chart | Row | PageBreak


@dataclass
class Doc:
    title: str
    subtitle: str | None = None         # 一句話：這頁回答什麼問題
    period_text: str = ""               # 2026/01–2026/08
    scope_text: str = ""                # 發稿口徑（老闆版）・不含轉撥
    filter_text: str = ""               # 公司=東吳　業務=陳絜心
    orientation: Literal["landscape", "portrait"] = "landscape"
    generated_by: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    as_of_note: str | None = None       # 「2026/09 進行中，未納入」
    blocks: list[Block] = field(default_factory=list)
    footer_note: str = "數字口徑見各表下方說明；金額單位：元（圖表軸：萬）。"
    xlsx_layout: Literal["sheets", "single"] = "sheets"   # single = 全部表寫同一張工作表（年度發稿明細）

    # ---- 記錄用的便利方法（頁面呼叫）----
    def add(self, block: Block) -> "Doc":
        self.blocks.append(block)
        return self

    def heading(self, text: str, level: int = 2) -> "Doc":
        return self.add(Heading(text, level))

    def text(self, text: str, style: str = "body") -> "Doc":
        return self.add(Text(text, style))  # type: ignore[arg-type]

    def kpis(self, items: list[dict], per_row: int = 4, title: str | None = None) -> "Doc":
        return self.add(Kpis(items, per_row, title))

    def table(self, title: str, df: pd.DataFrame, columns: list[Col], **kw) -> "Doc":
        return self.add(Table(title, df, columns, **kw))

    def chart(self, title: str, fig, **kw) -> "Doc":
        return self.add(Chart(title, fig, **kw))

    def row(self, *blocks) -> "Doc":
        return self.add(Row(list(blocks)))

    def page_break(self) -> "Doc":
        return self.add(PageBreak())

    def tables(self) -> list[Table]:
        out: list[Table] = []
        for b in self.blocks:
            if isinstance(b, Table):
                out.append(b)
            elif isinstance(b, Row):
                out.extend(x for x in b.blocks if isinstance(x, Table))
        return out

    def charts(self) -> list[Chart]:
        out: list[Chart] = []
        for b in self.blocks:
            if isinstance(b, Chart):
                out.append(b)
            elif isinstance(b, Row):
                out.extend(x for x in b.blocks if isinstance(x, Chart))
        return out


def cols(*specs) -> list[Col]:
    """簡寫：cols(("ext_net","除佣實收","money"), ("share","佔比","progress", {"max": 1}))"""
    out = []
    for s in specs:
        if isinstance(s, Col):
            out.append(s)
            continue
        key, label = s[0], s[1]
        kind = s[2] if len(s) > 2 else "text"
        opts = s[3] if len(s) > 3 else {}
        out.append(Col(key, label, kind, **opts))
    return out
