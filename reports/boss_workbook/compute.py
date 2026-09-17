"""
compute.py — 老闆工作簿（2025年度_三公司發稿明細分析）的計算層：一份「原始資料」DataFrame → 每張表的 DataFrame

和工作簿一樣的架構：所有表都從同一份 raw（= 工作簿的「原始資料_發稿分析」）算出來，
所以任何一張表的數字都能回溯到 raw 的哪幾列。raw 的欄名沿用工作簿（中文），由 v_boss_line 供給。

規則（從工作簿公式反推，逐格對過）：
- 平台欄：全家企頻 / 萬家福 / 新鮮視 / 廣播 固定四欄；期間內若有「健康視」金額就多一欄（2026 起）。
- 客戶數(不重複)：該範圍內出現過的客戶名稱去重（含金額 0 的）。
- 業務表 / 客戶表 排序：總計(除佣實收) 遞減，同額依名稱（Unicode 碼位）遞增；Company 一視同仁不特別排最後。
- 「公司」「業務」多值欄：去重後依 Unicode 碼位排序、以「、」連接（工作簿如此：東吳、聲活、鉑霖；Company、陳秀鈴）。
- 利率 = 毛利 ÷ 除佣實收（除以 0 → 0）；佔比分母見各函式 docstring。
- 逐筆明細排序：業務（依第一段順序）→ 除佣實收遞減 → 合約編號 → 上檔起始日期（工作簿同額列的順序不固定，這裡定死）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

COMPANIES = ["聲活", "東吳", "鉑霖"]
CORE_PLATS = ["全家企頻", "萬家福", "新鮮視", "廣播"]
OWN_MEDIA = ["全家企頻", "萬家福", "新鮮視"]          # 不含廣播 = 自媒體
EXTRA_PLATS = ["健康視"]                              # 有金額才出現
NET, COST, GROSS = "除佣實收", "實付金額", "實收金額"
SP, CUST, CO, PLAT = "業務_final", "客戶名稱", "公司別", "平台_顯示"


def _ratio(a, b) -> float:
    a = 0.0 if a is None or pd.isna(a) else float(a)
    b = 0.0 if b is None or pd.isna(b) else float(b)
    return a / b if b else 0.0


def _joined(values) -> str:
    return "、".join(sorted({str(v) for v in values if pd.notna(v)}))


def plats_in(raw: pd.DataFrame) -> list[str]:
    """固定四欄 + 期間內有金額的額外平台。"""
    out = list(CORE_PLATS)
    for p in EXTRA_PLATS:
        if p in set(raw[PLAT]) and raw.loc[raw[PLAT] == p, NET].sum() != 0:
            out.append(p)
    return out


def _pivot(df: pd.DataFrame, by: list[str], plats: list[str]) -> pd.DataFrame:
    """依 by 分組：各平台除佣、總計、成本、毛利、利率、客戶數。"""
    g = df.groupby(by, sort=False)
    out = g[NET].sum().to_frame("總計")
    for p in plats:
        out[p] = df[df[PLAT] == p].groupby(by)[NET].sum().reindex(out.index).fillna(0.0)
    out["成本"] = g[COST].sum()
    out["毛利"] = out["總計"] - out["成本"]
    out["利率"] = [(_ratio(a, b)) for a, b in zip(out["毛利"], out["總計"])]
    out["客戶數"] = g[CUST].nunique()
    return out.reset_index()


def _sort(df: pd.DataFrame, name_col: str) -> pd.DataFrame:
    """總計遞減；同額依名稱（碼位）遞增。排名表：工作簿 RANK+COUNTIF 於依名稱排序的清單 = 同樣結果；
    年度發稿明細第二段：工作簿同額客戶的先後沒有規則（41 組同額鄰居裡名稱升冪只佔一半），這裡定死為名稱遞增。"""
    return df.sort_values(["總計", name_col], ascending=[False, True], kind="mergesort").reset_index(drop=True)


# ------------------------------------------------------------------ 平台總計總覽
def platform_overview(raw: pd.DataFrame, plats: list[str], *, incl_radio: bool) -> dict[str, pd.DataFrame]:
    """
    回傳四個 DataFrame：net / cost / profit / rate，每個都是 公司列 + 三公司合計列。
    佔比欄：net → 除佣佔比 = 公司總計 ÷ 三公司總計；cost → 成本佔比 = 公司成本 ÷ 公司除佣；profit → 毛利佔比 = 公司毛利 ÷ 三公司毛利。
    客戶數(不重複)：該公司在這些平台有出現過的客戶去重；合計列 = 三公司去重。
    """
    use = [p for p in plats if incl_radio or p != "廣播"]
    sub = raw[raw[PLAT].isin(use)]
    rows = []
    for co in COMPANIES:
        s = sub[sub[CO] == co]
        r = {"公司": co}
        for p in use:
            r[p] = float(s.loc[s[PLAT] == p, NET].sum())
            r[f"成本_{p}"] = float(s.loc[s[PLAT] == p, COST].sum())
        r["總計"] = sum(r[p] for p in use)
        r["成本"] = sum(r[f"成本_{p}"] for p in use)
        r["客戶數"] = int(s[CUST].nunique())
        rows.append(r)
    tot = {"公司": "三公司合計", **{p: sum(r[p] for r in rows) for p in use},
           **{f"成本_{p}": sum(r[f"成本_{p}"] for r in rows) for p in use},
           "總計": sum(r["總計"] for r in rows), "成本": sum(r["成本"] for r in rows), "客戶數": int(sub[CUST].nunique())}
    all_rows = rows + [tot]
    grand_net, grand_profit = tot["總計"], tot["總計"] - tot["成本"]
    net = pd.DataFrame([{"公司": r["公司"], **{p: r[p] for p in use}, "總計": r["總計"], "客戶數(不重複)": r["客戶數"],
                         "除佣佔比": _ratio(r["總計"], grand_net)} for r in all_rows])
    cost = pd.DataFrame([{"公司": r["公司"], **{p: r[f"成本_{p}"] for p in use}, "總計": r["成本"],
                          "成本佔比": _ratio(r["成本"], r["總計"])} for r in all_rows])
    profit = pd.DataFrame([{"公司": r["公司"], **{p: r[p] - r[f"成本_{p}"] for p in use}, "總計": r["總計"] - r["成本"],
                            "毛利佔比": _ratio(r["總計"] - r["成本"], grand_profit)} for r in all_rows])
    rate = pd.DataFrame([{"公司": r["公司"], **{p: _ratio(r[p] - r[f"成本_{p}"], r[p]) for p in use},
                          "總計": _ratio(r["總計"] - r["成本"], r["總計"])} for r in all_rows])
    return {"net": net, "cost": cost, "profit": profit, "rate": rate, "plats": use}


# ------------------------------------------------------------------ 客戶數統計與客戶排名
def salesperson_table(raw: pd.DataFrame, plats: list[str], company: str | None = None) -> pd.DataFrame:
    """
    依業務（同名跨公司合併）。company=None → 三公司合計，多一欄「公司」；發稿佔比分母 = 三公司總計。
    company 指定 → 該公司區塊；發稿佔比分母 = 該公司總計。最後一列「合計」。
    """
    sub = raw if company is None else raw[raw[CO] == company]
    t = _pivot(sub, [SP], plats)
    t = _sort(t, SP)
    if company is None:
        t.insert(1, "公司", [_joined(sub.loc[sub[SP] == s, CO]) for s in t[SP]])
    denom = float(sub[NET].sum())
    t["發稿佔比"] = [_ratio(v, denom) for v in t["總計"]]
    tot = {SP: "合計", **{p: t[p].sum() for p in plats}, "總計": t["總計"].sum(), "成本": t["成本"].sum(),
           "毛利": t["毛利"].sum(), "利率": _ratio(t["毛利"].sum(), t["總計"].sum()), "發稿佔比": t["發稿佔比"].sum(),
           "客戶數": int(sub[CUST].nunique())}
    if company is None:
        tot["公司"] = ""
    t = pd.concat([t, pd.DataFrame([tot])], ignore_index=True)
    cols = [SP] + (["公司"] if company is None else []) + plats + ["總計", "成本", "毛利", "利率", "發稿佔比"]
    return t[cols].rename(columns={SP: "業務"})


def customer_ranking(raw: pd.DataFrame, plats: list[str], company: str | None = None, top: int | None = None) -> pd.DataFrame:
    """
    客戶排名。company=None → 跨公司合併（欄：排名、公司、業務、客戶名稱…；佔比分母 = 三公司總計）；
    company 指定 → 該公司（欄：排名、業務、客戶名稱…；佔比分母 = 該公司總計）。
    top=10 → 前 10 名 + 「前10大合計」列；top=None → 全部 + 「除佣實收總計」列。
    排名：總計遞減，同額依客戶名稱碼位（工作簿 RANK+COUNTIF 於依名稱排序的清單 = 同樣結果）。
    """
    sub = raw if company is None else raw[raw[CO] == company]
    t = _pivot(sub, [CUST], plats)
    t = _sort(t, CUST)
    t.insert(0, "排名", range(1, len(t) + 1))
    if company is None:
        t.insert(1, "公司", [_joined(sub.loc[sub[CUST] == c, CO]) for c in t[CUST]])
    t.insert(2 if company is None else 1, "業務", [_joined(sub.loc[sub[CUST] == c, SP]) for c in t[CUST]])
    denom = float(sub[NET].sum())
    t["發稿佔比"] = [_ratio(v, denom) for v in t["總計"]]
    if top:
        t = t.head(top).copy()
        label = "前10大合計" if top == 10 else f"前{top}大合計"
    else:
        label = "除佣實收總計"
    tot = {"排名": label, **{p: t[p].sum() for p in plats}, "總計": t["總計"].sum(), "成本": t["成本"].sum(),
           "毛利": t["毛利"].sum(), "利率": _ratio(t["毛利"].sum(), t["總計"].sum()), "發稿佔比": t["發稿佔比"].sum()}
    t = pd.concat([t, pd.DataFrame([tot])], ignore_index=True)
    cols = ["排名"] + (["公司"] if company is None else []) + ["業務", CUST] + plats + ["總計", "成本", "毛利", "利率", "發稿佔比"]
    return t[cols]


# ------------------------------------------------------------------ 年度發稿明細（每家公司）
@dataclass
class AnnualDetail:
    company: str
    plats: list[str]
    section1: pd.DataFrame                                  # 各業務客戶數與發稿總計（含合計列）
    section2: list[tuple[str, pd.DataFrame]] = field(default_factory=list)   # [(業務, 每客戶總計含小計列)]
    section3: pd.DataFrame = field(default_factory=pd.DataFrame)             # 逐筆明細（不含合計列）
    totals: dict = field(default_factory=dict)              # 各平台除佣實收小計 / 除佣實收總計


def annual_detail(raw: pd.DataFrame, plats: list[str], company: str) -> AnnualDetail:
    sub = raw[raw[CO] == company].copy()
    denom = float(sub[NET].sum())              # 發稿佔比 / 除佣佔比 分母 = 該公司總計（平台總計總覽!F5/F6/F7）
    # 第一段
    s1 = _pivot(sub, [SP], plats)
    s1 = _sort(s1, SP)
    s1["發稿佔比"] = [_ratio(v, denom) for v in s1["總計"]]
    sp_order = list(s1[SP])
    tot = {SP: "合計", "客戶數": int(s1["客戶數"].sum()),      # 工作簿：SUM 各業務客戶數（不是去重）
           **{p: s1[p].sum() for p in plats}, "總計": s1["總計"].sum(), "毛利": s1["毛利"].sum(),
           "利率": _ratio(s1["毛利"].sum(), s1["總計"].sum()), "發稿佔比": s1["發稿佔比"].sum()}
    s1 = pd.concat([s1, pd.DataFrame([tot])], ignore_index=True)
    s1 = s1[[SP, "客戶數"] + plats + ["總計", "毛利", "利率", "發稿佔比"]].rename(columns={SP: "業務", "客戶數": "客戶數(不重複)"})
    # 第二段
    s2 = []
    for sp in sp_order:
        d = sub[sub[SP] == sp]
        t = _pivot(d, [CUST], plats)
        t = _sort(t, CUST)
        t["除佣佔比"] = [_ratio(v, denom) for v in t["總計"]]
        st = {CUST: f"{sp} 小計", **{p: t[p].sum() for p in plats}, "總計": t["總計"].sum(), "毛利": t["毛利"].sum(),
              "利率": _ratio(t["毛利"].sum(), t["總計"].sum()), "除佣佔比": t["除佣佔比"].sum()}
        t = pd.concat([t, pd.DataFrame([st])], ignore_index=True)
        s2.append((sp, t[[CUST] + plats + ["總計", "毛利", "利率", "除佣佔比"]]))
    # 第三段
    d = sub.copy()
    d["_spo"] = d[SP].map({s: i for i, s in enumerate(sp_order)})
    d = d.sort_values(["_spo", NET, "合約編號", "上檔起始日期"], ascending=[True, False, True, True], kind="mergesort")
    rows = []
    for _, r in d.iterrows():
        # 原檔：除佣實收／實收為空的線，儲存格留空（不是 0）；成本空 → 0
        net = None if pd.isna(r[NET]) else float(r[NET])
        row = {"業務": r[SP], "客戶名稱": r[CUST], "實收": None if pd.isna(r[GROSS]) else float(r[GROSS]), "執行走期": r["走期"]}
        for p in plats:
            row[p] = net if r[PLAT] == p else None
        row["成本"] = float(r[COST]) if pd.notna(r[COST]) else 0.0
        row["毛利"] = (net or 0.0) - row["成本"]
        row["利率"] = _ratio(row["毛利"], r[NET])
        row["發稿佔比"] = _ratio(r[NET], denom)
        rows.append(row)
    s3 = pd.DataFrame(rows, columns=["業務", "客戶名稱", "實收", "執行走期"] + plats + ["成本", "毛利", "利率", "發稿佔比"])
    totals = {"實收": float(d[GROSS].sum()), **{p: float(d.loc[d[PLAT] == p, NET].sum()) for p in plats},
              "成本": float(d[COST].sum()), "毛利": float(d[NET].sum() - d[COST].sum()),
              "利率": _ratio(d[NET].sum() - d[COST].sum(), d[NET].sum()), "發稿佔比": _ratio(d[NET].sum(), denom),
              "總計": float(d[NET].sum())}
    return AnnualDetail(company, plats, s1, s2, s3, totals)


# ------------------------------------------------------------------ 說明與假設（動態數字）
def notes(raw: pd.DataFrame, full_count: int, production_count: int, production_cost: float, year_label: str) -> list[str]:
    return [
        f"{year_label} 三公司發稿明細分析 — 說明與假設",
        "",
        "資料來源",
        f"・ 本表由業績系統資料庫即時產生：媒體上稿線共 {len(raw):,} 筆（原始 {full_count:,} 筆，排除製作費線 {production_count:,} 筆、實付合計 {production_cost:,.0f}）。",
        "・ 表格格式比照「喬商_彥星年度發稿明細」版型（業務／客戶／實收／執行走期／平台分欄／成本／毛利／%）。",
        "",
        "資料處理規則",
        "・ 排除「電台」為製作費（錄音室／配音員等代收代付）之線，僅保留媒體上稿線。",
        "・ 業務欄位帶「換」字者已併入原業務（例：蔡伊閔換→蔡伊閔Heidi；陳絜心-換→陳絜心）；金額計入業績。",
        "・ 平台名稱：「家樂福企頻」顯示為「萬家福」；全家各分區企頻（全企／北／桃／中／南）併為「全家企頻」；其餘維持原名。",
        "・ 不含內部轉撥線（聲活-東／聲活-鉑）。",
        "・ 執行走期：上檔起始日期至上檔結束日期，以 月/日-月/日 呈現。",
        "",
        "指標定義",
        "・ 除佣實收：扣除業務佣金後之實際認列收入。",
        "・ 成本：實付金額，即支付予媒體／電台之成本。",
        "・ 毛利：除佣實收 － 成本。　利率(%)：毛利 ÷ 除佣實收。",
        "・ 客戶數(不重複)：範圍內出現過的客戶名稱去重（含金額為 0 者）；年度發稿明細第一段的合計列為各業務客戶數加總。",
        "",
        "工作表索引",
        "・ 平台總計總覽：各公司及三公司合計之除佣實收／成本／毛利／利率，分平台列示，並提供不含廣播對照。",
        "・ 客戶數統計與客戶排名：上半部為各公司客戶數與除佣實收總計（不分平台）與各業務分平台總計；下半部為三公司前 10 大、各公司前 10 大與三公司客戶排名。",
        "・ 聲活／東吳／鉑霖_年度發稿明細：比照喬商版型，三段式：各業務總計、各業務每客戶總計、逐筆明細。",
        "・ 原始資料_發稿分析：供各表數字回溯之資料來源（同資料庫 v_boss_line）。",
    ]
