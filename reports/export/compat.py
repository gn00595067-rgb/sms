"""
reports.export.compat — 記錄式頁面（報表中心 / 業績查詢 / 獎金 / 應收）的橋接

把「一份 DataFrame + 欄位鍵清單」轉成匯出層的 Doc / Col：
  欄位中文名取 core.format.label；欄位型別（money/int/pct/ym/date/text）由 core.format
  的 MONEY_COLS / RATIO_PCT_COLS / … 集合對照——與舊 render_excel / render_html 同一套規則，
  因此報表中心的每張報表換到匯出層後欄位格式不變。

取代舊的 reports/render_excel.py 與 reports/render_html.py。
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.format import (DATE_COLS, INT_COLS, MONEY_COLS, PERCENT_NUM_COLS,
                         RATIO_PCT_COLS, YM_COLS, label)

from .doc import Col, Doc


def kind_of(key: str) -> str:
    """欄位鍵 → Doc 欄位型別。與 render_excel 的判斷同源。"""
    if key in YM_COLS:
        return "ym"
    if key in DATE_COLS:
        return "date"
    if key in MONEY_COLS:
        return "money"
    if key in RATIO_PCT_COLS or key in PERCENT_NUM_COLS:
        return "pct"
    if key in INT_COLS:
        return "int"
    return "text"


def cols_from_keys(keys, *, helps: dict | None = None) -> list[Col]:
    """欄位鍵清單 → Col 清單（中文表頭 + 型別 + 可選 help 說明）。"""
    helps = helps or {}
    return [Col(k, label(k), kind_of(k), help=helps.get(k)) for k in keys]


def cols_from_registry(r: dict, df: pd.DataFrame | None = None, *, helps: dict | None = None) -> list[Col]:
    """registry 報表定義 → Col 清單。優先用 r['columns']，否則用 df 欄位。"""
    keys = r.get("columns") or (list(df.columns) if df is not None else [])
    return cols_from_keys(keys, helps=helps)


def _normalize_pct(df: pd.DataFrame, keys) -> pd.DataFrame:
    """PERCENT_NUM_COLS 的值是「10」代表 10%；Doc 的 pct 會 ×100，故先 ÷100 對齊 ratio。"""
    pcols = [k for k in keys if k in PERCENT_NUM_COLS and df is not None and k in df.columns]
    if not pcols:
        return df
    out = df.copy()
    for k in pcols:
        out[k] = pd.to_numeric(out[k], errors="coerce") / 100.0
    return out


def record_doc(title: str, *, subtitle: str | None = None, period_text: str = "", filter_text: str = "",
               user: dict | None = None, orientation: str = "landscape", as_of_note: str | None = None,
               footer_note: str | None = None) -> Doc:
    """記錄式頁面用的 Doc 表頭（沒有分析頁的 f dict，篩選文字直接給）。"""
    doc = Doc(title=title, subtitle=subtitle, period_text=period_text, filter_text=filter_text,
              orientation=orientation,  # type: ignore[arg-type]
              generated_by=(user or {}).get("display_name") or (user or {}).get("username") or "",
              generated_at=datetime.now(), as_of_note=as_of_note)
    if footer_note:
        doc.footer_note = footer_note
    return doc


def add_table(doc: Doc, title: str, df: pd.DataFrame, *, columns=None, totals: dict | None = None,
              note: str | None = None, helps: dict | None = None, **kw) -> Doc:
    """把一份 df（記錄式）加進 doc：自動抓欄位型別、對齊 PERCENT_NUM_COLS、帶 totals。"""
    df = df if df is not None else pd.DataFrame()
    keys = [c for c in (columns or list(df.columns)) if df.empty or c in df.columns]
    ndf = _normalize_pct(df, keys)
    ntot = totals
    if totals:
        ntot = dict(totals)
        for k in keys:
            if k in PERCENT_NUM_COLS and ntot.get(k) is not None:
                try:
                    ntot[k] = float(ntot[k]) / 100.0
                except (TypeError, ValueError):
                    pass
    doc.table(title, ndf, cols_from_keys(keys, helps=helps), totals=ntot, note=note, **kw)
    return doc
