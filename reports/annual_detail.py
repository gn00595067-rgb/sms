"""
annual_detail.py — 年度發稿明細（喬商版型）｜階段 L §4.1

口徑：發稿口徑（老闆版，見 core.analysis scope="media"）。一家公司一個工作表，由上而下三段：
  第一段 各業務客戶數與發稿總計
  第二段 各業務每客戶總計（分平台）
  第三段 逐筆明細
可下載 Excel（多工作表）或列印。include_group_profit=True 時三段各多「集團毛利／集團利率」欄。

驗收（2025 鉑霖）：第一段 許雅婷 11,431,326 / 4,949,150 / 43.3% / 54 家；
                 第三段末列 11,907,516 / 6,932,238 / 4,975,277。
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from core import analysis as A

PLATFORMS = ["全家企頻", "萬家福", "新鮮視", "廣播", "健康視"]


# ------------------------------------------------------------------ 資料
def load(year: int, company: str, scope: dict | str = "media", user: dict | None = None) -> pd.DataFrame:
    """該公司該年、發稿口徑的線層 df，加集團毛利分攤欄 _gp。"""
    lines = A.load_lines(date(year, 1, 1), date(year, 12, 1), scope=scope,
                         filters={"company": company}, user=user)
    if lines.empty:
        return lines
    lines = lines.copy()
    lines["_gp"] = A.line_group_profit(lines)
    lines["sp"] = lines["salesperson_merged"].fillna("（未填）")
    return lines


def _present_platforms(df: pd.DataFrame) -> list[str]:
    have = set(df["report_platform"])
    return [p for p in PLATFORMS if p in have]


def _plat_pivot(df: pd.DataFrame, index_col: str, plats: list[str]) -> pd.DataFrame:
    piv = df.pivot_table(index=index_col, columns="report_platform", values="net_amount",
                         aggfunc="sum", fill_value=0.0)
    for p in plats:
        if p not in piv.columns:
            piv[p] = 0.0
    return piv[plats]


# ------------------------------------------------------------------ 三段
def section1(df: pd.DataFrame, company_total: float, plats: list[str],
             include_group_profit: bool = False) -> pd.DataFrame:
    """各業務：客戶數、四平台、總計、毛利、利率、發稿佔比。末列合計。"""
    if df.empty:
        return pd.DataFrame()
    piv = _plat_pivot(df, "sp", plats)
    g = df.groupby("sp").agg(customers=("customer_id", "nunique"), net=("net_amount", "sum"),
                             cost=("cost_amount", "sum"), gp=("_gp", "sum"))
    out = piv.join(g).reset_index().rename(columns={"sp": "業務"})
    out["總計"] = out["net"]
    out["帳上毛利"] = out["net"] - out["cost"]
    out["利率"] = out["帳上毛利"] / out["net"].where(out["net"] != 0)
    out["發稿佔比"] = out["net"] / company_total if company_total else 0.0
    if include_group_profit:
        out["集團毛利"] = out["gp"]
        out["集團利率"] = out["gp"] / out["net"].where(out["net"] != 0)
    out = out.sort_values("總計", ascending=False)
    total = {"業務": "合計", "customers": int(df["customer_id"].nunique()),
             "總計": out["net"].sum(), "帳上毛利": out["帳上毛利"].sum(),
             "利率": (out["帳上毛利"].sum() / out["net"].sum()) if out["net"].sum() else None,
             "發稿佔比": 1.0}
    for p in plats:
        total[p] = out[p].sum()
    if include_group_profit:
        total["集團毛利"] = out["集團毛利"].sum()
        total["集團利率"] = (out["集團毛利"].sum() / out["net"].sum()) if out["net"].sum() else None
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)


def section2(df: pd.DataFrame, plats: list[str], include_group_profit: bool = False) -> list[tuple[str, pd.DataFrame]]:
    """每個業務一個區塊：客戶 × 四平台、總計、毛利、利率、佔該業務%。回 [(業務, df), …]。"""
    blocks = []
    sp_order = df.groupby("sp")["net_amount"].sum().sort_values(ascending=False).index
    for sp in sp_order:
        sub = df[df["sp"] == sp]
        piv = _plat_pivot(sub, "customer", plats)
        g = sub.groupby("customer").agg(net=("net_amount", "sum"), cost=("cost_amount", "sum"), gp=("_gp", "sum"))
        b = piv.join(g).reset_index().rename(columns={"customer": "客戶"})
        b["總計"] = b["net"]
        b["帳上毛利"] = b["net"] - b["cost"]
        b["利率"] = b["帳上毛利"] / b["net"].where(b["net"] != 0)
        sp_total = float(sub["net_amount"].sum())
        b["佔該業務"] = b["net"] / sp_total if sp_total else 0.0
        if include_group_profit:
            b["集團毛利"] = b["gp"]
            b["集團利率"] = b["gp"] / b["net"].where(b["net"] != 0)
        b = b.sort_values("總計", ascending=False)
        blocks.append((sp, b))
    return blocks


def section3(df: pd.DataFrame, plats: list[str], include_group_profit: bool = False) -> pd.DataFrame:
    """逐筆明細：業務｜客戶｜實收｜走期｜四平台（金額落對應欄）｜成本｜毛利｜%｜佔比。"""
    if df.empty:
        return pd.DataFrame()
    total_net = float(df["net_amount"].sum())
    rows = []
    d = df.sort_values(["sp", "customer", "air_start"], na_position="last")
    for _, r in d.iterrows():
        net = float(r["net_amount"]); cost = float(r["cost_amount"])
        row = {"業務": r["sp"], "客戶": r["customer"], "實收": net,
               "走期": r.get("air_period_text"), "成本": cost, "帳上毛利": net - cost,
               "利率": (net - cost) / net if net else None,
               "佔比": net / total_net if total_net else 0.0}
        for p in plats:
            row[p] = net if r["report_platform"] == p else 0.0
        if include_group_profit:
            row["集團毛利"] = float(r["_gp"])
        rows.append(row)
    out = pd.DataFrame(rows)
    return out


def totals_line(df: pd.DataFrame, plats: list[str]) -> dict:
    net = float(df["net_amount"].sum()); cost = float(df["cost_amount"].sum())
    t = {"業務": "除佣實收總計", "實收": net, "成本": cost, "帳上毛利": net - cost}
    for p in plats:
        t[p] = float(df[df["report_platform"] == p]["net_amount"].sum())
    return t


# ------------------------------------------------------------------ Excel
def build_workbook(year: int, companies: list[str], scope: dict | str = "media",
                   include_group_profit: bool = False, user: dict | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    FONT = "微軟正黑體"
    hfill = PatternFill("solid", fgColor="1F5F8B")
    hfont = Font(name=FONT, bold=True, color="FFFFFF")
    tfont = Font(name=FONT, bold=True, size=13)
    sfont = Font(name=FONT, bold=True, size=11, color="1F5F8B")
    base = Font(name=FONT)
    bold = Font(name=FONT, bold=True)
    topb = Border(top=Side(style="thin"))
    money_fmt, pct_fmt = "#,##0", "0.0%"

    wb = Workbook()
    wb.remove(wb.active)
    for company in companies:
        df = load(year, company, scope, user)
        ws = wb.create_sheet(title=f"{company}_{year}"[:31])
        if df.empty:
            ws.cell(1, 1, f"{company} {year}：查無資料").font = tfont
            continue
        plats = _present_platforms(df)
        company_total = float(df["net_amount"].sum())
        r = 1
        ws.cell(r, 1, f"{company} {year} 年度發稿明細（發稿口徑）").font = tfont
        r += 2

        def write_table(tdf: pd.DataFrame, cols: list[str], headers: list[str], bold_last: bool = False):
            nonlocal r
            for j, h in enumerate(headers, 1):
                c = ws.cell(r, j, h); c.fill = hfill; c.font = hfont
                c.alignment = Alignment(horizontal="center")
            r += 1
            n = len(tdf)
            for i, (_, row) in enumerate(tdf.iterrows()):
                is_last = bold_last and i == n - 1
                for j, col in enumerate(cols, 1):
                    v = row.get(col)
                    c = ws.cell(r, j)
                    if isinstance(v, float) and pd.isna(v):
                        v = None
                    c.value = v
                    c.font = bold if is_last else base
                    if col in ("利率", "發稿佔比", "佔該業務", "佔比", "集團利率"):
                        if v is not None:
                            c.number_format = pct_fmt
                    elif col not in ("業務", "客戶", "走期"):
                        if v is not None:
                            c.number_format = money_fmt
                    if is_last:
                        c.border = topb
                r += 1
            r += 1

        # 第一段
        ws.cell(r, 1, "第一段：各業務客戶數與發稿總計").font = sfont; r += 1
        s1 = section1(df, company_total, plats, include_group_profit)
        cols1 = ["業務", "customers"] + plats + ["總計", "帳上毛利", "利率", "發稿佔比"]
        head1 = ["業務", "客戶數"] + plats + ["總計(除佣實收)", "帳上毛利", "利率", "發稿佔比"]
        if include_group_profit:
            cols1 += ["集團毛利", "集團利率"]; head1 += ["集團毛利", "集團利率"]
        write_table(s1, cols1, head1, bold_last=True)

        # 第二段
        ws.cell(r, 1, "第二段：各業務每客戶總計（分平台）").font = sfont; r += 1
        cols2 = ["客戶"] + plats + ["總計", "帳上毛利", "利率", "佔該業務"]
        head2 = ["客戶"] + plats + ["總計", "帳上毛利", "利率", "佔該業務"]
        if include_group_profit:
            cols2 += ["集團毛利", "集團利率"]; head2 += ["集團毛利", "集團利率"]
        for sp, b in section2(df, plats, include_group_profit):
            ws.cell(r, 1, f"【{sp}】").font = bold; r += 1
            write_table(b, cols2, head2)

        # 第三段
        ws.cell(r, 1, "第三段：逐筆明細").font = sfont; r += 1
        s3 = section3(df, plats, include_group_profit)
        cols3 = ["業務", "客戶", "實收", "走期"] + plats + ["成本", "帳上毛利", "利率", "佔比"]
        head3 = ["業務", "客戶", "實收", "執行走期"] + plats + ["成本", "帳上毛利", "利率", "佔比"]
        if include_group_profit:
            cols3 += ["集團毛利"]; head3 += ["集團毛利"]
        write_table(s3, cols3, head3)
        # 末列：各平台小計 + 總計
        tl = totals_line(df, plats)
        for j, col in enumerate(cols3, 1):
            v = tl.get(col)
            c = ws.cell(r, j); c.font = bold; c.border = topb
            if v is not None:
                c.value = v
                if col not in ("業務", "客戶", "走期", "利率", "佔比"):
                    c.number_format = money_fmt
        r += 2

        ws.freeze_panes = "A4"
        for j in range(1, len(cols3) + 1):
            ws.column_dimensions[get_column_letter(j)].width = 13

    if not wb.sheetnames:
        wb.create_sheet("空")
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# ------------------------------------------------------------------ 報表中心入口
def render(user: dict | None = None) -> None:
    import streamlit as st
    from core.format import money, pct

    years = A._df("select distinct perf_year from v_report_line where in_media_scope order by 1 desc")
    year_opts = [int(y) for y in years["perf_year"].tolist()] if not years.empty else [date.today().year]
    c = st.columns([1, 2, 1])
    year = c[0].selectbox("年度", year_opts, key="ad_year")
    companies = c[1].multiselect("公司", ["聲活", "東吳", "鉑霖", "瑞迪"],
                                 default=["聲活", "東吳", "鉑霖"], key="ad_cos")
    incl_gp = c[2].checkbox("含集團毛利欄", value=False, key="ad_gp")
    st.caption("口徑：發稿口徑（只算媒體上稿線、交換併回原業務、四平台+健康視、帳上毛利）。")
    if not companies:
        st.info("請選至少一家公司。"); return

    # 畫面預覽：第一段 + 第二段（第三段太長，只在 Excel）
    prev_co = companies[0]
    df = load(year, prev_co, "media", user)
    if df.empty:
        st.info(f"{prev_co} {year} 查無資料。")
    else:
        plats = _present_platforms(df)
        ctot = float(df["net_amount"].sum())
        st.markdown(f"**{prev_co} {year}｜第一段：各業務客戶數與發稿總計**")
        s1 = section1(df, ctot, plats, incl_gp)
        spec = [("業務", "業務", "text"), ("customers", "客戶數", "int")]
        spec += [(p, p, "money") for p in plats]
        spec += [("總計", "總計", "money"), ("帳上毛利", "帳上毛利", "money"),
                 ("利率", "利率", "pct"), ("發稿佔比", "發稿佔比", "pct")]
        if incl_gp:
            spec += [("集團毛利", "集團毛利", "money"), ("集團利率", "集團利率", "pct")]
        A.show_ranking(s1, spec, height=None, key="ad_s1")
        with st.expander("第二段：各業務每客戶總計（分平台）"):
            for sp, b in section2(df, plats, incl_gp):
                st.markdown(f"**【{sp}】** 合計 {money(float(b['net'].sum()))}")
                spec2 = [("客戶", "客戶", "text")] + [(p, p, "money") for p in plats]
                spec2 += [("總計", "總計", "money"), ("利率", "利率", "pct"), ("佔該業務", "佔該業務", "pct")]
                A.show_ranking(b, spec2, height=None, key=f"ad_s2_{sp}")

    data = build_workbook(year, companies, "media", incl_gp, user)
    st.download_button("⬇ 下載年度發稿明細（Excel，每家一工作表）", data=data,
                       file_name=f"年度發稿明細_{year}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)

    # 列印級 PDF / 單一工作表 Excel（每家一份，走匯出層）
    from reports import export as X
    from core.docs.annual_detail import build_doc as _ad_doc
    _f = {"ym_from": date(year, 1, 1), "ym_to": date(year, 12, 1), "scope": "media"}
    st.divider()
    st.caption("列印版（PDF）／單一工作表 Excel — 每家一份：")
    _co = st.selectbox("選公司產列印版", companies, key="ad_pdf_co")
    X.ui.export_bar(_ad_doc(_f, user, company=_co), key=f"ad_{_co}")
