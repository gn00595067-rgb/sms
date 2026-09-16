"""P15 銷售分析 — 分佈比平均重要；訂單層的定價與成本。

MEDIA / FINANCE / EXEC 可看全部；SALES 只看自己。低毛利原因可直接回填。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import transaction  # noqa: E402

from core import analysis as A
from core.auth import require_role
from core.format import COLORS, money, pct
from core.ui import feedback_widget, page_header
from core.uimode import page_available
from reports.render_excel import build_excel

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
# 只有在「業績登打」頁可達時才開放點列 → 修改（本階段測試隱藏登打頁）
can_edit_deal = user["role"] in ("MEDIA", "EXEC") and page_available("deal_entry")
page_header("🧾 銷售分析", "分佈比平均重要：錢集中在哪個級距、有多少業績在低毛利下做的。")

f = A.filter_bar_analysis("asales", user=user, show_house_toggle=True)
# 銷售分析含成本單（ext_net<=0），故 load 全部（仍可排除交換）
d_all = A.load_deals(f["ym_from"], f["ym_to"], f, exclude_barter=f["exclude_barter"], user=user)
if d_all.empty:
    st.info("此條件查無資料。")
    feedback_widget("analysis_sales")
    st.stop()

d = d_all[d_all["ext_net"] > 0].copy()
zero = d_all[d_all["ext_net"] <= 0].copy()
pf, pt = A.prev_window(f["ym_from"], f["ym_to"])
dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
deals_p = int((dp["ext_net"] > 0).sum()) if not dp.empty else 0

net_sum = float(d["ext_net"].sum())
A.kpi_row([
    {"label": "有收入的訂單", "value": f"{len(d)}", "sub": f"同期 {deals_p}"},
    {"label": "平均單筆", "value": money(d["ext_net"].mean()), "sub": f"中位數 {money(d['ext_net'].median())}"},
    {"label": "大單（≥100 萬）", "value": f"{int((d['ext_net'] >= 1_000_000).sum())} 筆",
     "sub": f"佔業績 {pct(float(d[d['ext_net'] >= 1_000_000]['ext_net'].sum()) / net_sum) if net_sum else '–'}"},
    {"label": "低毛利（<16%）", "value": f"{int(d['is_low_margin'].sum())} 筆",
     "sub": f"佔業績 {pct(float(d[d['is_low_margin']]['ext_net'].sum()) / net_sum) if net_sum else '–'}"},
    {"label": "零收入成本單", "value": f"{len(zero)} 筆", "sub": f"成本 {money(float(zero['booked_cost'].sum()))}"},
    {"label": "帳上毛利率（含成本單）", "value": pct(float(d_all['booked_profit'].sum()) / float(d_all['ext_net'].sum())) if float(d_all['ext_net'].sum()) else "–",
     "sub": f"只看有收入 {pct(float(d['booked_profit'].sum()) / net_sum) if net_sum else '–'}"},
])

st.divider()

# ---- 兩張圖：金額分佈 / 毛利率分佈 ----
c1, c2 = st.columns(2)
with c1:
    st.markdown("**訂單金額分佈**")
    sb = A.size_buckets(d)
    labels = [s[3:] for s in sb["size_bucket"]]
    fig = go.Figure(go.Bar(y=labels, x=sb["net"], orientation="h", marker_color=COLORS["accent"],
                           text=[f"{money(n)}｜{int(c)} 筆｜{pct(m)}" for n, c, m in zip(sb["net"], sb["n"], sb["booked_margin"])],
                           textposition="outside", hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(showlegend=False, height=260, margin=dict(l=8, r=8, t=8, b=8),
                      yaxis=dict(autorange="reversed"), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.markdown("**毛利率分佈**")
    mb = A.margin_bands(d)
    labels = [s[3:] for s in mb["band"]]
    def _c(b):
        return COLORS["alert"]["red"] if b.startswith("<0") else (COLORS["alert"]["yellow"] if b.startswith("0–16") else COLORS["accent"])
    fig2 = go.Figure(go.Bar(y=labels, x=mb["net"], orientation="h",
                            marker_color=[_c(s[3:]) for s in mb["band"]],
                            text=[f"{money(n)}｜{int(c)} 筆" for n, c in zip(mb["net"], mb["n"])],
                            textposition="outside", hovertemplate="%{text}<extra></extra>"))
    fig2.update_layout(showlegend=False, height=260, margin=dict(l=8, r=8, t=8, b=8),
                       yaxis=dict(autorange="reversed"), font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig2, use_container_width=True)

# ---- 產業 × 平台歸類熱圖 ----
st.markdown("**產業 × 平台歸類**（除佣實收；產業取前 9）")
dd = d.copy()
dd["ind"] = dd["industry"].fillna("(未分類)")
dd["pg"] = dd["main_platform_group"].map(lambda p: p if p in ("企頻", "新鮮視", "廣播") else "其他")
top9 = dd.groupby("ind")["ext_net"].sum().sort_values(ascending=False).head(9).index.tolist()
pv = dd[dd["ind"].isin(top9)].pivot_table(index="ind", columns="pg", values="ext_net", aggfunc="sum")
pv = pv.reindex(index=top9, columns=["企頻", "新鮮視", "廣播", "其他"]).fillna(0)
fig3 = px.imshow(pv.values / 10000, x=list(pv.columns), y=top9, color_continuous_scale="Blues", aspect="auto",
                 labels=dict(color="萬"))
fig3.update_layout(height=max(260, 34 * len(top9)), margin=dict(l=8, r=8, t=8, b=8),
                   font=dict(family="Noto Sans TC, Microsoft JhengHei"))
st.plotly_chart(fig3, use_container_width=True)

# ---- 訂單排名 ----
st.markdown("**訂單排名**" + ("（點一列 → 業績登打修改）" if can_edit_deal else ""))
sort_opt = st.selectbox("排序依", ["除佣實收", "帳上毛利", "毛利率", "集團淨利率"], key="sales_sort")
sort_col = {"除佣實收": "ext_net", "帳上毛利": "booked_profit", "毛利率": "booked_margin", "集團淨利率": "net_margin"}[sort_opt]
top = d.sort_values(sort_col, ascending=False).head(50)
ev = A.show_ranking(top, [
    ("contract_no", "合約", "text"), ("ad_name", "廣告", "text"),
    ("customer", "客戶", "text"), ("industry", "產業", "text"),
    ("salesperson", "業務", "text"), ("company", "公司", "text"),
    ("platform_groups", "平台歸類", "text"), ("perf_ym_text", "年月", "text"),
    ("ext_net", "除佣實收", "money"), ("booked_cost", "實付", "money"),
    ("booked_profit", "帳上毛利", "money"), ("booked_margin", "毛利率", "pct"),
    ("net_margin", "集團淨利率", "pct"), ("production_cost", "製作費", "money"),
], key="sales_rank", on_select=("rerun" if can_edit_deal else "ignore"))

if can_edit_deal and ev and getattr(ev, "selection", None) and ev.selection.get("rows"):
    st.session_state["edit_contract"] = top.iloc[ev.selection["rows"][0]]["contract_no"]
    st.switch_page("pages_app/deal_entry.py")

xcols = ["contract_no", "ad_name", "customer", "industry", "salesperson", "company",
         "platform_groups", "perf_ym_text", "ext_net", "booked_cost", "booked_profit",
         "booked_margin", "net_margin", "production_cost"]
st.download_button("⬇ 下載 Excel", data=build_excel(d.sort_values(sort_col, ascending=False)[xcols], "銷售分析", A.filter_text(f), columns=xcols),
                   file_name="analysis_sales.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- 低毛利清單（可回填原因） ----
st.divider()
st.markdown("**⚠ 低毛利訂單**（≥10 萬、毛利率最低）— 直接填「低毛利原因」後儲存")
n_low = st.number_input("顯示筆數", min_value=1, max_value=100, value=10, key="low_n")
low = d[d["ext_net"] >= 100000].sort_values("booked_margin").head(int(n_low)).copy()
if low.empty:
    st.caption("此條件下無低毛利訂單。")
else:
    reasons = A.query_reasons(low["deal_id"].tolist()) if hasattr(A, "query_reasons") else {}
    disp = pd.DataFrame({
        "合約": low["contract_no"], "廣告": low["ad_name"], "客戶": low["customer"],
        "業務": low["salesperson"], "除佣實收": low["ext_net"].round(0),
        "毛利率": low["booked_margin"], "低毛利原因": [reasons.get(x, "") for x in low["deal_id"]],
    })
    disp = disp.reset_index(drop=True)
    edited = st.data_editor(
        disp, hide_index=True, use_container_width=True, key="low_editor",
        column_config={
            "除佣實收": st.column_config.NumberColumn("除佣實收", format="localized", disabled=True),
            "毛利率": st.column_config.NumberColumn("毛利率", format="percent", disabled=True),
            "合約": st.column_config.TextColumn("合約", disabled=True),
            "廣告": st.column_config.TextColumn("廣告", disabled=True),
            "客戶": st.column_config.TextColumn("客戶", disabled=True),
            "業務": st.column_config.TextColumn("業務", disabled=True),
            "低毛利原因": st.column_config.TextColumn("低毛利原因"),
        })
    if user["role"] in ("MEDIA", "FINANCE", "EXEC") and st.button("儲存低毛利原因"):
        deal_ids = low["deal_id"].tolist()
        n_saved = 0
        with transaction(user["username"]) as cur:
            for i, did in enumerate(deal_ids):
                new_r = (edited.iloc[i]["低毛利原因"] or "").strip()
                old_r = (reasons.get(did) or "").strip()
                if new_r != old_r:
                    cur.execute(
                        "update deal_line set low_margin_reason=%s, low_margin_handled=%s where deal_id=%s",
                        (new_r or None, bool(new_r), did))
                    n_saved += 1
        st.success(f"已儲存 {n_saved} 筆低毛利原因。")

feedback_widget("analysis_sales")
