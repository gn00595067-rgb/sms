"""P 自訂報表 — 選期間 → 口徑 → 篩選 → 列/欄維度 → 指標 → 表格 → Excel／存成我的報表。

安全模型見 reports/builder.py（維度/指標/篩選全白名單、值全參數化、SALES 自動限縮）。
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from core import analysis as A
from core.auth import require_role
from core.format import ym_text
from core.ui import feedback_widget, page_header
from core import data as _data
from reports import builder as B

user = require_role("MEDIA", "FINANCE", "EXEC", "SALES")
is_sales = user["role"] == "SALES"
page_header("📐 自訂報表", "選期間 → 口徑 → 篩選 → 列/欄維度 → 指標 → 查詢；可存成我的報表、下載 Excel。")

ss = st.session_state
if "rb" not in ss:
    ss.rb = B.default_definition()

# ---- 我的報表 / 同仁分享 ----
saved = B.list_saved(user)
saved_by_id = {int(r["id"]): r for r in saved}
pick_opts = [0] + list(saved_by_id.keys())
def _pick_label(i):
    if i == 0:
        return "（新報表）"
    r = saved_by_id[i]
    return ("🔗 " if r["is_shared"] else "") + r["name"]
c_load = st.columns([3, 1, 1])
pick = c_load[0].selectbox("我的報表 / 同仁分享", pick_opts, format_func=_pick_label, key="rb_pick")
if c_load[1].button("載入", use_container_width=True, disabled=(pick == 0)):
    ss.rb = B.load_definition(saved_by_id[pick]["definition"])
    ss.rb["_id"] = pick
    st.rerun()
if c_load[2].button("刪除", use_container_width=True,
                    disabled=(pick == 0 or saved_by_id.get(pick, {}).get("owner_id") != user["id"])):
    B.delete_saved(pick, user); ss.pop("rb_pick", None); st.rerun()

rb = ss.rb
st.divider()

# ---- ① 期間 ----
months = A.analysis_months()
if not months:
    st.info("尚無資料。"); feedback_widget("report_builder"); st.stop()
ao = A.as_of()
c1, c2, c3 = st.columns([2, 2, 3])
def_from = rb["period"].get("from") or date(ao["as_of_year"], 1, 1)
def_to = rb["period"].get("to") or ao["as_of_ym"]
def _nearest(t):
    return min(months, key=lambda m: abs((m - t).days))
ym_from = c1.selectbox("期間（起）", months, index=months.index(_nearest(def_from)),
                       format_func=ym_text, key="rb_from")
ym_to = c2.selectbox("期間（迄）", months, index=months.index(_nearest(def_to)),
                     format_func=ym_text, key="rb_to")
yoy = c3.checkbox("加去年同期欄（僅金額指標）", value=rb["period"].get("yoy", False), key="rb_yoy")

# ---- ② 口徑與篩選 ----
scope = A.scope_bar("rb")
fc = st.columns(3)
with fc[0]:
    comp = st.multiselect("公司", [o[1] for o in _data.options("company")],
                          default=rb["filters"].get("company", []), key="rb_f_co")
    rp = st.multiselect("報表平台", A.REPORT_PLATFORM_ORDER,
                        default=rb["filters"].get("report_platform", []), key="rb_f_rp")
with fc[1]:
    if not is_sales:
        sps = st.multiselect("業務", [o[1] for o in _data.options("salesperson")],
                             default=rb["filters"].get("salesperson", []), key="rb_f_sp")
    else:
        sps = []
    inds = st.multiselect("產業別", [o[1] for o in _data.options("industry")],
                          default=rb["filters"].get("industry", []), key="rb_f_ind")
with fc[2]:
    cust_like = st.text_input("客戶（模糊，逗號分隔多個）",
                              value="、".join(rb["filters"].get("customer_like", [])), key="rb_f_cust")
    net_min = st.number_input("金額門檻（群組除佣實收 ≥）", min_value=0, value=int(rb["filters"].get("net_min") or 0),
                              step=100000, key="rb_f_netmin")

filters = {}
if comp:
    filters["company"] = comp
if rp:
    filters["report_platform"] = rp
if sps:
    filters["salesperson"] = sps
if inds:
    filters["industry"] = inds
if cust_like.strip():
    filters["customer_like"] = [x.strip() for x in cust_like.replace(",", "、").split("、") if x.strip()]
if net_min:
    filters["net_min"] = net_min

# ---- ③ 版面：列 / 欄 / 指標 ----
dim_keys = list(B.DIMENSIONS.keys())
meas_keys = list(B.MEASURES.keys())
vc = st.columns(3)
rows = vc[0].multiselect("列維度（最多 3，明細模式留空）", dim_keys,
                         default=[k for k in rb.get("rows", []) if k in dim_keys][:3],
                         format_func=lambda k: B.DIMENSIONS[k][0], key="rb_rows", max_selections=3)
col_choice = vc[1].selectbox("欄維度（樞紐，可無）", ["（無）"] + dim_keys,
                             index=(dim_keys.index(rb["col"]) + 1) if rb.get("col") in dim_keys else 0,
                             format_func=lambda k: "（無）" if k == "（無）" else B.DIMENSIONS[k][0], key="rb_col")
col = None if col_choice == "（無）" else col_choice
measures = vc[2].multiselect("指標", meas_keys,
                             default=[m for m in rb.get("measures", []) if m in meas_keys] or ["net_amount"],
                             format_func=lambda k: B.MEASURES[k][0], key="rb_meas")

sc = st.columns(4)
show = {
    "total": sc[0].checkbox("合計列", value=rb["show"].get("total", True), key="rb_total"),
    "share": sc[1].checkbox("佔比欄", value=rb["show"].get("share", True), key="rb_share"),
    "top_n": sc[2].number_input("前 N（每第一層，0=全部）", min_value=0,
                                value=int(rb["show"].get("top_n") or 0), key="rb_topn") or None,
    "sort": ["net_amount", "desc"],
}

defn = {"v": 1, "name": rb.get("name", ""), "period": {"from": ym_from, "to": ym_to, "yoy": yoy},
        "scope": scope, "filters": filters, "rows": rows, "col": col,
        "measures": measures or ["net_amount"], "show": show,
        "detail_columns": rb.get("detail_columns")}
ss.rb = {**defn, "_id": rb.get("_id")}

st.divider()

# ---- ④ 查詢 ----
if st.button("查詢", type="primary"):
    ss["rb_run"] = True
if ss.get("rb_run"):
    import time
    t0 = time.time()
    df = B.run(defn, user)
    res, spec = B.shape(df, defn)
    took = time.time() - t0
    if res is None or len(res) == 0:
        st.info("查無資料。")
    else:
        mode = "明細" if not rows else ("樞紐" if col else "彙總")
        st.caption(f"{ym_text(ym_from)}–{ym_text(ym_to)}｜口徑 {scope.get('preset')}｜{mode}"
                   f"｜{len(res)} 列｜{took:.2f}s")
        # 明細模式限畫面 5000 列
        show_df = res.head(5000) if not rows else res
        A.show_ranking(show_df, spec, height=520, key="rb_result")
        title = defn["name"] or "自訂報表"
        subs = [f"期間 {ym_text(ym_from)}–{ym_text(ym_to)}　口徑 {scope.get('preset')}", "單位：元"]
        st.download_button("⬇ 下載 Excel", data=B.build_excel(res, spec, title, subs),
                           file_name=f"自訂報表_{title}_{ym_from:%Y%m}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

# ---- 儲存 ----
st.divider()
sv = st.columns([3, 1, 1])
name = sv[0].text_input("報表名稱", value=defn["name"], key="rb_name")
share = sv[1].checkbox("分享給同仁", value=False, disabled=is_sales, key="rb_shareflag")
if sv[2].button("儲存", use_container_width=True, disabled=not name.strip()):
    defn["name"] = name.strip()
    rid = B.save_saved(name.strip(), defn, user, is_shared=bool(share),
                       report_id=(rb.get("_id") if rb.get("_id") and saved_by_id.get(rb["_id"], {}).get("owner_id") == user["id"] else None))
    ss.rb["_id"] = rid
    st.success(f"已儲存「{name.strip()}」。")
    st.rerun()

feedback_widget("report_builder")
