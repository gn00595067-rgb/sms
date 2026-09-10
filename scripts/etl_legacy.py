"""
etl_legacy.py — 把舊 Access 系統匯出的 legacy_csv/ 匯入新資料庫

做的事（可重複執行；同一個 --source 會先清掉上次匯入的 deal/deal_line/invoice/writeoff 再重匯）：
  1. 每個 CSV 原樣寫進 legacy_<表名>（全部 text 欄位 + _row_no + _source），永久保留供對帳。
  2. 從 業績資料表 / 客戶資料表 / 業務資料表 / 電台資料表 / 節目資料表 / 各人員資料表 建立主檔（get-or-create）。
  3. 業績資料表 → deal（依合約編號分組）+ deal_line（每列一條線，粒度不變、金額不重算）。
  4. 發票開立資料表 → invoice（+ 有銷帳金額者產生 writeoff）。
  5. 獎金百分比資料表 → bonus_rule（只匯 平台 ∈ 企頻/廣播/新鮮視 且 獎金百分比 > 0 的規則，供參考）。
  6. legacy_users.csv + 使用者業務資料表 → app_user（隨機密碼寫到 seed_passwords.local.txt，首次登入強制改密碼）。
  7. 對帳：v_deal_line_flat 的 (年月 × 公司別) 實收/除佣/實付 合計 必須 == CSV 合計（誤差 ≤ 1 元），否則 exit 1。

用法：
  python scripts/etl_legacy.py --csv legacy_csv --source ACCESS_2026_V109g
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import secrets
import sys
from collections import defaultdict
from datetime import date

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect  # noqa: E402

INTERCOMPANY_GROUPS = {"聲活-東", "聲活-鉑"}
PRODUCTION_PREFIX = "製作費"
STAFF_ROLE_COLS = {
    "媒體人員": "MEDIA", "企劃人員": "PLANNER", "文案人員": "COPY", "協辦人員": "ASSIST",
    "客服人員": "CS", "請款人員": "BILLING", "結案人員": "CLOSING",
}
DEAL_STAFF_COLS = {
    "媒體人員": "media_staff_id", "企劃人員": "planner_staff_id", "文案人員": "copy_staff_id",
    "協辦人員": "assist_staff_id", "客服人員": "cs_staff_id", "請款人員": "billing_staff_id", "結案人員": "closing_staff_id",
}


# ---------------------------------------------------------------- helpers
def s(v) -> str:
    """strip；NaN/None → ''"""
    if v is None:
        return ""
    v = str(v)
    return "" if v.lower() == "nan" else v.strip()


def num(v, default=0.0) -> float:
    v = s(v)
    if v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def intn(v):
    v = s(v)
    if v == "":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def boolean(v) -> bool:
    return s(v) in {"1", "True", "true", "-1", "是", "Y"}


def ym(v) -> date | None:
    """'2026/09' / '2026-09' / '202609' → date(2026,9,1)"""
    v = s(v)
    m = re.match(r"^(\d{4})[/\-]?(\d{1,2})$", v)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return date(y, mo, 1)


def dt(v) -> date | None:
    v = s(v)
    if not v:
        return None
    try:
        return pd.to_datetime(v).date()
    except Exception:  # noqa: BLE001
        return None


def read_csv(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


class Lookup:
    """get-or-create 主檔 id 的快取"""

    def __init__(self, cur, table: str, key_col: str = "name", extra_cols: dict | None = None):
        self.cur, self.table, self.key_col = cur, table, key_col
        self.extra = extra_cols or {}
        cur.execute(f"select id, {key_col} as k from {table}")
        self.cache = {r["k"]: r["id"] for r in cur.fetchall()}

    def get(self, name: str, **cols):
        name = s(name)
        if not name:
            return None
        if name in self.cache:
            return self.cache[name]
        cols = {**self.extra, **cols}
        col_names = [self.key_col] + list(cols)
        placeholders = ", ".join(["%s"] * len(col_names))
        self.cur.execute(
            f"insert into {self.table}({', '.join(col_names)}) values ({placeholders}) "
            f"on conflict ({self.key_col}) do update set {self.key_col} = excluded.{self.key_col} returning id",
            [name] + list(cols.values()),
        )
        self.cache[name] = self.cur.fetchone()["id"]
        return self.cache[name]


# ---------------------------------------------------------------- steps
def load_legacy_tables(cur, csv_dir: pathlib.Path, source: str, issues: list) -> dict[str, pd.DataFrame]:
    frames = {}
    for f in sorted(csv_dir.glob("*.csv")):
        name = f.stem
        df = read_csv(f)
        frames[name] = df
        tbl = f'"legacy_{name}"'
        cols = [c for c in df.columns]
        col_defs = ", ".join(f'"{c}" text' for c in cols)
        cur.execute(f"create table if not exists {tbl} (_row_no int, _source text, {col_defs})")
        # 舊檔若新增欄位，補欄
        cur.execute(
            "select column_name from information_schema.columns where table_name = %s", (f"legacy_{name}",)
        )
        existing = {r["column_name"] for r in cur.fetchall()}
        for c in cols:
            if c not in existing:
                cur.execute(f'alter table {tbl} add column "{c}" text')
        cur.execute(f"delete from {tbl} where _source = %s", (source,))
        if len(df):
            rows = [[i + 1, source] + [s(v) for v in rec] for i, rec in enumerate(df.itertuples(index=False, name=None))]
            with cur.copy(f'copy {tbl} (_row_no, _source, {", ".join(chr(34)+c+chr(34) for c in cols)}) from stdin') as cp:
                for r in rows:
                    cp.write_row(r)
        print(f"  legacy_{name:<24s} {len(df):6d} rows")
    return frames


def build_masters(cur, frames: dict, issues: list) -> dict:
    perf = frames["業績資料表"]
    L = {}
    L["company"] = Lookup(cur, "company")
    L["group"] = Lookup(cur, "business_group")
    L["salesperson"] = Lookup(cur, "salesperson")
    L["staff"] = Lookup(cur, "staff")
    L["industry"] = Lookup(cur, "industry")
    L["customer_category"] = Lookup(cur, "customer_category")
    L["sales_category"] = Lookup(cur, "sales_category")
    L["platform"] = Lookup(cur, "platform")
    L["media_channel"] = Lookup(cur, "media_channel")
    L["customer"] = Lookup(cur, "customer")

    # 組別 → 公司、轉撥旗標
    for g in perf["組別"].unique():
        gid = L["group"].get(g)
        if gid and s(g) in INTERCOMPANY_GROUPS:
            cur.execute("update business_group set is_intercompany = true where id = %s", (gid,))

    # 業務資料表：主管
    if "業務資料表" in frames:
        for r in frames["業務資料表"].itertuples(index=False):
            d = r._asdict() if hasattr(r, "_asdict") else dict(zip(frames["業務資料表"].columns, r))
            sid = L["salesperson"].get(d.get("業務名稱"))
            if sid:
                cur.execute("update salesperson set manager_name = nullif(%s,'') where id = %s", (s(d.get("主管")), sid))
    for name in perf["業務"].unique():
        L["salesperson"].get(name)

    # 人員（七種角色）
    role_names: dict[str, set] = defaultdict(set)
    for col, role in STAFF_ROLE_COLS.items():
        if col in perf.columns:
            for n in perf[col].unique():
                if s(n):
                    role_names[s(n)].add(role)
    for extra_tbl, role in [("媒體人員資料表", "MEDIA"), ("企劃人員資料表", "PLANNER"), ("文案人員資料表", "COPY"), ("協辦人員資料表", "ASSIST")]:
        if extra_tbl in frames:
            for n in frames[extra_tbl].iloc[:, 0].unique():
                if s(n):
                    role_names[s(n)].add(role)
    for n, roles in role_names.items():
        sid = L["staff"].get(n, roles=sorted(roles))
        cur.execute("update staff set roles = %s where id = %s", (sorted(roles), sid))

    # 產業別 / 客戶類別 / 業績類別（業績類別資料表 帶認定比例）
    for n in perf["產業別"].unique():
        L["industry"].get(n)
    for n in perf["客戶類別"].unique():
        L["customer_category"].get(n)
    if "業績類別資料表" in frames:
        for _, r in frames["業績類別資料表"].iterrows():
            scid = L["sales_category"].get(r["業績類別"])
            if scid:
                cur.execute(
                    "update sales_category set parent_category = nullif(%s,''), recognition_ratio = %s where id = %s",
                    (s(r["類別"]), num(r["毛利認定比例"], 1.0), scid),
                )
    for n in perf["業績類別"].unique():
        L["sales_category"].get(n)

    # 平台（主檔沒有的值自動補：名稱含「企」→ 企頻，含「新鮮視」→ 新鮮視，其餘 其它）
    if "平台資料表" in frames:
        for _, r in frames["平台資料表"].iterrows():
            pid = L["platform"].get(r["平台"], platform_group=s(r["平台歸類"]) or "其它")
            cur.execute("update platform set platform_group = %s, sort_order = %s where id = %s",
                        (s(r["平台歸類"]) or "其它", intn(r["顯示順序"]) or 99, pid))
    for n in perf["平台"].unique():
        n = s(n)
        if not n or n in L["platform"].cache:
            continue
        grp = "企頻" if "企" in n else "新鮮視" if "新鮮視" in n else "其它"
        L["platform"].get(n, platform_group=grp)
        issues.append(("業績資料表", n, "PLATFORM_NOT_IN_MASTER", {"platform": n, "assigned_group": grp}))

    # 電台 / 成本項目
    if "電台資料表" in frames:
        for _, r in frames["電台資料表"].iterrows():
            n = s(r["電台名稱"])
            ctype = "PRODUCTION" if n.startswith(PRODUCTION_PREFIX) else "MEDIA"
            mid = L["media_channel"].get(n, channel_type=ctype)
            cur.execute(
                "update media_channel set channel_type = %s, is_designated = %s, tax_rate = %s, sort_order = %s where id = %s",
                (ctype, boolean(r["指定電台"]), num(r["稅率"]), intn(r["電台順序"]) or 99, mid),
            )
    for n in perf["電台"].unique():
        n = s(n)
        if n and n not in L["media_channel"].cache:
            L["media_channel"].get(n, channel_type="PRODUCTION" if n.startswith(PRODUCTION_PREFIX) else "MEDIA")

    # 節目（name + 電台）
    cur.execute("select id, name, media_channel_id from program")
    prog_cache = {(r["name"], r["media_channel_id"]): r["id"] for r in cur.fetchall()}

    def program_id(name, channel_name):
        name = s(name)
        if not name:
            return None
        mid = L["media_channel"].get(channel_name) if s(channel_name) else None
        key = (name, mid)
        if key not in prog_cache:
            cur.execute(
                "insert into program(name, media_channel_id) values (%s, %s) on conflict (name, media_channel_id) do update set name = excluded.name returning id",
                (name, mid),
            )
            prog_cache[key] = cur.fetchone()["id"]
        return prog_cache[key]

    if "節目資料表" in frames:
        for _, r in frames["節目資料表"].iterrows():
            program_id(r["節目名稱"], r["電台名稱"])
    L["program_id"] = program_id

    # 客戶：客戶資料表 屬性 + 業績資料表 出現的所有名稱
    if "客戶資料表" in frames:
        for _, r in frames["客戶資料表"].iterrows():
            cid = L["customer"].get(r["客戶名稱"])
            if cid:
                cur.execute(
                    "update customer set customer_category_id = %s, industry_id = %s, is_new_case = %s, is_top1000 = %s where id = %s",
                    (L["customer_category"].get(r["客戶類別"]), L["industry"].get(r["產業別"]), boolean(r["新案"]), boolean(r["千大"]), cid),
                )
    for n in perf["客戶名稱"].unique():
        L["customer"].get(n)
    return L


def load_deals(cur, frames: dict, L: dict, source: str, issues: list) -> int:
    perf = frames["業績資料表"].copy()
    perf["_row_no"] = range(1, len(perf) + 1)
    perf["_ym"] = perf["業績年月份"].map(ym)
    perf["_line_type"] = [
        "PRODUCTION" if s(ch).startswith(PRODUCTION_PREFIX)
        else "INTERCOMPANY" if (s(g) in INTERCOMPANY_GROUPS or s(c) in INTERCOMPANY_GROUPS)
        else "MEDIA"
        for ch, g, c in zip(perf["電台"], perf["組別"], perf["公司別"])
    ]
    perf["_type_rank"] = perf["_line_type"].map({"MEDIA": 0, "PRODUCTION": 1, "INTERCOMPANY": 2})

    cur.execute("delete from invoice where legacy_source = %s", (source,))  # 先清發票（cascade writeoff）
    cur.execute("delete from deal where legacy_source = %s", (source,))     # cascade deal_line

    cur.execute("select id, default_region from platform")
    platform_region = {r["id"]: r["default_region"] or "ALL" for r in cur.fetchall()}

    n_lines = 0
    for contract_no, grp in perf.groupby("合約編號", sort=False):
        grp = grp.sort_values(["_type_rank", "_ym", "_row_no"], na_position="last")
        head = grp.iloc[0]
        # header 衝突紀錄（不影響匯入，line 自帶維度）
        for col in ["客戶名稱", "業務", "組別", "公司別"]:
            vals = {s(v) for v in grp[col] if s(v)}
            if len(vals) > 1:
                issues.append(("業績資料表", contract_no, "HEADER_CONFLICT", {"column": col, "values": sorted(vals)}))
        staff_ids = {DEAL_STAFF_COLS[c]: L["staff"].get(head[c]) for c in DEAL_STAFF_COLS if c in grp.columns}
        air_start = min((d for d in map(dt, grp["上檔起始日期"]) if d), default=None)
        air_end = max((d for d in map(dt, grp["上檔結束日期"]) if d), default=None)
        cur.execute(
            """insert into deal(contract_no, company_id, customer_id, ad_name, salesperson_id, group_id, sales_category_id,
                                customer_category_id, industry_id, air_start, air_end, order_ym, contract_term,
                                media_staff_id, planner_staff_id, copy_staff_id, assist_staff_id, cs_staff_id, billing_staff_id, closing_staff_id,
                                is_original_received, is_copy_received, is_sales_signed, notes, legacy_source, created_by)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'etl') returning id""",
            (
                s(contract_no), L["company"].get(head["公司別"]), L["customer"].get(head["客戶名稱"]), s(head["廣告名稱"]) or None,
                L["salesperson"].get(head["業務"]), L["group"].get(head["組別"]), L["sales_category"].get(head["業績類別"]),
                L["customer_category"].get(head["客戶類別"]), L["industry"].get(head["產業別"]), air_start, air_end,
                ym(head["進單年月"]), s(head["合約期限"]) or None,
                staff_ids.get("media_staff_id"), staff_ids.get("planner_staff_id"), staff_ids.get("copy_staff_id"),
                staff_ids.get("assist_staff_id"), staff_ids.get("cs_staff_id"), staff_ids.get("billing_staff_id"), staff_ids.get("closing_staff_id"),
                boolean(head["正本"]), boolean(head["影本"]), boolean(head["業務簽名"]), None, source,
            ),
        )
        deal_id = cur.fetchone()["id"]

        rows = []
        for line_no, (_, r) in enumerate(grp.iterrows(), start=1):
            if r["_ym"] is None:
                issues.append(("業績資料表", int(r["_row_no"]), "BAD_PERF_YM", {"value": s(r["業績年月份"]), "contract_no": s(contract_no)}))
                continue
            pid = L["platform"].get(r["平台"])
            region = platform_region.get(pid, "ALL") if pid else "ALL"
            rows.append((
                deal_id, line_no, r["_line_type"], r["_ym"], ym(r["BLINK認列年月"]), ym(r["進單年月"]),
                L["company"].get(r["公司別"]), L["customer"].get(r["客戶名稱"]), L["salesperson"].get(r["業務"]), L["group"].get(r["組別"]),
                L["sales_category"].get(r["業績類別"]), L["customer_category"].get(r["客戶類別"]), L["industry"].get(r["產業別"]),
                pid, L["media_channel"].get(r["電台"]), L["program_id"](r["節目名稱"], r["電台"]), [region],
                boolean(r["聯網"]), boolean(r["指定電台"]),
                num(r["實收金額"]), num(r["退佣折扣"]), 0, num(r["除佣實收"]), num(r["實付金額"]), num(r["電台實付金額"]), num(r["媒體效益"]),
                intn(r["購買檔次"]), intn(r["搭贈檔次"]), num(r["搭贈金額"]) if s(r["搭贈金額"]) else None, s(r["搭贈組合"]) or None,
                intn(r["編播贈檔"]), boolean(r["搭贈方案"]), intn(r["BLINK檔數"]), intn(r["達鈴通數"]), num(r["責任檔"]) if s(r["責任檔"]) else None,
                boolean(r["電台已付款"]), dt(r["收款日期"]), dt(r["預計發票日"]),
                boolean(r["低毛利已處理"]), s(r["低毛利原因"]) or None, boolean(r["不計客服獎金"]), s(r["備註"]) or None,
                source, int(r["_row_no"]), s(r["客戶名稱"]) or None, s(r["建立者"]) or "etl",
            ))
        if rows:
            cur.executemany(
                """insert into deal_line(deal_id, line_no, line_type, perf_ym, blink_ym, order_ym,
                     company_id, customer_id, salesperson_id, group_id, sales_category_id, customer_category_id, industry_id,
                     platform_id, media_channel_id, program_id, region_codes, is_network, is_designated,
                     gross_amount, rebate_pct, cash_discount_pct, net_amount, cost_amount, channel_cost_amount, media_benefit,
                     purchased_slots, bonus_slots, bonus_amount, bonus_combo, edited_bonus_slots, is_bonus_plan, blink_slots, daling_count, responsibility_slots,
                     is_channel_paid, payment_received_on, planned_invoice_on, low_margin_handled, low_margin_reason, exclude_cs_bonus, notes,
                     legacy_source, legacy_row_no, legacy_customer_name, created_by)
                   values (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s)""",
                rows,
            )
            n_lines += len(rows)
    return n_lines


def load_invoices(cur, frames: dict, L: dict, source: str, issues: list) -> int:
    if "發票開立資料表" not in frames:
        return 0
    inv = frames["發票開立資料表"]
    cur.execute("delete from invoice where legacy_source = %s", (source,))  # cascade writeoff
    cur.execute("select id, contract_no from deal")
    deal_by_no = {r["contract_no"]: r["id"] for r in cur.fetchall()}
    n = 0
    for i, r in inv.iterrows():
        contract_no = s(r["合約編號"])
        cur.execute(
            """insert into invoice(legacy_seq, deal_id, contract_no, customer_id, customer_title, customer_tax_id, salesperson_id, group_id, ad_name,
                 air_start, air_end, invoice_due_on, expected_cash_on, payment_method, ad_income, production_income, sales_allowance,
                 cash_discount_pct, cash_discount_amount, rebate_pct, rebate_amount, discount_method, allowance_note_amount, invoice_allowance_amount,
                 invoice_no, invoice_issued_on, invoice_delivered_on, invoice_signed, invoice_signed_by, invoice_signed_at,
                 finance_signed, finance_signed_by, finance_signed_at, notes, notes2, legacy_source, legacy_row_no, created_by)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,'etl') returning id""",
            (
                intn(r["單號"]), deal_by_no.get(contract_no), contract_no or None, L["customer"].get(r["客戶名稱"]), s(r["客戶公司抬頭"]) or None,
                s(r["客戶統一編號"]) or None, L["salesperson"].get(r["業務"]), L["group"].get(r["組別"]), s(r["廣告名稱"]) or None,
                dt(r["上檔起始日期"]), dt(r["上檔結束日期"]), dt(r["發票應交付日"]), dt(r["預定兌現日"]), s(r["收款方式"]) or None,
                num(r["廣告收入"]), num(r["製作收入"]), num(r["銷貨折讓金額"]),
                num(r["現金折扣"]), num(r["現金折扣金額"]), num(r["退佣折扣"]), num(r["退佣折扣金額"]), s(r["折扣方式"]) or None,
                num(r["折讓單金額"]), num(r["發票折讓金額"]),
                s(r["發票號碼"]) or None, dt(r["發票開立日"]), dt(r["發票交付日"]), boolean(r["發票簽收"]), s(r["發票簽收人"]) or None,
                pd.to_datetime(s(r["發票簽收時間"])) if s(r["發票簽收時間"]) else None,
                boolean(r["財務簽收"]), s(r["財務簽收人"]) or None,
                pd.to_datetime(s(r["財務簽收時間"])) if s(r["財務簽收時間"]) else None,
                s(r["備註"]) or None, s(r["備註2"]) or None, source, i + 1,
            ),
        )
        invoice_id = cur.fetchone()["id"]
        # 舊系統三組銷帳欄位 → writeoff（有金額才建）
        for amt_col, date_col, role in [("銷帳金額", "銷帳日", None), ("銷帳金額-業助", "銷帳日期-業助", "ASSIST"), ("銷帳金額-財務", "銷帳日期-財務", "FINANCE")]:
            amt = num(r[amt_col])
            d = dt(r[date_col])
            if amt and d:
                cur.execute(
                    "insert into writeoff(invoice_id, deal_id, received_on, received_amount, method, entered_role, remark, legacy_source, created_by) values (%s,%s,%s,%s,%s,%s,%s,%s,'etl')",
                    (invoice_id, deal_by_no.get(contract_no), d, amt, s(r["收款方式"]) or None, role, f"legacy {amt_col}", source),
                )
            elif amt and not d:
                issues.append(("發票開立資料表", i + 1, "WRITEOFF_AMOUNT_WITHOUT_DATE", {"column": amt_col, "amount": amt}))
        n += 1
    return n


def load_bonus_rules(cur, frames: dict, L: dict, source: str, issues: list) -> int:
    if "獎金百分比資料表" not in frames:
        return 0
    b = frames["獎金百分比資料表"]
    cur.execute("delete from bonus_rule where note like %s", (f"legacy:{source}%",))
    n = 0
    for i, r in b.iterrows():
        plat, item, pct = s(r["平台"]), s(r["業績項目"]), num(r["獎金百分比"])
        if plat not in {"企頻", "廣播", "新鮮視"} or pct <= 0:
            continue
        f, t = ym(r["年月開始"]), ym(r["年月結束"])
        if not f:
            continue
        cur.execute(
            "insert into bonus_rule(salesperson_id, platform_group, sales_item, ym_from, ym_to, bonus_pct, threshold_amount, note) values (%s,%s,%s,%s,%s,%s,%s,%s)",
            # 舊表存小數（0.02 = 2%），bonus_rule 存百分比數字（2 = 2%）
            (L["salesperson"].get(r["業務"]), plat, item or None, f, t, round(pct * 100, 4), num(r["業績門檻"]), f"legacy:{source} row {i+1}"),
        )
        n += 1
    return n


def load_users(cur, frames: dict, L: dict, out_dir: pathlib.Path) -> int:
    if "legacy_users" not in frames:
        return 0
    try:
        import bcrypt
    except ImportError:
        print("  !! 未安裝 bcrypt，略過 app_user 建立（pip install bcrypt）")
        return 0
    users = frames["legacy_users"]
    user_sales = {}
    if "使用者業務資料表" in frames:
        for _, r in frames["使用者業務資料表"].iterrows():
            user_sales[s(r["使用者"]).lower()] = s(r["業務"])
    cur.execute("select username from app_user")
    existing = {r["username"] for r in cur.fetchall()}
    lines, n = [], 0
    for _, r in users.iterrows():
        uname = s(r["使用者"]).lower()
        if not uname or uname in existing:
            continue  # 舊系統帳號大小寫混用（JAMES / james）→ 視為同一人
        existing.add(uname)
        sales_name = user_sales.get(uname)
        role = "EXEC" if boolean(r["機密報表權限"]) else ("SALES" if sales_name else "MEDIA")
        pw = secrets.token_urlsafe(8)
        h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "insert into app_user(username, password_hash, display_name, role, salesperson_id, must_change_password) values (%s,%s,%s,%s,%s,true)",
            (uname, h, s(r["使用者"]), role, L["salesperson"].get(sales_name) if sales_name else None),
        )
        lines.append(f"{uname}\t{pw}\t{role}")
        n += 1
    if lines:
        p = out_dir / "seed_passwords.local.txt"
        p.write_text("username\tpassword\trole\n" + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"  初始密碼寫到 {p}（已在 .gitignore，發給同仁後刪除）")
    return n


def reconcile(cur, frames: dict, source: str) -> bool:
    perf = frames["業績資料表"].copy()
    perf["_ym"] = perf["業績年月份"].map(ym)
    perf = perf[perf["_ym"].notna()]
    for c in ["實收金額", "除佣實收", "實付金額"]:
        perf[c] = perf[c].map(num)
    exp = perf.groupby(["_ym", "公司別"]).agg(rows=("合約編號", "size"), gross=("實收金額", "sum"), net=("除佣實收", "sum"), cost=("實付金額", "sum"))
    cur.execute(
        """select perf_ym, coalesce(company,'') as company, count(*) as rows, sum(gross_amount) as gross, sum(net_amount) as net, sum(cost_amount) as cost
           from v_deal_line_flat where legacy_source = %s group by perf_ym, company""",
        (source,),
    )
    got = {(r["perf_ym"], r["company"]): r for r in cur.fetchall()}
    bad = 0
    for (d, comp), e in exp.iterrows():
        g = got.get((d, comp))
        if not g:
            print(f"  !! 缺少 {d} {comp}")
            bad += 1
            continue
        for k, ek in [("rows", "rows"), ("gross", "gross"), ("net", "net"), ("cost", "cost")]:
            if abs(float(g[k]) - float(e[ek])) > 1:
                print(f"  !! {d:%Y/%m} {comp:6s} {k}: db={float(g[k]):,.0f} csv={float(e[ek]):,.0f}")
                bad += 1
    print(f"  對帳 {len(exp)} 組 (年月 × 公司別)，不符 {bad} 項")
    return bad == 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="legacy_csv")
    ap.add_argument("--source", default="ACCESS_2026_V109g")
    args = ap.parse_args()
    csv_dir = pathlib.Path(args.csv)
    if not (csv_dir / "業績資料表.csv").exists():
        print(f"找不到 {csv_dir}/業績資料表.csv")
        return 2
    issues: list = []
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("select set_config('app.user_name', 'etl', true)")
                cur.execute("select set_config('app.skip_audit', 'on', true)")  # 匯入不寫 audit_log
                cur.execute("delete from etl_run where source = %s", (args.source,))  # 舊的 run 與 issue 一併清掉
                cur.execute("insert into etl_run(source) values (%s) returning id", (args.source,))
                run_id = cur.fetchone()["id"]
                print("1) legacy 原樣匯入")
                frames = load_legacy_tables(cur, csv_dir, args.source, issues)
                print("2) 主檔")
                L = build_masters(cur, frames, issues)
                print("3) deal / deal_line")
                n_lines = load_deals(cur, frames, L, args.source, issues)
                print(f"   {n_lines} lines")
                print("4) invoice / writeoff")
                print(f"   {load_invoices(cur, frames, L, args.source, issues)} invoices")
                print("5) bonus_rule（參考用）")
                print(f"   {load_bonus_rules(cur, frames, L, args.source, issues)} rules")
                print("6) app_user")
                print(f"   {load_users(cur, frames, L, pathlib.Path('.'))} users")
                for tbl, ref, issue, detail in issues:
                    cur.execute(
                        "insert into etl_issue(run_id, table_name, row_ref, issue, detail) values (%s,%s,%s,%s,%s)",
                        (run_id, tbl, str(ref), issue, json.dumps(detail, ensure_ascii=False)),
                    )
                cur.execute("update etl_run set finished_at = now(), rows_in = %s, rows_out = %s, note = %s where id = %s",
                            (len(frames["業績資料表"]), n_lines, f"issues={len(issues)}", run_id))
                print(f"   etl_issue {len(issues)} 筆（HEADER_CONFLICT 為資訊性，不是錯誤）")
                print("7) 對帳")
                ok = reconcile(cur, frames, args.source)
                if not ok:
                    raise SystemExit("對帳不符，已 rollback；請檢查上面的差異")
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
