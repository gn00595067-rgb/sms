"""
layout.py — 老闆工作簿每一張表「長什麼樣」：區塊順序、標題文字、表頭、空列數（照原檔逐列量的）

這裡只描述版面，不碰 openpyxl 或 HTML：同一份 layout 交給 xlsx.Sheet 寫成 Excel、交給 html.HtmlSheet 寫成畫面／PDF。
寫入端要實作的介面（duck typing）：
    title(text, *, size, bold, color, merge_to, center)   blank(n)   block_title(text, ncol)
    header(labels, *, fill, size, height)   table(df, fmts, *, pct, bold_cols, bold_first, size, first_col_bold_rows)
    detail_title(company, year_label, ncol)   section3_header(plats)   section3_rows(df, plats)   section3_totals(totals, plats)
    raw_table(raw, cols)   widths(spec)   freeze(cell)   print_setup(landscape, repeat_rows)   mark() -> 目前列
"""
from __future__ import annotations

import pandas as pd

from . import compute as C

BLUE, GREEN, YELLOW, LBLUE, SUBTOT, TITLE_INK = "2F5496", "548235", "FFFF00", "8EA9DB", "D9E2F3", "203864"
PCT1, PCT2 = "0.0%", "0.00%"

RAW_COLS = ["公司別", "業績年月份", "BLINK認列年月", "進單年月", "平台", "合約編號", "客戶名稱", "廣告名稱", "上檔起始日期", "上檔結束日期",
            "節目名稱", "實收金額", "除佣實收", "實付金額", "組別", "業務", "客服", "客戶類別", "產業別", "電台", "備註", "購買檔次",
            "搭贈檔次", "搭贈金額", "搭贈組合", "編播贈檔", "合約期限", "業務_final", "平台_顯示", "走期"]


def fmts(plats, extra: dict | None = None) -> dict:
    f = {p: "money" for p in plats}
    f.update({"總計": "money", "總計(除佣實收)": "money", "成本": "money", "毛利": "money", "實收": "money",
              "利率": "pct", "利率(%)": "pct", "發稿佔比": "pct", "除佣佔比": "pct", "成本佔比": "pct", "毛利佔比": "pct",
              "客戶數": "count", "客戶數(不重複)": "count", "排名": "int"})
    if extra:
        f.update(extra)
    return f


def layout_notes(s, lines: list[str]) -> None:
    for i, line in enumerate(lines):
        s.title(line, size=13 if i == 0 else 10, bold=(i == 0 or bool(line and not line.startswith("・"))),
                color=TITLE_INK if i == 0 else None, merge_to=8 if line else None)
    s.widths({"A": 14})


def layout_platform_overview(s, raw: pd.DataFrame, plats: list[str], year_label: str) -> None:
    s.title(f"{year_label} 三公司平台總計總覽（除佣實收 / 成本 / 毛利 / 利率，分平台列示）", size=13, merge_to=9)
    s.blank()
    blocks = [("一、除佣實收（含廣播）（$）", "net", True), ("二、成本（含廣播）（$）＝實付金額", "cost", True),
              ("三、毛利（含廣播）（$）＝除佣實收－成本", "profit", True), ("四、利率（含廣播）（%）＝毛利÷除佣實收", "rate", True),
              (f"五、除佣實收（不含廣播，僅自媒體：{'/'.join(p for p in plats if p != '廣播')}）（$）", "net", False),
              ("六、成本（不含廣播）（$）", "cost", False), ("七、毛利（不含廣播）（$）＝除佣實收－成本", "profit", False),
              ("八、利率（不含廣播）（%）", "rate", False)]
    cache = {True: C.platform_overview(raw, plats, incl_radio=True), False: C.platform_overview(raw, plats, incl_radio=False)}
    for title, key, incl in blocks:
        res = cache[incl]
        df = res[key]
        s.title(title, size=10, color=None)
        s.header(list(df.columns))
        f = fmts(res["plats"])
        if key == "rate":
            f.update({p: "pct" for p in res["plats"]})
            f["總計"] = "pct"
        s.table(df, f, pct=PCT1, bold_cols=("總計",) if key != "rate" else ())
        s.blank(2)
    # 欄寬比原檔寬（原檔 C–H 是預設寬度，$31,744,374 會顯示成 ###）
    s.widths({"A": 16, "B": 15, "C": 15, "D": 15, "E": 15, "F": 16, "G": 15, "H": 11})
    s.freeze("A2")
    s.print_setup(landscape=True)


