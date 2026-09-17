"""P16 公司分析 — 三家公司加起來到底賺多少（三層毛利橋 + 目標達成 + 平台總覽）。

Doc 優先（CLAUDE_CODE_TASK_5 §1.3 A）：頁面只負責「篩選列 + 兩個互動選單」，
把值傳進 core.docs.analysis_company.build_doc 組出 Doc，再交給 X.ui.render 畫畫面、
X.ui.export_bar 產 PDF / Excel / 列印版 HTML。月報包（scripts/export_pack.py）重用同一個 build_doc。
"""
from __future__ import annotations

import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.docs.analysis_company import build_doc
from core.ui import feedback_widget, page_header
from reports import export as X

user = require_role("MEDIA", "FINANCE", "EXEC")
page_header("🏛️ 公司分析", "三層毛利橋：帳上 → 集團 → 淨利；目標達成用老闆儀表板口徑。")

f = A.filter_bar_analysis("aco", user=user, show_industry=False, show_salesperson=False, show_scope=True)

# 平台總覽的兩個互動選單（在 Doc 之外先讀好值，改了就重組 Doc；§1.3）
oc = st.columns([3, 2])
metric = oc[0].radio("平台總覽指標", ["除佣實收", "成本", "帳上毛利", "帳上利率", "集團毛利", "集團利率"],
                     horizontal=True, key="co_metric",
                     help="決定下方「公司 × 報表平台」表顯示哪個數字；利率＝Σ毛利 ÷ Σ除佣。")
prange = oc[1].radio("平台範圍", ["全部", "自媒體（不含廣播）", "只看廣播"],
                     horizontal=True, key="co_prange")

doc = build_doc(f, user, metric=metric, prange=prange)
X.ui.render(doc, key="aco")

st.divider()
X.ui.export_bar(doc, key="aco")
feedback_widget("analysis_company")
