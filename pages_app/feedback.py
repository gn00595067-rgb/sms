"""P9 問題回報清單（EXEC）"""
import streamlit as st

from core import admin
from core.auth import require_role
from core.format import FEEDBACK_STATUS_LABELS
from core.ui import feedback_widget, page_header

user = require_role("EXEC")
page_header("問題回報清單", "同仁邊用邊回報的問題；這是 MVP 迭代的來源。")

STATUSES = ["NEW", "DOING", "DONE", "WONTFIX"]

col1, _ = st.columns([1, 3])
status_filter = col1.selectbox(
    "狀態", [None] + STATUSES,
    format_func=lambda v: "全部" if v is None else FEEDBACK_STATUS_LABELS.get(v, v),
)

df = admin.list_feedback(status_filter)
if df.empty:
    st.info("目前沒有回報。")
else:
    st.caption(f"共 {len(df)} 筆")
    for _, r in df.iterrows():
        title = f"#{r['id']}　[{r['category']}]　{FEEDBACK_STATUS_LABELS.get(r['status'], r['status'])}　— {r['user_name'] or '匿名'}／{r['page'] or ''}"
        with st.expander(title, expanded=(r["status"] == "NEW")):
            st.write(r["message"])
            st.caption(f"時間：{r['created_at']}")
            with st.form(f"fb_{r['id']}"):
                new_status = st.selectbox(
                    "狀態", STATUSES, index=STATUSES.index(r["status"]) if r["status"] in STATUSES else 0,
                    format_func=lambda v: FEEDBACK_STATUS_LABELS.get(v, v), key=f"st_{r['id']}",
                )
                reply = st.text_area("回覆", value=r["reply"] or "", key=f"rp_{r['id']}")
                if st.form_submit_button("更新"):
                    admin.update_feedback(int(r["id"]), new_status, reply, user["username"])
                    st.success("已更新")
                    st.rerun()

feedback_widget("feedback")
