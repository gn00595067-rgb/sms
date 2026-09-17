"""
html.py — Doc → 列印版 HTML

- 同一份 HTML 兩用：瀏覽器開啟（工具列有「列印 / 存成 PDF」）與 pdf.py 用 Chromium 轉 PDF。
- 圖表：plotly 直接在頁面裡畫（向量，跟畫面一模一樣），不用 kaleido。
- 表格：thead 會在每頁重複、列不跨頁切、合計列粗體、負數紅字、佔比畫長條。
"""
from __future__ import annotations

import copy
import html as _h
import math
from datetime import date, datetime

import pandas as pd

from .doc import Chart, Col, Doc, Heading, Kpis, PageBreak, Row, Table, Text
from .theme import COMPANY, FONT_STACK, PAGE, print_css

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


# ------------------------------------------------------------------ 格式
def _missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    try:
        return bool(pd.isna(v)) if not isinstance(v, (list, tuple, dict, str)) else False
    except (TypeError, ValueError):
        return False


def fmt(v, kind: str) -> str:
    if _missing(v):
        return ""
    if kind in ("money", "int"):
        try:
            return f"{float(v):,.0f}"
        except (TypeError, ValueError):
            return _h.escape(str(v))
    if kind in ("pct", "progress"):
        try:
            return f"{float(v) * 100:.1f}%"
        except (TypeError, ValueError):
            return _h.escape(str(v))
    if kind == "ym":
        if isinstance(v, (date, datetime)):
            return f"{v.year}/{v.month:02d}"
        return _h.escape(str(v))
    if kind == "date":
        if isinstance(v, (date, datetime)):
            return f"{v.year}/{v.month:02d}/{v.day:02d}"
        return _h.escape(str(v))
    return _h.escape(str(v))


def _neg(v) -> bool:
    try:
        return float(v) < 0
    except (TypeError, ValueError):
        return False


def _md(text: str) -> str:
    """極簡 markdown：**粗體**、換行。"""
    out = _h.escape(text)
    while "**" in out:
        out = out.replace("**", "<b>", 1).replace("**", "</b>", 1)
    return out.replace("\n", "<br>")


# ------------------------------------------------------------------ 區塊
def _kpis(b: Kpis) -> str:
    cards = []
    for it in b.items:
        delta = it.get("delta")
        d = ""
        if delta is not None and not _missing(delta):
            if isinstance(delta, str):
                d = f'<div class="d flat">{_h.escape(delta)}</div>'
            else:
                cls = "up" if delta > 0.0005 else ("down" if delta < -0.0005 else "flat")
                arrow = "▲" if cls == "up" else ("▼" if cls == "down" else "＝")
                d = f'<div class="d {cls}">{arrow} {abs(delta) * 100:.1f}% 同期</div>'
        sub = f'<div class="s">{_md(it["sub"])}</div>' if it.get("sub") else ""
        color = it.get("color") or COMPANY.get(str(it.get("label", "")).split(" ")[0])
        style = f' style="--co:{color}"' if color else ""
        cls = "kpi co" if color else "kpi"
        cards.append(f'<div class="{cls}"{style}><div class="l">{_h.escape(str(it["label"]))}</div>'
                     f'<div class="v">{_h.escape(str(it["value"]))}</div>{d}{sub}</div>')
    title = f"<h3>{_h.escape(b.title)}</h3>" if b.title else ""
    n = max(1, min(b.per_row, len(b.items) or 1))
    return f'{title}<div class="block kpis" style="grid-template-columns: repeat({n}, 1fr)">{"".join(cards)}</div>'


