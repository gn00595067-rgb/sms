"""P5 主檔維護 masters.py — tabs × st.data_editor，通用 apply_edits。

除通用主檔外，另含「目標 / 預估」兩張分析用表（sales_target / forecast）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import connect, transaction  # noqa: E402

from core import data as mdata
from core.auth import require_role
from core.data import clear_cache
from core.masters import apply_edits, fetch
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "EXEC")
is_exec = user["role"] == "EXEC"

page_header("主檔維護", "直接在表格編輯後按「儲存」。不刪除有引用的列，改用「啟用」欄關閉。")

# 每個 tab：(標題, table, 全欄, 可編輯欄, order_by, key)
TABS = [
    ("平台", "platform", ["id", "name", "platform_group", "default_region", "sort_order", "is_active"],
     ["name", "platform_group", "default_region", "sort_order", "is_active"], "sort_order, name", "id"),
    ("電台/成本項目", "media_channel",
     ["id", "name", "channel_type", "is_designated", "tax_rate", "sort_order", "is_active"],
     ["name", "channel_type", "is_designated", "tax_rate", "sort_order", "is_active"], "sort_order, name", "id"),
    ("節目", "program", ["id", "name", "media_channel_id"], ["name", "media_channel_id"], "name", "id"),
    ("公司", "company", ["id", "name", "is_parent", "sort_order", "is_active"],
     ["name", "is_parent", "sort_order", "is_active"], "sort_order, name", "id"),
    ("組別", "business_group", ["id", "name", "company_id", "is_intercompany", "sort_order", "is_active"],
     ["name", "company_id", "is_intercompany", "sort_order", "is_active"], "sort_order, name", "id"),
    ("業務", "salesperson", ["id", "name", "group_id", "manager_name", "is_active"],
     ["name", "group_id", "manager_name", "is_active"], "name", "id"),
    ("人員", "staff", ["id", "name", "roles", "is_active"], ["name", "is_active"], "name", "id"),
    ("產業別", "industry", ["id", "name"], ["name"], "name", "id"),
    ("客戶類別", "customer_category", ["id", "name"], ["name"], "name", "id"),
    ("業績類別", "sales_category", ["id", "name", "parent_category", "recognition_ratio", "is_active"],
     ["name", "parent_category", "recognition_ratio", "is_active"], "name", "id"),
    ("區域", "region", ["code", "name", "sort_order"], ["code", "name", "sort_order"], "sort_order", "code"),
    ("固定成本規則", "fixed_cost_rule",
     ["id", "platform_group", "platform_id", "media_channel_id", "company_id", "ym_from", "ym_to", "monthly_amount", "note"],
     ["platform_group", "platform_id", "media_channel_id", "company_id", "ym_from", "ym_to", "monthly_amount", "note"],
     "ym_from desc, id", "id"),
    ("轉撥規則", "intercompany_rule",
     ["id", "from_company_id", "to_company_id", "platform_group", "rate", "ym_from", "ym_to", "note"],
     ["from_company_id", "to_company_id", "platform_group", "rate", "ym_from", "ym_to", "note"],
     "ym_from desc, id", "id"),
    ("獎金規則", "bonus_rule",
     ["id", "salesperson_id", "platform_group", "sales_item", "ym_from", "ym_to", "bonus_pct", "threshold_amount", "note"],
     ["salesperson_id", "platform_group", "sales_item", "ym_from", "ym_to", "bonus_pct", "threshold_amount", "note"],
     "ym_from desc, id", "id"),
]

MEDIA_TABS = {"platform", "media_channel", "program"}
visible = TABS if is_exec else [t for t in TABS if t[1] in MEDIA_TABS]
if not is_exec:
    st.caption("媒體人員可維護：平台、電台/成本項目、節目。")

for tab, (title, table, cols, editable, order_by, key) in zip(st.tabs([t[0] for t in visible]), visible):
    with tab:
        original = fetch(table, cols, order_by=order_by, key=key)
        # roles 陣列欄唯讀顯示
        disabled_cols = [c for c in cols if c not in editable]
        edited = st.data_editor(
            original, num_rows="dynamic", use_container_width=True, hide_index=True,
            disabled=disabled_cols, key=f"editor_{table}",
        )
        if st.button("儲存", key=f"save_{table}"):
            res = apply_edits(table, original, edited, editable, user["username"], key=key)
            clear_cache()
            st.success(f"已儲存：新增 {res['inserted']} 筆、更新 {res['updated']} 筆")


# ====================================================================
# 目標 / 預估（分析報表用）
# ====================================================================
def _name_id_maps():
    comps = {r["name"]: int(r["id"]) for _, r in mdata.companies().iterrows()}
    sps = {r["name"]: int(r["id"]) for _, r in mdata.salespersons().iterrows()}
    custs = {r["name"]: int(r["id"]) for _, r in mdata.customers().iterrows()}
    return comps, sps, custs


def _fetch_df(sql, params=None) -> pd.DataFrame:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())


def _edit_targets(user):
    comps, sps, _ = _name_id_maps()
    st.caption("口徑：老闆儀表板為『企頻＋新鮮視、不含公司戶』。平台歸類欄留空 = 不分平台；用逗號分隔多個。")
    df = _fetch_df(
        """select t.id, t.year, t.period_type, t.period_no, c.name as company, sp.name as salesperson,
                  t.platform_groups, t.include_house, t.target_amount, t.note
           from sales_target t left join company c on c.id=t.company_id
           left join salesperson sp on sp.id=t.salesperson_id
           order by t.year desc, t.period_type, t.period_no""")
    if df.empty:
        df = pd.DataFrame(columns=["id", "year", "period_type", "period_no", "company", "salesperson",
                                   "platform_groups", "include_house", "target_amount", "note"])
    disp = pd.DataFrame({
        "id": df["id"], "年": df["year"], "期別": df["period_type"], "期次": df["period_no"],
        "公司": df["company"].fillna("") if "company" in df else "",
        "業務": df["salesperson"].fillna("") if "salesperson" in df else "",
        "平台歸類": df["platform_groups"].map(lambda v: ",".join(v) if isinstance(v, list) else (v or "")),
        "含公司戶": df["include_house"].fillna(False) if "include_house" in df else False,
        "目標金額": df["target_amount"], "備註": df["note"].fillna("") if "note" in df else "",
    })
    edited = st.data_editor(
        disp, num_rows="dynamic", hide_index=True, use_container_width=True, key="tgt_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "年": st.column_config.NumberColumn("年", min_value=2020, max_value=2100, step=1, format="%d"),
            "期別": st.column_config.SelectboxColumn("期別", options=["Y", "Q", "M"], required=True),
            "期次": st.column_config.NumberColumn("期次", min_value=1, max_value=12, step=1, format="%d"),
            "公司": st.column_config.SelectboxColumn("公司", options=[""] + list(comps.keys())),
            "業務": st.column_config.SelectboxColumn("業務", options=[""] + list(sps.keys())),
            "平台歸類": st.column_config.TextColumn("平台歸類", help="逗號分隔，如 企頻,新鮮視；空=不分平台"),
            "含公司戶": st.column_config.CheckboxColumn("含公司戶"),
            "目標金額": st.column_config.NumberColumn("目標金額", format="localized"),
            "備註": st.column_config.TextColumn("備註"),
        })
    if st.button("儲存目標", key="save_targets"):
        ins = upd = 0
        with transaction(user["username"]) as cur:
            for _, r in edited.iterrows():
                if pd.isna(r["目標金額"]) or r["期別"] in (None, ""):
                    continue
                pgs = [p.strip() for p in str(r["平台歸類"] or "").replace("＋", ",").split(",") if p.strip()]
                vals = (int(r["年"]), r["期別"], int(r["期次"] or 1),
                        comps.get(r["公司"] or ""), sps.get(r["業務"] or ""),
                        pgs or None, bool(r["含公司戶"]), float(r["目標金額"]), (r["備註"] or None))
                if pd.isna(r["id"]):
                    cur.execute(
                        """insert into sales_target(year,period_type,period_no,company_id,salesperson_id,
                           platform_groups,include_house,target_amount,note,updated_by)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        vals + (user["username"],))
                    ins += 1
                else:
                    cur.execute(
                        """update sales_target set year=%s,period_type=%s,period_no=%s,company_id=%s,
                           salesperson_id=%s,platform_groups=%s,include_house=%s,target_amount=%s,note=%s,
                           updated_by=%s,updated_at=now() where id=%s""",
                        vals + (user["username"], int(r["id"])))
                    upd += 1
        clear_cache()
        st.success(f"已儲存目標：新增 {ins} 筆、更新 {upd} 筆")


