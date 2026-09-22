"""📑 財務報表專區 — 舊 Access 業績系統財務還在用的六個功能，版型、數字 100% 重現（CLAUDE_CODE_TASK_7）

    業績成本報表(區間) ／ 媒體發稿量分析 ／ 成本毛利分析（綜合分析・客戶同期比較表・業績認定表・月獎金計算總表・業務發稿統計 A3）／
    業績達成表（月責任檔業績達成表）／ 三單查詢（廣告時段採購申請單・發票開立申請單）／ 電台預付查詢（電台預付明細表＋標記已付）

一份資料 v_finance_line → reports/finance/compute（算）→ layout（排）→ grid（畫面 st.html／Excel／PDF 三處同一份版面）。
篩選列照舊 Access 表單（含「排除」型篩選）；只有 FINANCE / EXEC 看得到（app.py PAGES）。
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.data import query_df
from core.format import ym_text
from core.ui import feedback_widget, page_header
from db import transaction   # scripts/db.py（core/ui.py 同樣寫法）
from reports.finance import compute as C, grid as G, layout as L

user = require_role("FINANCE", "EXEC")
page_header("📑 財務報表專區", "舊 Access 系統財務六個功能的原版報表：篩選 → 預覽 → PDF／Excel／列印版 HTML。數字、版型與舊系統一致（差異見各表「說明」）。")
st.markdown(f"<style>{G.CSS}</style>", unsafe_allow_html=True)      # 全頁注入一次報表樣式；各 st.html 片段共用


# ------------------------------------------------------------------ 資料
@st.cache_data(ttl=300, show_spinner="讀取中…")
def load_lines(ym_from: date, ym_to: date) -> pd.DataFrame:
    return C.prepare(query_df("select * from v_finance_line where perf_ym between %s and %s order by perf_ym, contract_no, line_no",
                              (ym_from, ym_to)))


@st.cache_data(ttl=300)
def option_lists(ym_from: date, ym_to: date) -> dict:
    df = load_lines(ym_from, ym_to)
    return {c: sorted([x for x in df[c].unique() if x], key=C.zh_key) for c in
            ("business_group", "salesperson", "customer", "customer_category", "sales_category", "platform", "media_channel",
             "industry", "contract_term", "company")}


def _pdf_ok() -> bool:
    try:
        from reports.export.pdf import available
        return available()
    except Exception:  # noqa: BLE001
        return False


def _period_bar(key: str) -> tuple[date, date, str, str]:
    months = A.analysis_months()
    c1, c2 = st.columns(2)
    ym_from = c1.selectbox("統計年月 起", months, index=0, format_func=ym_text, key=f"{key}_from")
    ym_to = c2.selectbox("統計年月 迄", months, index=0, format_func=ym_text, key=f"{key}_to")
    if ym_from > ym_to:
        ym_from, ym_to = ym_to, ym_from
    return ym_from, ym_to, ym_text(ym_from), ym_text(ym_to)


def _filters(key: str, opts: dict, fields: list[str]) -> C.Filters:
    """舊表單的篩選列；fields 決定顯示哪些（每張報表不同）。多選空白 = 全部（舊表單的 *）。"""
    f = C.Filters()
    cols = st.columns(4)
    i = 0

    def nxt():
        nonlocal i
        c = cols[i % 4]
        i += 1
        return c
    spec = {
        "groups": ("組別", "business_group"), "salespeople": ("業務", "salesperson"), "customers": ("客戶", "customer"),
        "customer_categories": ("客戶類別", "customer_category"), "sales_categories": ("業績類別", "sales_category"),
        "platforms": ("平台", "platform"), "channels": ("電台", "media_channel"), "companies": ("公司別", "company"),
        "industries": ("產業別", "industry"), "contract_terms": ("年季約", "contract_term"),
    }
    for fld in fields:
        if fld in spec:
            lab, col = spec[fld]
            setattr(f, fld, nxt().multiselect(lab, opts.get(col, []), key=f"{key}_{fld}", placeholder="全部"))
        elif fld == "ad_like":
            f.ad_like = nxt().text_input("廣告名稱（含）", key=f"{key}_ad")
        elif fld == "contract_like":
            f.contract_like = nxt().text_input("CUE 號（含）", key=f"{key}_cue")
        elif fld == "exclude":
            with st.expander("排除條件（舊表單的 排除廣告／排除客戶／排除業務）", expanded=False):
                e1, e2, e3 = st.columns(3)
                f.exclude_salespeople = e1.multiselect("排除業務", opts.get("salesperson", []), key=f"{key}_xsp")
                f.exclude_customers = e2.multiselect("排除客戶", opts.get("customer", []), key=f"{key}_xcu")
                f.exclude_ad_like = e3.text_input("排除廣告（含此字）", key=f"{key}_xad")
    return f


def _export_bar(grids: list[G.Grid], *, key: str, title: str, period: str) -> None:
    fname = f"{title}_{period}".replace("/", "-").replace(" ", "")
    html = G.to_html(grids, title=title)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    with c1:
        if st.button("📄 產生 PDF", key=f"{key}_pdf_btn", use_container_width=True, disabled=not _pdf_ok()):
            from reports.export.pdf import html_to_pdf
            with st.spinner("排版中（約 3–10 秒）…"):
                st.session_state[f"{key}_pdf"] = html_to_pdf(html, orientation="landscape" if grids[0].landscape else "portrait",
                                                             title=title, period=period)
        if st.session_state.get(f"{key}_pdf"):
            st.download_button("⬇ 下載 PDF", data=st.session_state[f"{key}_pdf"], file_name=f"{fname}.pdf", mime="application/pdf",
                               key=f"{key}_pdf_dl", use_container_width=True)
    with c2:
        st.download_button("📊 下載 Excel", data=G.to_xlsx(grids, title=title, footer_left=date.today().strftime("%Y/%m/%d"), footer_center=period),
                           file_name=f"{fname}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=f"{key}_xlsx", use_container_width=True)
    with c3:
        st.download_button("🖨 列印版 HTML", data=html.encode("utf-8"), file_name=f"{fname}.html", mime="text/html",
                           key=f"{key}_html", use_container_width=True)
    with c4:
        st.caption("PDF 由伺服器排版（A4；業務發稿統計為 A3）" if _pdf_ok() else "此環境無 PDF 引擎：請用列印版 HTML 開啟後 Ctrl+P 存成 PDF")


def _preview(grids: list[G.Grid], *, key: str, title: str, period: str, max_rows: int = 800) -> None:
    n = sum(len(g.rows) for g in grids)
    if n > max_rows:
        st.info(f"共 {n:,} 列，畫面只預覽前 {max_rows} 列；PDF／Excel 是完整的。")
        shown, left = [], max_rows
        for g in grids:
            gg = G.Grid(g.name, g.rows[:left], g.widths, g.header_rows, g.landscape, g.paper, g.font_size)
            shown.append(gg)
            left -= len(gg.rows)
            if left <= 0:
                break
        grids_screen = shown
    else:
        grids_screen = grids
    _export_bar(grids, key=key, title=title, period=period)
    st.html("".join(G.grid_html(g) for g in grids_screen))


# ------------------------------------------------------------------ 六個分頁
tabs = st.tabs(["業績成本報表(區間)", "媒體發稿量分析", "成本毛利分析", "獎金總表(分平台成本)", "業績達成表", "三單查詢", "電台預付查詢", "對帳表(業績vs會計帳)", "說明"])

# 1 ---------------------------------------------------------------- 業績成本報表(區間)
with tabs[0]:
    st.markdown("#### 業績表區間統計 → 月業績成本報表")
    ym_from, ym_to, t_from, t_to = _period_bar("f1")
    opts = option_lists(ym_from, ym_to)
    f = _filters("f1", opts, ["customer_categories", "salespeople", "exclude"])
    df = C.apply_filters(load_lines(ym_from, ym_to), f)
    if df.empty:
        st.info("此條件查無資料")
    else:
        rep = C.cost_report(df)
        grids = L.layout_cost_report(rep, ym_from=t_from, ym_to=t_to,
                                     sales_text="/".join(f.salespeople) or "*", cat_text="/".join(f.customer_categories) or "*")
        st.caption(f"{len(df):,} 線・{df['contract_no'].nunique():,} 張合約・{df['salesperson'].nunique()} 位業務。"
                   "與舊報表的差異：最後一頁 (3) 健康視、(4) 廣播成本、(5) 其他 新版有值（舊版因欄位對不上是空白／0）；"
                   "(7) 製作費為備註列，不重複加入合計。")
        with st.expander("只看某一段（畫面預覽）", expanded=False):
            which = st.radio("顯示", ["全部", "只看最後一頁（平台總表）"], horizontal=True, key="f1_which")
        _preview(grids if which == "全部" else grids[-1:], key="f1", title="月業績成本報表", period=f"{t_from}~{t_to}")

# 2 ---------------------------------------------------------------- 媒體發稿量分析
with tabs[1]:
    st.markdown("#### 電台發稿量分析")
    ym_from, ym_to, t_from, t_to = _period_bar("f2")
    opts = option_lists(ym_from, ym_to)
    f = _filters("f2", opts, ["groups", "salespeople", "ad_like", "channels", "customer_categories", "customers", "sales_categories",
                             "contract_terms", "industries", "exclude"])
    c1, c2 = st.columns(2)
    version = c1.radio("報表選擇", ["客戶版", "業務版", "明細版", "電台總表", "業務總表"], horizontal=True, key="f2_ver")
    sort_by = c2.radio("排序項目", ["實收金額", "除佣實收", "實付金額", "毛利", "Total"], horizontal=True, key="f2_sort",
                       help="Total = 毛利+退佣（毛利 + 實付 × 電台當年退佣%）")
    df = C.apply_filters(load_lines(ym_from, ym_to), f)
    if df.empty:
        st.info("此條件查無資料")
    else:
        groups = C.media_volume(df, version, sort_by)
        grids = L.layout_media_volume(groups, version=version, sort_by=sort_by, ym_from=t_from, ym_to=t_to)
        st.caption(f"{len(groups)} 個電台・佔比＝該列 ÷ 該電台合計・毛利% = 毛利 ÷ 除佣實收・毛利+退佣 = 毛利 + 實付 × 電台年度退佣%（主檔維護 → 電台退佣）。"
                   "新版每個電台多一列「合計」（舊版沒有）。")
        _preview(grids, key="f2", title=f"月電台發稿量{version}", period=f"{t_from}~{t_to}")

# 3 ---------------------------------------------------------------- 成本毛利分析
with tabs[2]:
    st.markdown("#### 聲活成本毛利分析")
    ym_from, ym_to, t_from, t_to = _period_bar("f3")
    opts = option_lists(ym_from, ym_to)
    f = _filters("f3", opts, ["groups", "salespeople", "ad_like", "contract_like", "industries", "channels", "platforms",
                             "customer_categories", "customers", "companies", "exclude"])
    report = st.radio("成本毛利報表選擇", ["綜合分析", "客戶同期比較(全部)", "客戶同期比較(企頻)", "客戶同期比較(廣播)", "客戶同期比較(新鮮視)",
                                          "業績認定表", "獎金總表(月獎金計算總表)", "獎金總表(製作成本分平台A3)", "業務發稿統計(A3)"], horizontal=True, key="f3_rep")
    df = C.apply_filters(load_lines(ym_from, ym_to), f)
    if df.empty:
        st.info("此條件查無資料")
    elif report == "綜合分析":
        res = C.combined_analysis(df)
        grids = L.layout_combined(res, ym_from=t_from, ym_to=t_to, cust_text="/".join(f.customers) or "*")
        st.caption("企頻小計 = 平台名含「企」的所有線（舊：IIf([平台] Like '*企*')）；公司列 = 組別（聲活組→聲活…）；"
                   "聲-東鉑 = 聲活-東 + 聲活-鉑；聲+東+鉑 = 聲活組 + 東吳組 + 鉑霖組（不含錄音室、轉撥）。「其他」欄舊版永遠 0（平台名 其他／其它 對不上），新版有值。")
        _preview(grids, key="f3a", title="綜合成本毛利分析", period=f"{t_from}~{t_to}")
    elif report.startswith("客戶同期比較"):
        variant = report[report.index("(") + 1:-1]
        p_from, p_to = A.prev_window(ym_from, ym_to)          # 去年同一段月份
        prev = C.apply_filters(load_lines(p_from, p_to), f)
        res = C.period_compare(df, prev, variant)
        grids = L.layout_period_compare(res, ym_from=t_from, ym_to=t_to, year=ym_from.year,
                                        plat_text=(variant if variant != "全部" else "*"), exclude_text=f.exclude_text())
        st.caption("同期 = 去年同月區間；成長率 = 成長 ÷ 去年（去年 0 → 100%）；業務 = 該客戶當期除佣最多的業務；排名依當期除佣實收。")
        _preview(grids, key="f3b", title=f"客戶同期比較表({variant})", period=f"{t_from}~{t_to}")
    elif report == "業績認定表":
        res = C.recognition_table(df)
        grids = L.layout_recognition(res, ym_from=t_from, ym_to=t_to)
        st.caption("每位業務一頁；列 = 合約 × 平台；A/B = 該合約全部線的實收／除佣；C = 非製作費線實付（舊版此欄一律印 0）；D = 製作費線實付；除佣-製作 = B − D。")
        _preview(grids, key="f3c", title="月業績認定表", period=f"{t_from}~{t_to}")
    elif report == "獎金總表(製作成本分平台A3)":
        bs = C.bonus_summary_platform_cost(df)
        grids = L.layout_bonus_summary_platform_cost(bs, ym_from=t_from, ym_to=t_to, sales_text="/".join(f.salespeople) or "*", group_text="/".join(f.groups) or "*")
        st.caption("同月獎金計算總表，但每平台同時列「除佣實收」與「製作成本」兩組欄；製作成本合計 = 7 個平台製作成本相加 = 原獎金總表的製作成本。A3 橫向。")
        _preview(grids, key="f3d2", title="月獎金計算總表(製作成本分平台)", period=f"{t_from}~{t_to}")
    elif report.startswith("獎金總表"):
        bs = C.bonus_summary(df)
        grids = L.layout_bonus_summary(bs, ym_from=t_from, ym_to=t_to, sales_text="/".join(f.salespeople) or "*", group_text="/".join(f.groups) or "*")
        st.caption("平台欄 = 除佣實收；製作成本 = 製作費線實付；認定業績 = 除佣 − 製作成本。交換（X換）與轉撥組（聲活-東／聲活-鉑）照舊分開列。")
        _preview(grids, key="f3d", title="月獎金計算總表", period=f"{t_from}~{t_to}")
    else:
        ws = C.sales_wave_stats(df)
        grids = L.layout_wave_stats(ws, ym_from=t_from, ym_to=t_to)
        st.caption("執行波段 = 不重複的（客戶, 廣告, 合約編號）；平均單波 = 實收（毛利）÷ 波段；平台區塊：企頻＝平台含「企」、新鮮視、廣播（健康視／營運只進合計，同舊報表）。A3 橫向。")
        _preview(grids, key="f3e", title="業務發稿統計報表", period=f"{t_from}~{t_to}")

# 3d' --------------------------------------------------------------- 獎金總表(製作成本分平台) 獨立分頁（常用，拉到上方）
with tabs[3]:
    st.markdown("#### 月獎金計算總表（製作成本分平台）")
    ym_from, ym_to, t_from, t_to = _period_bar("fbp")
    opts = option_lists(ym_from, ym_to)
    f = _filters("fbp", opts, ["groups", "salespeople", "exclude"])
    df = C.apply_filters(load_lines(ym_from, ym_to), f)
    if df.empty:
        st.info("此條件查無資料")
    else:
        bs = C.bonus_summary_platform_cost(df)
        grids = L.layout_bonus_summary_platform_cost(bs, ym_from=t_from, ym_to=t_to,
                                                     sales_text="/".join(f.salespeople) or "*", group_text="/".join(f.groups) or "*")
        st.caption("同月獎金計算總表，但每平台同時列「除佣實收」與「製作成本」兩組欄；製作成本合計 = 7 個平台製作成本相加 = 原獎金總表的製作成本。A3 橫向。"
                   "（成本毛利分析分頁也有同一張。）")
        _preview(grids, key="fbp", title="月獎金計算總表(製作成本分平台)", period=f"{t_from}~{t_to}")

# 4 ---------------------------------------------------------------- 業績達成表
with tabs[4]:
    st.markdown("#### 業績達成統計 → 月責任檔業績達成表")
    ym_from, ym_to, t_from, t_to = _period_bar("f4")
    opts = option_lists(ym_from, ym_to)
    f = _filters("f4", opts, ["groups", "salespeople", "sales_categories", "exclude"])
    df = C.apply_filters(load_lines(ym_from, ym_to), f)
    if df.empty:
        st.info("此條件查無資料")
    else:
        res = C.achievement(df)
        grids = L.layout_achievement(res, ym_from=t_from, ym_to=t_to)
        st.caption("列 = 合約 × 業績類別；實收金額 = 該合約全部線實收；製作成本 = 製作費線實付；認定業績 = 實收 − 製作成本；"
                   "小計 = 業績類別、合計 = 業務、總計 = 組別。舊版把製作費藏在隱藏列、只在小計出現；新版直接放在合約列上。")
        _preview(grids, key="f4", title="月責任檔業績達成表", period=f"{t_from}~{t_to}")

# 5 ---------------------------------------------------------------- 三單查詢
with tabs[5]:
    st.markdown("#### 三單查詢")
    c1, c2, c3 = st.columns([2, 2, 3])
    contract_no = c1.text_input("合約編號", key="f5_cue", placeholder="例：1150622").strip()
    doc = c2.radio("單據選擇", ["採購申請單", "發票開立申請單"], horizontal=True, key="f5_doc")
    if contract_no:
        lines = C.prepare(query_df("select * from v_finance_line where contract_no = %s order by line_no", (contract_no,)))
        inv = query_df("select * from v_invoice_request where contract_no = %s order by request_no", (contract_no,))
        if lines.empty:
            st.warning("查無此合約")
        else:
            media = lines[~lines["is_intercompany"].astype(bool)]
            first = (media if len(media) else lines).iloc[0]
            t1, t2 = st.tabs([f"採購申請單 資料（{len(lines)} 線）", f"發票開立申請單 資料（{len(inv)} 張）"])
            with t1:
                show = lines[["contract_no", "business_group", "customer", "ad_name", "media_channel", "air_start", "air_end",
                              "cost_amount", "channel_cost_amount", "net_amount", "line_type"]].rename(columns={
                    "contract_no": "合約編號", "business_group": "組別", "customer": "客戶名稱", "ad_name": "廣告名稱", "media_channel": "電台",
                    "air_start": "上檔起始", "air_end": "上檔結束", "cost_amount": "實付金額", "channel_cost_amount": "電台實付金額",
                    "net_amount": "除佣實收", "line_type": "線類型"})
                st.dataframe(show, hide_index=True, use_container_width=True)
            with t2:
                if inv.empty:
                    st.info("此合約尚未開立發票")
                else:
                    st.dataframe(inv[["request_no", "invoice_no", "customer_title", "customer_tax_id", "payment_method", "ad_income",
                                      "production_income", "expected_cash_on", "invoice_issued_on", "notes"]].rename(columns={
                        "request_no": "單號", "invoice_no": "發票號碼", "customer_title": "抬頭", "customer_tax_id": "統編", "payment_method": "收款方式",
                        "ad_income": "廣告收入", "production_income": "製作收入", "expected_cash_on": "預定兌現日", "invoice_issued_on": "開立日", "notes": "備註"}),
                        hide_index=True, use_container_width=True)
            if doc == "採購申請單":
                pr = C.purchase_request(lines)
                grids = L.layout_purchase_request(pr, contract_no=contract_no, customer=first["customer"], group=first["business_group"],
                                                  ad_name=first["ad_name"], salesperson=first["salesperson"])
                st.caption("列 = 非製作費、非尼爾森的線（含轉撥線）；% = 電台主檔的現金折扣；實際成本 = 實付金額；應付金額 = 電台實付金額；"
                           "現折後 = 減去 金額 × 現折%；好事／城市聯播網總額 = 該聯播網電台的應付合計（主檔維護 → 電台 → 聯播網）。表頭公司固定為聲活（同舊表單）。")
                _preview(grids, key="f5a", title=f"廣告時段採購申請單_{contract_no}", period=contract_no)
            else:
                grids = L.layout_invoice_request(inv, contract_no=contract_no, customer=first["customer"], group=first["business_group"],
                                                 ad_name=first["ad_name"], salesperson=first["salesperson"], air_text=first["air_period_text"])
                st.caption("舊系統沒有此單的樣張，版面依 發票開立資料表 欄位設計；單號 = 舊資料的單號、新資料的發票 id。")
                _preview(grids, key="f5b", title=f"發票開立申請單_{contract_no}", period=contract_no)

# 6 ---------------------------------------------------------------- 電台預付查詢
with tabs[6]:
    st.markdown("#### 電台預付查詢")
    today = date.today()
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    d_from = c1.date_input("預付日期 起", value=today - timedelta(days=today.weekday()), key="f6_from")
    d_to = c2.date_input("預付日期 迄", value=today - timedelta(days=today.weekday()) + timedelta(days=6), key="f6_to")
    ch_opts = query_df("select distinct m.name from channel_payment_rule r join media_channel m on m.id = r.media_channel_id order by 1")
    ch = c3.multiselect("電台", list(ch_opts["name"]) if not ch_opts.empty else [], key="f6_ch", placeholder="全部")
    cue = c4.text_input("合約編號（含）", key="f6_cue")
    sql = "select * from v_channel_prepay where prepay_on between %s and %s"
    params: list = [d_from, d_to]
    if ch:
        sql += " and media_channel = any(%s)"
        params.append(ch)
    if cue.strip():
        sql += " and contract_no like %s"
        params.append(f"%{cue.strip()}%")
    pp = query_df(sql + " order by prepay_on, media_channel, contract_no", tuple(params))
    st.caption("預付日依「電台付款規則」推算（主檔維護 → 電台付款規則）：次週三付＝上檔起始日的下週三；每月2付＝上檔日 ≤ 一段日前 → 當月付款日，否則次月付款日；"
               "次月1付；第N天付＝起始日+N−1；播畢第N天付＝結束日+N−1；播畢次月1付。只列有付款規則的電台線。")
    if pp.empty:
        st.info("此區間沒有到期的電台預付")
    else:
        # 標記電台已付款（舊：電台預付查詢表單下方的 電台已付款 子表單）
        edit = pp[["line_id", "prepay_on", "media_channel", "is_network", "is_channel_paid", "contract_no", "customer", "ad_name",
                   "air_start", "air_end", "cost_amount", "channel_cost_amount", "ym", "pay_type"]].copy()
        edit = edit.rename(columns={"prepay_on": "電台預付日", "media_channel": "電台", "is_network": "聯網", "is_channel_paid": "電台已付款",
                                    "contract_no": "合約編號", "customer": "客戶名稱", "ad_name": "廣告名稱", "air_start": "上檔起始", "air_end": "上檔結束",
                                    "cost_amount": "實付金額", "channel_cost_amount": "電台實付金額", "ym": "業績年月", "pay_type": "付款種類"})
        edited = st.data_editor(edit, hide_index=True, use_container_width=True, key="f6_editor",
                                disabled=[c for c in edit.columns if c != "電台已付款"],
                                column_config={"line_id": None, "電台已付款": st.column_config.CheckboxColumn("電台已付款")})
        changed = edited[edited["電台已付款"] != edit["電台已付款"]]
        if len(changed) and st.button(f"💾 儲存已付款標記（{len(changed)} 筆）", key="f6_save"):
            with transaction(user["username"]) as cur:
                for _, r in changed.iterrows():
                    cur.execute("update deal_line set is_channel_paid = %s, updated_by = %s where id = %s",
                                (bool(r["電台已付款"]), user["username"], int(r["line_id"])))
            st.cache_data.clear()
            st.success("已更新")
            st.rerun()
        groups = C.prepay_groups(pp)
        grids = L.layout_prepay(groups, d_from=d_from.strftime("%Y/%m/%d"), d_to=d_to.strftime("%Y/%m/%d"), channel_text="/".join(ch) or "*")
        _preview(grids, key="f6", title="電台預付明細表", period=f"{d_from:%Y-%m-%d}~{d_to:%Y-%m-%d}")

# 7' --------------------------------------------------------------- 業績系統 vs 會計帳 對帳表
with tabs[7]:
    st.markdown("#### 業績系統 vs 會計帳 對帳表（媒體發稿量分）")
    ym_from, ym_to, t_from, t_to = _period_bar("frc")
    opts = option_lists(ym_from, ym_to)
    groups = opts.get("business_group", [])
    default_i = groups.index("東吳組") if "東吳組" in groups else 0
    grp = st.selectbox("組別", groups, index=default_i, key="frc_grp") if groups else None
    lines = load_lines(ym_from, ym_to)
    if grp:
        lines = lines[lines["business_group"] == grp]
    if lines.empty:
        st.info("此條件查無資料")
    else:
        res = C.reconciliation(lines)
        grids = L.layout_reconciliation(res, ym_from=t_from, ym_to=t_to, group_text=grp or "*")
        st.caption("全部由業績系統（v_finance_line）推算：**會計帳收入 = 除傭實收 − 交換**；**會計帳成本 = 實付金額 − 製作費 − 交換未認成本**；"
                   "折讓 = Σ(實付 × 電台現金折扣%)、現% = 折讓 ÷ 實付；交換 = 廣告交換線（is_barter）的除傭實收（不列入會計帳收入）。"
                   "數字為當前資料庫快照，與手工底稿可能因抓取日不同而有差（例：新鮮視）。")
        _preview(grids, key="frc", title=f"對帳表_{grp or '全部'}", period=f"{t_from}~{t_to}")

# 8 ---------------------------------------------------------------- 說明
with tabs[8]:
    st.markdown("#### 說明")
    st.markdown(
        "本專區把舊 Access 業績系統仍在用的六個財務功能，用資料庫即時算、版型與數字 100% 重現。"
        "資料一律走 `v_finance_line`（舊「業績資料表」一列 = 一線，含轉撥線／交換線／製作費線／錄音室，不套分析頁的排除口徑）。"
    )

    st.markdown("##### 一、與舊系統刻意不同的地方（都是修正舊系統對不上的欄位）")
    st.markdown(
        "- **業績成本報表最後一頁**：舊版 (3) 健康視空白、(4) 廣播成本 0、(5) 其他空白、(7) 製作費空白（報表欄名對不上資料）；新版填真實值。(7) 製作費為備註列，不重複加入合計。\n"
        "- **綜合分析「其他」欄**：舊版永遠 0（報表找『其他』、資料是『其它』），連總計也少算；新版有值。\n"
        "- **業績認定表 C 欄（實付金額 C不含D）**：舊版一律印 0（欄位壞掉）；新版印真實非製作費成本（不影響認定金額）。\n"
        "- **月責任檔業績達成表 製作成本**：舊版藏在隱藏列、只在小計出現；新版直接放在合約列，小計＝列的加總。\n"
        "- **媒體發稿量分析**：新版每個電台多一列「合計」（舊版沒有）。\n"
        "- **平台歸類**：財務 8 類照舊系統的意思（『企頻』歸全家企頻／企頻小計），與老闆報表（007 report_platform 把『企頻』歸營運）不同。"
    )

    st.markdown("##### 二、舊「成本毛利分析」27 個選項 → 新系統對照")
    st.caption("PDF 有示範的 5 個已做在本專區「成本毛利分析」分頁；其餘 22 個對照如下（之後財務要再補）。")
    st.table(pd.DataFrame([
        ["帳上毛利", "綜合分析（帳上層）／公司分析"],
        ["企頻檔次", "報表中心「媒體發稿量與秒數」"],
        ["客戶兩期比較（全部／企頻／廣播／新鮮視）", "本專區 客戶同期比較表（已做）"],
        ["業務業績毛利／業務客戶毛利／業務兩期", "業務分析、業務頁"],
        ["人力統計／統一商機／媒體出CUE&進單（總表/業務）", "不做（已停用／另一套系統）"],
        ["客戶毛利排行", "客戶分析排名、常用分析 客戶排名"],
        ["業績認定表", "本專區（已做）"],
        ["電台／依毛利", "本專區 媒體發稿量分析（電台總表、依毛利排序）"],
        ["業務發稿統計(A3)", "本專區（已做）"],
        ["獎金總表(A3)／獎金總表B／業務獎金／客服獎金／專案獎金／主管獎金", "月獎金計算總表（已做）；各類獎金＝業務獎金頁（第一層），其餘待"],
        ["客戶兩年", "客戶頁 歷年同期比較"],
        ["企頻預估", "公司分析 進單＋預估"],
    ], columns=["舊選項", "新系統"]))

    st.markdown("##### 三、待財務確認（不影響上線）")
    st.markdown(
        "1. **聯播網歸屬**：好事＝BEST989／港都／山海屯／蓮花／南方之音，城市＝GOLD 系列（從付款規則的『聯網』旗標與電台名推的）。\n"
        "2. **採購申請單**：應付金額用「電台實付金額」、實際成本用「實付金額」（2025 起只有 118 筆不同）。\n"
        "3. **發票開立申請單** 沒有舊樣張，版面照欄位設計，請拿一張舊單來對。\n"
        "4. **業績認定表 C 欄** 新版印真實成本；若要維持舊樣（印 0）可調 `layout_recognition`。\n"
        "5. **業績成本報表最後一頁** (3)/(4)/(5) 新版有值。\n"
        "6. **業績達成表** 其餘四種（業務認定／業績類別／客戶統計／責任檔合計）與媒體發稿量「Total」定義（本系統當作 毛利+退佣）待樣張確認。\n"
        "7. **電台年度退佣** 每年要新增當年度比例（主檔維護 → 電台年度退佣，有『複製去年』按鈕）。"
    )
    st.caption("完整規格見 CLAUDE_CODE_TASK_7.md。")

feedback_widget("finance_reports")
