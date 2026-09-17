"""P8 簡易業務獎金 — EXEC（全部）/ SALES（只看自己）"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import require_role
from core.data import months
from core.format import ym_text
from core.ui import feedback_widget, page_header, show_df
from reports.query import run_report
from reports import export as X
from reports.export import compat

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
    sub = None
    if "salesperson" in df.columns:
        agg = {c: "sum" for c in ("net_amount", "gross_profit", "bonus_amount") if c in df.columns}
        if agg:
            sub = df.groupby("salesperson", as_index=False).agg(agg)
            st.subheader("業務小計")
            show_df(sub)

    st.divider()
    doc = compat.record_doc("業務獎金（簡易）", filter_text=ym_text(m), user=user, orientation="landscape")
    compat.add_table(doc, "獎金明細", show, note="第一層業務獎金＝業務×平台歸類×業績項目×生效%×門檻；未設規則者標「未設定規則」。",
                     helps={"bonus_pct": "適用的獎金%（依規則）", "bonus_amount": "該列業績×獎金%",
                            "threshold_amount": "達到才計獎金的門檻"})
    if sub is not None and not sub.empty:
        compat.add_table(doc, "業務小計", sub, sheet_name="業務小計", note="每位業務的業績、毛利、獎金合計。")
    from core.docs.glossary import annotate
    annotate(doc)
    X.ui.export_bar(doc, key="bonus")

st.page_link("pages_app/masters.py", label="→ 到「主檔維護」設定獎金規則", icon="🗂️")

feedback_widget("bonus")