def _edit_forecast(user):
    comps, sps, custs = _name_id_maps()
    st.caption("客戶可選主檔或直接打字（打字視為潛在客戶）。狀態 WON 代表已成交。")
    df = _fetch_df(
        """select f.id, f.perf_ym, c.name as company, sp.name as salesperson,
                  coalesce(cu.name, f.customer_text) as customer, f.ad_name, f.platform_group,
                  f.amount, f.probability, f.status, f.note
           from forecast f left join company c on c.id=f.company_id
           left join salesperson sp on sp.id=f.salesperson_id
           left join customer cu on cu.id=f.customer_id
           order by f.perf_ym desc, f.id""")
    if df.empty:
        df = pd.DataFrame(columns=["id", "perf_ym", "company", "salesperson", "customer", "ad_name",
                                   "platform_group", "amount", "probability", "status", "note"])
    disp = pd.DataFrame({
        "id": df["id"], "業績年月": df["perf_ym"],
        "公司": df["company"].fillna("") if "company" in df else "",
        "業務": df["salesperson"].fillna("") if "salesperson" in df else "",
        "客戶": df["customer"].fillna("") if "customer" in df else "",
        "廣告名稱": df["ad_name"].fillna("") if "ad_name" in df else "",
        "平台歸類": df["platform_group"].fillna("") if "platform_group" in df else "",
        "金額": df["amount"], "機率%": df["probability"],
        "狀態": df["status"].fillna("OPEN") if "status" in df else "OPEN",
        "備註": df["note"].fillna("") if "note" in df else "",
    })
    pgs = mdata.platform_groups()
    edited = st.data_editor(
        disp, num_rows="dynamic", hide_index=True, use_container_width=True, key="fc_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "業績年月": st.column_config.DateColumn("業績年月", format="YYYY/MM/DD"),
            "公司": st.column_config.SelectboxColumn("公司", options=[""] + list(comps.keys())),
            "業務": st.column_config.SelectboxColumn("業務", options=[""] + list(sps.keys())),
            "客戶": st.column_config.TextColumn("客戶"),
            "廣告名稱": st.column_config.TextColumn("廣告名稱"),
            "平台歸類": st.column_config.SelectboxColumn("平台歸類", options=[""] + list(pgs)),
            "金額": st.column_config.NumberColumn("金額", format="localized"),
            "機率%": st.column_config.NumberColumn("機率%", min_value=0, max_value=100, step=5, format="%d"),
            "狀態": st.column_config.SelectboxColumn("狀態", options=["OPEN", "WON", "LOST"], required=True),
            "備註": st.column_config.TextColumn("備註"),
        })
    if st.button("儲存預估", key="save_forecast"):
        ins = upd = 0
        with transaction(user["username"]) as cur:
            for _, r in edited.iterrows():
                if pd.isna(r["業績年月"]) or pd.isna(r["金額"]):
                    continue
                cname = (r["客戶"] or "").strip()
                cid = custs.get(cname)
                ctext = None if cid else (cname or None)
                vals = (r["業績年月"], comps.get(r["公司"] or ""), sps.get(r["業務"] or ""),
                        cid, ctext, (r["廣告名稱"] or None), (r["平台歸類"] or None),
                        float(r["金額"]), float(r["機率%"] or 100), (r["狀態"] or "OPEN"), (r["備註"] or None))
                if pd.isna(r["id"]):
                    cur.execute(
                        """insert into forecast(perf_ym,company_id,salesperson_id,customer_id,customer_text,
                           ad_name,platform_group,amount,probability,status,note,created_by,updated_by)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        vals + (user["username"], user["username"]))
                    ins += 1
                else:
                    cur.execute(
                        """update forecast set perf_ym=%s,company_id=%s,salesperson_id=%s,customer_id=%s,
                           customer_text=%s,ad_name=%s,platform_group=%s,amount=%s,probability=%s,status=%s,
                           note=%s,updated_by=%s where id=%s""",
                        vals + (user["username"], int(r["id"])))
                    upd += 1
        clear_cache()
        st.success(f"已儲存預估：新增 {ins} 筆、更新 {upd} 筆")


st.divider()
st.subheader("業績目標 / 預估（分析報表用）")
ttab, ftab = st.tabs(["🎯 目標", "🔮 預估"])
with ttab:
    _edit_targets(user)
with ftab:
    _edit_forecast(user)


# ====================================================================
# 電台財務規則（財務報表專區 TASK_7 用）
# ====================================================================
PAY_TYPES = ["每月2付", "次月1付", "次週三付", "第N天付", "播畢第N天付", "播畢次月1付"]


def _channel_maps():
    mc = mdata.media_channels()
    name_to_id = {r["name"]: int(r["id"]) for _, r in mc.iterrows()}
    return name_to_id, list(name_to_id.keys())


def _edit_channel_payment(user):
    st.caption("電台預付日推算規則（電台預付查詢用）。鍵＝電台＋是否聯網；同一電台聯網／非聯網可各一條。刪除列＝停用該規則。")
    ch_map, ch_names = _channel_maps()
    df = _fetch_df(
        """select r.id, mc.name as channel, r.is_network, r.pay_type, r.first_cutoff_day, r.second_cutoff_day,
                  r.same_month_day, r.next_month_day, r.n_days, r.note
           from channel_payment_rule r join media_channel mc on mc.id = r.media_channel_id
           order by mc.sort_order, mc.name, r.is_network""")
    if df.empty:
        df = pd.DataFrame(columns=["id", "channel", "is_network", "pay_type", "first_cutoff_day",
                                   "second_cutoff_day", "same_month_day", "next_month_day", "n_days", "note"])
    disp = pd.DataFrame({
        "id": df["id"], "電台": df["channel"], "聯網": df["is_network"].fillna(False),
        "付款種類": df["pay_type"], "一段日前": df["first_cutoff_day"], "二段日前": df["second_cutoff_day"],
        "當月付款日": df["same_month_day"], "次月付款日": df["next_month_day"], "第N天付款": df["n_days"],
        "備註": df["note"].fillna("") if "note" in df else "",
    })
    edited = st.data_editor(
        disp, num_rows="dynamic", hide_index=True, use_container_width=True, key="cpr_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "電台": st.column_config.SelectboxColumn("電台", options=ch_names, required=True),
            "聯網": st.column_config.CheckboxColumn("聯網"),
            "付款種類": st.column_config.SelectboxColumn("付款種類", options=PAY_TYPES, required=True),
            "一段日前": st.column_config.NumberColumn("一段日前", min_value=0, max_value=31, step=1, format="%d",
                                               help="每月2付：上檔日 ≤ 此日 → 當月付款日"),
            "二段日前": st.column_config.NumberColumn("二段日前", min_value=0, max_value=31, step=1, format="%d"),
            "當月付款日": st.column_config.NumberColumn("當月付款日", min_value=0, max_value=31, step=1, format="%d"),
            "次月付款日": st.column_config.NumberColumn("次月付款日", min_value=0, max_value=31, step=1, format="%d"),
            "第N天付款": st.column_config.NumberColumn("第N天付款", min_value=0, max_value=90, step=1, format="%d"),
            "備註": st.column_config.TextColumn("備註"),
        })
    if st.button("儲存付款規則", key="save_cpr"):
        ins = upd = dele = 0
        keep_ids = {int(v) for v in edited["id"] if not pd.isna(v)}
        orig_ids = {int(v) for v in df["id"] if not pd.isna(v)}
        with transaction(user["username"]) as cur:
            for _, r in edited.iterrows():
                ch = (r["電台"] or "").strip()
                pt = (r["付款種類"] or "").strip()
                if ch not in ch_map or pt not in PAY_TYPES:
                    continue
                vals = (ch_map[ch], bool(r["聯網"]), pt, int(r["一段日前"] or 0), int(r["二段日前"] or 0),
                        int(r["當月付款日"] or 0), int(r["次月付款日"] or 0), int(r["第N天付款"] or 0), (r["備註"] or None))
                if pd.isna(r["id"]):
                    cur.execute(
                        """insert into channel_payment_rule(media_channel_id, is_network, pay_type, first_cutoff_day,
                           second_cutoff_day, same_month_day, next_month_day, n_days, note)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict (media_channel_id, is_network) do update set
                           pay_type=excluded.pay_type, first_cutoff_day=excluded.first_cutoff_day,
                           second_cutoff_day=excluded.second_cutoff_day, same_month_day=excluded.same_month_day,
                           next_month_day=excluded.next_month_day, n_days=excluded.n_days, note=excluded.note""", vals)
                    ins += 1
                else:
                    cur.execute(
                        """update channel_payment_rule set media_channel_id=%s, is_network=%s, pay_type=%s,
                           first_cutoff_day=%s, second_cutoff_day=%s, same_month_day=%s, next_month_day=%s,
                           n_days=%s, note=%s where id=%s""", vals + (int(r["id"]),))
                    upd += 1
            for rid in orig_ids - keep_ids:
                cur.execute("delete from channel_payment_rule where id=%s", (rid,))
                dele += 1
        clear_cache()
        st.success(f"已儲存付款規則：新增 {ins}、更新 {upd}、停用 {dele}")


def _edit_channel_rebate(user):
    st.caption("電台年度退佣%（媒體發稿量分析「毛利+退佣」用）。10＝10%。每年需新增當年度；可用下方按鈕整批複製。")
    ch_map, ch_names = _channel_maps()
    this_year = date.today().year
    c1, c2, c3 = st.columns([1, 1, 2])
    src_year = c1.number_input("來源年", min_value=2020, max_value=2100, value=this_year - 1, step=1, key="reb_src")
    dst_year = c2.number_input("目標年", min_value=2020, max_value=2100, value=this_year, step=1, key="reb_dst")
    if c3.button(f"複製 {int(src_year)} → {int(dst_year)}（只補缺）", key="copy_rebate"):
        with transaction(user["username"]) as cur:
            cur.execute(
                """insert into channel_rebate_rate(media_channel_id, year, rebate_pct, note)
                   select media_channel_id, %s, rebate_pct, note from channel_rebate_rate where year=%s
                   on conflict (media_channel_id, year) do nothing""", (int(dst_year), int(src_year)))
            n = cur.rowcount
        clear_cache()
        st.success(f"已從 {int(src_year)} 複製 {n} 筆到 {int(dst_year)}")
        st.rerun()
    df = _fetch_df(
        """select r.id, mc.name as channel, r.year, r.rebate_pct, r.note
           from channel_rebate_rate r join media_channel mc on mc.id = r.media_channel_id
           order by r.year desc, mc.sort_order, mc.name""")
    if df.empty:
        df = pd.DataFrame(columns=["id", "channel", "year", "rebate_pct", "note"])
    disp = pd.DataFrame({
        "id": df["id"], "電台": df["channel"], "年度": df["year"],
        "退佣%": df["rebate_pct"].map(lambda v: float(v) if pd.notna(v) else None),
        "備註": df["note"].fillna("") if "note" in df else "",
    })
    edited = st.data_editor(
        disp, num_rows="dynamic", hide_index=True, use_container_width=True, key="reb_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "電台": st.column_config.SelectboxColumn("電台", options=ch_names, required=True),
            "年度": st.column_config.NumberColumn("年度", min_value=2020, max_value=2100, step=1, format="%d"),
            "退佣%": st.column_config.NumberColumn("退佣%", min_value=0.0, max_value=100.0, step=0.01, format="%.4f",
                                              help="10＝10%（毛利+退佣＝毛利＋實付×退佣%÷100）"),
            "備註": st.column_config.TextColumn("備註"),
        })
    if st.button("儲存年度退佣", key="save_rebate"):
        ins = upd = dele = 0
        keep_ids = {int(v) for v in edited["id"] if not pd.isna(v)}
        orig_ids = {int(v) for v in df["id"] if not pd.isna(v)}
        with transaction(user["username"]) as cur:
            for _, r in edited.iterrows():
                ch = (r["電台"] or "").strip()
                if ch not in ch_map or pd.isna(r["年度"]) or pd.isna(r["退佣%"]):
                    continue
                vals = (ch_map[ch], int(r["年度"]), float(r["退佣%"]), (r["備註"] or None))
                if pd.isna(r["id"]):
                    cur.execute(
                        """insert into channel_rebate_rate(media_channel_id, year, rebate_pct, note)
                           values (%s,%s,%s,%s) on conflict (media_channel_id, year)
                           do update set rebate_pct=excluded.rebate_pct, note=excluded.note""", vals)
                    ins += 1
                else:
                    cur.execute(
                        "update channel_rebate_rate set media_channel_id=%s, year=%s, rebate_pct=%s, note=%s where id=%s",
                        vals + (int(r["id"]),))
                    upd += 1
            for rid in orig_ids - keep_ids:
                cur.execute("delete from channel_rebate_rate where id=%s", (rid,))
                dele += 1
        clear_cache()
        st.success(f"已儲存年度退佣：新增 {ins}、更新 {upd}、刪除 {dele}")


def _edit_channel_purchase(user):
    st.caption("電台採購申請單用欄位（現金折扣、現金預付、一般付款、採購單備註、聯播網）。只編輯既有電台，新增電台請到「電台/成本項目」。")
    df = _fetch_df(
        """select id, name, cash_discount_pct, is_cash_prepaid, is_normal_payment, purchase_note, network_name
           from media_channel order by sort_order, name""")
    if df.empty:
        st.info("尚無電台資料。")
        return
    disp = pd.DataFrame({
        "id": df["id"], "電台": df["name"],
        "現金折扣%": df["cash_discount_pct"].map(lambda v: round(float(v) * 100, 4) if pd.notna(v) else 0.0),
        "現金預付": df["is_cash_prepaid"].fillna(False),
        "一般付款": df["is_normal_payment"].fillna(False),
        "採購單備註": df["purchase_note"].fillna("") if "purchase_note" in df else "",
        "聯播網": df["network_name"].fillna("") if "network_name" in df else "",
    })
    edited = st.data_editor(
        disp, num_rows="fixed", hide_index=True, use_container_width=True, key="mcp_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "電台": st.column_config.TextColumn("電台", disabled=True),
            "現金折扣%": st.column_config.NumberColumn("現金折扣%", min_value=0.0, max_value=100.0, step=0.01,
                                                 format="%.2f", help="4＝4%（採購申請單現折金額＝實付×現金折扣%÷100）"),
            "現金預付": st.column_config.CheckboxColumn("現金預付"),
            "一般付款": st.column_config.CheckboxColumn("一般付款"),
            "採購單備註": st.column_config.TextColumn("採購單備註", help="印在採購申請單備註欄，如「已於預付明細表申請」"),
            "聯播網": st.column_config.SelectboxColumn("聯播網", options=["", "好事", "城市"],
                                                 help="採購申請單「好事／城市聯播網總額」用"),
        })
    if st.button("儲存採購欄位", key="save_mcp"):
        orig = {int(r["id"]): r for _, r in df.iterrows()}
        upd = 0
        with transaction(user["username"]) as cur:
            for _, r in edited.iterrows():
                rid = int(r["id"])
                o = orig.get(rid)
                new_disc = round(float(r["現金折扣%"] or 0) / 100, 4)
                new = (new_disc, bool(r["現金預付"]), bool(r["一般付款"]),
                       (r["採購單備註"] or None), (r["聯播網"] or None))
                old = (round(float(o["cash_discount_pct"] or 0), 4), bool(o["is_cash_prepaid"]),
                       bool(o["is_normal_payment"]), (o["purchase_note"] or None), (o["network_name"] or None))
                if new != old:
                    cur.execute(
                        """update media_channel set cash_discount_pct=%s, is_cash_prepaid=%s, is_normal_payment=%s,
                           purchase_note=%s, network_name=%s where id=%s""", new + (rid,))
                    upd += 1
        clear_cache()
        st.success(f"已儲存採購欄位：更新 {upd} 筆")


st.divider()
st.subheader("電台財務規則（財務報表專區用）")
ptab, rtab, mtab = st.tabs(["💰 電台付款規則", "↩️ 電台年度退佣", "🧾 電台採購欄位"])
with ptab:
    _edit_channel_payment(user)
with rtab:
    _edit_channel_rebate(user)
with mtab:
    _edit_channel_purchase(user)

feedback_widget("masters")
