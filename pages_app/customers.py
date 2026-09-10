"""P4 客戶主檔 customers.py — 列表/搜尋、編輯、別名、合併客戶。"""
from __future__ import annotations

import pathlib
import sys

import streamlit as st

from core.auth import require_role
from core.data import clear_cache, customer_lookup, customers, options, query_df
from core.masters import merge_customers
from core.ui import feedback_widget, page_header, show_df

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from db import transaction  # noqa: E402

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
can_edit = user["role"] in ("MEDIA", "EXEC")

page_header("客戶主檔", "客戶資料、別名與合併。財務／業務為唯讀。")

tab_list, tab_edit, tab_alias, tab_merge = st.tabs(["列表 / 搜尋", "編輯客戶", "別名管理", "合併客戶"])

# --------------------------------------------------------------- 列表 / 搜尋
with tab_list:
    kw = st.text_input("搜尋客戶（名稱或別名）", key="cust_search")
    if kw.strip():
        df = customer_lookup(kw, limit=200)
    else:
        df = customers()
    st.caption(f"共 {len(df)} 筆")
    show_df(df, cols=["id", "name"] if not df.empty and "name" in df.columns else None)

# --------------------------------------------------------------- 編輯
with tab_edit:
    cust = customers()
    if cust.empty:
        st.info("尚無客戶資料")
    else:
        opts = list(zip(cust["id"], cust["name"]))
        cid = st.selectbox("選擇客戶", [o[0] for o in opts],
                           format_func=lambda v: dict(opts).get(v, str(v)), key="cust_edit_sel")
        row = cust[cust["id"] == cid].iloc[0]
        cat_opts = options("customer_category")
        ind_opts = options("industry")
        with st.form("cust_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("名稱", row["name"], disabled=not can_edit)
            cat = c2.selectbox("客戶類別", [None] + [o[0] for o in cat_opts],
                               index=([None] + [o[0] for o in cat_opts]).index(row["customer_category_id"])
                               if row["customer_category_id"] in [o[0] for o in cat_opts] else 0,
                               format_func=lambda v: "（未設定）" if v is None else dict(cat_opts).get(v, str(v)),
                               disabled=not can_edit)
            ind = c1.selectbox("產業別", [None] + [o[0] for o in ind_opts],
                               index=([None] + [o[0] for o in ind_opts]).index(row["industry_id"])
                               if row["industry_id"] in [o[0] for o in ind_opts] else 0,
                               format_func=lambda v: "（未設定）" if v is None else dict(ind_opts).get(v, str(v)),
                               disabled=not can_edit)
            tax_id = c2.text_input("統編", row["tax_id"] or "", disabled=not can_edit)
            contact = c1.text_input("聯絡人", row["contact_person"] or "", disabled=not can_edit)
            phone = c2.text_input("電話", row["phone"] or "", disabled=not can_edit)
            email = c1.text_input("Email", row["email"] or "", disabled=not can_edit)
            is_new = c2.checkbox("新案", bool(row["is_new_case"]), disabled=not can_edit)
            is_top = c1.checkbox("千大", bool(row["is_top1000"]), disabled=not can_edit)
            is_active = c2.checkbox("啟用", bool(row["is_active"]), disabled=not can_edit)
            notes = st.text_area("備註", row["notes"] or "", disabled=not can_edit)
            saved = st.form_submit_button("儲存", disabled=not can_edit)
        if saved and can_edit:
            with transaction(user["username"]) as cur:
                cur.execute(
                    """update customer set name=%s, customer_category_id=%s, industry_id=%s, tax_id=%s,
                       contact_person=%s, phone=%s, email=%s, is_new_case=%s, is_top1000=%s, notes=%s,
                       is_active=%s, updated_by=%s where id=%s""",
                    (name.strip(), cat, ind, tax_id or None, contact or None, phone or None, email or None,
                     is_new, is_top, notes or None, is_active, user["username"], int(cid)),
                )
            clear_cache()
            st.success("已儲存")

# --------------------------------------------------------------- 別名
with tab_alias:
    cust = customers()
    if cust.empty:
        st.info("尚無客戶資料")
    else:
        opts = list(zip(cust["id"], cust["name"]))
        cid = st.selectbox("客戶", [o[0] for o in opts],
                           format_func=lambda v: dict(opts).get(v, str(v)), key="alias_sel")
        aliases = query_df("select id, alias from customer_alias where customer_id=%s order by alias", (int(cid),))
        show_df(aliases if not aliases.empty else aliases)
        if can_edit:
            c1, c2 = st.columns([3, 1])
            new_alias = c1.text_input("新增別名", key="new_alias")
            if c2.button("新增", key="add_alias") and new_alias.strip():
                with transaction(user["username"]) as cur:
                    cur.execute(
                        "insert into customer_alias(customer_id, alias) values (%s,%s) on conflict (alias) do nothing",
                        (int(cid), new_alias.strip()),
                    )
                clear_cache()
                st.success("已新增")
                st.rerun()
            if not aliases.empty:
                del_id = st.selectbox("刪除別名", aliases["id"].tolist(),
                                      format_func=lambda v: aliases[aliases["id"] == v]["alias"].iloc[0],
                                      key="del_alias_sel")
                if st.button("刪除選取別名", key="del_alias"):
                    with transaction(user["username"]) as cur:
                        cur.execute("delete from customer_alias where id=%s", (int(del_id),))
                    clear_cache()
                    st.success("已刪除")
                    st.rerun()
        else:
            st.caption("唯讀角色不可編輯別名")

# --------------------------------------------------------------- 合併
with tab_merge:
    if not can_edit:
        st.caption("唯讀角色不可合併客戶")
    else:
        st.warning("合併會把「來源客戶 A」的所有業績線／合約／發票改掛到「目標客戶 B」，A 名稱轉為 B 的別名並停用。此動作無法自動復原。")
        cust = customers()
        opts = list(zip(cust["id"], cust["name"]))
        c1, c2 = st.columns(2)
        from_id = c1.selectbox("來源客戶 A（將被併入）", [o[0] for o in opts],
                               format_func=lambda v: dict(opts).get(v, str(v)), key="merge_from")
        into_id = c2.selectbox("目標客戶 B（保留）", [o[0] for o in opts],
                               format_func=lambda v: dict(opts).get(v, str(v)), key="merge_into")
        confirm = st.checkbox("我確認要把 A 併入 B", key="merge_confirm")
        if st.button("執行合併", key="do_merge", disabled=not confirm):
            if from_id == into_id:
                st.error("來源與目標不可相同")
            else:
                counts = merge_customers(int(from_id), int(into_id), user["username"])
                clear_cache()
                st.success(f"已合併：deal_line {counts.get('deal_line', 0)} 筆、deal {counts.get('deal', 0)} 筆、invoice {counts.get('invoice', 0)} 筆改掛。")

feedback_widget("customers")