def _table(b: Table, *, in_row: bool = False) -> str:
    df = b.df if b.df is not None else pd.DataFrame()
    cols = [c for c in b.columns if c.key in df.columns] if not df.empty else list(b.columns)
    # 欄位太多 → 拆成幾張，前 freeze_cols 欄每張都重複（老闆版 19 欄的排名表不會被裁掉）
    if len(cols) > b.max_cols_pdf and not in_row:
        keep, rest = cols[:b.freeze_cols], cols[b.freeze_cols:]
        per = max(1, b.max_cols_pdf - len(keep))
        parts = []
        for i in range(0, len(rest), per):
            sub = Table(title=b.title if i == 0 else f"{b.title}（續 {i // per + 1}）", df=df, columns=keep + rest[i:i + per],
                        totals=b.totals, note=b.note if i + per >= len(rest) else None, wide=b.wide,
                        row_class=b.row_class, max_rows_pdf=b.max_rows_pdf, max_cols_pdf=10 ** 6, freeze_cols=b.freeze_cols)
            parts.append(_table(sub))
        return "".join(parts)
    # 兩層表頭
    grp = ""
    if b.col_groups:
        cells = []
        for label, n in b.col_groups:
            cells.append(f'<th class="grp" colspan="{n}">{_h.escape(label)}</th>' if label else f'<th colspan="{n}"></th>')
        grp = "<tr>" + "".join(cells) + "</tr>"
    head = "".join(
        f'<th class="{"txt" if c.kind in ("text", "ym", "date") else ""}"{f" title={_h.escape(c.help)!r}" if c.help else ""}>{_h.escape(c.label)}</th>'
        for c in cols)
    # progress 分母
    pmax = {}
    for c in cols:
        if c.kind == "progress":
            if c.max and c.max > 0:
                pmax[c.key] = float(c.max)
            else:
                s = pd.to_numeric(df[c.key], errors="coerce") if not df.empty else pd.Series(dtype=float)
                pmax[c.key] = float(s.max()) if len(s) and float(s.max() or 0) > 0 else 1.0
    body = []
    n_all = len(df)
    view = df.head(b.max_rows_pdf) if n_all > b.max_rows_pdf else df
    for i, (_, r) in enumerate(view.iterrows()):
        tds = []
        for c in cols:
            v = r[c.key]
            if c.kind == "progress":
                try:
                    ratio = max(0.0, min(1.0, float(v) / pmax[c.key])) if not _missing(v) else 0.0
                except (TypeError, ValueError, ZeroDivisionError):
                    ratio = 0.0
                tds.append(f'<td><span class="bar" style="width:{int(ratio * 56)}px"></span>{fmt(v, "pct")}</td>')
            elif c.kind in ("money", "int", "pct"):
                tds.append(f'<td class="{"neg" if _neg(v) else ""}">{fmt(v, c.kind)}</td>')
            else:
                tds.append(f'<td class="txt">{fmt(v, c.kind)}</td>')
        rc = b.row_class(r) if b.row_class else None
        cls_ = " ".join(x for x in (rc, "z" if i % 2 else None) if x)
        body.append((f'<tr class="{cls_}">' if cls_ else "<tr>") + "".join(tds) + "</tr>")
    total = ""
    if b.totals:
        tds = []
        has_label = any(c.kind == "text" and b.totals.get(c.key) is not None for c in cols)
        for i, c in enumerate(cols):
            v = b.totals.get(c.key)
            if i == 0 and (v is None or c.kind == "text"):
                tds.append(f'<td class="txt">{fmt(v, "text") if v is not None else ("" if has_label else "合計")}</td>')
            elif v is None:
                tds.append("<td></td>")
            elif c.kind == "progress":
                tds.append(f"<td>{fmt(v, 'pct')}</td>")
            else:
                tds.append(f'<td class="{"neg" if _neg(v) else ""}{" txt" if c.kind == "text" else ""}">{fmt(v, c.kind)}</td>')
        total = '<tr class="total">' + "".join(tds) + "</tr>"
    trunc = f'<div class="trunc">共 {n_all:,} 列，此處列出前 {b.max_rows_pdf} 列；完整資料請用 Excel。</div>' if n_all > b.max_rows_pdf else ""
    note = f'<div class="tnote">{_md(b.note)}</div>' if b.note else ""
    title = f"<h3>{_h.escape(b.title)}</h3>" if b.title else ""
    cls = "t wide" if b.wide else "t"
    wrap = "" if in_row else ' class="tblock"'
    # 最後 2 列 + 合計列放同一個 tbody 且不可切頁 → 合計列不會單獨掉到下一頁
    keep = 2 if total else 0
    main, tail = body[:len(body) - keep], body[len(body) - keep:]
    tbodies = f"<tbody>{''.join(main)}</tbody>" + (f'<tbody class="keep">{"".join(tail)}{total}</tbody>' if (tail or total) else "")
    return (f'<div{wrap}>{title}<table class="{cls}"><thead>{grp}<tr>{head}</tr></thead>'
            f"{tbodies}</table>{trunc}{note}</div>")


