"""
create_user.py — 建立新帳號，印出隨機初始密碼（首次登入強制改密碼）

用法：
  python scripts/create_user.py jonathan --role EXEC
  python scripts/create_user.py amy --role SALES --salesperson 洪佳琪
  python scripts/create_user.py bob --role MEDIA --password 手動指定
"""
from __future__ import annotations

import argparse
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, transaction  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.auth import hash_password  # noqa: E402

ROLES = ("MEDIA", "FINANCE", "EXEC", "SALES")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--salesperson", help="SALES 角色綁定的業務名稱（v_deal_line_flat 的 salesperson）")
    ap.add_argument("--display", help="顯示名稱（預設 = username）")
    ap.add_argument("--password", help="手動指定密碼（預設隨機產生）")
    ap.add_argument("--no-force-change", action="store_true", help="不強制首次改密碼")
    args = ap.parse_args()

    username = args.username.strip().lower()
    salesperson_id = None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from app_user where username = %s", (username,))
            if cur.fetchone():
                print(f"帳號已存在：{username}")
                return 1
            if args.salesperson:
                cur.execute("select id from salesperson where name = %s", (args.salesperson,))
                r = cur.fetchone()
                if not r:
                    print(f"找不到業務：{args.salesperson}（請確認名稱與 salesperson 表一致）")
                    return 1
                salesperson_id = r["id"]

    pw = args.password or secrets.token_urlsafe(8)
    with transaction(username) as cur:
        cur.execute(
            """insert into app_user(username, password_hash, display_name, role, salesperson_id, must_change_password)
               values (%s,%s,%s,%s,%s,%s)""",
            (username, hash_password(pw), args.display or args.username, args.role,
             salesperson_id, not args.no_force_change),
        )
    print(f"已建立帳號：{username}  角色：{args.role}")
    print(f"初始密碼：{pw}")
    print("（請安全交付給本人，首次登入會要求改密碼）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
