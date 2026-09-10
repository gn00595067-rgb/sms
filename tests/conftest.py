"""
conftest.py — 測試共用 fixture

DB 測試：若連不上 Supabase / 未設 secrets 就自動 skip（純 Python 測試照跑）。
測試不得寫入 deal/deal_line/invoice；需要寫入者用合約編號前綴 TEST- 並在 teardown 刪除。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _can_connect() -> bool:
    try:
        from db import connect
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
        return True
    except Exception:  # noqa: BLE001
        return False


HAS_DB = _can_connect()
requires_db = pytest.mark.skipif(not HAS_DB, reason="需要可連線的資料庫（.streamlit/secrets.toml）")


@pytest.fixture(scope="session")
def db():
    if not HAS_DB:
        pytest.skip("無資料庫連線")
    from db import connect
    return connect
