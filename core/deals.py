"""
deals.py — deal / deal_line 讀寫 + 子公司轉撥線

save_deal 以一個交易 upsert deal，並以 deal_id 為單位「先刪後插」deal_line。
make_intercompany_line 依 intercompany_rule 由子公司 MEDIA 線產生一條 INTERCOMPANY 線。
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402

# deal 可寫欄位
DEAL_COLS = [
    "contract_no", "company_id", "customer_id", "ad_name", "salesperson_id", "group_id",
    "sales_category_id", "customer_category_id", "industry_id", "category_dc",
    "air_start", "air_end", "order_ym", "contract_term",
    "media_staff_id", "planner_staff_id", "copy_staff_id", "assist_staff_id",
    "cs_staff_id", "billing_staff_id", "closing_staff_id",
    "is_original_received", "is_copy_received", "is_sales_signed", "notes",
]

# deal_line 可寫欄位（不含 total_seconds：generated）
LINE_COLS = [
    "line_no", "line_type", "perf_ym", "blink_ym", "order_ym",
    "company_id", "customer_id", "salesperson_id", "group_id", "sales_category_id",
    "customer_category_id", "industry_id", "platform_id", "media_channel_id", "program_id",
    "region_codes", "is_network", "is_designated",
    "gross_amount", "rebate_pct", "cash_discount_pct", "net_amount", "cost_amount",
    "channel_cost_amount", "media_benefit",
    "material_seconds", "total_frames", "purchased_slots", "bonus_slots", "bonus_amount",
    "bonus_combo", "edited_bonus_slots", "is_bonus_plan", "blink_slots", "daling_count",
    "responsibility_slots", "is_channel_paid", "payment_received_on", "planned_invoice_on",
    "low_margin_handled", "low_margin_reason", "exclude_cs_bonus", "notes",
]

# 子公司 → 轉撥組別名 / 轉撥客戶名
INTERCOMPANY_MAP = {
    "東吳": {"group": "聲活-東", "customer": "東吳廣告"},
    "鉑霖": {"group": "聲活-鉑", "customer": "鉑霖廣告"},
}


# ------------------------------------------------------------------ 公式
def compute_net(gross, rebate_pct, cash_discount_pct) -> int:
    """除佣實收 = round(gross × (1 − rebate/100) × (1 − cash_discount/100))。"""
    g = Decimal(str(gross or 0))
    r = Decimal(str(rebate_pct or 0)) / Decimal(100)
    c = Decimal(str(cash_discount_pct or 0)) / Decimal(100)
    val = g * (Decimal(1) - r) * (Decimal(1) - c)
    return int(val.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _round0(v) -> int:
    return int(Decimal(str(v or 0)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ 讀取
def load_deal(contract_no: str) -> tuple[dict | None, pd.DataFrame]:
    """回傳 (header dict | None, lines DataFrame from v_deal_line_flat)。"""
    contract_no = (contract_no or "").strip()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select * from deal where contract_no = %s", (contract_no,))
            header = cur.fetchone()
            if not header:
                return None, pd.DataFrame()
            cur.execute(
                "select * from v_deal_line_flat where contract_no = %s order by line_no",
                (contract_no,),
            )
            lines = pd.DataFrame(cur.fetchall())
    return dict(header), lines


def deal_totals(lines: pd.DataFrame) -> dict:
    """合計：實收 / 除佣 / 實付 / 毛利。"""
    if lines is None or lines.empty:
        return {"gross_amount": 0, "net_amount": 0, "cost_amount": 0, "gross_profit": 0}
    def _sum(col):
        return float(pd.to_numeric(lines[col], errors="coerce").fillna(0).sum()) if col in lines else 0.0
    net, cost = _sum("net_amount"), _sum("cost_amount")
    return {
        "gross_amount": _sum("gross_amount"),
        "net_amount": net,
        "cost_amount": cost,
        "gross_profit": net - cost,
    }


# ------------------------------------------------------------------ 轉撥線
def _find_rate(rules: pd.DataFrame, from_company: str, platform_group: str, perf_ym: date) -> float:
    """從 intercompany_rules DataFrame 找生效中的 rate；找不到回 0.65。"""
    if rules is None or rules.empty:
        return 0.65
    df = rules[rules["from_company"] == from_company]
    if df.empty:
        return 0.65
    best = None
    for _, r in df.iterrows():
        if perf_ym is not None:
            if r["ym_from"] and perf_ym < r["ym_from"]:
                continue
            if r["ym_to"] and perf_ym > r["ym_to"]:
                continue
        pg = r.get("platform_group")
        if pg and platform_group and pg != platform_group:
            continue
        # 指定平台歸類優先於通用
        score = 1 if pg else 0
        if best is None or score > best[0]:
            best = (score, float(r["rate"]))
    return best[1] if best else 0.65


def make_intercompany_line(line: dict, rules: pd.DataFrame) -> dict | None:
    """
    給一條子公司（東吳/鉑霖）的 MEDIA 線 dict，產生一條 INTERCOMPANY 線 dict。
    line 需含：company（名稱）、net_amount、platform_group、perf_ym 及各維度 id。
    回傳的 dict 用 *_name 表示待解析的組別/客戶（save 時 get-or-create）。
    非子公司或非 MEDIA 線回 None。
    """
    company = (line.get("company") or "").strip()
    if company not in INTERCOMPANY_MAP:
        return None
    if (line.get("line_type") or "MEDIA") != "MEDIA":
        return None
    m = INTERCOMPANY_MAP[company]
    rate = _find_rate(rules, company, line.get("platform_group") or "", line.get("perf_ym"))
    amount = _round0(float(line.get("net_amount") or 0) * rate)
    new = {
        "line_type": "INTERCOMPANY",
        "perf_ym": line.get("perf_ym"),
        "blink_ym": line.get("blink_ym"),
        "order_ym": line.get("order_ym"),
        "company_id": line.get("company_id"),        # 同公司別
        "company": company,
        "customer_name": m["customer"],               # 東吳廣告 / 鉑霖廣告（save 時建）
        "group_name": m["group"],                     # 聲活-東 / 聲活-鉑
        "salesperson_id": line.get("salesperson_id"),
        "sales_category_id": line.get("sales_category_id"),
        "customer_category_id": line.get("customer_category_id"),
        "industry_id": line.get("industry_id"),
        "platform_id": line.get("platform_id"),
        "platform_group": line.get("platform_group"),
        "media_channel_id": line.get("media_channel_id"),
        "program_id": line.get("program_id"),
        "region_codes": line.get("region_codes") or ["ALL"],
        "gross_amount": amount,
        "net_amount": amount,
        "cost_amount": 0,
        "rebate_pct": 0,
        "cash_discount_pct": 0,
        "_rate": rate,
        "_source_amount": amount,   # 若原線 cost 為 0，save 時把原線 cost 設為此金額
    }
    return new


def generate_intercompany(lines: list[dict], rules: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """
    對一批線（list[dict]，需含 company 名稱/net_amount/platform_group/perf_ym/line_type）：
      - 對每條「子公司 MEDIA 線」且尚無對應 INTERCOMPANY 線者，產生一條轉撥線；
      - 若原線 cost_amount 為 0，把原線 cost_amount 設為轉撥金額（對齊舊資料做法）。
    回傳 (更新後的完整線清單, 新產生的轉撥線清單) 供預覽。
    """
    existing_ic = sum(1 for ln in lines if (ln.get("line_type") == "INTERCOMPANY"))
    result = [dict(ln) for ln in lines]
    new_lines = []
    for ln in result:
        if (ln.get("line_type") or "MEDIA") != "MEDIA":
            continue
        if (ln.get("company") or "").strip() not in INTERCOMPANY_MAP:
            continue
        ic = make_intercompany_line(ln, rules)
        if ic is None:
            continue
        # 原線 cost 為 0 → 設為轉撥金額
        if not ln.get("cost_amount"):
            ln["cost_amount"] = ic["_source_amount"]
        new_lines.append(ic)
    # 已有轉撥線就不重複產生（MVP：只在完全沒有轉撥線時產生）
    if existing_ic and new_lines:
        return lines, []
    return result + new_lines, new_lines


def _get_or_create_customer(cur, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    cur.execute("select id from customer where name = %s", (name,))
    r = cur.fetchone()
    if r:
        return r["id"]
    cur.execute("insert into customer(name) values (%s) returning id", (name,))
    return cur.fetchone()["id"]


def _get_group_id(cur, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    cur.execute("select id from business_group where name = %s", (name,))
    r = cur.fetchone()
    return r["id"] if r else None


# ------------------------------------------------------------------ 寫入
def _norm_line(line: dict, header: dict, cur) -> dict:
    """把一條 UI 線正規化成 LINE_COLS 的 dict：帶入 header 預設、解析轉撥名稱、算 net。"""
    out = {c: line.get(c) for c in LINE_COLS}
    # header 預設維度
    for dim in ["company_id", "customer_id", "salesperson_id", "group_id",
                "sales_category_id", "customer_category_id", "industry_id"]:
        if out.get(dim) in (None, "") and header.get(dim) is not None:
            out[dim] = header.get(dim)
    # 轉撥線的組別/客戶用名稱解析
    if line.get("group_name"):
        out["group_id"] = _get_group_id(cur, line["group_name"])
    if line.get("customer_name"):
        out["customer_id"] = _get_or_create_customer(cur, line["customer_name"])
    # line_type 預設 MEDIA
    if not out.get("line_type"):
        out["line_type"] = "MEDIA"
    # 區域預設
    if not out.get("region_codes"):
        out["region_codes"] = ["ALL"]
    # net 自動：使用者沒填（None）就用公式
    if out.get("net_amount") in (None, ""):
        out["net_amount"] = compute_net(out.get("gross_amount"), out.get("rebate_pct"), out.get("cash_discount_pct"))
    # NOT NULL 欄位補預設（避免顯式塞 NULL 蓋掉 DB default）
    for c in ("gross_amount", "rebate_pct", "cash_discount_pct", "net_amount", "cost_amount",
              "channel_cost_amount", "media_benefit"):
        if out.get(c) in (None, ""):
            out[c] = 0
    for c in ("is_network", "is_designated", "is_bonus_plan", "is_channel_paid",
              "low_margin_handled", "exclude_cs_bonus"):
        out[c] = bool(out.get(c))
    return out


def save_deal(header: dict, lines, user: str) -> tuple[int, int]:
    """
    upsert deal + 先刪後插 deal_line（一個交易）。
    header：deal 欄位 dict（含 contract_no）。lines：list[dict] 或 DataFrame。
    回傳 (deal_id, 寫入線數)。
    """
    if isinstance(lines, pd.DataFrame):
        lines = lines.to_dict("records")
    contract_no = (header.get("contract_no") or "").strip()
    if not contract_no:
        raise ValueError("缺少合約編號")

    with transaction(user) as cur:
        # upsert deal
        cur.execute("select id from deal where contract_no = %s", (contract_no,))
        row = cur.fetchone()
        deal_vals = {c: header.get(c) for c in DEAL_COLS}
        deal_vals["contract_no"] = contract_no
        for c in ("is_original_received", "is_copy_received", "is_sales_signed"):
            deal_vals[c] = bool(deal_vals.get(c))
        if row:
            deal_id = row["id"]
            set_cols = [c for c in DEAL_COLS if c != "contract_no"]
            cur.execute(
                f"update deal set {', '.join(f'{c} = %s' for c in set_cols)}, updated_by = %s where id = %s",
                [deal_vals[c] for c in set_cols] + [user, deal_id],
            )
        else:
            cols = DEAL_COLS + ["legacy_source", "created_by"]
            cur.execute(
                f"insert into deal({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) returning id",
                [deal_vals[c] for c in DEAL_COLS] + [None, user],
            )
            deal_id = cur.fetchone()["id"]

        # 先刪後插 deal_line
        cur.execute("delete from deal_line where deal_id = %s", (deal_id,))
        n = 0
        for i, ln in enumerate(lines, start=1):
            norm = _norm_line(ln, header, cur)
            if not norm.get("line_no"):
                norm["line_no"] = i
            cols = ["deal_id"] + LINE_COLS + ["created_by"]
            vals = [deal_id] + [norm.get(c) for c in LINE_COLS] + [user]
            cur.execute(
                f"insert into deal_line({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                vals,
            )
            n += 1
    return deal_id, n


def delete_deal(contract_no: str, user: str) -> bool:
    contract_no = (contract_no or "").strip()
    with transaction(user) as cur:
        cur.execute("delete from deal where contract_no = %s", (contract_no,))
        deleted = cur.rowcount
    return deleted > 0
