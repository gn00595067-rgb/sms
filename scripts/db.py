"""
db.py — 共用資料庫連線（scripts/ 與 Streamlit app 共用）

連線字串來源（依序）：
  1. 環境變數 DATABASE_URL
  2. .streamlit/secrets.toml 的 [db] url = "..."
  3. Streamlit 執行環境的 st.secrets["db"]["url"]

Supabase 注意：Streamlit Cloud 只有 IPv4，必須用 **Session pooler** 連線字串
  postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
（Supabase 後台 → Connect → Session pooler），不要用 db.<ref>.supabase.co 的直連字串。
"""
from __future__ import annotations

import os
import pathlib
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secrets = pathlib.Path(".streamlit/secrets.toml")
    if secrets.exists():
        try:
            import tomllib  # py3.11+
        except ModuleNotFoundError:  # pragma: no cover
            import tomli as tomllib  # type: ignore
        data = tomllib.loads(secrets.read_text(encoding="utf-8"))
        if "db" in data and "url" in data["db"]:
            return data["db"]["url"]
    try:  # 在 Streamlit 內執行時
        import streamlit as st

        return st.secrets["db"]["url"]
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(
        "找不到資料庫連線字串：請設定環境變數 DATABASE_URL，或在 .streamlit/secrets.toml 寫入\n"
        '[db]\nurl = "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"'
    )


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(get_database_url(), autocommit=autocommit, row_factory=dict_row)


@contextmanager
def transaction(user_name: str | None = None):
    """
    with transaction('jonathan') as cur:
        cur.execute(...)
    交易開頭會 set_config('app.user_name')，讓 002_audit.sql 的 trigger 記到操作者。
    """
    conn = connect()
    try:
        with conn:
            with conn.cursor() as cur:
                if user_name:
                    cur.execute("select set_config('app.user_name', %s, true)", (user_name,))
                yield cur
    finally:
        conn.close()


def fetch_df(sql: str, params=None):
    """讀成 pandas DataFrame（報表用）。"""
    import pandas as pd

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return pd.DataFrame(rows)
