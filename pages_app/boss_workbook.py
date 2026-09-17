"""⭐ 常用分析 — 老闆工作簿（三公司發稿明細分析）精準重現（CLAUDE_CODE_TASK_6）。

一份原始資料 v_boss_line → compute/layout（reports/boss_workbook）→ 畫面(st.html)、Excel、PDF 三處同一份版面。
期間可選：去年整年（= 老闆工作簿口徑，預設）／今年至今／自訂。計算層與版面來自 kit，不在此重算。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

from core import analysis as A
from core.auth import require_role
from core.data import query_df
from core.format import ym_text
from core.ui import feedback_widget, page_header
from reports.boss_workbook import compute as C, html as H, layout as L, xlsx as BX

user = require_role("MEDIA", "FINANCE", "EXEC")   # SALES 不顯示（三公司全貌）
page_header("⭐ 常用分析", "老闆工作簿（三公司發稿明細分析）精準重現：期間可選，畫面／Excel／PDF 一模一樣。")


@st.cache_data(ttl=300, show_spinner="讀取中…")
def load_boss(ym_from: date, ym_to: date):
    raw = query_df('select * from v_boss_line where perf_ym between %s and %s order by perf_ym, "合約編號"',
                   (ym_from, ym_to))
    cnt = query_df(
        """select count(*) n, count(*) filter (where line_type='PRODUCTION') np,
                  coalesce(sum(cost_amount) filter (where line_type='PRODUCTION'),0) pc
           from v_line_ext where not is_intercompany and perf_ym between %s and %s""", (ym_from, ym_to))
    n = int(cnt.iloc[0]["n"]) if not cnt.empty else 0
    np_ = int(cnt.iloc[0]["np"]) if not cnt.empty else 0
    pc = float(cnt.iloc[0]["pc"]) if not cnt.empty else 0.0
    return raw, n, np_, pc


# ---- 期間 ----
ao = A.as_of()
last_year = date.today().year - 1
c_mode, c_x = st.columns([3, 4])
mode = c_mode.radio("期間", ["去年整年", "今年至今", "自訂"], horizontal=True, key="bw_mode",
                    help="去年整年＝老闆工作簿的口徑（預設）；今年至今＝今年 1 月到上月；自訂＝自己選起迄月。")
if mode == "去年整年":
    ym_from, ym_to = date(last_year, 1, 1), date(last_year, 12, 1)
    year_label = f"{last_year}年度"
elif mode == "今年至今":
    ym_from, ym_to = date(ao["as_of_year"], 1, 1), ao["as_of_ym"]
    year_label = f"{ym_text(ym_from)}–{ym_text(ym_to)}"
else:
    months = A.analysis_months()
    with c_x:
        cc1, cc2 = st.columns(2)
        ym_from = cc1.selectbox("起", months, index=min(len(months) - 1, 11), format_func=ym_text, key="bw_from")
        ym_to = cc2.selectbox("迄", months, index=0, format_func=ym_text, key="bw_to")
    if ym_from > ym_to:
        ym_from, ym_to = ym_to, ym_from
    year_label = f"{ym_text(ym_from)}–{ym_text(ym_to)}"

raw, n_all, n_prod, prod_cost = load_boss(ym_from, ym_to)
if raw.empty:
    st.info("此期間查無媒體上稿線。")
    feedback_widget("boss_workbook")
    st.stop()

praw, plats = L.prepare(raw)
notes_lines = C.notes(raw, n_all, n_prod, prod_cost, year_label)
n_media = len(raw)

st.caption(f"媒體上稿線 {n_media:,} 筆（不含製作費 {n_prod:,} 筆）・交換併回原業務・"
           f"客戶數含 0 元客戶・平台：{'／'.join(plats)}"
           + ("　⚠ 2024 公司別已合併、無意義，只看三公司合計" if ym_from.year <= 2024 and ym_to.year <= 2024 else ""))


# 工作表順序：說明與假設放最後（其餘＝工作簿順序）。匯出 Excel / PDF 同此順序。
_CSS = f"<style>{H.CSS}</style>"        # H.CSS 是純 CSS，st.html 要自己包 <style>，否則會漏出文字
SHEET_ORDER = ["平台總計總覽", "客戶數統計與客戶排名", "聲活_年度發稿明細", "東吳_年度發稿明細",
               "鉑霖_年度發稿明細", "原始資料_發稿分析", "說明與假設"]
PDF_ORDER = [s for s in SHEET_ORDER if s != "原始資料_發稿分析"]   # 逐筆原始資料太長不進整本 PDF
st.markdown(_CSS, unsafe_allow_html=True)   # 全站注入一次工作簿樣式；各分頁的表格片段吃這份 CSS


# ---- 匯出（整本）----
def _fname(ext: str) -> str:
    return f"常用分析_{year_label}.{ext}".replace("/", "-")


e1, e2, e3, _ = st.columns([1.2, 1, 1.4, 3])
with e1:
    st.download_button("📊 下載 Excel（整本）",
                       data=BX.build_bytes(raw, year_label=year_label, notes_lines=notes_lines, sheets=SHEET_ORDER),
                       file_name=_fname("xlsx"),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True, key="bw_xlsx")
with e2:
    try:
        from reports.export.pdf import available as _pdf_ok, html_to_pdf
    except Exception:  # noqa: BLE001
        _pdf_ok = lambda: False  # noqa: E731
    if st.button("📄 PDF（整本）", use_container_width=True, key="bw_pdf_btn", disabled=not _pdf_ok()):
        with st.spinner("排版中（約 5–15 秒）…"):
            html = H.page_html(PDF_ORDER, raw, year_label=year_label, notes_lines=notes_lines,
                               title=f"常用分析 {year_label}")
            pdf = html_to_pdf(html, orientation="landscape", title=f"常用分析 {year_label}")
        st.session_state["bw_pdf"] = pdf
    if st.session_state.get("bw_pdf"):
        st.download_button("⬇ 下載 PDF", data=st.session_state["bw_pdf"], file_name=_fname("pdf"),
                           mime="application/pdf", use_container_width=True, key="bw_pdf_dl")
with e3:
    st.download_button("🖨 列印版 HTML（整本）",
                       data=H.page_html(PDF_ORDER, raw, year_label=year_label, notes_lines=notes_lines,
                                        title=f"常用分析 {year_label}").encode("utf-8"),
                       file_name=_fname("html"), mime="text/html", use_container_width=True, key="bw_html")

st.divider()


def _print_one(name: str):
    """單張『只印這一張』：優先 PDF，沒有引擎給列印版 HTML。"""
    key = f"bw_one_{name}"
    try:
        from reports.export.pdf import available as _ok, html_to_pdf
    except Exception:  # noqa: BLE001
        _ok = lambda: False  # noqa: E731
    html = H.page_html([name], raw, year_label=year_label, notes_lines=notes_lines, title=f"{name} {year_label}")
    cc = st.columns([1, 1, 4])
    if _ok():
        if cc[0].button("📄 只印這一張", key=f"{key}_btn"):
            with st.spinner("排版中…"):
                from reports.export.pdf import html_to_pdf as _h2p
                st.session_state[key] = _h2p(html, orientation="landscape", title=name)
        if st.session_state.get(key):
            cc[1].download_button("⬇ 下載", data=st.session_state[key], file_name=f"常用分析_{name}_{year_label}.pdf".replace("/", "-"),
                                  mime="application/pdf", key=f"{key}_dl")
    cc[2 if _ok() else 0].download_button("🖨 只印這一張（列印版 HTML）", data=html.encode("utf-8"),
                                          file_name=f"常用分析_{name}_{year_label}.html".replace("/", "-"),
                                          mime="text/html", key=f"{key}_html")


# ---- 七個分頁（說明與假設放最後；CSS 已由上方 st.markdown 全站注入，這裡只放表格片段）----
tabs = st.tabs(["平台總計總覽", "客戶數統計與客戶排名", "聲活_年度發稿明細",
                "東吳_年度發稿明細", "鉑霖_年度發稿明細", "原始資料", "說明與假設"])

with tabs[0]:
    st.html(H.sheet_html("平台總計總覽", praw, plats, year_label=year_label, notes_lines=notes_lines))
    _print_one("平台總計總覽")
with tabs[1]:
    st.html(H.sheet_html("客戶數統計與客戶排名", praw, plats, year_label=year_label, notes_lines=notes_lines))
    _print_one("客戶數統計與客戶排名")
for _i, _co in enumerate(("聲活", "東吳", "鉑霖")):
    name = f"{_co}_年度發稿明細"
    with tabs[2 + _i]:
        st.html(H.sheet_html(name, praw, plats, year_label=year_label, notes_lines=notes_lines, sections=(1, 2)))
        n_lines = int((raw["公司別"] == _co).sum())
        with st.expander(f"逐筆明細（{n_lines} 筆）"):
            st.html(H.sheet_html(name, praw, plats, year_label=year_label, notes_lines=notes_lines, sections=(3,)))
        _print_one(name)
with tabs[5]:
    cols = [c for c in L.RAW_COLS if c in raw.columns]
    st.dataframe(raw[cols], hide_index=True, use_container_width=True, height=560)
    st.download_button("⬇ 下載 CSV（原始資料）", data=raw[cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=_fname("csv"), mime="text/csv", key="bw_csv")
with tabs[6]:
    st.html(H.sheet_html("說明與假設", praw, plats, year_label=year_label, notes_lines=notes_lines))
    _print_one("說明與假設")

feedback_widget("boss_workbook")
