"""P5 主檔維護 masters.py — tabs × st.data_editor，通用 apply_edits。"""
from __future__ import annotations

import streamlit as st

from core.auth import require_role
from core.data import clear_cache
from core.masters import apply_edits, fetch
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "EXEC")
is_exec = user["role"] == "EXEC"

page_header("主檔維護", "直接在表格編輯後按「儲存」。不刪除有引用的列，改用「啟用」欄關閉。")

# 每個 tab：(標題, table, 全欄, 可編輯欄, order_by, key)
TABS = [
    ("平台", "platform", ["id", "name", "platform_group", "default_region", "sort_order", "is_active"],
     ["name", "platform_group", "default_region", "sort_order", "is_active"], "sort_order, name", "id"),
    ("電台/成本項目", "media_channel",
     ["id", "name", "channel_type", "is_designated", "tax_rate", "sort_order", "is_active"],
     ["name", "channel_type", "is_designated", "tax_rate", "sort_order", "is_active"], "sort_order, name", "id"),
    ("節目", "program", ["id", "name", "media_channel_id"], ["name", "media_channel_id"], "name", "id"),
    ("公司", "company", ["id", "name", "is_parent", "sort_order", "is_active"],
     ["name", "is_parent", "sort_order", "is_active"], "sort_order, name", "id"),
    ("組別", "business_group", ["id", "name", "company_id", "is_intercompany", "sort_order", "is_active"],
     ["name", "company_id", "is_intercompany", "sort_order", "is_active"], "sort_order, name", "id"),
    ("業務", "salesperson", ["id", "name", "group_id", "manager_name", "is_active"],
     ["name", "group_id", "manager_name", "is_active"], "name", "id"),
    ("人員", "staff", ["id", "name", "roles", "is_active"], ["name", "is_active"], "name", "id"),
    ("產業別", "industry", ["id", "name"], ["name"], "name", "id"),
    ("客戶類別", "customer_category", ["id", "name"], ["name"], "name", "id"),
    ("業績類別", "sales_category", ["id", "name", "parent_category", "recognition_ratio", "is_active"],
     ["name", "parent_category", "recognition_ratio", "is_active"], "name", "id"),
    ("區域", "region", ["code", "name", "sort_order"], ["code", "name", "sort_order"], "sort_order", "code"),
    ("固定成本規則", "fixed_cost_rule",
     ["id", "platform_group", "platform_id", "media_channel_id", "company_id", "ym_from", "ym_to", "monthly_amount", "note"],
     ["platform_group", "platform_id", "media_channel_id", "company_id", "ym_from", "ym_to", "monthly_amount", "note"],
     "ym_from desc, id", "id"),
    ("轉撥規則", "intercompany_rule",
     ["id", "from_company_id", "to_company_id", "platform_group", "rate", "ym_from", "ym_to", "note"],
     ["from_company_id", "to_company_id", "platform_group", "rate", "ym_from", "ym_to", "note"],
     "ym_from desc, id", "id"),
    ("獎金規則", "bonus_rule",
     ["id", "salesperson_id", "platform_group", "sales_item", "ym_from", "ym_to", "bonus_pct", "threshold_amount", "note"],
     ["salesperson_id", "platform_group", "sales_item", "ym_from", "ym_to", "bonus_pct", "threshold_amount", "note"],
     "ym_from desc, id", "id"),
]

MEDIA_TABS = {"platform", "media_channel", "program"}
visible = TABS if is_exec else [t for t in TABS if t[1] in MEDIA_TABS]
if not is_exec:
    st.caption("媒體人員可維護：平台、電台/成本項目、節目。")

for tab, (title, table, cols, editable, order_by, key) in zip(st.tabs([t[0] for t in visible]), visible):
    with tab:
        original = fetch(table, cols, order_by=order_by, key=key)
        # roles 陣列欄唯讀顯示
        disabled_cols = [c for c in cols if c not in editable]
        edited = st.data_editor(
            original, num_rows="dynamic", use_container_width=True, hide_index=True,
            disabled=disabled_cols, key=f"editor_{table}",
        )
        if st.button("儲存", key=f"save_{table}"):
            res = apply_edits(table, original, edited, editable, user["username"], key=key)
            clear_cache()
            st.success(f"已儲存：新增 {res['inserted']} 筆、更新 {res['updated']} 筆")

feedback_widget("masters")