def layout_customer_stats(s, raw: pd.DataFrame, plats: list[str], year_label: str) -> None:
    s.title(f"{year_label} 三公司客戶數與除佣實收總計（不分平台）", size=13, merge_to=13)
    s.blank()
    net = C.platform_overview(raw, plats, incl_radio=True)["net"]
    net.loc[net["公司"] == "三公司合計", "除佣佔比"] = net.loc[net["公司"] != "三公司合計", "除佣佔比"].sum()
    s.header(list(net.columns))
    s.table(net, fmts(plats), pct=PCT1)
    s.blank(2)
    s.title("各業務分平台總計（除佣實收/成本/毛利/利率及佔比）", size=10, color=None)
    s.title("三公司合計（依業務，同名業務已合併）", size=10, color=None)
    t = C.salesperson_table(raw, plats)
    s.header(["業務", "公司"] + plats + ["總計(除佣實收)", "成本", "毛利", "利率(%)", "發稿佔比"], fill=GREEN)
    s.table(t, fmts(plats))
    s.blank(2)
    # 空列數照原檔（公司區塊之間 2 列、最後一個區塊之後直接接標題；前 10 大區塊之間 1 列）
    for i, co in enumerate(C.COMPANIES):
        s.block_title(f"【{co}】", 5 + len(plats))
        s.blank()
        t = C.salesperson_table(raw, plats, company=co)
        s.header(["業務"] + plats + ["總計(除佣實收)", "成本", "毛利", "利率(%)", "發稿佔比"])
        s.table(t, fmts(plats))
        if i < len(C.COMPANIES) - 1:
            s.blank(2)
    s.title("三公司總計 前10大客戶（跨公司合併，依除佣實收總計排序）", size=10, color=None)
    t = C.customer_ranking(raw, plats, top=10)
    s.header(["排名", "公司", "業務", "客戶名稱"] + plats + ["總計(除佣實收)", "成本", "毛利", "利率(%)", "發稿佔比"], fill=GREEN)
    s.table(t, fmts(plats), bold_first=False)
    s.blank(2)
    s.title("各公司前10大客戶（依除佣實收排序，各平台總計與佔該公司發稿佔比）", size=10, color=None)
    for co in C.COMPANIES:
        s.block_title(f"【{co}】", 8 + len(plats))
        t = C.customer_ranking(raw, plats, company=co, top=10)
        s.header(["排名", "業務", "客戶名稱"] + plats + ["總計(除佣實收)", "成本", "毛利", "利率(%)", "發稿佔比(佔該公司總計)"])
        s.table(t, fmts(plats), bold_first=False)
        s.blank()
    s.title("三公司客戶排名（依除佣實收總計排序；同一客戶已合併所有公司/業務/平台，跨平台金額同列呈現）", size=10, color=None)
    t = C.customer_ranking(raw, plats)
    s.header(["排名", "公司", "業務", "客戶名稱"] + plats + ["總計(除佣實收)", "成本", "毛利", "利率(%)", "發稿佔比"])
    s.table(t, fmts(plats), bold_first=False)
    s.widths({"A": 16, "B": 20, "C": 16, "D": 26, "E": 16, "F": 16, "G": 16, "H": 16, "I": 16, "J": 16, "K": 16, "L": 11, "M": 11})
    s.print_setup(landscape=True)


def layout_annual_detail(s, raw: pd.DataFrame, plats: list[str], company: str, year_label: str,
                         sections: tuple[int, ...] = (1, 2, 3)) -> None:
    """sections：畫面上可以只畫 (1, 2)，逐筆明細 (3,) 另放 expander；Excel／PDF 一律 (1, 2, 3)。"""
    d = C.annual_detail(raw, plats, company)
    n_plat = len(plats)
    ncol3 = 4 + n_plat + 4
    s.detail_title(company, year_label, ncol3)      # 第 1 列；之後從第 3 列開始
    if 1 in sections:
        s.title("各業務客戶數與發稿總計", size=12)
        s.header(["業務", "客戶數(不重複)"] + plats + ["總計(除佣實收)", "毛利", "利率(%)", "發稿佔比"], size=11, height=29)
        s.table(d.section1, fmts(plats), size=12)
        s.blank(2)
    if 2 in sections:
        s.title("各業務每客戶總計（分平台，客戶僅列一列總計）", size=12)
        for sp, t in d.section2:
            s.block_title(f"【{sp}】", 5 + n_plat)
            s.header(["客戶名稱"] + plats + ["總計(除佣實收)", "毛利", "利率(%)", "除佣佔比"], size=11)
            s.table(t, fmts(plats), size=12, first_col_bold_rows=False)
            s.blank()
    r0 = s.mark()
    if 3 in sections:
        s.section3_header(plats)                      # 三列合併表頭，緊接最後一個小計之後空一列
        s.section3_rows(d.section3, plats)
        s.section3_totals(d.totals, plats)
    s.widths({"A": 14, "B": 26, "C": 14.6, "D": 13, "E": 14, "F": 14, "G": 15.9, "H": 14, "I": 14, "J": 14, "K": 10, "L": 10})
    s.print_setup(landscape=True, repeat_rows=f"{r0}:{r0 + 2}" if 3 in sections else None)


def layout_raw(s, raw: pd.DataFrame) -> None:
    cols = [c for c in RAW_COLS if c in raw.columns]
    s.raw_table(raw, cols)
    s.freeze("A2")


def prepare(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    raw = raw.copy()
    for c in ("實收金額", "除佣實收", "實付金額"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")      # 空值保留（逐筆明細留空），彙總 sum 會略過
    return raw, C.plats_in(raw)


SHEETS = ["說明與假設", "平台總計總覽", "客戶數統計與客戶排名", "聲活_年度發稿明細", "東吳_年度發稿明細", "鉑霖_年度發稿明細", "原始資料_發稿分析"]


def layout_sheet(s, name: str, raw: pd.DataFrame, plats: list[str], *, year_label: str, notes_lines: list[str],
                 sections: tuple[int, ...] = (1, 2, 3)) -> None:
    if name == "說明與假設":
        layout_notes(s, notes_lines)
    elif name == "平台總計總覽":
        layout_platform_overview(s, raw, plats, year_label)
    elif name == "客戶數統計與客戶排名":
        layout_customer_stats(s, raw, plats, year_label)
    elif name.endswith("_年度發稿明細"):
        layout_annual_detail(s, raw, plats, name.split("_")[0], year_label, sections)
    elif name == "原始資料_發稿分析":
        layout_raw(s, raw)
    else:
        raise KeyError(name)
