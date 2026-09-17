"""
platform_overview.py — 平台總計總覽（老闆版 Excel）｜階段 L §4.2

一鍵匯出老闆工作簿「平台總計總覽」的八個區塊（除佣／成本／帳上毛利／利率 × 含廣播／不含廣播），
再加 第九區塊 集團毛利（含廣播）、第十區塊 客戶數（含／不含廣播）。口徑＝發稿口徑。

驗收（2025）：區塊一（除佣・含廣播）合計 134,303,021；區塊五（除佣・不含廣播）98,408,698；
             客戶數 265／259。
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from core import analysis as A

PLATFORMS = ["全家企頻", "萬家福", "新鮮視", "廣播", "健康視"]
OWN = ["全家企頻", "萬家福", "新鮮視", "健康視"]          # 自媒體（不含廣播）
COMPANIES = ["聲活", "東吳", "鉑霖", "瑞迪"]


def _base(year: int, scope: dict | str = "media", user: dict | None = None) -> pd.DataFrame:
    lines = A.load_lines(date(year, 1, 1), date(year, 12, 1), scope=scope, user=user)
    if lines.empty:
        return lines
    lines = lines.copy()
    lines["_gp"] = A.line_group_profit(lines)
    return lines


def _present(df: pd.DataFrame, own_only: bool) -> list[str]:
    pool = OWN if own_only else PLATFORMS
    have = set(df["report_platform"])
    return [p for p in pool if p in have]


def _block(df: pd.DataFrame, metric: str, own_only: bool) -> pd.DataFrame:
    """一個區塊：rows=公司(+合計)，cols=平台(+合計)。metric: net/cost/profit/margin/group_profit/customers。"""
    plats = _present(df, own_only)
    sub = df[df["report_platform"].isin(plats)]
    cos = [c for c in COMPANIES if c in set(sub["company"])]
    rows = []
    for co in cos + ["三公司合計"]:
        d = sub if co == "三公司合計" else sub[sub["company"] == co]
        row = {"公司": co}
        tot_net = float(d["net_amount"].sum())
        tot_num = 0.0
        for p in plats:
            dp = d[d["report_platform"] == p]
            net = float(dp["net_amount"].sum())
            if metric == "net":
                v = net
            elif metric == "cost":
                v = float(dp["cost_amount"].sum())
            elif metric == "profit":
                v = net - float(dp["cost_amount"].sum())
            elif metric == "group_profit":
                v = float(dp["_gp"].sum())
            elif metric == "margin":
                v = ((net - float(dp["cost_amount"].sum())) / net) if net else None
            elif metric == "customers":
                v = int(dp["customer_id"].nunique())
            else:
                v = None
            row[p] = v
            if metric not in ("margin", "customers") and v is not None:
                tot_num += v
        if metric == "margin":
            cost = float(d["cost_amount"].sum())
            row["合計"] = ((tot_net - cost) / tot_net) if tot_net else None
        elif metric == "customers":
            row["合計"] = int(d["customer_id"].nunique())
        else:
            row["合計"] = tot_num
        rows.append(row)
    return pd.DataFrame(rows)


BLOCKS = [
    ("一、除佣實收（含廣播）", "net", False), ("二、成本（含廣播）", "cost", False),
    ("三、帳上毛利（含廣播）", "profit", False), ("四、帳上利率（含廣播）", "margin", False),
    ("五、除佣實收（不含廣播）", "net", True), ("六、成本（不含廣播）", "cost", True),
    ("七、帳上毛利（不含廣播）", "profit", True), ("八、帳上利率（不含廣播）", "margin", True),
    ("九、集團毛利（含廣播）", "group_profit", False),
    ("十、客戶數（含廣播）", "customers", False), ("十、客戶數（不含廣播）", "customers", True),
]


def build_workbook(year: int, scope: dict | str = "media", user: dict | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    FONT = "微軟正黑體"
    hfill = PatternFill("solid", fgColor="1F5F8B")
    blkfill = PatternFill("solid", fgColor="E8EEF4")
    hfont = Font(name=FONT, bold=True, color="FFFFFF")
    tfont = Font(name=FONT, bold=True, size=13)
    bfont = Font(name=FONT, bold=True, size=11, color="1F5F8B")
    base = Font(name=FONT); bold = Font(name=FONT, bold=True)
    topb = Border(top=Side(style="thin"))

    df = _base(year, scope, user)
    wb = Workbook(); ws = wb.active; ws.title = f"平台總計總覽_{year}"[:31]
    if df.empty:
        ws.cell(1, 1, f"{year}：查無資料").font = tfont
        buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

    r = 1
    ws.cell(r, 1, f"{year} 平台總計總覽（發稿口徑）　單位：元").font = tfont
    r += 2
    for title, metric, own in BLOCKS:
        blk = _block(df, metric, own)
        if blk.empty:
            continue
        plats = _present(df, own)
        cols = ["公司"] + plats + ["合計"]
        cell = ws.cell(r, 1, title); cell.font = bfont; cell.fill = blkfill
        for j in range(2, len(cols) + 1):
            ws.cell(r, j).fill = blkfill
        r += 1
        for j, h in enumerate(cols, 1):
            c = ws.cell(r, j, h); c.fill = hfill; c.font = hfont; c.alignment = Alignment(horizontal="center")
        r += 1
        n = len(blk)
        for i, (_, row) in enumerate(blk.iterrows()):
            is_tot = i == n - 1
            for j, col in enumerate(cols, 1):
                v = row.get(col)
                c = ws.cell(r, j)
                if isinstance(v, float) and pd.isna(v):
                    v = None
                c.value = v
                c.font = bold if is_tot else base
                if is_tot:
                    c.border = topb
                if col != "公司" and v is not None:
                    c.number_format = "0.0%" if metric == "margin" else ("#,##0" if metric != "customers" else "#,##0")
            r += 1
        r += 1

    ws.freeze_panes = "B1"
    ws.column_dimensions["A"].width = 14
    for j in range(2, 8):
        ws.column_dimensions[get_column_letter(j)].width = 14
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def render(user: dict | None = None) -> None:
    import streamlit as st
    from core.format import money

    years = A._df("select distinct perf_year from v_report_line where in_media_scope order by 1 desc")
    year_opts = [int(y) for y in years["perf_year"].tolist()] if not years.empty else [date.today().year]
    year = st.selectbox("年度", year_opts, key="po_year")
    st.caption("口徑：發稿口徑。畫面同「公司分析 → 平台總計總覽」；此報表提供一鍵匯出老闆版八區塊 Excel。")

    df = _base(year, "media", user)
    if df.empty:
        st.info(f"{year} 查無資料。"); return
    # 畫面預覽：區塊一（除佣・含廣播）+ 客戶數
    b1 = _block(df, "net", False)
    plats = _present(df, False)
    spec = [("公司", "公司", "text")] + [(p, p, "money") for p in plats] + [("合計", "合計", "money")]
    st.markdown("**區塊一：除佣實收（含廣播）**")
    A.show_ranking(b1, spec, height=None, key="po_b1")
    st.caption(f"三公司合計 {money(float(b1[b1['公司']=='三公司合計']['合計'].iloc[0]))}"
               f"｜不重複客戶 {int(df['customer_id'].nunique())} 家")

    data = build_workbook(year, "media", user)
    st.download_button("⬇ 下載平台總計總覽（Excel，八區塊）", data=data,
                       file_name=f"平台總計總覽_{year}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
