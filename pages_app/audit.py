"""P10 稽核紀錄（EXEC）"""
import streamlit as st

from core import admin
from core.auth import require_role
from core.format import label
from core.ui import feedback_widget, page_header

require_role("EXEC")
page_header("稽核紀錄", "所有寫入資料庫的動作（新增/修改/刪除）都會被記錄，含操作者與前後差異。")

tables = admin.audit_tables()
c1, c2, c3 = st.columns(3)
table = c1.selectbox("資料表", [None] + tables, format_func=lambda v: "全部" if v is None else v)
user_name = c2.text_input("操作者帳號")
contract_no = c3.text_input("合約編號")

df = admin.list_audit(table=table, user_name=user_name or None, contract_no=contract_no or None)
if df.empty:
    st.info("查無稽核紀錄。")
else:
    st.caption(f"最近 {len(df)} 筆")
    ACTION_ZH = {"INSERT": "新增", "UPDATE": "修改", "DELETE": "刪除"}
    for _, r in df.iterrows():
        head = f"{r['at']}　{ACTION_ZH.get(r['action'], r['action'])}　{r['table_name']} #{r['row_pk']}　by {r['user_name'] or '?'}"
        with st.expander(head):
            old, new = r.get("old_data") or {}, r.get("new_data") or {}
            changed = r.get("changed_cols") or (list(new.keys()) if r["action"] == "INSERT" else list(old.keys()))
            rows = []
            for col in changed:
                rows.append({
                    "欄位": label(col),
                    "舊值": "" if old is None else old.get(col, ""),
                    "新值": "" if new is None else new.get(col, ""),
                })
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.caption("（無欄位差異）")

feedback_widget("audit")
