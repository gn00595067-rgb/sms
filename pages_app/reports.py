"""P7 報表中心 — 全部角色（SALES 只看自己）"""
from __future__ import annotations

import streamlit as st

from core.auth import require_role
from core.data import query_df
from core.format import ym_text
from core.ui import feedback_widget, filters_bar, page_header, show_df
from reports.query import run_report, totals_row
from reports.registry import report, reports_for_role
from reports.render_excel import build_excel
from reports.render_html import build_html

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("📈 報表中心", "選報表 → 設篩選 → 查詢；可下載 Excel 或列印。")

choices = reports_for_role(user["role"])
if not choices:
    st.info("目前角色沒有可用報表")
    feedback_widget("reports")
    st.stop()

# 同仁分享 / 我的自訂報表（§5.6）：選了跳到「自訂報表」頁並載入定義
from reports import builder as _B
_saved = [rr for rr in _B.list_saved(user) if rr["is_shared"] or rr["owner_id"] == user["id"]]
if _saved:
    with st.expander(f"📐 自訂報表（{len(_saved)} 個：我的 / 同仁分享）"):
        for rr in _saved:
            if st.button(("🔗 " if rr["is_shared"] else "⭐ ") + rr["name"], key=f"open_saved_{rr['id']}"):
                st.session_state["rb"] = _B.load_definition(rr["definition"])
                st.session_state["rb"]["_id"] = int(rr["id"])
                st.switch_page("pages_app/report_builder.py")

key = st.selectbox("報表", [c[0] for c in choices], format_func=lambda k: dict(choices)[k])
r = report(key)
if r.get("note"):
    st.info(r["note"])

# custom 模式（階段 L 老闆版報表）：查詢與輸出交給指定模組，走自己的 UI
if r.get("mode") == "custom":
    import importlib
    importlib.import_module(r["module"]).render(user)
    feedback_widget("reports")
    st.stop()

filters = filters_bar(r["filters"], key_prefix=key)

# customer_rank 需要 perf_year（不在 filters_bar 內）
if r.get("top_n"):
    years = query_df("select distinct perf_year from v_customer_ranking order by 1 desc")
    year_opts = years["perf_year"].tolist() if not years.empty else []
    c1, c2 = st.columns(2)
    if year_opts:
        filters["perf_year"] = c1.selectbox("年", year_opts, key=f"{key}_year")
    top_n = int(c2.number_input("前 N 名", min_value=1, max_value=200, value=20, key=f"{key}_topn"))
else:
    top_n = None

# aggregate 報表選 group by
group_label = None
if r.get("mode") == "aggregate":
    group_label = st.selectbox("彙總方式", list(r["group_by_options"].keys()), key=f"{key}_grp")


def _filter_text() -> str:
    parts = []
    if filters.get("ym_from") and filters.get("ym_to"):
        parts.append(f"{ym_text(filters['ym_from'])}–{ym_text(filters['ym_to'])}")
    labels = {"company": "公司", "platform_group": "平台歸類", "platform": "平台", "region": "區域",
              "salesperson": "業務", "business_group": "組別", "sales_category": "業績類別",
              "industry": "產業別", "customer": "客戶", "line_type": "線類型", "perf_year": "年"}
    for k, lab in labels.items():
        v = filters.get(k)
        if v not in (None, ""):
            parts.append(f"{lab}={v}")
    if group_label:
        parts.append(f"彙總：{group_label}")
    return "　".join(parts)


if st.button("查詢", type="primary"):
    st.session_state[f"{key}_run"] = True

if st.session_state.get(f"{key}_run"):
    df = run_report(key, filters, group_by_label=group_label, user=user, top_n=top_n)
    show_df(df)

    tot = {}
    if r.get("totals") and df is not None and not df.empty:
        sum_cols = r.get("sum_cols") or [m for m in r.get("measures", []) if m not in ("margin_pct",)]
        tot = totals_row(df, sum_cols)
        if tot:
            st.caption("合計")
            show_df(__import__("pandas").DataFrame([tot]))

    if df is not None and not df.empty:
        cols = list(df.columns)
        ft = _filter_text()
        c1, c2 = st.columns(2)
        c1.download_button(
            "⬇ 下載 Excel",
            data=build_excel(df, r["title"], ft, columns=cols, totals=tot or None),
            file_name=f"{key}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        if c2.button("🖨 列印版", use_container_width=True):
            st.session_state[f"{key}_print"] = True
        if st.session_state.get(f"{key}_print"):
            st.components.v1.html(build_html(df, r["title"], ft, columns=cols, totals=tot or None),
                                  height=600, scrolling=True)

feedback_widget("reports")
