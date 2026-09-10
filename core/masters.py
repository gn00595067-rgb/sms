"""
masters.py — 主檔通用 CRUD（給 P5 主檔維護頁的 st.data_editor 用）

原則：比對差異後 insert / update；不刪有被引用的列（改 is_active=false）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402


def fetch(table: str, cols: list[str], order_by: str = "id", key: str = "id") -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {', '.join(cols)} from {table} order by {order_by}")
            return pd.DataFrame(cur.fetchall(), columns=cols)


def _norm(v):
    """把 pandas 的 NaN/NaT/空字串正規化成 None。"""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def apply_edits(table: str, original: pd.DataFrame, edited: pd.DataFrame,
                editable_cols: list[str], user: str, key: str = "id") -> dict:
    """
    比對 original 與 edited（st.data_editor 回傳），對：
      - 新列（key 為空）→ insert
      - key 存在且欄位有變 → update 變動欄位
    回傳 {"inserted": n, "updated": n}。
    """
    orig_by_key = {}
    if not original.empty and key in original.columns:
        orig_by_key = {r[key]: r for _, r in original.iterrows()}

    inserted = updated = 0
    with transaction(user) as cur:
        for _, row in edited.iterrows():
            kval = _norm(row.get(key))
            vals = {c: _norm(row.get(c)) for c in editable_cols if c in row}
            if kval is None:
                # 新列：至少要有一個非空值才 insert
                if not any(v is not None for v in vals.values()):
                    continue
                cols = list(vals.keys())
                cur.execute(
                    f"insert into {table}({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                    [vals[c] for c in cols],
                )
                inserted += 1
            else:
                orig = orig_by_key.get(kval)
                changed = {}
                for c in editable_cols:
                    if c not in row:
                        continue
                    new_v = _norm(row.get(c))
                    old_v = _norm(orig[c]) if orig is not None and c in orig else None
                    if new_v != old_v:
                        changed[c] = new_v
                if changed:
                    cur.execute(
                        f"update {table} set {', '.join(f'{c} = %s' for c in changed)} where {key} = %s",
                        list(changed.values()) + [kval],
                    )
                    updated += 1
    return {"inserted": inserted, "updated": updated}


def deactivate(table: str, key_val, user: str, key: str = "id") -> None:
    with transaction(user) as cur:
        cur.execute(f"update {table} set is_active = false where {key} = %s", (key_val,))


def merge_customers(from_id: int, into_id: int, user: str) -> dict:
    """把客戶 A（from_id）併入 B（into_id）：改所有引用、A 名稱變 B 別名、A 停用。"""
    with transaction(user) as cur:
        cur.execute("select name from customer where id = %s", (from_id,))
        r = cur.fetchone()
        if not r:
            raise ValueError("來源客戶不存在")
        from_name = r["name"]
        counts = {}
        for tbl in ("deal_line", "deal", "invoice"):
            cur.execute(f"update {tbl} set customer_id = %s where customer_id = %s", (into_id, from_id))
            counts[tbl] = cur.rowcount
        # A 名稱變成 B 的別名（避免與現有別名/客戶名衝突）
        cur.execute("select 1 from customer_alias where alias = %s", (from_name,))
        if not cur.fetchone():
            cur.execute(
                "insert into customer_alias(customer_id, alias) values (%s, %s) on conflict (alias) do nothing",
                (into_id, from_name),
            )
        # A 改名 + 停用（避免 unique name 衝突）
        cur.execute(
            "update customer set is_active = false, name = %s where id = %s",
            (f"{from_name}（已併入#{into_id}）", from_id),
        )
    return counts
