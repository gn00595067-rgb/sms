"""
finance.py — 發票 / 銷帳讀寫
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402

# 發票可編輯欄位（MVP）
INVOICE_COLS = [
    "deal_id", "contract_no", "customer_id", "customer_title", "customer_tax_id",
    "salesperson_id", "group_id", "ad_name", "payment_method",
    "ad_income", "production_income", "allowance_note_amount",
    "invoice_no", "invoice_issued_on", "invoice_due_on", "expected_cash_on",
    "settled_manually", "settled_note", "notes",
]


def _df(sql: str, params=None) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())


def list_ar(where_sql: str = "", params=None, only_open: bool = False) -> pd.DataFrame:
    sql = "select * from v_ar_open"
    clauses = []
    if where_sql:
        clauses.append(where_sql)
    if only_open:
        clauses.append("not is_settled")
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by expected_cash_on nulls last, invoice_id"
    return _df(sql, params)


def load_invoice(invoice_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select * from invoice where id = %s", (invoice_id,))
            r = cur.fetchone()
    return dict(r) if r else None


def deal_defaults_for_invoice(contract_no: str) -> dict | None:
    """輸入合約編號帶出 deal 的客戶/業務/組別/廣告名稱。"""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id as deal_id, customer_id, salesperson_id, group_id, ad_name from deal where contract_no = %s",
                ((contract_no or "").strip(),),
            )
            r = cur.fetchone()
    return dict(r) if r else None


def save_invoice(data: dict, user: str, invoice_id: int | None = None) -> int:
    vals = {c: data.get(c) for c in INVOICE_COLS}
    with transaction(user) as cur:
        if invoice_id:
            cur.execute(
                f"update invoice set {', '.join(f'{c} = %s' for c in INVOICE_COLS)}, updated_by = %s where id = %s",
                [vals[c] for c in INVOICE_COLS] + [user, invoice_id],
            )
            return invoice_id
        cols = INVOICE_COLS + ["created_by"]
        cur.execute(
            f"insert into invoice({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) returning id",
            [vals[c] for c in INVOICE_COLS] + [user],
        )
        return cur.fetchone()["id"]


def writeoffs_for(invoice_id: int) -> pd.DataFrame:
    return _df(
        "select id, received_on, received_amount, method, bank_ref, entered_role, remark "
        "from writeoff where invoice_id = %s order by received_on",
        (invoice_id,),
    )


def add_writeoff(invoice_id: int, data: dict, user: str) -> int:
    with transaction(user) as cur:
        cur.execute("select deal_id from invoice where id = %s", (invoice_id,))
        r = cur.fetchone()
        deal_id = r["deal_id"] if r else None
        cur.execute(
            """insert into writeoff(invoice_id, deal_id, received_on, received_amount, method, bank_ref,
                                    entered_role, remark, created_by)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (invoice_id, deal_id, data.get("received_on"), data.get("received_amount"),
             data.get("method"), data.get("bank_ref"), "FINANCE", data.get("remark"), user),
        )
        return cur.fetchone()["id"]


def mark_settled(invoice_ids: list[int], note: str, user: str, settled: bool = True) -> int:
    if not invoice_ids:
        return 0
    with transaction(user) as cur:
        cur.execute(
            "update invoice set settled_manually = %s, settled_note = %s where id = any(%s)",
            (settled, note or None, list(invoice_ids)),
        )
        return cur.rowcount
