"""P14 業務分析 — 量（金額、佔比）與質（毛利率、新客、依賴度）並列。

MEDIA / FINANCE / EXEC 可看全部；SALES 只看自己。
"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.format import money, pct
from core.ui import feedback_widget, page_header
from reports.render_excel import build_excel

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
page_header("🧑‍💼 業務分析", "量與質並列：金額、佔比是量，毛利率、新客、依賴度是質。")

f = A.filter_bar_analysis("asp", user=user, show_salesperson=False)
dw = A.load_deals(f["ym_from"], f["ym_to"], f, exclude_barter=f["exclude_barter"], user=user)
if dw.empty:
    st.info("此條件查無資料。")
    feedback_widget("analysis_salesperson")
    st.stop()

pf, pt = A.prev_window(f["ym_from"], f["ym_to"])
dp = A.load_deals(pf, pt, f, exclude_barter=f["exclude_barter"], user=user)
cy = A.customer_year(f["ym_from"].year)
cust = A.agg_customers(dw, dp, cy)
new_by = A.new_customers_by_salesperson(cust)
barter_by = A.load_barter_by("salesperson", f["ym_from"], f["ym_to"])
sp = A.agg_salespeople(dw, dp, new_by, barter_by)

nonh = sp[~sp["is_house"]].copy()
house = sp[sp["is_house"]].copy()

# ---- KPI ----
n = len(nonh)
tot = float(nonh["ext_net"].sum())
tot_bp = float(nonh["booked_profit"].sum())
A.kpi_row([
    {"label": "有業績的業務", "value": f"{n} 人", "sub": f"公司戶另計 {money(float(house['ext_net'].sum()))}"},
    {"label": "人均除佣實收", "value": money(tot / n) if n else "–", "sub": f"人均帳上毛利 {money(tot_bp / n) if n else '–'}"},
    {"label": "人均客戶數", "value": f"{nonh['customers'].sum() / n:.1f}" if n else "–",
     "sub": f"人均新客 {nonh['new_customers'].sum() / n:.1f}" if n else "–"},
    {"label": "業務業績合計", "value": money(tot), "sub": f"帳上毛利率 {pct(tot_bp / tot) if tot else '–'}"},
    {"label": "交換（另計）", "value": money(float(sp["barter_net"].sum())), "sub": "不計入排名與毛利"},
])

st.divider()

# ---- 排名表 ----
st.markdown("**業務排名**（點一列 → 業務頁）")
mxnet = float(nonh["ext_net"].max()) if n else 1.0
nonh["mix"] = nonh.apply(lambda r: A.platform_mix_text(r["net_cp"], r["net_fresh"], r["net_radio"], r["net_other"]), axis=1)
event = A.show_ranking(nonh, [
    ("rank_in_year", "#", "int"),
    ("salesperson", "業務", "text"),
    ("main_company", "公司", "text"),
    ("main_group", "組別", "text"),
    ("ext_net", "除佣實收", "progress", {"max": mxnet}),
    ("yoy_pct", "同期%", "pct"),
    ("share", "佔比", "pct"),
    ("booked_profit", "帳上毛利", "money"),
    ("booked_margin", "毛利率", "pct"),
    ("net_margin", "集團淨利率", "pct"),
    ("recognized_amount", "認定業績", "money"),
    ("customers", "客戶數", "int"),
    ("new_customers", "新客", "int"),
    ("deals", "訂單數", "int"),
    ("avg_deal", "平均單筆", "money"),
    ("top3_share", "前3大依賴度", "pct"),
    ("top_customer", "最大客戶", "text"),
    ("mix", "平台組合", "text"),
    ("barter_net", "交換", "money"),
], key="sp_rank", on_select="rerun")

if event and getattr(event, "selection", None) and event.selection.get("rows"):
    idx = event.selection["rows"][0]
    st.session_state["salesperson_focus"] = nonh.iloc[idx]["salesperson"]
    st.switch_page("pages_app/salesperson_detail.py")

if not house.empty:
    st.caption("公司戶（Company 等）— 另列、不排名")
    A.show_ranking(house, [
        ("salesperson", "業務", "text"), ("main_company", "公司", "text"),
        ("ext_net", "除佣實收", "money"), ("booked_profit", "帳上毛利", "money"),
        ("booked_margin", "毛利率", "pct"), ("deals", "訂單數", "int"),
    ], height=None, key="sp_house")

xcols = ["rank_in_year", "salesperson", "main_company", "main_group", "ext_net", "yoy_pct",
         "share", "booked_profit", "booked_margin", "net_margin", "recognized_amount",
         "customers", "new_customers", "deals", "avg_deal", "top3_share", "barter_net"]
st.download_button("⬇ 下載 Excel", data=build_excel(nonh[xcols], "業務分析", A.filter_text(f), columns=xcols),
                   file_name="analysis_salesperson.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- 業務 × 月 熱圖 ----
st.divider()
st.markdown("**業務 × 月 熱圖**（前 8 名，顏色深 = 金額大）")
top8 = nonh.head(8)["salesperson"].tolist()
if top8:
    hm = A.load_deals(f["ym_from"], f["ym_to"], f, exclude_barter=True, user=user)
    hm = hm[hm["salesperson"].isin(top8)].copy()
    hm["month"] = hm["perf_ym"].map(lambda d: f"{d.month}月")
    months = [f"{m.month}月" for m in A.month_range(f["ym_from"], f["ym_to"])]
    pv = hm.pivot_table(index="salesperson", columns="month", values="ext_net", aggfunc="sum").reindex(index=top8, columns=months).fillna(0)
    fig = px.imshow(pv.values / 10000, x=months, y=top8, color_continuous_scale="Blues", aspect="auto",
                    labels=dict(color="萬"))
    fig.update_layout(height=max(240, 34 * len(top8)), margin=dict(l=8, r=8, t=8, b=8),
                      font=dict(family="Noto Sans TC, Microsoft JhengHei"))
    st.plotly_chart(fig, use_container_width=True)

# ---- 業務 × 平台 總計 ----
st.divider()
st.markdown("**業務 × 平台 總計**（每個業務在各媒體平台賣出的除佣實收）")
gran = st.radio("平台細度", ["個別平台（家樂福企頻/健康視…）", "平台歸類（企頻/新鮮視/廣播…）"],
                horizontal=True, key="sp_plat_gran")
by = "platform" if gran.startswith("個別") else "platform_group"
mat = A.salesperson_platform(f["ym_from"], f["ym_to"], f, exclude_barter=f["exclude_barter"], user=user, by=by)
if mat is None or mat.empty:
    st.info("此條件查無資料。")
else:
    disp = mat.reset_index().rename(columns={"salesperson": "業務"})
    cfg = {c: st.column_config.NumberColumn(c, format="localized") for c in mat.columns}
    st.dataframe(disp, column_config=cfg, hide_index=True, use_container_width=True)
    st.caption("數字為除佣實收（對外、已排除內部轉撥"
               + ("、排除交換" if f["exclude_barter"] else "") + "）；欄依總額由大到小排，末欄為該業務合計。")

feedback_widget("analysis_salesperson")
