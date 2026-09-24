"""P3 業績查詢 / 修改 — MEDIA/FINANCE/EXEC；SALES 只看自己"""
from __future__ import annotations

import streamlit as st

from core.auth import require_role
from core.data import query_df
from core.format import ym_text
from core.ui import feedback_widget, filters_bar, page_header, show_df
from reports.query import salesperson_name
from reports import export as X
from reports.export import compat

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("🔍 業績查詢", "查 v_deal_line_flat；可下載 Excel、跳轉修改。")

filters = filters_bar(["ym_range", "company", "salesperson", "customer", "contract_no", "platform", "line_type"],
                      key_prefix="ds")
low_margin = st.checkbox("只看低毛利（毛利率 ≤ 15.99%，排除瑞*/製作* 電台）")

# 組參數化查詢
clauses, params = [], []
if filters.get("ym_from") and filters.get("ym_to"):
    clauses.append("perf_ym between %s and %s")
    params += [filters["ym_from"], filters["ym_to"]]
for key, col, like in [("company", "company", False), ("platform", "platform", False),
                       ("line_type", "line_type", False), ("customer", "customer", True),
                       ("contract_no", "contract_no", True)]:
    v = filters.get(key)
    if v:
        clauses.append(f"{col} ilike %s" if like else f"{col} = %s")
        params.append(f"%{v}%" if like else v)
if filters.get("salesperson"):
    # filters_bar 的 salesperson 回傳 id → 轉名稱
    nm = salesperson_name(filters["salesperson"])
    if nm:
        clauses.append("salesperson = %s")
        params.append(nm)
# SALES 只看自己
if user["role"] == "SALES":
    nm = salesperson_name(user.get("salesperson_id"))
    clauses.append("salesperson = %s")
    params.append(nm or "\x00")
if low_margin:
    clauses.append("margin_pct <= 0.1599 and coalesce(media_channel,'') !~ '^(瑞|製作)'")

where = (" where " + " and ".join(clauses)) if clauses else ""
df = query_df(f"select * from v_deal_line_flat{where} order by perf_ym, contract_no, line_no limit 5000", params)

cols = ["perf_ym_text", "contract_no", "line_no", "company", "customer", "salesperson", "platform_group",
        "platform", "media_channel", "line_type", "gross_amount", "rebate_pct", "net_amount",
        "cost_amount", "gross_profit", "margin_pct"]
st.caption(f"共 {0 if df is None else len(df)} 筆" + ("（上限 5000）" if df is not None and len(df) == 5000 else ""))
show_df(df, cols=cols)

if df is not None and not df.empty:
    # 跳轉修改（MEDIA/EXEC）
    if user["role"] in ("MEDIA", "EXEC"):
        contract = st.selectbox("選合約編號修改", sorted(df["contract_no"].unique()))
        if st.button("✏️ 開啟修改"):
            st.session_state["edit_contract"] = contract
            st.switch_page("pages_app/deal_entry.py")
    _fp = []
    if filters.get("ym_from") and filters.get("ym_to"):
        _fp.append(f"{ym_text(filters['ym_from'])}–{ym_text(filters['ym_to'])}")
    for _k, _lab in (("company", "公司"), ("platform", "平台"), ("line_type", "線類型"),
                     ("customer", "客戶"), ("contract_no", "合約")):
        if filters.get(_k):
            _fp.append(f"{_lab}={filters[_k]}")
    if low_margin:
        _fp.append("只看低毛利")
    st.divider()
    doc = compat.record_doc("業績查詢", filter_text="　".join(_fp), user=user, orientation="landscape")
    compat.add_table(doc, "業績查詢", df, columns=[c for c in cols if c in df.columns], wide=True,
                     max_rows_pdf=300, freeze_cols=3,
                     note="完整清單（可超過 300 筆）請用 Excel。金額單位：元。")
    from core.docs.glossary import annotate
    annotate(doc)
    X.ui.export_bar(doc, key="ds")

feedback_widget("deal_search")
