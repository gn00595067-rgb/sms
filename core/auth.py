"""
auth.py — 登入 / 權限 / 密碼雜湊

登入狀態放 st.session_state["user"]（dict）。
角色：MEDIA 媒體 / FINANCE 財務 / EXEC 高階 / SALES 業務（只看自己）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import bcrypt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402

ROLES = ("MEDIA", "FINANCE", "EXEC", "SALES")


# ------------------------------------------------------------------ 密碼
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ 登入
def login(username: str, password: str) -> dict | None:
    """驗證帳密；成功回傳 user dict 並寫入 session_state，失敗回 None。"""
    username = (username or "").strip().lower()
    if not username or not password:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id, username, password_hash, display_name, role, salesperson_id,
                          is_active, must_change_password
                   from app_user where username = %s""",
                (username,),
            )
            row = cur.fetchone()
    if not row or not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    # 更新 last_login_at（經 transaction 讓稽核記到操作者）
    with transaction(username) as cur:
        cur.execute("update app_user set last_login_at = now() where id = %s", (row["id"],))
    user = {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "role": row["role"],
        "salesperson_id": row["salesperson_id"],
        "must_change_password": row["must_change_password"],
    }
    st.session_state["user"] = user
    return user


def logout() -> None:
    st.session_state.pop("user", None)


def current_user() -> dict | None:
    return st.session_state.get("user")


def is_logged_in() -> bool:
    return "user" in st.session_state


def require_login() -> dict:
    user = current_user()
    if not user:
        st.error("請先登入")
        st.stop()
    return user


def require_role(*roles: str) -> dict:
    """不符角色就顯示錯誤並停止渲染。"""
    user = require_login()
    if roles and user["role"] not in roles:
        st.error("沒有權限")
        st.stop()
    return user


def has_role(*roles: str) -> bool:
    user = current_user()
    return bool(user) and user["role"] in roles


def change_own_password(new_password: str) -> None:
    """修改目前登入者密碼並清掉 must_change_password。"""
    user = require_login()
    h = hash_password(new_password)
    with transaction(user["username"]) as cur:
        cur.execute(
            "update app_user set password_hash = %s, must_change_password = false where id = %s",
            (h, user["id"]),
        )
    user["must_change_password"] = False
    st.session_state["user"] = user
