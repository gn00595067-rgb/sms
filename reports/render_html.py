"""
render_html.py — DataFrame → 列印用 HTML（A4 樣式 + 列印按鈕）

回傳完整 HTML 字串，可丟給 st.components.v1.html 顯示。
"""
from __future__ import annotations

import html
from datetime import datetime

import pandas as pd

from core.format import (DATE_COLS, INT_COLS, MONEY_COLS, PERCENT_NUM_COLS,
                         RATIO_PCT_COLS, YM_COLS, date_text, label, money, pct, ym_text)

_CSS = """
<style>
  @page { size: A4 landscape; margin: 12mm; }
  * { font-family: "微軟正黑體","Microsoft JhengHei",sans-serif; }
  body { color:#222; margin:0; }
  .toolbar { margin:8px 0; }
  .toolbar button { padding:6px 16px; font-size:14px; cursor:pointer;
    background:#1f5f8b; color:#fff; border:none; border-radius:4px; }
  h1 { font-size:18px; margin:4px 0; }
  .sub { color:#666; font-size:11px; margin-bottom:8px; }
  table { border-collapse:collapse; width:100%; font-size:12px; }
  th { background:#1f5f8b; color:#fff; padding:5px 8px; text-align:center; border:1px solid #14486a; }
  td { padding:4px 8px; border:1px solid #ddd; }
  td.num { text-align:right; }
  td.neg { color:#c00000; }
  tr:nth-child(even) td { background:#f5f8fb; }
  tr.total td { font-weight:bold; border-top:2px solid #333; background:#eef3f8; }
  @media print { .toolbar { display:none; } }
</style>
"""


def _cell(col: str, v) -> tuple[str, str]:
    """回傳 (顯示文字, td class)。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "", ""
    if col in YM_COLS:
        return html.escape(ym_text(v)), ""
    if col in DATE_COLS:
        return html.escape(date_text(v)), ""
    if col in MONEY_COLS:
        cls = "num neg" if _is_neg(v) else "num"
        return html.escape(money(v)), cls
    if col in INT_COLS:
        try:
            return f"{int(v):,}", "num"
        except (ValueError, TypeError):
            return html.escape(str(v)), "num"
    if col in RATIO_PCT_COLS:
        return html.escape(pct(v, already_ratio=True)), "num"
    if col in PERCENT_NUM_COLS:
        return html.escape(pct(v, already_ratio=False)), "num"
    return html.escape(str(v)), ""


def _is_neg(v) -> bool:
    try:
        return float(v) < 0
    except (ValueError, TypeError):
        return False


def build_html(df: pd.DataFrame, title: str, filter_text: str = "",
               columns: list[str] | None = None, totals: dict | None = None) -> str:
    if df is None:
        df = pd.DataFrame()
    cols = [c for c in (columns or list(df.columns)) if c in df.columns] if not df.empty else (columns or [])
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    head = "".join(f"<th>{html.escape(label(c))}</th>" for c in cols)
    body_rows = []
    for _, row in (df.iterrows() if not df.empty else []):
        tds = []
        for c in cols:
            text, cls = _cell(c, row[c])
            tds.append(f'<td class="{cls}">{text}</td>' if cls else f"<td>{text}</td>")
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    total_row = ""
    if totals:
        tds, first = [], True
        for c in cols:
            if first:
                tds.append(f"<td>合計</td>")
                first = False
                if c in totals:  # 第一欄剛好是合計欄
                    text, cls = _cell(c, totals[c])
                    tds[-1] = f'<td class="{cls}">合計 {text}</td>'
                continue
            if c in totals:
                text, cls = _cell(c, totals[c])
                tds.append(f'<td class="{cls}">{text}</td>')
            else:
                tds.append("<td></td>")
        total_row = '<tr class="total">' + "".join(tds) + "</tr>"

    sub = (html.escape(filter_text) + "　" if filter_text else "") + f"產出時間：{stamp}"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">{_CSS}</head>
<body>
  <div class="toolbar"><button onclick="window.print()">🖨 列印 / 存成 PDF</button></div>
  <h1>{html.escape(title)}</h1>
  <div class="sub">{sub}</div>
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{''.join(body_rows)}{total_row}</tbody>
  </table>
</body></html>"""
