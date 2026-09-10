"""
admin.py — 使用者管理 / 問題回報 / 稽核 的讀寫（給 P9/P10/P11 用）
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402

from core.auth import hash_password


def _df(sql: str, params=None) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())


# ------------------------------------------------------------------ 使用者
def list_users() -> pd.DataFrame:
    return _df(
        """select u.id, u.username, u.display_name, u.role, u.salesperson_id, sp.name as salesperson,
                  u.is_active, u.must_change_password, u.last_login_at
           from app_user u left join salesperson sp on sp.id = u.salesperson_id
           order by u.username"""
    )


def create_user(username: str, role: str, admin: str, *, display_name: str | None = None,
                salesperson_id: int | None = None) -> str:
    username = username.strip().lower()
    pw = secrets.token_urlsafe(8)
    with transaction(admin) as cur:
        cur.execute("select 1 from app_user where username = %s", (username,))
        if cur.fetchone():
            raise ValueError("帳號已存在")
        cur.execute(
            """insert into app_user(username, password_hash, display_name, role, salesperson_id, must_change_password)
               values (%s,%s,%s,%s,%s,true)""",
            (username, hash_password(pw), display_name or username, role, salesperson_id),
        )
    return pw


def set_active(user_id: int, active: bool, admin: str) -> None:
    with transaction(admin) as cur:
        cur.execute("update app_user set is_active = %s where id = %s", (active, user_id))


def reset_password(user_id: int, admin: str) -> str:
    pw = secrets.token_urlsafe(8)
    with transaction(admin) as cur:
        cur.execute(
            "update app_user set password_hash = %s, must_change_password = true where id = %s",
            (hash_password(pw), user_id),
        )
    return pw


def set_role(user_id: int, role: str, admin: str) -> None:
    with transaction(admin) as cur:
        cur.execute("update app_user set role = %s where id = %s", (role, user_id))


def set_salesperson(user_id: int, salesperson_id: int | None, admin: str) -> None:
    with transaction(admin) as cur:
        cur.execute("update app_user set salesperson_id = %s where id = %s", (salesperson_id, user_id))


# ------------------------------------------------------------------ 問題回報
def list_feedback(status: str | None = None) -> pd.DataFrame:
    sql = "select id, created_at, user_name, page, category, message, status, reply, updated_at from feedback"
    params = None
    if status:
        sql += " where status = %s"
        params = (status,)
    sql += " order by created_at desc"
    return _df(sql, params)


def update_feedback(feedback_id: int, status: str, reply: str, admin: str) -> None:
    with transaction(admin) as cur:
        cur.execute(
            "update feedback set status = %s, reply = %s, updated_at = now() where id = %s",
            (status, reply or None, feedback_id),
        )


# ------------------------------------------------------------------ 稽核
def list_audit(table: str | None = None, user_name: str | None = None,
               contract_no: str | None = None, limit: int = 500) -> pd.DataFrame:
    clauses, params = [], []
    if table:
        clauses.append("table_name = %s")
        params.append(table)
    if user_name:
        clauses.append("user_name = %s")
        params.append(user_name)
    if contract_no:
        clauses.append("(row_pk = %s or new_data->>'contract_no' = %s or old_data->>'contract_no' = %s)")
        params.extend([contract_no, contract_no, contract_no])
    where = (" where " + " and ".join(clauses)) if clauses else ""
    params.append(limit)
    return _df(
        f"""select id, at, user_name, action, table_name, row_pk, changed_cols, old_data, new_data
            from audit_log{where} order by at desc limit %s""",
        params,
    )


def audit_tables() -> list[str]:
    df = _df("select distinct table_name from audit_log order by table_name")
    return df["table_name"].tolist() if not df.empty else []
