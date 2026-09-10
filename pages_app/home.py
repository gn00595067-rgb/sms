"""P1 首頁儀表板 — 全部角色（SALES 只看自己）"""
from __future__ import annotations

import plotly.express as px
import streamlit as st
from dateutil.relativedelta import relativedelta

from core.auth import require_role
from core.data import months, query_df
from core.format import FEEDBACK_STATUS_LABELS, money, pct, ym_text
from core.ui import feedback_widget, page_header, show_df
from reports.query import salesperson_name

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header(f"🏠 首頁", f"歡迎，{user['display_name']}")

# SALES 範圍
sp_name = salesperson_name(user.get("salesperson_id")) if user["role"] == "SALES" else None
scope_sql, scope_params = "", []
if sp_name is not None:
    scope_sql = " and salesperson = %s"
    scope_params = [sp_name]
elif user["role"] == "SALES":
    scope_sql = " and false"

ms = months()
if not ms:
    st.info("尚無業績資料，請先於「業績登打」新增或匯入舊資料。")
    feedback_widget("home")
    st.stop()

this_month = ms[0]
last_month = this_month - relativedelta(months=1)


def kpi_by_company(m):
    return query_df(
        f"""select company,
                   sum(gross_amount) as gross, sum(net_amount) as net,
                   sum(gross_profit) as gp,
                   case when sum(net_amount)<>0 then sum(gross_profit)/sum(net_amount) end as margin
            from v_deal_line_flat where perf_ym = %s{scope_sql}
            group by company order by net desc nulls last""",
        [m] + scope_params,
    )


# ---- KPI 卡（本月，依公司別分欄）----
st.subheader(f"本月 {ym_text(this_month)} KPI（依公司別）")
cur = kpi_by_company(this_month)
prev = kpi_by_company(last_month)
if cur is None or cur.empty:
    st.info("本月尚無資料")
else:
    prev_net = {r["company"]: float(r["net"] or 0) for _, r in prev.iterrows()} if prev is not None and not prev.empty else {}
    cols = st.columns(min(len(cur), 5) or 1)
    for col, (_, r) in zip(cols, cur.iterrows()):
        with col:
            st.markdown(f"**{r['company']}**")
            delta = float(r["net"] or 0) - prev_net.get(r["company"], 0)
            st.metric("除佣實收", money(r["net"]), delta=f"{money(delta)}（vs 上月）")
            st.caption(f"實收 {money(r['gross'])}")
            st.caption(f"毛利 {money(r['gp'])}　毛利率 {pct(r['margin'])}")

# ---- 圖 1：近 12 個月除佣實收趨勢（依公司堆疊）----
st.subheader("近 12 個月除佣實收趨勢")
start = this_month - relativedelta(months=11)
trend = query_df(
    f"""select perf_ym_text, company, sum(net_amount) as net
        from v_deal_line_flat where perf_ym between %s and %s{scope_sql}
        group by perf_ym_text, company order by perf_ym_text""",
    [start, this_month] + scope_params,
)
if trend is not None and not trend.empty:
    fig = px.bar(trend, x="perf_ym_text", y="net", color="company",
                 labels={"perf_ym_text": "業績年月", "net": "除佣實收", "company": "公司別"})
    fig.update_layout(barmode="stack", legend_title_text="公司別", height=380)
    st.plotly_chart(fig, use_container_width=True)

# ---- 圖 2：本月平台歸類佔比 ----
st.subheader(f"本月 {ym_text(this_month)} 平台歸類佔比")
mix = query_df(
    f"""select platform_group, sum(net_amount) as net
        from v_deal_line_flat where perf_ym = %s{scope_sql}
        group by platform_group having sum(net_amount) > 0""",
    [this_month] + scope_params,
)
if mix is not None and not mix.empty:
    fig2 = px.pie(mix, names="platform_group", values="net", hole=0.4)
    fig2.update_layout(height=360)
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.caption("本月無平台歸類資料")

# ---- 最近回報的問題 ----
st.subheader("最近回報的問題")
if user["role"] == "EXEC":
    fb = query_df("select created_at, user_name, page, category, message, status from feedback order by created_at desc limit 10")
else:
    fb = query_df("select created_at, page, category, message, status from feedback where user_name = %s order by created_at desc limit 10",
                  (user["username"],))
if fb is not None and not fb.empty and "status" in fb.columns:
    fb = fb.copy()
    fb["status"] = fb["status"].map(lambda s: FEEDBACK_STATUS_LABELS.get(s, s))
show_df(fb)

feedback_widget("home")