def _chart(b: Chart, orientation: str, *, in_row: bool = False) -> str:
    w = PAGE[orientation]["content_px"]
    px = (w - 18) if (b.width == "full" and not in_row) else int((w - 16) / 2) - 18
    fig = copy.deepcopy(b.fig)
    fig.update_layout(width=px, height=b.height, autosize=False, paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family=FONT_STACK, size=11, color="#1d2733"),
                      margin=dict(l=48, r=16, t=28 if fig.layout.title and fig.layout.title.text else 12, b=36))
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"staticPlot": True, "displayModeBar": False},
                        div_id=None, default_width=f"{px}px", default_height=f"{b.height}px")
    cap = f'<div class="cap">{_md(b.caption)}</div>' if b.caption else ""
    cls = "chart half" if (b.width == "half" or in_row) else "chart full"
    wrap = "" if in_row else ' class="block"'
    return f'<div{wrap}><div class="{cls}"><div class="ct">{_h.escape(b.title)}</div>{cap}<div class="plot">{inner}</div></div></div>'


def _text(b: Text) -> str:
    return f'<p class="{b.style}">{_md(b.text)}</p>'


def render_block(b, orientation: str, *, in_row: bool = False) -> str:
    if isinstance(b, Heading):
        return f"<h{b.level}>{_h.escape(b.text)}</h{b.level}>"
    if isinstance(b, Text):
        return _text(b)
    if isinstance(b, Kpis):
        return _kpis(b)
    if isinstance(b, Table):
        return _table(b, in_row=in_row)
    if isinstance(b, Chart):
        return _chart(b, orientation, in_row=in_row)
    if isinstance(b, Row):
        return '<div class="row2">' + "".join(render_block(x, orientation, in_row=True) for x in b.blocks) + "</div>"
    if isinstance(b, PageBreak):
        return '<div class="pb"></div>'
    return ""


# ------------------------------------------------------------------ 整頁
def _cover(doc: Doc) -> str:
    meta = []
    if doc.period_text:
        meta.append(f"<span>期間 <b>{_h.escape(doc.period_text)}</b></span>")
    if doc.scope_text:
        meta.append(f"<span>口徑 <b>{_h.escape(doc.scope_text)}</b></span>")
    if doc.filter_text:
        meta.append(f"<span>篩選 <b>{_h.escape(doc.filter_text)}</b></span>")
    who = f"{doc.generated_by}・" if doc.generated_by else ""
    meta.append(f"<span>產出 <b>{who}{doc.generated_at:%Y/%m/%d %H:%M}</b></span>")
    if doc.as_of_note:
        meta.append(f'<span class="asof">{_h.escape(doc.as_of_note)}</span>')
    sub = f'<p class="sub">{_h.escape(doc.subtitle)}</p>' if doc.subtitle else ""
    return f'<div class="cover"><h1>{_h.escape(doc.title)}</h1>{sub}<div class="meta">{"".join(meta)}</div></div>'


def _body(doc: Doc) -> str:
    return "".join(render_block(b, doc.orientation) for b in doc.blocks) + \
        f'<div class="foot">{_h.escape(doc.footer_note or "")}</div>'


def _js(docs: list[Doc], plotly_js: str) -> str:
    if not any(d.charts() for d in docs):
        return ""
    if plotly_js == "cdn":
        return f'<script src="{PLOTLY_CDN}"></script>'
    if plotly_js == "inline":
        from plotly.offline import get_plotlyjs
        return f"<script>{get_plotlyjs()}</script>"
    return ""


_TOOLBAR = ('<div class="toolbar noprint"><button onclick="window.print()">🖨 列印 / 存成 PDF</button>'
            '<span>列印對話框請取消「頁首及頁尾」、勾選「背景圖形」。</span></div>')


def to_html(doc: Doc, *, plotly_js: str = "cdn", toolbar: bool = True) -> str:
    """plotly_js: 'cdn'（給人開的 HTML，檔案小）/ 'inline'（給 Chromium 轉 PDF，不需網路）/ 'none'。"""
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>{_h.escape(doc.title)}</title>{_js([doc], plotly_js)}<style>{print_css(doc.orientation)}</style></head>
<body>{_TOOLBAR if toolbar else ""}<div class="page">{_cover(doc)}{_body(doc)}</div></body></html>"""


def to_html_multi(docs: list[Doc], pack_title: str, *, plotly_js: str = "cdn", toolbar: bool = True) -> str:
    """多份 Doc 合成一份（月報包）：每份從新的一頁開始、各有自己的封面列；方向以第一份為準。"""
    if not docs:
        return to_html(Doc(pack_title), plotly_js=plotly_js, toolbar=toolbar)
    orientation = docs[0].orientation
    parts = []
    for i, d in enumerate(docs):
        parts.append(f'<div class="page{" pb" if i else ""}">{_cover(d)}{_body(d)}</div>')
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>{_h.escape(pack_title)}</title>{_js(docs, plotly_js)}<style>{print_css(orientation)}</style></head>
<body>{_TOOLBAR if toolbar else ""}{"".join(parts)}</body></html>"""
