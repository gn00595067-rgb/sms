"""P8 簡易業務獎金 — EXEC（全部）/ SALES（只看自己）"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import require_role
from core.data import months
from core.format import ym_text
from core.ui import feedback_widget, page_header, show_df
from reports.query import run_report

user = require_role("EXEC", "SALES")
page_header("🎯 業務獎金（簡易）")

st.info("MVP 只實作第一層業務獎金（業務 × 平台歸類 × 業績項目 × 生效區間 × %、門檻），"
        "主管/協辦/客服/專案/加碼獎金尚未實作。")

ms = months()
if not ms:
    st.info("尚無業績資料")
    feedback_widget("bonus")
    st.stop()

m = st.selectbox("年月", ms, format_func=ym_text)
df = run_report("bonus", {"ym_from": m, "ym_to": m}, user=user)

if df is None or df.empty:
    st.info("查無資料")
else:
    show = df.copy()
    # 沒有規則的列標示
    if "rule_note" in show.columns and "bonus_pct" in show.columns:
        show["rule_note"] = show.apply(
            lambda r: r["rule_note"] if pd.notna(r.get("bonus_pct")) else "未設定規則", axis=1
        )
    show_df(show)

    # 依業務小計
    if "salesperson" in df.columns:
        agg = {c: "sum" for c in ("net_amount", "gross_profit", "bonus_amount") if c in df.columns}
        if agg:
            sub = df.groupby("salesperson", as_index=False).agg(agg)
            st.subheader("業務小計")
            show_df(sub)

st.page_link("pages_app/masters.py", label="→ 到「主檔維護」設定獎金規則", icon="🗂️")

feedback_widget("bonus")
