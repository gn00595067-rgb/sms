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
    """SALES：自己的（v_deal_line_flat 可依業務限縮）。"""
    return query_df(
        f"""select company,
                   sum(gross_amount) as gross, sum(net_amount) as net,
                   sum(gross_profit) as gp,
                   case when sum(net_amount)<>0 then sum(gross_profit)/sum(net_amount) end as margin
            from v_deal_line_flat where perf_ym = %s{scope_sql}
            group by company order by net desc nulls last""",
        [m] + scope_params,
    )


def kpi_group_company(m):
    """非 SALES：集團口徑（v_company_month，除佣實收=對外、毛利=帳上毛利），與分析頁一致。"""
    return query_df(
        """select company, sum(ext_gross) as gross, sum(ext_net) as net,
                  sum(booked_profit) as gp,
                  case when sum(ext_net)<>0 then sum(booked_profit)/sum(ext_net) end as margin
           from v_company_month where perf_ym = %s
           group by company order by net desc nulls last""",
        [m],
    )


# ---- KPI 卡（本月，依公司別分欄）----
st.subheader(f"本月 {ym_text(this_month)} KPI（依公司別，集團口徑）")
is_sales = sp_name is not None or user["role"] == "SALES"
cur = kpi_by_company(this_month) if is_sales else kpi_group_company(this_month)
prev = kpi_by_company(last_month) if is_sales else kpi_group_company(last_month)
if cur is None or cur.empty:
    st.info("本月尚無資料")
else:
    prev_net = {r["company"]: float(r["net"] or 0) for _, r in prev.iterrows()} if prev is not None and not prev.empty else {}
    # 集團合併卡（非 SALES）
    n_cards = min(len(cur), 4) + (0 if is_sales else 1)
    cols = st.columns(n_cards or 1)
    ci = 0
    if not is_sales:
        g = query_df(
            "select sum(ext_net) net, sum(group_profit) gp, sum(net_profit) np, case when sum(ext_net)<>0 then sum(group_profit)/sum(ext_net) end margin from v_group_month where perf_ym=%s",
            [this_month])
        gp_prev = query_df("select sum(ext_net) net from v_group_month where perf_ym=%s", [last_month])
        if g is not None and not g.empty and g.iloc[0]["net"] is not None:
            with cols[0]:
                gr = g.iloc[0]
                d = float(gr["net"] or 0) - (float(gp_prev.iloc[0]["net"]) if gp_prev is not None and not gp_prev.empty and gp_prev.iloc[0]["net"] is not None else 0)
                st.markdown("**集團合併**")
                st.metric("除佣實收", money(gr["net"]), delta=f"{money(d)}（vs 上月）")
                st.caption(f"集團毛利 {money(gr['gp'])}　毛利率 {pct(gr['margin'])}")
                st.caption(f"集團淨利 {money(gr['np'])}")
            ci = 1
    for (_, r) in list(cur.iterrows())[: (n_cards - ci)]:
        with cols[ci]:
            st.markdown(f"**{r['company']}**")
            delta = float(r["net"] or 0) - prev_net.get(r["company"], 0)
            st.metric("除佣實收", money(r["net"]), delta=f"{money(delta)}（vs 上月）")
            st.caption(f"實收 {money(r['gross'])}")
            st.caption(f"毛利 {money(r['gp'])}　毛利率 {pct(r['margin'])}")
        ci += 1

# ---- 當季目標達成 ----
if not is_sales:
    q = (this_month.month - 1) // 3 + 1
    tq = query_df(
        """select company, target_amount, actual, achieved_pct, required_monthly, months_left
           from v_target_progress where period_type='Q' and year=%s and period_no=%s order by company""",
        [this_month.year, q])
    if tq is not None and not tq.empty:
        st.subheader(f"當季目標達成（{this_month.year} Q{q}）")
        tcols = st.columns(min(len(tq), 4) or 1)
        for col, (_, r) in zip(tcols, tq.iterrows()):
            with col:
                st.markdown(f"**{r['company']}**")
                st.metric("達成率", pct(r["achieved_pct"]),
                          delta=f"進單 {money(r['actual'])} / 目標 {money(r['target_amount'])}")
                if r["months_left"] and int(r["months_left"]) > 0:
                    st.caption(f"剩 {int(r['months_left'])} 月・每月需 {money(r['required_monthly'])}")

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
