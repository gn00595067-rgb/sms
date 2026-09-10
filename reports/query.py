"""
query.py — 依 registry + 篩選值組 SQL（只用參數化查詢）

安全：group by 欄位一律來自 registry 的 group_by_options（白名單）；
所有值都用參數綁定，不做字串拼接。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect  # noqa: E402

from reports.registry import report

# 彙總模式：measure → SQL 片段
MEASURE_SQL = {
    "line_count": "count(*)",
    "deal_count": "count(distinct contract_no)",
    "gross_amount": "sum(gross_amount)",
    "net_amount": "sum(net_amount)",
    "cost_amount": "sum(cost_amount)",
    "gross_profit": "sum(gross_profit)",
    "recognized_amount": "sum(recognized_amount)",
    "total_frames": "sum(total_frames)",
    "total_seconds": "sum(total_seconds)",
    "purchased_slots": "sum(purchased_slots)",
    "bonus_slots": "sum(bonus_slots)",
    "blink_slots": "sum(blink_slots)",
    # 比率不能平均：Σ毛利 / Σ除佣
    "margin_pct": "case when sum(net_amount) <> 0 then round(sum(gross_profit) / sum(net_amount), 4) end",
}

# 每個 view 支援哪些篩選 → (SQL 片段, 值轉換)。片段用 %s 綁參數。
_LIKE = lambda v: f"%{v}%"  # noqa: E731


def _view_filters(view: str) -> dict:
    common_ym = ("perf_ym between %s and %s", "ym_range")
    f = {
        "v_deal_line_flat": {
            "ym_range": ("perf_ym between %s and %s", None),
            "company": ("company = %s", None),
            "platform_group": ("platform_group = %s", None),
            "platform": ("platform = %s", None),
            "region": ("%s = any(region_codes)", None),
            "salesperson": ("salesperson = %s", None),
            "business_group": ("business_group = %s", None),
            "sales_category": ("sales_category = %s", None),
            "industry": ("industry = %s", None),
            "customer": ("customer ilike %s", _LIKE),
            "line_type": ("line_type = %s", None),
        },
        "v_profit_two_layer": {
            "ym_range": ("perf_ym between %s and %s", None),
            "platform_group": ("platform_group = %s", None),
        },
        "v_media_volume": {
            "ym_range": ("perf_ym between %s and %s", None),
            "company": ("company = %s", None),
            "platform_group": ("platform_group = %s", None),
            "platform": ("platform = %s", None),
            "region": ("region_code = %s", None),
        },
        "v_sales_recognition": {
            "ym_range": ("perf_ym between %s and %s", None),
            "company": ("company = %s", None),
            "salesperson": ("salesperson = %s", None),
        },
        "v_ar_open": {
            "salesperson": ("salesperson = %s", None),
            "customer": ("customer ilike %s", _LIKE),
        },
        "v_bonus_simple": {
            "ym_range": ("perf_ym between %s and %s", None),
            "salesperson": ("salesperson = %s", None),
            "platform_group": ("platform_group = %s", None),
        },
        "v_customer_ranking": {
            "perf_year": ("perf_year = %s", None),
            "company": ("company = %s", None),
        },
    }
    return f.get(view, {})


# SALES 角色範圍限制（依業務名稱）
_SALES_SCOPE = {
    "v_deal_line_flat": "salesperson = %s",
    "v_sales_recognition": "salesperson = %s",
    "v_bonus_simple": "salesperson = %s",
    "v_ar_open": "salesperson = %s",
    "v_customer_ranking": "customer in (select distinct customer from v_deal_line_flat where salesperson = %s)",
}


def salesperson_name(salesperson_id: int | None) -> str | None:
    if salesperson_id is None:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select name from salesperson where id = %s", (salesperson_id,))
            r = cur.fetchone()
    return r["name"] if r else None


def _build_where(view: str, filters: dict, user: dict | None, apply_sales_scope: bool) -> tuple[list[str], list]:
    handlers = _view_filters(view)
    clauses, params = [], []
    for key, val in (filters or {}).items():
        if val is None or val == "":
            continue
        if key == "ym_range":
            frag, _ = handlers.get("ym_range", (None, None))
            if frag:
                clauses.append(frag)
                params.extend([filters.get("ym_from"), filters.get("ym_to")])
            continue
        if key in ("ym_from", "ym_to"):
            continue
        h = handlers.get(key)
        if not h:
            continue
        frag, conv = h
        clauses.append(frag)
        params.append(conv(val) if conv else val)
    # SALES 範圍
    if apply_sales_scope and user and user.get("role") == "SALES":
        scope = _SALES_SCOPE.get(view)
        name = salesperson_name(user.get("salesperson_id"))
        if scope and name:
            clauses.append(scope)
            params.append(name)
        elif scope is None:
            # 該 view 無法依業務限縮 → 保守起見回傳不可能條件
            clauses.append("false")
    return clauses, params


def _fetch(sql: str, params: list) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())


def _order_by(sort_spec, available: list[str]) -> str:
    parts = []
    for col, direction in (sort_spec or []):
        if col in available:
            parts.append(f"{col} {'desc' if direction == 'desc' else 'asc'}")
    return (" order by " + ", ".join(parts)) if parts else ""


def run_report(key: str, filters: dict, *, group_by_label: str | None = None,
               user: dict | None = None, top_n: int | None = None) -> pd.DataFrame:
    r = report(key)
    view = r["view"]
    apply_scope = r.get("sales_scope", False)
    where, params = _build_where(view, filters, user, apply_scope)
    if r.get("only_open"):
        where.append("not is_settled")
    where_sql = (" where " + " and ".join(where)) if where else ""

    if r.get("mode") == "aggregate" and group_by_label and r["group_by_options"].get(group_by_label):
        group_cols = r["group_by_options"][group_by_label]          # 白名單
        measures = r["measures"]
        select_cols = list(group_cols) + [f"{MEASURE_SQL[m]} as {m}" for m in measures if m in MEASURE_SQL]
        sql = f"select {', '.join(select_cols)} from {view}{where_sql} group by {', '.join(group_cols)}"
        sql += _order_by(r.get("default_sort"), group_cols)
        return _fetch(sql, params)

    # direct / 明細
    if r.get("mode") == "aggregate":  # 明細模式
        cols = r["detail_columns"]
    else:
        cols = r.get("columns")
    select = "*" if not cols else ", ".join(cols)
    sql = f"select {select} from {view}{where_sql}"
    sql += _order_by(r.get("default_sort"), cols or [])
    if top_n:
        sql += " limit %s"
        params = params + [int(top_n)]
    df = _fetch(sql, params)
    if cols and not df.empty:
        df = df[[c for c in cols if c in df.columns]]
    return df


def totals_row(df: pd.DataFrame, sum_cols: list[str], net_col: str = "net_amount",
               gp_col: str = "gross_profit") -> dict:
    """合計列：sum_cols 相加；margin_pct 重算（Σ毛利/Σ除佣）。"""
    if df is None or df.empty:
        return {}
    row = {}
    for c in sum_cols:
        if c in df.columns:
            row[c] = float(pd.to_numeric(df[c], errors="coerce").fillna(0).sum())
    if "margin_pct" in df.columns and net_col in df.columns and gp_col in df.columns:
        net = float(pd.to_numeric(df[net_col], errors="coerce").fillna(0).sum())
        gp = float(pd.to_numeric(df[gp_col], errors="coerce").fillna(0).sum())
        row["margin_pct"] = round(gp / net, 4) if net else None
    return row
