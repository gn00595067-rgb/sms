"""
layout.py — 六個舊 Access 財務報表的版面（照《舊業績系統現有功能》PDF 第 9–11、13、15–21、23–24、28–30 頁逐格排）

每個 layout_* 吃 compute.py 的結果，回傳 list[Grid]；Grid 交給 grid.to_html / grid.to_xlsx。
版面上的顏色、粗體、小計層級、方塊位置都照舊報表；只有下面幾處刻意跟舊的不同（見 CLAUDE_CODE_TASK_7.md §2 的「與舊報表的差異」）：
  - 舊報表因平台名「其他／其它」不一致而永遠是 0 的「其他」欄，新版會有值
  - 業績成本報表最後一頁「(3) 健康視」列（舊版空白）與「(4) 廣播 成本」（舊版 0）新版填真實值
  - 責任檔達成表每列的「製作成本」直接放在合約列上（舊版藏在隱藏列、只在小計出現）
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import compute as C
from .grid import Cell, Grid


# ---------------------------------------------------------------- 小工具
def M(v, **kw) -> Cell:      # 金額
    return Cell(v, "money", **kw)


def M2(v, **kw) -> Cell:     # 金額 2 位小數（舊報表的除佣實收方塊）
    return Cell(v, "money2", **kw)


def P(v, d: int = 2, **kw) -> Cell:   # 百分比
    return Cell(v, {0: "pct", 1: "pct1", 2: "pct2"}[d], **kw)


def T(v="", **kw) -> Cell:
    return Cell("" if v is None else v, "text", **kw)


def I(v, **kw) -> Cell:
    return Cell(v, "int", **kw)


def blanks(n: int, **kw) -> list[Cell]:
    return [Cell("", "text", **kw) for _ in range(n)]


def _period(ym_from: str, ym_to: str) -> str:
    return f"{ym_from} ~{ym_to}"


# ================================================================ 1. 業績成本報表(區間)  →  月業績成本報表（PDF 第 9–11 頁）
COST_COLS = ["組別", "業務", "合約編號", "客戶名稱", "廣告名稱", "上檔日期", "平台", "節目名稱", "實收金額", "除佣實收", "實付金額", "毛利", "毛利率", "媒體效益", "備註"]
COST_W = [7, 8, 14, 20, 16, 12, 10, 9, 10, 12, 10, 10, 9, 6, 8]


def _box(g: Grid, label: str, box: pd.DataFrame, first_fill: str) -> None:
    """業務／組別總業績方塊：從第 3 欄開始，右邊放 = A+…+G 與字母。"""
    off = blanks(2, cls="noborder")
    g.add(off + [T("類別", cls="b ctr", fill="grey"), T("實收金額", cls="b ctr", fill="grey"), T("除佣實收", cls="b ctr", fill="grey"),
                 T("實付金額", cls="b ctr", fill="grey"), T("毛利", cls="b ctr", fill="grey"), T("毛利率", cls="b ctr", fill="grey"), T(cls="noborder")], "kwn")
    tot = box.iloc[0]
    g.add(off + [T(f"{label}總業績", cls="b ctr", fill=first_fill), M(tot["gross"], cls="b", fill=first_fill), M2(tot["net"], cls="b", fill=first_fill),
                 M(tot["cost"], cls="b", fill=first_fill), M(tot["profit"], cls="b", fill=first_fill), P(tot["margin"], cls="b", fill=first_fill),
                 T("= A+B+C+D+E+F+G", span=3, cls="b noborder left")], "kwn")
    for _, r in box.iloc[1:].iterrows():
        memo = r["label"] == "製作費"
        z = (r["gross"] == 0 and r["net"] == 0 and r["cost"] == 0)
        fill = None if memo else "purple"
        cls = "grey" if memo else ""
        g.add(off + [T(r["label"], cls="b ctr", fill=fill),
                     M(None if z else r["gross"], cls=cls, fill=fill), M2(None if z else r["net"], cls=cls, fill=fill),
                     M(None if z else r["cost"], cls=cls, fill=fill), M(None if z else r["profit"], cls=cls, fill=fill),
                     P(None if z else r["margin"], cls=cls, fill=fill),
                     T(r["letter"] + ("（備註：已含在 A–G 內，不重複加）" if memo else ""), span=3, cls="b noborder left")], "kwn" if not memo else "")


def layout_cost_report(rep: C.CostReport, *, ym_from: str, ym_to: str, sales_text: str = "*", cat_text: str = "*") -> list[Grid]:
    g = Grid("月業績成本報表", widths=COST_W, landscape=True, font_size=8.5)
    n = len(COST_COLS)
    g.add([T(f"業務: {sales_text}", span=3, cls="b mid noborder left"),
           T(f"{_period(ym_from, ym_to)}  月業績成本報表", span=8, cls="b big noborder ctr"),
           T(f"客戶類別: {cat_text}", span=4, cls="b mid noborder left")], "title")
    g.gap()
    for gname, sps, gbox in rep.groups:
        for sname, contracts, sbox in sps:
            for cno, lines, sub in contracts:
                g.add([T(c, cls="b ctr wrap", fill="grey") for c in COST_COLS], "kwn")
                for i, (_, r) in enumerate(lines.iterrows()):
                    first = i == 0
                    g.add([T(r["business_group"], cls="ctr"), T(r["salesperson"] if first else "", cls="ctr"),
                           T(cno if first else "", cls="small"), T(r["customer"] if first else ""), T(r["ad_name"] if first else ""),
                           T(r["air_period_text"], cls="ctr"), T(r["platform"], cls="ctr"), T(r["program"]),
                           M(r["gross_amount"]), M(r["net_amount"]), M(r["cost_amount"]), M(r["net_amount"] - r["cost_amount"]),
                           P(C._ratio(r["net_amount"] - r["cost_amount"], r["net_amount"])), I(r["media_benefit"]), T(r["notes"], cls="small")])
                cust = lines.iloc[0]["customer"]
                g.add(blanks(3, cls="noborder") + [T(f"{cust} 小計", span=5, cls="b right", fill="cyan"),
                      M(sub["gross"], cls="b", fill="cyan"), M(sub["net"], cls="b", fill="cyan"), M(sub["cost"], cls="b", fill="cyan"),
                      M(sub["profit"], cls="b", fill="cyan"), P(sub["margin"], cls="b", fill="cyan")] + blanks(2, cls="noborder"))
                g.gap()
            _box(g, sname, sbox, "yellow")
            g.gap(2)
        _box(g, gname, gbox, "teal")
        g.gap(2)
    # 最後一頁：平台總表 + 企頻細項
    f = Grid("平台總表", widths=[3, 14, 12, 12, 12, 12, 10, 3, 10, 12], landscape=True, font_size=10, page_break_before=True)
    f.add([T(cls="noborder"), T(cls="noborder")] + [T(c, cls="b ctr", fill="grey") for c in ("實收金額", "除佣實收", "成本", "毛利", "毛利率")]
          + [T(cls="noborder"), T("廣播成本", span=2, cls="b ctr noborder")])
    for i, (_, r) in enumerate(rep.final.iterrows()):
        memo = r.get("memo") is True
        is_total = r["label"].startswith("(1)-(7)")
        fill = "cyan" if is_total else None
        cls = ("b" if is_total else "") + (" grey" if memo else "")
        z = memo and r["cost"] == 0 and r["gross"] == 0
        cells = [T(cls="noborder"), T(r["label"], cls=f"b ctr", fill=fill),
                 M(None if z else r["gross"], cls=cls, fill=fill), M(None if z else r["net"], cls=cls, fill=fill),
                 M(None if z else r["cost"], cls=cls, fill=fill), M(None if z else r["profit"], cls=cls, fill=fill),
                 P(None if z else r["margin"], cls=cls, fill=fill), T(cls="noborder")]
        if i == 0:
            cells += [T("合　計:", cls="b ctr", fill="orange"), M(rep.radio_cost, cls="b", fill="orange")]
        else:
            cells += blanks(2, cls="noborder")
        f.add(cells)
    f.add([T(cls="noborder"), T("實收與除佣實收差額:", span=2, cls="b right noborder"), M(rep.diff_gross_net, cls="b", fill="orange")] + blanks(6, cls="noborder"))
    f.add([T("（7）製作費為備註列：製作費線已含在 (1)–(6) 各平台內，不重複計入合計。廣播成本 = (4) 廣播 的成本。", span=10, cls="small grey noborder left")])
    f.gap(2)
    f.add([T(cls="noborder"), T("企頻細項", cls="b ctr", fill="grey")] + [T(c, cls="b ctr", fill="grey") for c in ("實收金額", "除佣實收", "成本", "毛利", "毛利率")] + blanks(3, cls="noborder"))
    for _, r in rep.cp_detail.iterrows():
        z = r["gross"] == 0 and r["net"] == 0 and r["cost"] == 0
        f.add([T(cls="noborder"), T(r["label"], cls="b ctr"), M(None if z else r["gross"]), M(None if z else r["net"]), M(None if z else r["cost"]),
               M(None if z else r["profit"]), P(None if z else r["margin"])] + blanks(3, cls="noborder"))
    return [g, f]


# ================================================================ 2. 媒體發稿量分析 → 月電台發稿量（PDF 第 13 頁）
MV_HEAD = ["排名", "電台", "客戶名稱", "實收金額", "實收佔比", "除佣實收", "除佣佔比", "發稿量", "發稿佔比", "毛利", "毛利佔比", "毛利%", "毛利+退佣", "毛利佔比", "毛利%"]
MV_W = [5, 9, 20, 11, 8, 11, 8, 11, 8, 11, 8, 8, 11, 8, 8]


def _mv_row(rk, ch, name, r, *, fill=None, bold=False) -> list[Cell]:
    b = "b" if bold else ""
    return [I(rk, cls=f"ctr {b}", fill=fill), T(ch, cls=f"ctr {b}", fill=fill or "lyellow"), T(name, cls=b, fill=fill),
            M(r["gross"], cls=f"b blue", fill=fill), P(r.get("gross_share"), 1, fill=fill), M(r["net"], cls=b, fill=fill), P(r.get("net_share"), 1, fill=fill),
            M(r["cost"], cls=b, fill=fill), P(r.get("cost_share"), 1, fill=fill), M(r["profit"], cls=b, fill=fill), P(r.get("profit_share"), 1, fill=fill),
            P(r["margin"], 1, cls=b, fill=fill), M(r["profit_rebate"], cls=b, fill=fill), P(r.get("profit_rebate_share"), 1, fill=fill),
            P(r["margin_rebate"], 1, cls=b, fill=fill)]


def layout_media_volume(groups: list[dict], *, version: str, sort_by: str, ym_from: str, ym_to: str) -> list[Grid]:
    title = f"{_period(ym_from, ym_to)} 月電台發稿量{version} 依{sort_by}排序"
    if version in ("客戶版", "業務版", "業務總表"):
        head = list(MV_HEAD)
        if version == "業務總表":
            head[2] = "業務"
        g = Grid(f"電台發稿量{version}", widths=MV_W, landscape=True, font_size=9, header_rows=2)
        g.title(title, len(head), cls="ctr")
        g.add([T(h, cls="b ctr wrap", fill="lyellow") for h in head])
        for grp in groups:
            rows, tot = grp["rows"], grp["totals"]
            for _, r in rows.iterrows():
                if version == "業務版" and r.get("level") == 1:
                    g.add(_mv_row(None, grp["channel"], f"【{r['salesperson']}】", r, fill="lgreen", bold=True))
                else:
                    g.add(_mv_row(r["rank"], grp["channel"], r.get("customer") if version != "業務總表" else r["salesperson"], r))
            t = {**tot.to_dict(), "gross_share": 1.0, "net_share": 1.0, "cost_share": 1.0, "profit_share": 1.0, "profit_rebate_share": 1.0}
            g.add(_mv_row(None, grp["channel"], "合計", t, fill="lyellow", bold=True))
        return [g]
    if version == "電台總表":
        head = ["排名", "電台", "實收金額", "除佣實收", "發稿量(實付)", "毛利", "毛利%", "電台退佣", "毛利+退佣", "毛利%"]
        g = Grid("電台總表", widths=[5, 12, 12, 12, 12, 12, 8, 12, 12, 8], landscape=False, font_size=10, header_rows=2)
        g.title(title, len(head), cls="ctr")
        g.add([T(h, cls="b ctr", fill="lyellow") for h in head])
        for i, grp in enumerate(groups, start=1):
            t = grp["totals"]
            g.add([I(i, cls="ctr"), T(grp["channel"], fill="lyellow"), M(t["gross"], cls="b blue"), M(t["net"]), M(t["cost"]), M(t["profit"]),
                   P(t["margin"], 1), M(t["rebate"]), M(t["profit_rebate"]), P(t["margin_rebate"], 1)])
        tot = {k: sum(grp["totals"][k] for grp in groups) for k in ("gross", "net", "cost", "profit", "rebate", "profit_rebate")}
        g.add([T(cls="noborder"), T("合計", cls="b ctr", fill="lyellow"), M(tot["gross"], cls="b blue", fill="lyellow"), M(tot["net"], cls="b", fill="lyellow"),
               M(tot["cost"], cls="b", fill="lyellow"), M(tot["profit"], cls="b", fill="lyellow"), P(C._ratio(tot["profit"], tot["net"]), 1, cls="b", fill="lyellow"),
               M(tot["rebate"], cls="b", fill="lyellow"), M(tot["profit_rebate"], cls="b", fill="lyellow"), P(C._ratio(tot["profit_rebate"], tot["net"]), 1, cls="b", fill="lyellow")])
        return [g]
    # 明細版
    head = ["電台", "平台", "合約編號", "客戶名稱", "客戶類別", "廣告名稱", "上檔日期", "節目名稱", "實收金額", "退佣折扣", "除佣實收", "實付金額", "組別", "業務",
            "業績年月", "業績類別", "產業別", "退佣%", "電台退佣", "備註"]
    g = Grid("電台發稿量明細", widths=[8, 8, 11, 16, 6, 14, 11, 8, 10, 6, 10, 10, 7, 7, 7, 8, 8, 6, 9, 10], landscape=True, font_size=8, header_rows=2)
    g.title(title, len(head), cls="ctr")
    g.add([T(h, cls="b ctr wrap", fill="lyellow") for h in head])
    for grp in groups:
        for _, r in grp["rows"].iterrows():
            g.add([T(r["media_channel"], fill="lyellow"), T(r["platform"]), T(r["contract_no"]), T(r["customer"]), T(r["customer_category"]), T(r["ad_name"]),
                   T(r["air_period_text"], cls="ctr"), T(r["program"]), M(r["gross_amount"], cls="blue"), P(r.get("rebate_pct", 0) / 100 if r.get("rebate_pct") is not None else None, 0),
                   M(r["net_amount"]), M(r["cost_amount"]), T(r["business_group"]), T(r["salesperson"]), T(r["ym"], cls="ctr"), T(r["sales_category"]), T(r["industry"]),
                   P(r["channel_rebate_pct"] / 100, 2), M(r["channel_rebate_amount"]), T(r["notes"])])
        t = grp["totals"]
        g.add([T(f"{grp['channel']} 合計", span=8, cls="b right", fill="lyellow"), M(t["gross"], cls="b blue", fill="lyellow"), T(fill="lyellow"), M(t["net"], cls="b", fill="lyellow"),
               M(t["cost"], cls="b", fill="lyellow")] + blanks(6, fill="lyellow") + [M(t["rebate"], cls="b", fill="lyellow"), T(fill="lyellow")])
    return [g]


# ================================================================ 3a. 綜合成本毛利分析（PDF 第 15 頁）
COMB_W = [11, 10, 10, 10, 10, 10, 1, 13, 10, 10, 10, 11]
_LEFT = ["全家", "家樂福", "企頻小計", "新鮮視", "健康視"]
_RIGHT = ["合計(企+新+健)", "廣播", "其他", "營運", "總計"]
_COLFILL = {"企頻小計": "lorange", "合計(企+新+健)": "lyellow", "廣播": "lgreen", "其他": "lgreen", "營運": "lgreen", "總計": "lgreen"}


def _comb_head(g: Grid, label: str, label_fill: str) -> None:
    g.add([T(label, cls="b ctr", fill=label_fill)] + [T(c, cls="b ctr", fill="lblue") for c in _LEFT] + [T(cls="noborder")]
          + [T("合計(企+新+健)", cls="b ctr", fill="lyellow")] + [T(c, cls="b ctr", fill="lgreen") for c in _RIGHT[1:]], "kwn")


def _comb_row(g: Grid, label: str, r, kind_money: bool, *, label_fill=None, bold=False) -> None:
    b = "b" if bold else ""
    def cell(c):
        v = r[c]
        return (M(v, cls=b, fill=_COLFILL.get(c)) if kind_money else P(v, 0, cls=b, fill=_COLFILL.get(c)))
    g.add([T(label, cls=f"b ctr", fill=label_fill)] + [cell(c) for c in _LEFT] + [T(cls="noborder")] + [cell(c) for c in _RIGHT])


def layout_combined(res: dict, *, ym_from: str, ym_to: str, cust_text: str = "*") -> list[Grid]:
    g = Grid("綜合成本毛利分析", widths=COMB_W, landscape=True, font_size=10)
    g.add([T(cust_text, span=2, cls="b mid noborder left"), T(f"{ym_from} ~ {ym_to}  綜合成本毛利分析", span=10, cls="b big noborder ctr")], "title")
    g.gap()
    _comb_head(g, "媒體頻道", "pink")
    for _, r in res["channel"].iterrows():
        _comb_row(g, r["label"], r, r["label"] != "毛利率")
    g.gap()
    out = [g]
    for i, (lab, df) in enumerate(res["by_group"].items()):
        if i == 2:   # 第 3 個區塊起換頁（舊報表：媒體頻道 + 實收 + 除佣 一頁）
            g = Grid(f"綜合成本毛利分析（續）", widths=COMB_W, landscape=True, font_size=10, page_break_before=True)
            out.append(g)
        _comb_head(g, lab, "purple")
        for _, r in df.iterrows():
            kind = r.get("kind", "")
            _comb_row(g, r["label"], r, lab != "毛利率", label_fill="lgreen", bold=(kind == "total"))
        g.gap()
    return out


# ================================================================ 3b. 客戶同期比較表（PDF 第 16 頁）
def layout_period_compare(res: dict, *, ym_from: str, ym_to: str, year: int, plat_text: str = "*", exclude_text: str = "") -> list[Grid]:
    y0, y1 = str(year), str(year - 1)
    g = Grid("客戶同期比較表", widths=[6, 22, 14, 14, 12, 8, 12, 12, 12, 8, 10, 10], landscape=True, font_size=10)
    g.add([T(f"平台: {plat_text}", span=2, cls="b mid noborder left blue"), T(f"{ym_from} ~ {ym_to} 客戶同期比較表", span=7, cls="b big noborder ctr"),
           T(f"排除: {exclude_text}", span=3, cls="b mid noborder left")], "title")
    g.gap()
    head = ["平台", f"{y0} 除佣實收", f"{y1} 除佣實收", "營收成長", "成長率", f"{y0} 毛利", f"{y1} 毛利", "毛利成長", "成長率", f"{y0} 營收", f"{y1} 營收"]
    g.add([T(cls="noborder")] + [T(h, cls="b ctr", fill="lyellow") for h in head], "kwn")
    fills = {"總計": None, "企頻": "lgreen", "新鮮視": None, "其他(廣播)": "lpink"}
    for _, r in res["platform"].iterrows():
        f = fills.get(r["label"])
        c = "magenta b" if r["label"] == "總計" else "b"
        g.add([T(cls="noborder"), T(r["label"], cls="b ctr", fill=f), M(r["net_cur"], cls=c, fill=f), M(r["net_prev"], cls=c, fill=f), M(r["net_growth"], cls=c, fill=f),
               P(r["net_rate"], 0, cls=c, fill=f), M(r["profit_cur"], cls=c, fill=f), M(r["profit_prev"], cls=c, fill=f), M(r["profit_growth"], cls=c, fill=f),
               P(r["profit_rate"], 0, cls=c, fill=f), P(r["share_cur"], 0, cls="b", fill=f), P(r["share_prev"], 0, cls="b", fill=f)])
    g.gap()
    h2 = ["排名", "客戶名稱", f"{y0} 除佣實收", f"{y1} 除佣實收", "營收成長", "成長率", f"{y0} 毛利", f"{y1} 毛利", "毛利成長", "成長率", f"{y0}業務", f"{y1}業務"]
    c2 = Grid("客戶同期比較表_客戶", widths=g.widths, landscape=True, font_size=10, header_rows=1)
    c2.add([T(h, cls="b ctr", fill="lyellow") for h in h2])
    for _, r in res["customers"].iterrows():
        c2.add([I(r["rank"], cls="ctr blue b"), T(r["customer"]), M(r["net_cur"], fill="orange"), M(r["net_prev"], fill="blue"), M(r["net_growth"]), P(r["net_rate"], 0),
                M(r["profit_cur"]), M(r["profit_prev"]), M(r["profit_growth"]), P(r["profit_rate"], 0), T(r["sp_cur"], cls="ctr"), T(r["sp_prev"], cls="ctr")])
    return [g, c2]


# ================================================================ 3c. 月業績認定表（PDF 第 17–18 頁）
REC_HEAD = ["合約編號", "客戶名稱", "廣告名稱", "上檔日期", "實收金額\nA", "除佣實收\nB", "實付金額\nC不含D", "製作費\n成本 D", "業績項目"]
REC_W = [13, 17, 17, 11, 12, 12, 12, 12, 8]


def layout_recognition(res: list[dict], *, ym_from: str, ym_to: str) -> list[Grid]:
    out = []
    for k, sp in enumerate(res):
        g = Grid(f"認定表_{sp['salesperson']}"[:31], widths=REC_W, landscape=False, font_size=9, page_break_before=(k > 0))
        g.add([T(f"{ym_from} ~ {ym_to}  月業績認定表", span=6, cls="b big noborder left"), T(f"業務: {sp['salesperson']}", span=3, cls="b big noborder left")], "title")
        for mo in sp["months"]:
            g.add([T(mo["ym"], span=2, cls="b mid ctr", fill="gold")] + blanks(7, cls="noborder"))
            g.gap()
            for blk in mo["blocks"]:
                g.add([T(h, cls="b ctr wrap", fill="lyellow") for h in REC_HEAD], "kwn", height=34)
                for _, r in blk["rows"].iterrows():
                    g.add([T(r["contract_no"]), T(r["customer"]), T(r["ad_name"]), T(r["air"], cls="ctr"), M(r["gross"]), M(r["net"]), M(r["cost"]), M(r["prod_cost"]), T(r["item"], cls="ctr")])
                t = blk["totals"]
                g.add([T(blk["platform"], span=4, cls="b ctr blue", fill="orange"), M(t["gross"], cls="b", fill="orange"), M(t["net"], cls="b", fill="orange"),
                       M(t["cost"], cls="b", fill="orange"), M(t["prod_cost"], cls="b", fill="orange"), T(fill="orange")])
                g.add(blanks(5, cls="noborder") + [T("除佣-製作", span=2, cls="b ctr", fill="blue"), M(t["recognized"], cls="b", fill="orange"), T(cls="noborder")])
                g.gap(2)
        g.gap(2)
        g.add([T("財務:", cls="right noborder"), T(ul=True), T("業務:", cls="right noborder"), T(ul=True), T("製表:", cls="right noborder"), T(ul=True)] + blanks(3, cls="noborder"))
        out.append(g)
    return out


# ================================================================ 3d. 月獎金計算總表（PDF 第 19 頁）
BONUS_HEAD = ["組別", "業務", "月份"] + C.FIN_PLATFORMS + ["實收金額", "除佣實收", "製作成本", "認定業績\n除佣-製作"]
BONUS_W = [7, 9, 5, 10, 10, 10, 10, 10, 9, 9, 11, 11, 10, 11]
_PCOLOR = {"全家企頻": "magenta", "家樂福企頻": "green", "新鮮視": "green", "健康視": "teal", "廣播": "orange", "其他": "orange", "營運": "blue"}


def layout_bonus_summary(df: pd.DataFrame, *, ym_from: str, ym_to: str, sales_text: str = "*", group_text: str = "*") -> list[Grid]:
    g = Grid("月獎金計算總表", widths=BONUS_W, landscape=True, font_size=10, header_rows=2)
    g.add([T(f"{ym_from} ~ {ym_to} 月獎金計算總表 業務: {sales_text}", span=9, cls="b big noborder left"), T(f"組別: {group_text}", span=5, cls="b big noborder left")], "title")
    g.add([T(h, cls="b ctr wrap", fill="lyellow") for h in BONUS_HEAD], height=32)
    for _, r in df.iterrows():
        if r["kind"] == "total":
            f = "cyan"
            g.add([T(r["salesperson"], span=3, cls="b ctr", fill=f)] + [M(r[p], cls="b", fill=f) for p in C.FIN_PLATFORMS]
                  + [M(r["gross"], cls="b", fill=f), M(r["net"], cls="b", fill=f), M(r["prod_cost"], cls="b", fill=f), M(r["recognized"], cls="b", fill=f)])
            g.gap()
        else:
            g.add([T(r["group"], cls="ctr"), T(r["salesperson"], cls="ctr"), T(r["month"], cls="ctr")] + [M(r[p], cls=_PCOLOR[p]) for p in C.FIN_PLATFORMS]
                  + [M(r["gross"]), M(r["net"]), M(r["prod_cost"]), M(r["recognized"])], "kwn")
    g.gap()
    g.add([T("核准:", cls="right noborder"), T(ul=True, span=2)] + blanks(4, cls="noborder") + [T("製表:", cls="right noborder"), T(ul=True, span=2)] + blanks(4, cls="noborder"))
    return [g]


# ---------------------------------------------------------------- 3d'. 月獎金計算總表（製作成本分平台，A3）
BONUS_PC_W = [7, 9, 5] + [9] * 7 + [11, 11] + [9] * 7 + [11, 11]   # 3 + 7除佣 + 2 + 7製作 + 2 = 21 欄


def layout_bonus_summary_platform_cost(df: pd.DataFrame, *, ym_from: str, ym_to: str, sales_text: str = "*", group_text: str = "*") -> list[Grid]:
    """同 3d 月獎金計算總表，但每平台同時列「除佣實收」與「製作成本」兩組欄（A3 橫向）。"""
    n = len(BONUS_PC_W)
    g = Grid("月獎金計算總表(製作成本分平台)", widths=BONUS_PC_W, landscape=True, paper="A3", font_size=9, header_rows=3)
    g.add([T(f"{ym_from} ~ {ym_to} 月獎金計算總表（製作成本分平台） 業務: {sales_text}", span=n - 5, cls="b big noborder left"),
           T(f"組別: {group_text}", span=5, cls="b big noborder left")], "title")
    # 表頭第一列：分群（除佣實收（分平台）／製作成本（分平台））
    g.add([T("組別", cls="b ctr wrap", fill="lyellow", rowspan=2), T("業務", cls="b ctr wrap", fill="lyellow", rowspan=2), T("月份", cls="b ctr wrap", fill="lyellow", rowspan=2),
           T("除佣實收（分平台）", span=7, cls="b ctr", fill="lyellow"),
           T("實收金額", cls="b ctr wrap", fill="lyellow", rowspan=2), T("除佣實收", cls="b ctr wrap", fill="lyellow", rowspan=2),
           T("製作成本（分平台）", span=7, cls="b ctr", fill="lorange"),
           T("製作成本\n合計", cls="b ctr wrap", fill="lorange", rowspan=2), T("認定業績\n除佣-製作", cls="b ctr wrap", fill="lyellow", rowspan=2)], height=20)
    # 表頭第二列：兩組平台名
    g.add([T(p, cls="b ctr wrap", fill="lyellow") for p in C.FIN_PLATFORMS] + [T(p, cls="b ctr wrap", fill="lorange") for p in C.FIN_PLATFORMS], height=30)
    for _, r in df.iterrows():
        if r["kind"] == "total":
            f = "cyan"
            g.add([T(r["salesperson"], span=3, cls="b ctr", fill=f)]
                  + [M(r[p], cls="b", fill=f) for p in C.FIN_PLATFORMS]
                  + [M(r["gross"], cls="b", fill=f), M(r["net"], cls="b", fill=f)]
                  + [M(r[f"{p}__pc"], cls="b", fill=f) for p in C.FIN_PLATFORMS]
                  + [M(r["prod_cost"], cls="b", fill=f), M(r["recognized"], cls="b", fill=f)])
            g.gap()
        else:
            g.add([T(r["group"], cls="ctr"), T(r["salesperson"], cls="ctr"), T(r["month"], cls="ctr")]
                  + [M(r[p], cls=_PCOLOR[p]) for p in C.FIN_PLATFORMS]
                  + [M(r["gross"]), M(r["net"])]
                  + [M(r[f"{p}__pc"], cls=_PCOLOR[p]) for p in C.FIN_PLATFORMS]
                  + [M(r["prod_cost"]), M(r["recognized"])], "kwn")
    g.gap()
    g.add([T("核准:", cls="right noborder"), T(ul=True, span=2)] + blanks(4, cls="noborder")
          + [T("製表:", cls="right noborder"), T(ul=True, span=2)] + blanks(n - 10, cls="noborder"))
    return [g]


# ================================================================ 3e. 業務發稿統計報表 A3（PDF 第 20–21 頁）
_WFILL = {"企頻": "lgreen", "新鮮視": "lpink", "廣播": "gold"}


def layout_wave_stats(res: dict, *, ym_from: str, ym_to: str) -> list[Grid]:
    top = Grid("業務發稿統計_業務", widths=[11, 6, 6, 10, 10, 12, 12, 12, 7] + [6, 10, 12, 12, 12, 7] * 3, landscape=True, paper="A3", font_size=8.5, header_rows=3)
    n = 9 + 18
    top.title(f"{ym_from} ~ {ym_to} 業務發稿統計報表 (依除佣實收排序)", n, cls="left")
    h1 = ["業務", "客戶數", "執行\n波段", "平均單波\n實收", "平均單波\n毛利", "實收金額", "除佣實收", "帳上毛利", "毛利率"]
    top.add([T(h, cls="b ctr wrap", fill="lyellow", rowspan=2) for h in h1] + [T(p, span=6, cls="b ctr", fill=_WFILL[p]) for p in C.WAVE_PLATS], height=30)
    top.add([T(h, cls="b ctr", fill=_WFILL[p]) for p in C.WAVE_PLATS for h in ("波段", "單波實收", "實收金額", "除佣實收", "帳上毛利", "毛利率")])

    def wave_cells(r, *, fill=None, bold=False):
        b = "b" if bold else ""
        cells = []
        for p in C.WAVE_PLATS:
            cells += [I(r[f"{p}_waves"], cls=f"ctr blue {b}", fill=fill), M(r[f"{p}_avg_gross"], cls=b, fill=fill), M(r[f"{p}_gross"], cls=b, fill=fill),
                      M(r[f"{p}_net"], cls=f"blue {b}", fill=fill), M(r[f"{p}_profit"], cls=f"blue {b}", fill=fill), P(r[f"{p}_margin"], 0, cls=b, fill=fill)]
        return cells

    for _, r in res["top"].iterrows():
        top.add([T(r["salesperson"], cls="b"), I(r["customers"], cls="ctr"), I(r["waves"], cls="ctr blue b"), M(r["avg_gross"]), M(r["avg_profit"]),
                 M(r["gross"]), M(r["net"]), M(r["profit"]), P(r["margin"], 0)] + wave_cells(r))
    t = res["total"]
    top.add([T("總計", cls="b ctr", fill="lgreen"), I(t["customers"], cls="ctr b", fill="lgreen"), I(t["waves"], cls="ctr b", fill="lgreen"), M(t["avg_gross"], cls="b", fill="lgreen"),
             M(t["avg_profit"], cls="b", fill="lgreen"), M(t["gross"], cls="b", fill="lgreen"), M(t["net"], cls="b", fill="lgreen"), M(t["profit"], cls="b", fill="lgreen"),
             P(t["margin"], 0, cls="b", fill="lgreen")] + wave_cells(t, fill="lgreen", bold=True))

    det = Grid("業務發稿統計_客戶廣告", widths=[10, 16, 18, 5, 9, 9] + [11, 11, 11, 7] * 4 + [10], landscape=True, paper="A3", font_size=8.5, header_rows=2)
    det.add([T(h, cls="b ctr wrap", fill="lyellow", rowspan=2) for h in ("業務", "客戶名稱", "廣告名稱", "執行\n波段", "平均單波\n實收", "平均單波\n毛利")]
            + [T(f"{ym_from}-{ym_to} 合計", span=4, cls="b ctr", fill="cyan")] + [T(p, span=4, cls="b ctr", fill=_WFILL[p]) for p in C.WAVE_PLATS]
            + [T("業務", cls="b ctr", fill="lyellow", rowspan=2)], height=30)
    det.add([T(h, cls="b ctr", fill=f) for f in ["cyan"] + [_WFILL[p] for p in C.WAVE_PLATS] for h in ("實收金額", "除佣實收", "帳上毛利", "毛利率")])

    def blocks(r, *, fill=None, bold=False, blue=False):
        b = ("b " if bold else "") + ("blue" if blue else "")
        cells = [M(r["gross"], cls=b, fill=fill), M(r["net"], cls=b, fill=fill), M(r["profit"], cls=b, fill=fill), P(r["margin"], 0, cls=b, fill=fill)]
        for p in C.WAVE_PLATS:
            cells += [M(r[f"{p}_gross"], cls=f"blue {'b' if bold else ''}", fill=fill), M(r[f"{p}_net"], cls=f"blue {'b' if bold else ''}", fill=fill),
                      M(r[f"{p}_profit"], cls=f"blue {'b' if bold else ''}", fill=fill), P(r[f"{p}_margin"], 0, cls=b, fill=fill)]
        return cells

    for sp in res["detail"]:
        for cu in sp["customers"]:
            for _, r in cu["ads"].iterrows():
                det.add([T(sp["salesperson"]), T(cu["customer"]), T(r["ad_name"]), I(r["waves"], cls="ctr blue b"), T(), T()] + blocks(r) + [T(sp["salesperson"])])
            s = cu["sub"]
            det.add([T(fill="lgreen"), T(cu["customer"], cls="b", fill="lgreen"), T(fill="lgreen"), I(s["waves"], cls="ctr blue b", fill="lgreen"), M(s["avg_gross"], fill="lgreen"),
                     M(s["avg_profit"], fill="lgreen")] + blocks(s, fill="lgreen", bold=True) + [T(cu["customer"], fill="lgreen")])
        t = sp["total"]
        det.add([T(f"{sp['salesperson']} 合計", span=3, cls="b ctr", fill="orange"), I(t["waves"], cls="ctr b", fill="orange"), M(t["avg_gross"], cls="b", fill="orange"),
                 M(t["avg_profit"], cls="b", fill="orange")] + blocks(t, fill="orange", bold=True) + [T(sp["salesperson"], cls="b", fill="orange")])
        det.gap()
    return [top, det]


# ================================================================ 4. 月責任檔業績達成表（PDF 第 23–24 頁）
ACH_HEAD = ["組別", "業務", "合約編號", "客戶", "廣告名稱", "實收金額", "製作成本", "認定業績", "執行日期"]
ACH_W = [9, 9, 13, 17, 16, 12, 11, 12, 12]


def layout_achievement(res: list[dict], *, ym_from: str, ym_to: str) -> list[Grid]:
    g = Grid("月責任檔業績達成表", widths=ACH_W, landscape=False, font_size=10, header_rows=2)
    period = ym_from if ym_from == ym_to else f"{ym_from} ~ {ym_to}"
    g.add([T(period, span=3, cls="b big noborder left"), T("月責任檔業績達成表", span=6, cls="b big noborder ctr")], "title")
    g.add([T(h, cls="b ctr") for h in ACH_HEAD])
    for grp in res:
        for sp in grp["salespeople"]:
            for cat in sp["categories"]:
                for i, (_, r) in enumerate(cat["rows"].iterrows()):
                    g.add([T(grp["group"] if i == 0 else "", cls="ctr"), T(sp["salesperson"] if i == 0 else "", cls="ctr"), T(r["contract_no"], cls="small"),
                           T(r["customer"]), T(r["ad_name"]), M(r["gross"]), M(r["prod_cost"]), M(r["recognized"]), T(r["air"], cls="ctr small")])
                s = cat["sub"]
                g.add(blanks(3, cls="noborder") + [T(f"{cat['category']} 小計", span=2, cls="b ctr", fill="lorange"), M(s["gross"], fill="lorange"), M(s["prod_cost"], fill="lorange"),
                      M(s["recognized"], fill="lorange"), T(cls="noborder")])
            t = sp["total"]
            g.add([T(fill="cyan"), T("合計", cls="b ctr", fill="cyan"), T(fill="cyan"), T(fill="cyan"), T(fill="cyan"), M(t["gross"], cls="b", fill="cyan"),
                   M(t["prod_cost"], cls="b", fill="cyan"), M(t["recognized"], cls="b", fill="cyan"), T(fill="cyan")])
        t = grp["total"]
        g.add([T("總計", cls="b ctr", fill="yellow"), T(fill="yellow"), T(fill="yellow"), T(fill="yellow"), T(fill="yellow"), M(t["gross"], cls="b", fill="yellow"),
               M(t["prod_cost"], cls="b", fill="yellow"), M(t["recognized"], cls="b", fill="yellow"), T(fill="yellow")])
        g.gap()
    return [g]


# ================================================================ 5. 三單：廣告時段採購申請單（PDF 第 28–29 頁）
COMPANY_FULL = {"聲活": "聲活數位科技股份有限公司", "東吳": "東吳廣告股份有限公司", "鉑霖": "鉑霖行動行銷股份有限公司", "瑞迪": "瑞迪廣告股份有限公司"}
PR_W = [5, 13, 5, 14, 11, 11, 9, 11, 11, 12, 9]


def layout_purchase_request(pr: dict, *, contract_no: str, customer: str, group: str, ad_name: str, salesperson: str,
                            company: str = "聲活", today: date | None = None) -> list[Grid]:
    today = today or date.today()
    g = Grid("廣告時段採購申請單", widths=PR_W, landscape=False, font_size=10)
    n = len(PR_W)
    g.add([T(COMPANY_FULL.get(company, company), span=n, cls="b big noborder ctr")], "title")
    g.add([T("廣告時段採購申請單", span=n, cls="b mid noborder ctr")], "title")
    g.add(blanks(8, cls="noborder") + [T("日期", cls="b ctr"), T(f"{today.year} 年 {today.month:02d} 月 {today.day:02d} 日", span=2, cls="b ctr")])
    g.add([T("CUE表編號", span=2, cls="b ctr"), T(contract_no, span=3, cls="b ctr"), T("客戶名稱", span=2, cls="b ctr"), T(customer, span=4, cls="b ctr")])
    g.add([T("業務部門別", span=2, cls="b ctr"), T(group, span=3, cls="b ctr"), T("廣告名稱", span=2, cls="b ctr"), T(ad_name, span=4, cls="b ctr")])
    g.add([T("請購內容詳如CUE表.", span=n, cls="small noborder left")])
    g.add([T("業務處填單", span=4, cls="b ctr"), T("媒體處採購填單", span=6, cls="b ctr"), T("財務填單", cls="b ctr")])
    g.add([T("序號", cls="b ctr wrap", rowspan=2), T("購買電台\n（廠商）", cls="b ctr wrap", rowspan=2), T("%", cls="b ctr", rowspan=2), T("上檔期間", cls="b ctr", rowspan=2),
           T("實際成本", cls="b ctr"), T("實際_\n現折後", cls="b ctr small wrap"), T("現折金額", cls="b ctr"), T("應付金額", cls="b ctr"), T("應付_\n現折後", cls="b ctr small wrap"),
           T("備註", cls="b ctr", rowspan=2), T("實際付\n款日", cls="b ctr wrap", rowspan=2)], height=30)
    g.add([T("財務實付金額", span=5, cls="b ctr")])
    for i, (_, r) in enumerate(pr["rows"].iterrows(), start=1):
        g.add([I(i, cls="ctr b", rowspan=2), T(r["media_channel"], cls="ctr b", rowspan=2), P(r["pct"], 0, cls="ctr", rowspan=2), T(r["air_period_text"], cls="ctr", rowspan=2),
               M(r["actual"], cls="b"), M(r["actual_after"], cls="grey"), M(r["discount"], cls="blue"), M(r["payable"], cls="b"), M(r["payable_after"], cls="blue b"),
               T(r["purchase_note"] or "", cls="small wrap", rowspan=2), T(rowspan=2)])
        g.add(blanks(5))
    t = pr["totals"]
    g.add(blanks(4, cls="noborder") + [T("實際成本", cls="b ctr"), T("實際_\n現折後", cls="b ctr small wrap"), T("現折金額", cls="b ctr"), T("應付金額", cls="b ctr"), T("應付_\n現折後", cls="b ctr small wrap")] + blanks(2, cls="noborder"))
    g.add([T("合計", span=3, cls="b ctr", rowspan=2), T("應付金額", cls="b ctr"), M(t["actual"], cls="b"), M(t["actual_after"], cls="grey"), M(t["discount"], cls="blue"),
           M(t["payable"], cls="b"), M(t["payable_after"], cls="blue b"), T("備註:應付由媒體處填寫", span=2, cls="small")])
    g.add([T("實付金額", cls="b ctr")] + blanks(5) + [T("備註:實付由財務處填寫", span=2, cls="small")])
    for k in ("好事", "城市"):
        nv = pr["networks"][k]
        g.add(blanks(4, cls="noborder") + [T(f"{k}聯播網總額", span=3, cls="b ctr"), M(nv["payable"], cls="b"), M(nv["payable_after"], cls="blue b")] + blanks(2, cls="noborder"))
    g.gap()
    g.add(blanks(2, cls="noborder") + [T("除佣實收", span=2, cls="grey right noborder"), M(pr["net"], cls="grey noborder"), M(pr["profit"], cls="grey noborder"), P(pr["margin"], 2, cls="grey noborder")] + blanks(4, cls="noborder"))
    g.gap(6)
    g.add([T("核准", cls="b ctr wrap", rowspan=2), T(span=3, rowspan=2), T("營管處", cls="b ctr wrap", rowspan=2), T("財務", cls="b ctr"), T(span=2), T("媒體", cls="b ctr"), T(span=2)], height=30)
    g.add([T("會計", cls="b ctr"), T(span=2), T("業務", cls="b ctr"), T(salesperson, span=2, cls="ctr")], height=30)
    g.add(blanks(5, cls="noborder") + [T("後補:", cls="b right noborder"), T("☐ 發票申請單", span=2, cls="noborder"), T("☐ 收款明細表", span=2, cls="noborder"), T(cls="noborder")])
    g.add(blanks(6, cls="noborder") + [T("☐ 回簽正本", span=2, cls="noborder")] + blanks(3, cls="noborder"))
    return [g]


# ================================================================ 5b. 發票開立申請單（舊系統無樣張；依 發票開立資料表 欄位設計）
def layout_invoice_request(inv: pd.DataFrame, *, contract_no: str, customer: str, group: str, ad_name: str, salesperson: str,
                           air_text: str, company: str = "聲活", today: date | None = None) -> list[Grid]:
    today = today or date.today()
    g = Grid("發票開立申請單", widths=[9, 12, 14, 9, 8, 11, 11, 10, 10, 10, 10, 12], landscape=True, font_size=10)
    n = 12
    g.add([T(COMPANY_FULL.get(company, company), span=n, cls="b big noborder ctr")], "title")
    g.add([T("發票開立申請單", span=n, cls="b mid noborder ctr")], "title")
    g.add(blanks(8, cls="noborder") + [T("日期", cls="b ctr"), T(f"{today.year} 年 {today.month:02d} 月 {today.day:02d} 日", span=3, cls="b ctr")])
    g.add([T("CUE表編號", cls="b ctr"), T(contract_no, span=2, cls="b ctr"), T("客戶名稱", cls="b ctr"), T(customer, span=4, cls="b ctr"), T("業務部門別", cls="b ctr"), T(group, span=3, cls="b ctr")])
    g.add([T("廣告名稱", cls="b ctr"), T(ad_name, span=2, cls="b ctr"), T("上檔期間", cls="b ctr"), T(air_text, span=4, cls="b ctr"), T("業務", cls="b ctr"), T(salesperson, span=3, cls="b ctr")])
    g.gap()
    head = ["單號", "發票號碼", "客戶公司抬頭", "統一編號", "收款方式", "廣告收入", "製作收入", "銷貨折讓", "折讓單金額", "發票折讓", "預定兌現日", "備註"]
    g.add([T(h, cls="b ctr", fill="lyellow") for h in head], "kwn")
    for _, r in inv.iterrows():
        g.add([T(r.get("request_no"), cls="ctr"), T(r.get("invoice_no")), T(r.get("customer_title")), T(r.get("customer_tax_id"), cls="ctr"), T(r.get("payment_method"), cls="ctr"),
               M(r.get("ad_income")), M(r.get("production_income")), M(r.get("sales_allowance")), M(r.get("allowance_note_amount")), M(r.get("invoice_allowance_amount")),
               Cell(r.get("expected_cash_on"), "date"), T(r.get("notes"), cls="small")])
    if len(inv):
        g.add([T("合計", span=5, cls="b ctr", fill="lyellow"), M(inv["ad_income"].sum(), cls="b", fill="lyellow"), M(inv["production_income"].sum(), cls="b", fill="lyellow"),
               M(inv["sales_allowance"].sum(), cls="b", fill="lyellow"), M(inv["allowance_note_amount"].sum(), cls="b", fill="lyellow"),
               M(inv["invoice_allowance_amount"].sum(), cls="b", fill="lyellow"), T(fill="lyellow"), T(fill="lyellow")])
    g.gap(5)
    g.add([T("核准", cls="b ctr", rowspan=2), T(span=3, rowspan=2), T("財務", cls="b ctr"), T(span=2), T("會計", cls="b ctr"), T(span=2), T("業務", cls="b ctr"), T(salesperson, span=2, cls="ctr")], height=30)
    g.add([T("媒體", cls="b ctr"), T(span=2), T("製表", cls="b ctr"), T(span=2), T(cls="noborder"), T(span=2, cls="noborder")], height=30)
    return [g]


# ================================================================ 6. 電台預付明細表（PDF 第 31 頁）
PP_HEAD1 = ["序號", "電台", "CUE號", "客戶名稱", "廣告名稱", "上檔日期", "應付金額", "預計付\n款日", "已付", "備註"]
PP_HEAD2 = ["實付金額", "傳票編號", "累計實付金額", "財務確認\n(簽名+日期)", "備註"]
PP_W = [4, 9, 12, 16, 12, 11, 10, 7, 4, 14, 10, 10, 10, 12, 10]


def layout_prepay(groups: list[dict], *, d_from: str, d_to: str, channel_text: str = "*") -> list[Grid]:
    g = Grid("電台預付明細表", widths=PP_W, landscape=True, font_size=9, header_rows=3)
    g.add([T(f"{d_from} ~{d_to}", span=6, cls="b big noborder ctr"), T(channel_text, span=2, cls="b big noborder ctr"), T("電台預付明細表", span=7, cls="b big noborder left")], "title")
    g.add([T("業務處填寫", span=10, cls="b ctr small", fill="grey"), T("財務處填寫", span=5, cls="b ctr small", fill="grey")])
    g.add([T(h, cls="b ctr wrap small", fill="white") for h in PP_HEAD1] + [T(h, cls="b ctr wrap small", fill="white") for h in PP_HEAD2], height=30)
    for grp in groups:
        for _, r in grp["rows"].iterrows():
            g.add([I(r["seq"], cls="ctr b"), T(r["media_channel"], cls="ctr b"), T(r["contract_no"], cls="b small"), T(r["customer"], cls="wrap small"), T(r["ad_name"], cls="wrap small"),
                   T(r["air_period_text"], cls="ctr"), M(r["cost_amount"]), Cell(r["prepay_on"], "md", cls="ctr"), T("☑" if r["is_channel_paid"] else "☐", cls="ctr"),
                   T(r.get("purchase_note") or "", cls="small")] + blanks(5))
        g.add(blanks(4, cls="noborder") + [T("電台應付小計:", span=2, cls="b right blue noborder"), M(grp["total"], cls="b", fill="lyellow")] + blanks(8, cls="noborder"))
        g.gap()
    return [g]


# ================================================================ 7. 業績系統 vs 會計帳 對帳表（媒體發稿量分）
RECON_W = [16, 13, 13, 13, 11, 13, 13, 10, 7]      # 列樣 + 業績系統4 + 會計帳4 = 9 欄
_RECON_FILL = {5: "lorange", 4: "lblue"}           # 5=製作費 6橘、4=廣播 藍


def layout_reconciliation(res: dict, *, ym_from: str, ym_to: str, group_text: str = "*") -> list[Grid]:
    """一張對帳表（主表 + 收入/成本差異 + 廣告交換明細）。數字全由業績系統推算，見各表註解。"""
    # ---- 主表 ----
    g = Grid("對帳表", widths=RECON_W, landscape=True, font_size=9.5, header_rows=3)
    g.add([T(f"{_period(ym_from, ym_to)} 業績系統 vs 會計帳 對帳表（媒體發稿量分） 組別: {group_text}", span=9, cls="b big noborder left")], "title")
    g.add([T("列樣", cls="b ctr", fill="grey", rowspan=2),
           T("業績系統", span=4, cls="b ctr", fill="lblue"), T("會計帳", span=4, cls="b ctr", fill="lgreen")], height=20)
    g.add([T(h, cls="b ctr wrap", fill="lblue") for h in ("加總-實收金額", "加總-除傭實收", "加總-實付金額", "交換")]
          + [T(h, cls="b ctr wrap", fill="lgreen") for h in ("收入", "成本", "折讓", "現%")], height=28)

    def _row(r, *, fill=None, bold=False):
        b = "b" if bold else ""
        gk = r.get("_grp")
        f = fill or (_RECON_FILL.get(gk) if not bold else fill)
        return [T(r["label"], cls=f"{'b ' if bold else ''}", fill=fill or ("grey" if gk == 5 else None)),
                M(r["gross"], cls=b, fill=f), M(r["net"], cls=b, fill=f), M(r["cost"], cls=b, fill=f),
                M(r["barter"] or None, cls=b, fill=f),
                M(r["acct_rev"], cls=b, fill=f), M(r["acct_cost"], cls=b, fill=f),
                M(r["discount"] or None, cls=b, fill=f), P(r["disc_pct"], 1, cls=b, fill=f) if r["disc_pct"] else T(fill=f)]

    for r in res["rows"]:
        g.add(_row(r), "kwn")
    g.add(_row(res["total"], fill="cyan", bold=True))

    # ---- 差異分析（收入差異 + 成本差異）----
    s = Grid("差異分析", widths=[22, 14], landscape=True, font_size=10, header_rows=1)
    s.add([T("收入差異（業績系統 → 會計帳）", span=2, cls="b ctr", fill="lgreen")], "title")
    for k, v in res["rev_diff"].items():
        fill = "lgreen" if k == "會計帳收入" else None
        s.add([T(k, cls="left", fill=fill), M(v, cls="b" if fill else "", fill=fill)])
    s.gap()
    s.add([T("成本差異（業績系統 → 會計帳）", span=2, cls="b ctr", fill="gold")], "title")
    cd = res["cost_diff"]
    for k in ("製作費", "廣告交換帳未認成本-企", "廣告交換帳未認成本-新", "廣告交換帳未認成本-其他", "四捨五入差", "成本差異合計", "實付金額", "會計帳成本"):
        fill = "gold" if k in ("成本差異合計", "會計帳成本") else None
        s.add([T(k, cls="left", fill=fill), M(cd[k], cls="b" if fill else "", fill=fill)])

    # ---- 廣告交換明細 ----
    b = Grid("廣告交換明細", widths=[14, 20, 20, 12, 10, 12], landscape=True, font_size=9.5, header_rows=2)
    b.add([T("廣告交換明細（is_barter；交換金額 = 除傭實收，不列入會計帳收入）", span=6, cls="b big noborder left")], "title")
    b.add([T(h, cls="b ctr", fill="lgreen") for h in ("合約編號", "客戶名稱", "廣告名稱", "上檔日期", "平台", "交換金額")])
    for _, r in res["barter"].iterrows():
        b.add([T(r["contract_no"], cls="small"), T(r["customer"], cls="wrap small"), T(r["ad_name"], cls="wrap small"),
               T(r["air_period_text"], cls="ctr"), T(r["fin_platform"], cls="ctr"), M(r["net_amount"])])
    b.add([T("合計", span=5, cls="b right", fill="lgreen"), M(float(res["barter"]["net_amount"].sum()) if len(res["barter"]) else 0, cls="b", fill="lgreen")])
    return [g, s, b]
