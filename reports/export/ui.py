"""
ui.py — Streamlit 端：一邊畫畫面、一邊把同樣的內容記進 Doc；頁尾（或頁首）放匯出列。

每個分析頁只要把
    st.plotly_chart(fig)            → X.ui.chart(doc, "標題", fig, excel=...)
    A.kpi_row(items)                → X.ui.kpis(doc, items)
    A.show_ranking(df, columns, …)  → X.ui.table(doc, "標題", df, columns, totals=…, …)
    st.markdown("**節名**")         → X.ui.section(doc, "節名")
換掉，畫面完全不變，PDF / Excel 就自動有同樣的內容。
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
import streamlit as st

from .doc import Chart, Col, Doc, Table, cols as _cols
from .html import to_html
from .pdf import available as pdf_available, to_pdf
from .xlsx import to_xlsx

_SAFE = re.compile(r"[^\w一-鿿－-]+")


def new_doc(title: str, *, subtitle: str | None = None, f: dict | None = None, user: dict | None = None,
            orientation: str = "landscape", scope_text: str = "", as_of_note: str | None = None) -> Doc:
    """頁首建立 Doc；f = filter_bar_analysis 回傳的 dict（期間 / 篩選文字自動帶入）。"""
    from core.analysis import filter_text          # 專案內的既有函式
    from core.format import ym_text
    period = f"{ym_text(f['ym_from'])}–{ym_text(f['ym_to'])}" if f else ""
    ftxt = ""
    if f:
        ftxt = filter_text(f)
        ftxt = ftxt.replace(period, "").strip("　 ")
    return Doc(title=title, subtitle=subtitle, period_text=period, scope_text=scope_text or _scope_text(f),
               filter_text=ftxt, orientation=orientation,   # type: ignore[arg-type]
               generated_by=(user or {}).get("display_name") or (user or {}).get("username") or "",
               generated_at=datetime.now(), as_of_note=as_of_note)


def _scope_text(f: dict | None) -> str:
    if not f:
        return ""
    s = f.get("scope")
    if s in (None, "analysis"):
        base = "分析口徑（對外收入全部"
        base += "、不含交換）" if f.get("exclude_barter", True) else "、含交換）"
        return base
    if s == "media":
        return "發稿口徑（老闆版：媒體上稿線、含交換併回業務、不含轉撥）"
    return "自訂口徑"


# ---- 記錄 + 顯示 ----
def section(doc: Doc, text: str, level: int = 2) -> None:
    st.markdown(f"**{text}**" if level >= 3 else f"#### {text}")
    doc.heading(text, level)


def note(doc: Doc, text: str, *, show: bool = True) -> None:
    if show:
        st.caption(text)
    doc.text(text, "note")


def kpis(doc: Doc, items: list[dict], *, per_row: int | None = None, title: str | None = None) -> None:
    from core.analysis import kpi_row
    if title:
        st.markdown(f"**{title}**")
    kpi_row(items)
    doc.kpis(items, per_row or min(len(items), 4) or 1, title)


def chart(doc: Doc, title: str, fig, *, height: int | None = None, caption: str | None = None,
          excel: dict | None = None, width: str = "full", show_title: bool = True, key: str | None = None) -> None:
    if show_title:
        st.markdown(f"**{title}**")
    st.plotly_chart(fig, use_container_width=True, key=key)
    if caption:
        st.caption(caption)
    doc.chart(title, fig, height=height or int(fig.layout.height or 320), caption=caption, excel=excel, width=width)  # type: ignore[arg-type]


def table(doc: Doc, title: str, df: pd.DataFrame, columns: list, *, totals: dict | None = None,
          note: str | None = None, col_groups=None, wide: bool = False, row_class=None,
          show_title: bool = True, height: int | None = 460, key: str | None = None, on_select=None,
          selection_mode="single-row", max_rows_pdf: int = 300, sheet_name: str | None = None,
          screen_columns: list | None = None):
    """
    columns：與 show_ranking 相同的 (col, header, kind[, opts]) 或 Col 物件。
    screen_columns：畫面用精簡欄（P1-4），匯出仍用 columns 全部欄位。
    """
    from core.analysis import show_ranking
    if show_title:
        st.markdown(f"**{title}**")
    ret = show_ranking(df, screen_columns or columns, height=height, key=key,
                       on_select=on_select, selection_mode=selection_mode)
    spec = _cols(*[c for c in columns if not (isinstance(c, tuple) and c[2] in ("bar", "line"))])
    doc.table(title, df, spec, totals=totals, note=note, col_groups=col_groups, wide=wide,
              row_class=row_class, max_rows_pdf=max_rows_pdf, sheet_name=sheet_name)
    return ret


# ---- Doc 優先：先把頁面組成 Doc，再交給 render() 畫畫面（分析頁採用這條路，月報包腳本才能重用）----
def render(doc: Doc, *, key: str) -> dict:
    """依 Doc 的區塊順序畫 Streamlit 畫面；回傳 {table.key: st.dataframe 回傳值}（給下鑽用）。"""
    from core.analysis import kpi_row, show_ranking
    out: dict = {}

    def _one(b, slot=None, idx: int = 0):
        from .doc import Chart, Heading, Kpis, PageBreak, Row, Table, Text
        ctx = slot if slot is not None else st.container()
        with ctx:
            if isinstance(b, Heading):
                st.markdown(f"#### {b.text}" if b.level <= 2 else f"**{b.text}**")
            elif isinstance(b, Text):
                (st.info if b.style == "callout" else st.caption)(b.text) if b.style != "body" else st.markdown(b.text)
            elif isinstance(b, Kpis):
                if b.title:
                    st.markdown(f"**{b.title}**")
                kpi_row(b.items)
            elif isinstance(b, Chart):
                st.markdown(f"**{b.title}**")
                st.plotly_chart(b.fig, use_container_width=True, key=f"{key}_c{idx}")
                if b.caption:
                    st.caption(b.caption)
            elif isinstance(b, Table):
                st.markdown(f"**{b.title}**")
                spec = [(c.key, c.label, c.kind, {"max": c.max}) if c.kind == "progress" else (c.key, c.label, c.kind)
                        for c in (b.screen_columns or b.columns)]
                out[b.key or f"{key}_t{idx}"] = show_ranking(b.df, spec, key=b.key or f"{key}_t{idx}",
                                                             height=None if len(b.df) <= 12 else 460)
                if b.note:
                    st.caption(b.note)
            elif isinstance(b, Row):
                cols_ = st.columns(len(b.blocks))
                for j, (c, x) in enumerate(zip(cols_, b.blocks)):
                    _one(x, c, idx * 10 + j)
            elif isinstance(b, PageBreak):
                st.divider()

    for i, b in enumerate(doc.blocks):
        _one(b, None, i)
    return out


# ---- 匯出列 ----
def export_bar(doc: Doc, *, key: str, location: str = "bottom") -> None:
    """三個按鈕：📄 PDF（Chromium 產生）、📊 Excel、🖨 列印版 HTML（沒有瀏覽器引擎時的備援）。"""
    fname = _SAFE.sub("_", f"{doc.title}_{doc.period_text}").strip("_")
    if location == "top":
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    with c1:
        if st.button("📄 產生 PDF", key=f"{key}_pdf_btn", use_container_width=True):
            with st.spinner("排版中（約 3–8 秒）…"):
                pdf = to_pdf(doc)
            if pdf:
                st.session_state[f"{key}_pdf"] = pdf
            else:
                st.session_state.pop(f"{key}_pdf", None)
                st.warning("這台主機沒有可用的瀏覽器引擎，請用「列印版 HTML」開啟後按 Ctrl+P 存成 PDF。")
        if st.session_state.get(f"{key}_pdf"):
            st.download_button("⬇ 下載 PDF", data=st.session_state[f"{key}_pdf"], file_name=f"{fname}.pdf",
                               mime="application/pdf", key=f"{key}_pdf_dl", use_container_width=True)
    with c2:
        st.download_button("📊 下載 Excel", data=_xlsx_cached(doc, key), file_name=f"{fname}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=f"{key}_xlsx_dl", use_container_width=True)
    with c3:
        st.download_button("🖨 列印版 HTML", data=to_html(doc, plotly_js="cdn").encode("utf-8"),
                           file_name=f"{fname}.html", mime="text/html", key=f"{key}_html_dl",
                           use_container_width=True)
    with c4:
        n_t, n_c = len(doc.tables()), len(doc.charts())
        st.caption(f"列印版內容：{n_t} 張表、{n_c} 張圖・{'PDF 由伺服器排版' if pdf_available() else '此環境無 PDF 引擎，請用列印版 HTML'}")


def _xlsx_cached(doc: Doc, key: str) -> bytes:
    """Excel 產生很快（<1 秒），直接算；避免重複算用 session_state 以內容指紋快取。"""
    sig = (doc.title, doc.period_text, doc.scope_text, doc.filter_text,
           tuple((t.title, len(t.df)) for t in doc.tables()))
    cache = st.session_state.setdefault("_xlsx_cache", {})
    if cache.get(key, (None, None))[0] != sig:
        cache[key] = (sig, to_xlsx(doc))
    return cache[key][1]
