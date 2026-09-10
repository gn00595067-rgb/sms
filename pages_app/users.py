"""P11 使用者管理（EXEC）"""
import pandas as pd
import streamlit as st

from core import admin, data
from core.auth import ROLES
from core.auth import require_role
from core.format import ROLE_LABELS
from core.ui import feedback_widget, page_header

user = require_role("EXEC")
page_header("使用者管理", "新增/停用帳號、重設密碼、改角色、綁定業務。")

sp_opts = data.options("salesperson")
sp_name = {sid: name for sid, name in sp_opts}

# --- 新增帳號 ---
with st.expander("➕ 新增帳號"):
    with st.form("new_user", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        username = c1.text_input("帳號（英數，會轉小寫）")
        display = c2.text_input("顯示名稱")
        role = c3.selectbox("角色", ROLES, format_func=lambda r: ROLE_LABELS.get(r, r))
        sp = st.selectbox("綁定業務（SALES 才需要）", [None] + [s[0] for s in sp_opts],
                          format_func=lambda v: "（無）" if v is None else sp_name.get(v, str(v)))
        if st.form_submit_button("建立"):
            if not username.strip():
                st.error("請輸入帳號")
            else:
                try:
                    pw = admin.create_user(username, role, user["username"],
                                           display_name=display or None, salesperson_id=sp)
                    st.success(f"已建立 {username.strip().lower()}，初始密碼：**{pw}**（請安全交付，對方首次登入需改密碼）")
                except ValueError as e:
                    st.error(str(e))

st.divider()

# --- 帳號清單 ---
df = admin.list_users()
if df.empty:
    st.info("尚無帳號。")
for _, r in df.iterrows():
    active = "✅" if r["is_active"] else "🚫"
    with st.expander(f"{active} {r['username']}　（{ROLE_LABELS.get(r['role'], r['role'])}）　{r['display_name'] or ''}"):
        c1, c2, c3, c4 = st.columns(4)
        # 改角色
        new_role = c1.selectbox("角色", ROLES, index=ROLES.index(r["role"]) if r["role"] in ROLES else 0,
                                format_func=lambda x: ROLE_LABELS.get(x, x), key=f"role_{r['id']}")
        if c1.button("更新角色", key=f"brole_{r['id']}"):
            admin.set_role(int(r["id"]), new_role, user["username"])
            st.success("已更新"); st.rerun()
        # 綁業務
        cur_sp = int(r["salesperson_id"]) if pd.notna(r["salesperson_id"]) else None
        new_sp = c2.selectbox("綁定業務", [None] + [s[0] for s in sp_opts],
                              index=([None] + [s[0] for s in sp_opts]).index(cur_sp) if cur_sp in [s[0] for s in sp_opts] else 0,
                              format_func=lambda v: "（無）" if v is None else sp_name.get(v, str(v)), key=f"sp_{r['id']}")
        if c2.button("更新業務", key=f"bsp_{r['id']}"):
            admin.set_salesperson(int(r["id"]), new_sp, user["username"])
            st.success("已更新"); st.rerun()
        # 重設密碼
        if c3.button("重設密碼", key=f"pw_{r['id']}"):
            pw = admin.reset_password(int(r["id"]), user["username"])
            st.warning(f"新密碼：**{pw}**（只顯示一次）")
        # 停用 / 啟用（不可停用自己，避免鎖死）
        is_self = int(r["id"]) == int(user["id"])
        if r["is_active"]:
            if c4.button("停用", key=f"deact_{r['id']}", disabled=is_self,
                         help="不可停用自己" if is_self else None):
                admin.set_active(int(r["id"]), False, user["username"]); st.rerun()
        else:
            if c4.button("啟用", key=f"act_{r['id']}"):
                admin.set_active(int(r["id"]), True, user["username"]); st.rerun()
        st.caption(f"最後登入：{r['last_login_at'] or '—'}　首次改密碼：{'待改' if r['must_change_password'] else '已改'}")

feedback_widget("users")
