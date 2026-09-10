"""
test_auth.py — 密碼雜湊（純 Python，不需要 DB）
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core.auth import hash_password, verify_password  # noqa: E402


def test_hash_roundtrip():
    h = hash_password("Secret123")
    assert h != "Secret123"
    assert verify_password("Secret123", h) is True
    assert verify_password("wrong", h) is False


def test_hash_unique_salt():
    assert hash_password("same") != hash_password("same")


def test_verify_bad_hash_is_false():
    assert verify_password("x", "not-a-bcrypt-hash") is False
