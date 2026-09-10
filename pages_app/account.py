"""P12 修改密碼（全部角色）"""
import streamlit as st

from core.auth import change_own_password, require_role, verify_password
from core.data import query_df
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("修改密碼", "首次登入請務必更改預設密碼。")

if user.get("must_change_password"):
    st.warning("這是預設密碼，請立即更改後才能使用其他功能。")

with st.form("change_pw", clear_on_submit=True):
    cur = st.text_input("目前密碼", type="password")
    p1 = st.text_input("新密碼（至少 8 個字元）", type="password")
    p2 = st.text_input("再輸入一次新密碼", type="password")
    ok = st.form_submit_button("更新密碼")

if ok:
    # 取目前密碼雜湊驗證
    row = query_df("select password_hash from app_user where id = %s", (user["id"],))
    current_hash = row.iloc[0]["password_hash"] if not row.empty else ""
    if not verify_password(cur, current_hash):
        st.error("目前密碼不正確")
    elif len(p1) < 8:
        st.error("新密碼至少 8 個字元")
    elif p1 != p2:
        st.error("兩次輸入不一致")
    elif p1 == cur:
        st.error("新密碼不可與目前密碼相同")
    else:
        change_own_password(p1)
        st.success("密碼已更新。")
        if user.get("must_change_password"):
            st.info("已解除預設密碼限制，左側選單現在可使用其他功能。")
        else:
            st.balloons()
        st.rerun()

feedback_widget("account")
