"""
compute.py — 財務報表專區的計算層（CLAUDE_CODE_TASK_7）

輸入永遠是一張 DataFrame：`select * from v_finance_line where perf_ym between %s and %s`（一列 = 舊「業績資料表」一列），
先 apply_filters() 套舊表單的篩選（含排除型），再交給各報表函式。函式只回傳 DataFrame / dict，不碰版面。

舊系統的排序是 Windows 繁中定序（＝Big5 碼序，筆畫順）：組別 東吳組 < 鉑霖組 < 錄音室 < 聲活-東 < 聲活-鉑 < 聲活組，
業務 江曼瑄 < 林怡慧 < 陳絜心。這裡用 big5 編碼當排序鍵重現（zh_key）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# 財務報表 8 類平台（業績成本報表 A–H、月獎金計算總表欄）；'企頻'（舊平台名就叫企頻）併入全家企頻欄
FIN_PLATFORMS = ["全家企頻", "家樂福企頻", "新鮮視", "健康視", "廣播", "其他", "營運"]
FIN_LETTERS = dict(zip(FIN_PLATFORMS + ["製作費"], "ABCDEFGH"))
# 綜合分析的公司列（組別 → 列名）
GROUP_LABEL = {"聲活組": "聲活", "東吳組": "東吳", "鉑霖組": "鉑霖"}
COMBINED_ROWS = ["聲活組", "東吳組", "鉑霖組", "聲活-東", "聲活-鉑", "公司", "錄音室"]
THREE = ["聲活組", "東吳組", "鉑霖組"]
MEASURES = [("gross", "實收金額"), ("net", "除佣實收"), ("cost", "實付金額"), ("profit", "帳上毛利"), ("margin", "毛利率")]
# 平台顯示順序（舊 平台資料表.顯示順序）：全家企頻 0、家樂福企頻 1、新鮮視 2、健康視 3、營運 4、廣播 5、其它 6；其餘排後面
PLAT_ORDER = {"全家企頻": 0, "家樂福企頻": 1, "新鮮視": 2, "健康視": 3, "營運": 4, "廣播": 5, "其它": 6}


# ---------------------------------------------------------------- 共用
def zh_key(s) -> bytes:
    """Windows 繁中定序 ≈ Big5 碼序（筆畫）。無法編碼的字退到 utf-8。"""
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    try:
        return s.encode("big5")
    except UnicodeEncodeError:
        return b"\xff" + s.encode("utf-8")


def _ratio(a, b):
    return (a / b) if b else None


def _fin_platform(p: str) -> str:
    return "全家企頻" if p == "企頻" else (p if p in FIN_PLATFORMS else "其他")


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """數值欄轉 float、衍生欄補齊。所有報表都先過這裡。"""
    df = raw.copy()
    for c in ("gross_amount", "net_amount", "cost_amount", "channel_cost_amount", "media_benefit",
              "channel_rebate_amount", "channel_rebate_pct", "channel_cash_discount_pct"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    for c in ("customer", "ad_name", "salesperson", "business_group", "platform", "media_channel", "program",
              "notes", "sales_category", "sales_item", "customer_category", "industry", "contract_term", "fin_platform",
              "plat_z", "air_period_text", "ym"):
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)
    df["is_production"] = df["is_production"].astype(bool)
    df["fin8"] = df["fin_platform"].map(_fin_platform)          # 8 類（製作費線仍照平台，另有 is_production）
    df["profit"] = df["net_amount"] - df["cost_amount"]
    df["profit_rebate"] = df["profit"] + df["channel_rebate_amount"]
    df["_po"] = df["platform"].map(lambda p: PLAT_ORDER.get(p, 50))
    df["_gk"] = df["business_group"].map(zh_key)
    df["_sk"] = df["salesperson"].map(zh_key)
    df["_ck"] = df["customer"].map(zh_key)
    return df


# ---------------------------------------------------------------- 篩選（舊表單）
@dataclass
class Filters:
    groups: list[str] = field(default_factory=list)          # 組別（空 = 全部）
    salespeople: list[str] = field(default_factory=list)     # 業務
    customers: list[str] = field(default_factory=list)       # 客戶
    customer_categories: list[str] = field(default_factory=list)
    sales_categories: list[str] = field(default_factory=list)  # 業績類別
    platforms: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)        # 電台
    companies: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    contract_terms: list[str] = field(default_factory=list)  # 年季約
    ad_like: str = ""                                        # 廣告名稱 含
    contract_like: str = ""                                  # CUE 號 含
    exclude_salespeople: list[str] = field(default_factory=list)
    exclude_customers: list[str] = field(default_factory=list)
    exclude_ad_like: str = ""                                # 排除廣告（含此字）
    include_intercompany: bool = True                        # 舊報表一律含轉撥線（聲活-東 / 聲活-鉑）

    def text(self) -> str:
        parts = []
        for lab, v in (("組別", self.groups), ("業務", self.salespeople), ("客戶", self.customers),
                       ("客戶類別", self.customer_categories), ("業績類別", self.sales_categories),
                       ("平台", self.platforms), ("電台", self.channels), ("公司", self.companies),
                       ("產業別", self.industries), ("年季約", self.contract_terms)):
            if v:
                parts.append(f"{lab}={'/'.join(v)}")
        if self.ad_like:
            parts.append(f"廣告含「{self.ad_like}」")
        if self.contract_like:
            parts.append(f"CUE含「{self.contract_like}」")
        return "　".join(parts)

    def exclude_text(self) -> str:
        parts = []
        if self.exclude_salespeople:
            parts.append("業務 " + "/".join(self.exclude_salespeople))
        if self.exclude_customers:
            parts.append("客戶 " + "/".join(self.exclude_customers))
        if self.exclude_ad_like:
            parts.append(f"廣告含「{self.exclude_ad_like}」")
        return "、".join(parts)


def apply_filters(df: pd.DataFrame, f: Filters | None) -> pd.DataFrame:
    if f is None:
        return df
    m = pd.Series(True, index=df.index)
    for col, vals in (("business_group", f.groups), ("salesperson", f.salespeople), ("customer", f.customers),
                      ("customer_category", f.customer_categories), ("sales_category", f.sales_categories),
                      ("platform", f.platforms), ("media_channel", f.channels), ("company", f.companies),
                      ("industry", f.industries), ("contract_term", f.contract_terms)):
        if vals and col in df.columns:
            m &= df[col].isin(vals)
    if f.ad_like:
        m &= df["ad_name"].str.contains(f.ad_like, regex=False)
    if f.contract_like:
        m &= df["contract_no"].astype(str).str.contains(f.contract_like, regex=False)
    if f.exclude_salespeople:
        m &= ~df["salesperson"].isin(f.exclude_salespeople)
    if f.exclude_customers:
        m &= ~df["customer"].isin(f.exclude_customers)
    if f.exclude_ad_like:
        m &= ~df["ad_name"].str.contains(f.exclude_ad_like, regex=False)
    if not f.include_intercompany and "is_intercompany" in df.columns:
        m &= ~df["is_intercompany"].astype(bool)
    return df[m].copy()


def _sums(df: pd.DataFrame) -> dict:
    g, n, c = float(df["gross_amount"].sum()), float(df["net_amount"].sum()), float(df["cost_amount"].sum())
    return {"gross": g, "net": n, "cost": c, "profit": n - c, "margin": _ratio(n - c, n),
            "benefit": float(df["media_benefit"].sum()) if "media_benefit" in df.columns else 0.0}


def _box(df: pd.DataFrame) -> pd.DataFrame:
    """業務／組別總業績方塊：總計列 + A–G 平台列（製作費線含在其平台內）+ H 製作費備註列。"""
    rows = [{"label": "總計", **_sums(df)}]
    for p in FIN_PLATFORMS:
        rows.append({"label": p, **_sums(df[df["fin8"] == p])})
    rows.append({"label": "製作費", **_sums(df[df["is_production"]])})
    out = pd.DataFrame(rows)
    out["letter"] = [""] + [FIN_LETTERS[p] for p in FIN_PLATFORMS] + ["H"]
    return out


# ---------------------------------------------------------------- 1. 業績成本報表(區間)
@dataclass
class CostReport:
    groups: list            # [(組別, [(業務, [(合約, lines_df, subtotal)], box_df)], box_df)]
    final: pd.DataFrame     # (1)–(7) 平台總表
    cp_detail: pd.DataFrame # 企頻細項
    diff_gross_net: float
    radio_cost: float


def cost_report(df: pd.DataFrame) -> CostReport:
    d = df.sort_values(["_gk", "_sk", "contract_no", "line_no"]).copy()
    groups = []
    for gname, gdf in d.groupby("business_group", sort=False):
        sps = []
        for sname, sdf in gdf.groupby("salesperson", sort=False):
            contracts = []
            for cno, cdf in sdf.groupby("contract_no", sort=False):
                contracts.append((cno, cdf, _sums(cdf)))
            sps.append((sname, contracts, _box(sdf)))
        groups.append((gname, sps, _box(gdf)))
    # 最後一頁：(1) 企頻 = 全家企頻 + 家樂福企頻（含舊平台名「企頻」）
    fin = []
    buckets = [("(1) 企頻", d["plat_z"] == "企頻"), ("(2) 新鮮視", d["fin8"] == "新鮮視"), ("(3) 健康視", d["fin8"] == "健康視"),
               ("(4) 廣播", d["fin8"] == "廣播"), ("(5) 其他", d["fin8"] == "其他"), ("(6) 營運", d["fin8"] == "營運")]
    for label, m in buckets:
        fin.append({"label": label, **_sums(d[m])})
    fin.append({"label": "(7) 製作費", **_sums(d[d["is_production"]]), "memo": True})
    fin.append({"label": "(1)-(7) 合計", **_sums(d)})
    final = pd.DataFrame(fin)
    cp = [{"label": "(1) 全家企頻", **_sums(d[d["fin_platform"] == "全家企頻"])},
          {"label": "(2) 家樂福企頻", **_sums(d[d["fin_platform"] == "家樂福企頻"])},
          {"label": "(3) 企頻", **_sums(d[d["fin_platform"] == "企頻"])}]
    tot = _sums(d)
    return CostReport(groups, final, pd.DataFrame(cp), tot["gross"] - tot["net"], float(d.loc[d["fin8"] == "廣播", "cost_amount"].sum()))


# ---------------------------------------------------------------- 2. 媒體發稿量分析（電台發稿量）
SORT_KEYS = {"實收金額": "gross", "除佣實收": "net", "實付金額": "cost", "毛利": "profit", "Total": "profit_rebate"}


def _agg(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = df.groupby(by, sort=False).agg(gross=("gross_amount", "sum"), net=("net_amount", "sum"), cost=("cost_amount", "sum"),
                                       rebate=("channel_rebate_amount", "sum")).reset_index()
    g["profit"] = g["net"] - g["cost"]
    g["profit_rebate"] = g["profit"] + g["rebate"]
    g["margin"] = [_ratio(p, n) for p, n in zip(g["profit"], g["net"])]
    g["margin_rebate"] = [_ratio(p, n) for p, n in zip(g["profit_rebate"], g["net"])]
    return g


def _with_share(g: pd.DataFrame, tot: pd.Series) -> pd.DataFrame:
    for k in ("gross", "net", "cost", "profit", "profit_rebate"):
        g[f"{k}_share"] = [_ratio(v, tot[k]) for v in g[k]]
    return g


def media_volume(df: pd.DataFrame, version: str = "客戶版", sort_by: str = "實收金額") -> list[dict]:
    """
    回傳 [{channel, totals(Series), rows(DataFrame)}]，電台依「排序項目」的電台合計由大到小；
    客戶版 rows = 客戶；業務版 rows = 業務 + 其客戶（level 欄 1/2）；明細版 rows = 逐線；
    電台總表 = 只有 totals；業務總表 rows = 業務。
    佔比 = 該列 ÷ 該電台合計；毛利% = 毛利 ÷ 除佣實收；毛利+退佣 = 毛利 + 實付 × 該電台當年退佣%。
    """
    key = SORT_KEYS.get(sort_by, "gross")
    ch_tot = _agg(df, ["media_channel"]).set_index("media_channel")
    ch_tot["_k"] = ch_tot.index.map(zh_key)
    order = ch_tot.sort_values([key, "_k"], ascending=[False, True]).index.tolist()
    out = []
    for ch in order:
        sub = df[df["media_channel"] == ch]
        tot = ch_tot.loc[ch]
        if version == "客戶版":
            rows = _with_share(_agg(sub, ["customer"]), tot)
            rows["_k"] = rows["customer"].map(zh_key)
            rows = rows.sort_values([key, "_k"], ascending=[False, True]).reset_index(drop=True)
            rows.insert(0, "rank", range(1, len(rows) + 1))
        elif version == "業務版":
            sp = _with_share(_agg(sub, ["salesperson"]), tot)
            sp["_k"] = sp["salesperson"].map(zh_key)
            sp = sp.sort_values([key, "_k"], ascending=[False, True])
            parts = []
            for _, r in sp.iterrows():
                parts.append(pd.DataFrame([{**r.to_dict(), "level": 1, "customer": ""}]))
                cu = _with_share(_agg(sub[sub["salesperson"] == r["salesperson"]], ["customer"]), tot)
                cu["_k"] = cu["customer"].map(zh_key)
                cu = cu.sort_values([key, "_k"], ascending=[False, True])
                cu["level"] = 2
                cu["salesperson"] = r["salesperson"]
                cu.insert(0, "rank", range(1, len(cu) + 1))
                parts.append(cu)
            rows = pd.concat(parts, ignore_index=True)
        elif version == "業務總表":
            rows = _with_share(_agg(sub, ["salesperson"]), tot)
            rows["_k"] = rows["salesperson"].map(zh_key)
            rows = rows.sort_values([key, "_k"], ascending=[False, True]).reset_index(drop=True)
            rows.insert(0, "rank", range(1, len(rows) + 1))
        elif version == "明細版":
            rows = sub.sort_values(["_gk", "_sk", "contract_no", "line_no"]).reset_index(drop=True)
        else:  # 電台總表
            rows = pd.DataFrame()
        out.append({"channel": ch, "totals": tot, "rows": rows})
    return out


# ---------------------------------------------------------------- 3a. 綜合分析
COMB_COLS = ["全家", "家樂福", "企頻小計", "新鮮視", "健康視", "合計(企+新+健)", "廣播", "其他", "營運", "總計"]


def _comb_cols(sub: pd.DataFrame) -> dict:
    s = lambda m: sub[m]  # noqa: E731
    parts = {
        "全家": s(sub["fin_platform"] == "全家企頻"), "家樂福": s(sub["fin_platform"] == "家樂福企頻"),
        "企頻小計": s(sub["plat_z"] == "企頻"), "新鮮視": s(sub["fin8"] == "新鮮視"), "健康視": s(sub["fin8"] == "健康視"),
        "合計(企+新+健)": s((sub["plat_z"] == "企頻") | sub["fin8"].isin(["新鮮視", "健康視"])),
        "廣播": s(sub["fin8"] == "廣播"), "其他": s(sub["fin8"] == "其他"), "營運": s(sub["fin8"] == "營運"), "總計": sub,
    }
    return {k: _sums(v) for k, v in parts.items()}


def combined_analysis(df: pd.DataFrame) -> dict:
    """{'channel': DataFrame(rows=5 measures × COMB_COLS), 'by_group': {measure: DataFrame(rows=組別 × COMB_COLS)}}"""
    tot = _comb_cols(df)
    channel = pd.DataFrame([{"label": lab, **{c: tot[c][m] for c in COMB_COLS}} for m, lab in MEASURES])
    present = [g for g in COMBINED_ROWS if g in set(df["business_group"])]
    extra = sorted(set(df["business_group"]) - set(COMBINED_ROWS), key=zh_key)
    per_group = {g: _comb_cols(df[df["business_group"] == g]) for g in present + extra}
    ic = _comb_cols(df[df["business_group"].isin(["聲活-東", "聲活-鉑"])])
    three = _comb_cols(df[df["business_group"].isin(THREE)])
    by_group = {}
    for m, lab in MEASURES:
        rows = [{"label": GROUP_LABEL.get(g, g), **{c: per_group[g][c][m] for c in COMB_COLS}} for g in present + extra]
        rows.append({"label": "聲-東鉑", **{c: ic[c][m] for c in COMB_COLS}, "kind": "sub"})
        rows.append({"label": "聲+東+鉑", **{c: three[c][m] for c in COMB_COLS}, "kind": "total"})
        by_group[lab] = pd.DataFrame(rows)
    return {"channel": channel, "by_group": by_group}


# ---------------------------------------------------------------- 3b. 客戶同期比較表
def period_compare(cur: pd.DataFrame, prev: pd.DataFrame, variant: str = "全部") -> dict:
    """cur / prev 已各自套好同一組篩選；variant: 全部 / 企頻 / 廣播 / 新鮮視（只影響納入的線）。"""
    def pick(d):
        if variant == "企頻":
            return d[d["plat_z"] == "企頻"]
        if variant in ("廣播", "新鮮視"):
            return d[d["fin8"] == variant]
        return d
    cur, prev = pick(cur), pick(prev)

    def plat_rows(d):
        return {"總計": _sums(d), "企頻": _sums(d[d["plat_z"] == "企頻"]), "新鮮視": _sums(d[d["fin8"] == "新鮮視"]),
                "其他(廣播)": _sums(d[(d["plat_z"] != "企頻") & (d["fin8"] != "新鮮視")])}
    pc, pp = plat_rows(cur), plat_rows(prev)
    rows = []
    for k in (["總計", "企頻", "新鮮視", "其他(廣播)"] if variant == "全部" else ["總計"]):
        rows.append({"label": k, "net_cur": pc[k]["net"], "net_prev": pp[k]["net"], "profit_cur": pc[k]["profit"], "profit_prev": pp[k]["profit"],
                     "share_cur": _ratio(pc[k]["net"], pc["總計"]["net"]), "share_prev": _ratio(pp[k]["net"], pp["總計"]["net"])})
    plat = pd.DataFrame(rows)
    for a in ("net", "profit"):
        plat[f"{a}_growth"] = plat[f"{a}_cur"] - plat[f"{a}_prev"]
        plat[f"{a}_rate"] = [(_ratio(g, p) if p else (1.0 if g else 0.0)) for g, p in zip(plat[f"{a}_growth"], plat[f"{a}_prev"])]

    def cust(d, suffix):
        g = d.groupby("customer").agg(net=("net_amount", "sum"), cost=("cost_amount", "sum")).reset_index()
        g["profit"] = g["net"] - g["cost"]
        # 業務 = 該客戶除佣最多的業務
        sp = d.groupby(["customer", "salesperson"])["net_amount"].sum().reset_index()
        sp = sp.sort_values(["customer", "net_amount"], ascending=[True, False]).drop_duplicates("customer")
        g = g.merge(sp[["customer", "salesperson"]], on="customer", how="left")
        return g.rename(columns={"net": f"net_{suffix}", "profit": f"profit_{suffix}", "salesperson": f"sp_{suffix}"}).drop(columns=["cost"])
    c = cust(cur, "cur").merge(cust(prev, "prev"), on="customer", how="outer")
    for col in ("net_cur", "net_prev", "profit_cur", "profit_prev"):
        c[col] = c[col].fillna(0.0)
    for col in ("sp_cur", "sp_prev"):
        c[col] = c[col].fillna("")
    for a in ("net", "profit"):
        c[f"{a}_growth"] = c[f"{a}_cur"] - c[f"{a}_prev"]
        c[f"{a}_rate"] = [(_ratio(g, p) if p else (1.0 if g else 0.0)) for g, p in zip(c[f"{a}_growth"], c[f"{a}_prev"])]
    c["_k"] = c["customer"].map(zh_key)
    c = c.sort_values(["net_cur", "_k"], ascending=[False, True]).reset_index(drop=True)
    c.insert(0, "rank", range(1, len(c) + 1))
    return {"platform": plat, "customers": c}


# ---------------------------------------------------------------- 3c. 業績認定表
def recognition_table(df: pd.DataFrame) -> list[dict]:
    """[{salesperson, months: [{ym, blocks: [{platform, rows(DataFrame), totals(dict)}]}]}]，列 = 合約 × 平台。"""
    out = []
    d = df.sort_values(["_sk", "ym", "_po", "platform", "contract_no"])
    for sp, sdf in d.groupby("salesperson", sort=False):
        months = []
        for ym, mdf in sdf.groupby("ym", sort=False):
            blocks = []
            for plat, pdf_ in mdf.groupby("platform", sort=False):
                rows = []
                for cno, cdf in pdf_.groupby("contract_no", sort=False):
                    media = cdf[~cdf["is_production"]]
                    prod = cdf[cdf["is_production"]]
                    first = cdf.iloc[0]
                    # A/B = 該合約所有線（製作費線的實收也算，例：錄音室的製作收入）；C = 非製作費線實付；D = 製作費線實付
                    rows.append({"contract_no": cno, "customer": first["customer"], "ad_name": first["ad_name"],
                                 "air": first["air_period_text"], "gross": float(cdf["gross_amount"].sum()),
                                 "net": float(cdf["net_amount"].sum()), "cost": float(media["cost_amount"].sum()),
                                 "prod_cost": float(prod["cost_amount"].sum()), "item": first["sales_item"] or first["sales_category"]})
                r = pd.DataFrame(rows)
                tot = {k: float(r[k].sum()) for k in ("gross", "net", "cost", "prod_cost")}
                tot["recognized"] = tot["net"] - tot["prod_cost"]
                blocks.append({"platform": plat, "rows": r, "totals": tot})
            months.append({"ym": ym, "blocks": blocks})
        out.append({"salesperson": sp, "months": months})
    return out


# ---------------------------------------------------------------- 3d. 月獎金計算總表
def bonus_summary(df: pd.DataFrame) -> pd.DataFrame:
    """列 = 組別 × 業務 × 月份，加每位業務的合計列（kind='total'）。平台欄 = 除佣實收；製作成本 = 製作費線實付。"""
    d = df.sort_values(["_gk", "_sk", "ym"])
    rows = []
    for (g, sp), sdf in d.groupby(["business_group", "salesperson"], sort=False):
        block = []
        for ym, mdf in sdf.groupby("ym", sort=False):
            r = {"group": g, "salesperson": sp, "month": ym[-2:], "kind": "row"}
            for p in FIN_PLATFORMS:
                r[p] = float(mdf.loc[mdf["fin8"] == p, "net_amount"].sum())
            r["gross"] = float(mdf["gross_amount"].sum())
            r["net"] = float(mdf["net_amount"].sum())
            r["prod_cost"] = float(mdf.loc[mdf["is_production"], "cost_amount"].sum())
            r["recognized"] = r["net"] - r["prod_cost"]
            block.append(r)
        t = {"group": "", "salesperson": f"{sp} 合計", "month": "", "kind": "total"}
        for k in FIN_PLATFORMS + ["gross", "net", "prod_cost", "recognized"]:
            t[k] = sum(b[k] for b in block)
        rows.extend(block + [t])
    return pd.DataFrame(rows)


def bonus_summary_platform_cost(df: pd.DataFrame) -> pd.DataFrame:
    """月獎金計算總表的加寬版：每平台同時給「除佣實收」（欄名＝平台名）與「製作成本」（欄名＝平台名＋'__pc'）。
    平台製作成本 = 該平台（fin8）製作費線的實付；7 個平台製作成本相加 = 該列 prod_cost（與原獎金總表一致）。"""
    d = df.sort_values(["_gk", "_sk", "ym"])
    rows = []
    for (g, sp), sdf in d.groupby(["business_group", "salesperson"], sort=False):
        block = []
        for ym, mdf in sdf.groupby("ym", sort=False):
            r = {"group": g, "salesperson": sp, "month": ym[-2:], "kind": "row"}
            for p in FIN_PLATFORMS:
                r[p] = float(mdf.loc[mdf["fin8"] == p, "net_amount"].sum())
                r[f"{p}__pc"] = float(mdf.loc[(mdf["fin8"] == p) & mdf["is_production"], "cost_amount"].sum())
            r["gross"] = float(mdf["gross_amount"].sum())
            r["net"] = float(mdf["net_amount"].sum())
            r["prod_cost"] = float(mdf.loc[mdf["is_production"], "cost_amount"].sum())
            r["recognized"] = r["net"] - r["prod_cost"]
            block.append(r)
        t = {"group": "", "salesperson": f"{sp} 合計", "month": "", "kind": "total"}
        for k in FIN_PLATFORMS + [f"{p}__pc" for p in FIN_PLATFORMS] + ["gross", "net", "prod_cost", "recognized"]:
            t[k] = sum(b[k] for b in block)
        rows.extend(block + [t])
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3e. 業務發稿統計 (A3)
WAVE_PLATS = ["企頻", "新鮮視", "廣播"]


def _waves(d: pd.DataFrame) -> int:
    """執行波段 = 不重複的 (客戶, 廣告, 合約編號)。"""
    return int(d[["customer", "ad_name", "contract_no"]].drop_duplicates().shape[0]) if len(d) else 0


def _plat_mask(d: pd.DataFrame, p: str) -> pd.Series:
    return (d["plat_z"] == "企頻") if p == "企頻" else (d["fin8"] == p)


def sales_wave_stats(df: pd.DataFrame) -> dict:
    """{'top': DataFrame(業務列 + 總計), 'detail': [{salesperson, customers: [{customer, ads: DataFrame, sub: dict}], total: dict}]}"""
    def stats(d):
        s = _sums(d)
        w = _waves(d)
        s.update({"customers": int(d["customer"].nunique()), "waves": w,
                  "avg_gross": _ratio(s["gross"], w), "avg_profit": _ratio(s["profit"], w)})
        for p in WAVE_PLATS:
            pdf_ = d[_plat_mask(d, p)]
            ps = _sums(pdf_)
            pw = _waves(pdf_)
            s[f"{p}_waves"] = pw
            s[f"{p}_avg_gross"] = _ratio(ps["gross"], pw)
            for k in ("gross", "net", "profit", "margin"):
                s[f"{p}_{k}"] = ps[k]
        return s
    top = []
    for sp, sdf in df.groupby("salesperson"):
        top.append({"salesperson": sp, **stats(sdf)})
    top = pd.DataFrame(top)
    top["_k"] = top["salesperson"].map(zh_key)
    top = top.sort_values(["net", "_k"], ascending=[False, True]).reset_index(drop=True)
    total = {"salesperson": "總計", **stats(df)}
    detail = []
    for sp in top["salesperson"]:
        sdf = df[df["salesperson"] == sp]
        cu = sdf.groupby("customer")["net_amount"].sum().reset_index()
        cu["_k"] = cu["customer"].map(zh_key)
        customers = []
        for cust in cu.sort_values(["net_amount", "_k"], ascending=[False, True])["customer"]:
            cdf = sdf[sdf["customer"] == cust]
            ads = []
            ad_order = cdf.groupby("ad_name")["net_amount"].sum().sort_values(ascending=False).index
            for ad in ad_order:
                adf = cdf[cdf["ad_name"] == ad]
                ads.append({"ad_name": ad, **stats(adf)})
            customers.append({"customer": cust, "ads": pd.DataFrame(ads), "sub": stats(cdf)})
        detail.append({"salesperson": sp, "customers": customers, "total": stats(sdf)})
    return {"top": top, "total": total, "detail": detail}


# ---------------------------------------------------------------- 4. 月責任檔業績達成表
def achievement(df: pd.DataFrame) -> list[dict]:
    """[{group, salespeople: [{salesperson, categories: [{category, rows(DataFrame), sub}], total}], total}]
    列 = 合約 × 業績類別：實收金額 = 該合約全部線實收；製作成本 = 製作費線實付；認定業績 = 實收 − 製作成本。"""
    d = df.sort_values(["_gk", "_sk", "sales_category", "contract_no"])
    out = []
    for g, gdf in d.groupby("business_group", sort=False):
        sps = []
        for sp, sdf in gdf.groupby("salesperson", sort=False):
            cats = []
            for cat, cdf in sdf.groupby("sales_category", sort=False):
                rows = []
                for cno, xdf in cdf.groupby("contract_no", sort=False):
                    prod = xdf[xdf["is_production"]]
                    first = xdf.iloc[0]
                    gross = float(xdf["gross_amount"].sum())          # 全部線的實收（含製作費線的製作收入）
                    pc = float(prod["cost_amount"].sum())              # 製作費線的實付
                    rows.append({"contract_no": cno, "customer": first["customer"], "ad_name": first["ad_name"],
                                 "gross": gross, "prod_cost": pc, "recognized": gross - pc, "air": first["air_period_text"]})
                r = pd.DataFrame(rows)
                cats.append({"category": cat or "(未填)", "rows": r, "sub": {k: float(r[k].sum()) for k in ("gross", "prod_cost", "recognized")}})
            sps.append({"salesperson": sp, "categories": cats,
                        "total": {k: sum(c["sub"][k] for c in cats) for k in ("gross", "prod_cost", "recognized")}})
        out.append({"group": g, "salespeople": sps,
                    "total": {k: sum(s["total"][k] for s in sps) for k in ("gross", "prod_cost", "recognized")}})
    return out


# ---------------------------------------------------------------- 5. 三單：廣告時段採購申請單
def purchase_request(lines: pd.DataFrame) -> dict:
    """lines = 該合約的所有線（v_finance_line where contract_no = ?）。
    列 = 非製作費、非尼爾森的線（含轉撥線），照 line_no；現折 = 實付 × 電台現金折扣%。"""
    d = lines[(~lines["is_production"]) & (~lines["media_channel"].str.startswith("尼"))].sort_values("line_no").copy()
    d["pct"] = d["channel_cash_discount_pct"]
    d["actual"] = d["cost_amount"]
    d["discount"] = (d["actual"] * d["pct"]).round(0)
    d["actual_after"] = d["actual"] - d["discount"]
    d["payable"] = d["channel_cost_amount"]
    d["payable_after"] = d["payable"] - (d["payable"] * d["pct"]).round(0)
    tot = {k: float(d[k].sum()) for k in ("actual", "actual_after", "discount", "payable", "payable_after")}
    net = {k: {"payable": float(d.loc[d["network_name"] == k, "payable"].sum()),
               "payable_after": float(d.loc[d["network_name"] == k, "payable_after"].sum())} for k in ("好事", "城市")}
    net_total = float(d["net_amount"].sum())
    profit = net_total - tot["actual"]
    return {"rows": d, "totals": tot, "networks": net, "net": net_total, "profit": profit, "margin": _ratio(profit, net_total)}


# ---------------------------------------------------------------- 6. 電台預付明細表
def prepay_groups(pp: pd.DataFrame) -> list[dict]:
    """pp = v_channel_prepay 篩過日期／電台／合約；依電台分組（電台順序 → 名稱），組內依預付日、合約。"""
    d = pp.copy()
    d["cost_amount"] = pd.to_numeric(d["cost_amount"], errors="coerce").fillna(0.0)
    d["_ck"] = d["media_channel"].map(zh_key)
    d = d.sort_values(["channel_order", "_ck", "prepay_on", "contract_no"])
    out = []
    for ch, cdf in d.groupby("media_channel", sort=False):
        cdf = cdf.reset_index(drop=True)
        cdf.insert(0, "seq", range(1, len(cdf) + 1))
        out.append({"channel": ch, "rows": cdf, "total": float(cdf["cost_amount"].sum())})
    return out
