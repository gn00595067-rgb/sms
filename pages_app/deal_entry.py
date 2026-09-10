"""P2 業績登打 / 修改 — MEDIA、EXEC"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import transaction  # noqa: E402

from core import data, deals
from core.auth import require_role
from core.format import REGION_LABELS
from core.ui import feedback_widget, page_header

user = require_role("MEDIA", "EXEC")
page_header("✍️ 業績登打", "輸入合約編號載入既有資料進入修改模式，或直接新建。")

# ---- 主檔對照表（名稱 → id）----
platforms = data.platforms()
channels = data.media_channels()
programs = data.programs()
PLATFORM_NAMES = platforms["name"].tolist() if not platforms.empty else []
PLATFORM_ID = dict(zip(platforms["name"], platforms["id"])) if not platforms.empty else {}
PLATFORM_GROUP = dict(zip(platforms["name"], platforms["platform_group"])) if not platforms.empty else {}
PLATFORM_REGION = dict(zip(platforms["name"], platforms["default_region"])) if not platforms.empty else {}
CHANNEL_NAMES = [""] + (channels["name"].tolist() if not channels.empty else [])
CHANNEL_ID = dict(zip(channels["name"], channels["id"])) if not channels.empty else {}
PROGRAM_NAMES = [""] + (programs["name"].tolist() if not programs.empty else [])
PROGRAM_ID = dict(zip(programs["name"], programs["id"])) if not programs.empty else {}
REGION_DISPLAY = list(REGION_LABELS.values())               # 全區域/北區/中區/南區
REGION_CODE_BY_NAME = {v: k for k, v in REGION_LABELS.items()}
COMPANY_NAME = dict(zip(data.companies()["id"], data.companies()["name"])) if not data.companies().empty else {}
PLATFORM_NAME_BY_ID = {v: k for k, v in PLATFORM_ID.items()}
CHANNEL_NAME_BY_ID = {v: k for k, v in CHANNEL_ID.items()}
PROGRAM_NAME_BY_ID = {v: k for k, v in PROGRAM_ID.items()}

EDITOR_COLS = ["線類型", "業績年月", "平台", "電台/項目", "節目", "區域", "素材秒數", "總檔數",
               "購買檔次", "搭贈檔次", "實收金額", "退佣%", "現折%", "除佣實收", "實付金額",
               "電台實付", "聯網", "指定電台", "備註"]


def _blank_editor() -> pd.DataFrame:
    df = pd.DataFrame([{c: None for c in EDITOR_COLS} for _ in range(3)])
    df["線類型"] = "MEDIA"
    df["業績年月"] = date.today().replace(day=1)
    df["區域"] = "全區域"
    df["退佣%"] = 0.0
    df["現折%"] = 0.0
    return df


def _flat_to_editor(lines: pd.DataFrame) -> pd.DataFrame:
    """v_deal_line_flat → 編輯表。"""
    if lines is None or lines.empty:
        return _blank_editor()
    rows = []
    for _, r in lines.iterrows():
        codes = r.get("region_codes") or ["ALL"]
        if isinstance(codes, str):
            codes = [c for c in codes.replace("{", "").replace("}", "").split(",") if c]
        region_name = REGION_LABELS.get(codes[0], "全區域") if codes else "全區域"
        rows.append({
            "線類型": r.get("line_type") or "MEDIA",
            "業績年月": r.get("perf_ym"),
            "平台": r.get("platform"),
            "電台/項目": r.get("media_channel") or "",
            "節目": r.get("program") or "",
            "區域": region_name,
            "素材秒數": r.get("material_seconds"),
            "總檔數": r.get("total_frames"),
            "購買檔次": r.get("purchased_slots"),
            "搭贈檔次": r.get("bonus_slots"),
            "實收金額": float(r.get("gross_amount") or 0),
            "退佣%": float(r.get("rebate_pct") or 0),
            "現折%": float(r.get("cash_discount_pct") or 0),
            "除佣實收": float(r.get("net_amount") or 0),
            "實付金額": float(r.get("cost_amount") or 0),
            "電台實付": float(r.get("channel_cost_amount") or 0),
            "聯網": bool(r.get("is_network")),
            "指定電台": bool(r.get("is_designated")),
            "備註": r.get("notes"),
        })
    return pd.DataFrame(rows, columns=EDITOR_COLS)


def _editor_to_lines(edf: pd.DataFrame, header: dict) -> list[dict]:
    """編輯表 → save_deal 用的 line dict list（名稱轉 id）。"""
    lines = []
    for _, r in edf.iterrows():
        plat = r.get("平台")
        if not plat and (r.get("實收金額") in (None, 0) or pd.isna(r.get("實收金額"))):
            continue  # 空列略過
        net_raw = r.get("除佣實收")
        net = None if (net_raw is None or (isinstance(net_raw, float) and pd.isna(net_raw)) or net_raw == 0) else net_raw
        region_code = REGION_CODE_BY_NAME.get(r.get("區域") or "全區域", "ALL")
        lines.append({
            "line_type": r.get("線類型") or "MEDIA",
            "perf_ym": r.get("業績年月"),
            "platform_id": PLATFORM_ID.get(plat),
            "platform_group": PLATFORM_GROUP.get(plat),
            "company": COMPANY_NAME.get(header.get("company_id")),
            "company_id": header.get("company_id"),
            "media_channel_id": CHANNEL_ID.get(r.get("電台/項目")),
            "program_id": PROGRAM_ID.get(r.get("節目")),
            "region_codes": [region_code],
            "material_seconds": _int(r.get("素材秒數")),
            "total_frames": _int(r.get("總檔數")),
            "purchased_slots": _int(r.get("購買檔次")),
            "bonus_slots": _int(r.get("搭贈檔次")),
            "gross_amount": _num(r.get("實收金額")),
            "rebate_pct": _num(r.get("退佣%")),
            "cash_discount_pct": _num(r.get("現折%")),
            "net_amount": net,
            "cost_amount": _num(r.get("實付金額")),
            "channel_cost_amount": _num(r.get("電台實付")),
            "is_network": bool(r.get("聯網")),
            "is_designated": bool(r.get("指定電台")),
            "notes": r.get("備註") or None,
        })
    return lines


def _lines_to_editor(lines: list[dict]) -> pd.DataFrame:
    """save 風格 line dict → 編輯表（供轉撥線加入後回填）。"""
    rows = []
    for ln in lines:
        codes = ln.get("region_codes") or ["ALL"]
        rows.append({
            "線類型": ln.get("line_type") or "MEDIA",
            "業績年月": ln.get("perf_ym"),
            "平台": PLATFORM_NAME_BY_ID.get(ln.get("platform_id")),
            "電台/項目": CHANNEL_NAME_BY_ID.get(ln.get("media_channel_id"), ""),
            "節目": PROGRAM_NAME_BY_ID.get(ln.get("program_id"), ""),
            "區域": REGION_LABELS.get(codes[0], "全區域"),
            "素材秒數": ln.get("material_seconds"),
            "總檔數": ln.get("total_frames"),
            "購買檔次": ln.get("purchased_slots"),
            "搭贈檔次": ln.get("bonus_slots"),
            "實收金額": _num(ln.get("gross_amount")),
            "退佣%": _num(ln.get("rebate_pct")),
            "現折%": _num(ln.get("cash_discount_pct")),
            "除佣實收": _num(ln.get("net_amount")),
            "實付金額": _num(ln.get("cost_amount")),
            "電台實付": _num(ln.get("channel_cost_amount")),
            "聯網": bool(ln.get("is_network")),
            "指定電台": bool(ln.get("is_designated")),
            "備註": ln.get("notes"),
        })
    return pd.DataFrame(rows, columns=EDITOR_COLS)


def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0


def _int(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------ 載入
default_contract = st.session_state.pop("edit_contract", "")
contract_no = st.text_input("合約編號", value=st.session_state.get("de_contract", default_contract))
c1, c2 = st.columns(2)
if c1.button("載入 / 新建", use_container_width=True):
    st.session_state["de_contract"] = contract_no
    hdr, lines = deals.load_deal(contract_no)
    st.session_state["de_header"] = hdr or {"contract_no": contract_no}
    st.session_state["de_editor"] = _flat_to_editor(lines)
    st.session_state["de_mode"] = "修改" if hdr else "新建"
    st.rerun()

if "de_header" not in st.session_state:
    st.info("輸入合約編號後按「載入 / 新建」開始。")
    feedback_widget("deal_entry")
    st.stop()

header = st.session_state["de_header"]
st.caption(f"目前模式：**{st.session_state.get('de_mode','新建')}**　合約：{header.get('contract_no')}")


# ------------------------------------------------------------------ Header
def _sel_id(label, table, current, colcnt):
    opts = data.options(table)
    values = [None] + [o[0] for o in opts]
    names = {None: "（無）", **{o[0]: o[1] for o in opts}}
    idx = values.index(current) if current in values else 0
    return colcnt.selectbox(label, values, index=idx, format_func=lambda v: names.get(v, str(v)))


st.subheader("合約基本資料")
h1, h2 = st.columns(2)
header["company_id"] = _sel_id("公司別 *", "company", header.get("company_id"), h1)
header["salesperson_id"] = _sel_id("業務 *", "salesperson", header.get("salesperson_id"), h2)

# 客戶搜尋
h3, h4 = st.columns(2)
with h3:
    q = st.text_input("客戶搜尋", key="de_cust_q")
    cust_df = data.customer_lookup(q) if q else data.customers().head(50)
    cust_opts = list(zip(cust_df["id"], cust_df["name"])) if cust_df is not None and not cust_df.empty else []
    cvals = [o[0] for o in cust_opts]
    cnames = {o[0]: o[1] for o in cust_opts}
    cur_cid = header.get("customer_id")
    if cur_cid and cur_cid not in cvals:
        cvals = [cur_cid] + cvals
        cnames[cur_cid] = data.customers().set_index("id")["name"].get(cur_cid, str(cur_cid))
    header["customer_id"] = st.selectbox("客戶 *", cvals or [None],
                                         index=(cvals.index(cur_cid) if cur_cid in cvals else 0) if cvals else 0,
                                         format_func=lambda v: cnames.get(v, "（請搜尋）"))
with h4:
    header["ad_name"] = st.text_input("廣告名稱", value=header.get("ad_name") or "")

with st.expander("➕ 新增客戶（找不到時）"):
    nc1, nc2, nc3 = st.columns(3)
    new_name = nc1.text_input("客戶名稱", key="de_newcust")
    new_cat = _sel_id("客戶類別", "customer_category", None, nc2)
    new_ind = _sel_id("產業別", "industry", None, nc3)
    if st.button("建立客戶"):
        if new_name.strip():
            with transaction(user["username"]) as cur:
                cur.execute("insert into customer(name, customer_category_id, industry_id) values (%s,%s,%s) returning id",
                            (new_name.strip(), new_cat, new_ind))
                header["customer_id"] = cur.fetchone()["id"]
            data.clear_cache()
            st.success(f"已建立客戶：{new_name}")
        else:
            st.warning("請輸入名稱")

h5, h6, h7 = st.columns(3)
header["group_id"] = _sel_id("組別", "business_group", header.get("group_id"), h5)
header["sales_category_id"] = _sel_id("業績類別 *", "sales_category", header.get("sales_category_id"), h6)
header["industry_id"] = _sel_id("產業別", "industry", header.get("industry_id"), h7)

h8, h9, h10 = st.columns(3)
dc_opts = ["", "直客", "廣代"]
header["category_dc"] = h8.selectbox("直客/廣代", dc_opts,
                                     index=dc_opts.index(header.get("category_dc")) if header.get("category_dc") in dc_opts else 0) or None
header["air_start"] = h9.date_input("上檔起始", value=header.get("air_start"), format="YYYY-MM-DD")
header["air_end"] = h10.date_input("上檔結束", value=header.get("air_end"), format="YYYY-MM-DD")

with st.expander("七種人員 / 簽核狀態"):
    staff_cols = st.columns(4)
    for i, (fld, lab) in enumerate([("media_staff_id", "媒體"), ("planner_staff_id", "企劃"),
                                    ("copy_staff_id", "文案"), ("assist_staff_id", "協辦"),
                                    ("cs_staff_id", "客服"), ("billing_staff_id", "請款"),
                                    ("closing_staff_id", "結案")]):
        header[fld] = _sel_id(lab, "staff", header.get(fld), staff_cols[i % 4])
    sc = st.columns(3)
    header["is_original_received"] = sc[0].checkbox("正本", value=bool(header.get("is_original_received")))
    header["is_copy_received"] = sc[1].checkbox("影本", value=bool(header.get("is_copy_received")))
    header["is_sales_signed"] = sc[2].checkbox("業務簽名", value=bool(header.get("is_sales_signed")))

header["notes"] = st.text_area("備註", value=header.get("notes") or "")
st.session_state["de_header"] = header

# ------------------------------------------------------------------ Lines
st.subheader("業績線")
edited = st.data_editor(
    st.session_state["de_editor"], num_rows="dynamic", use_container_width=True, key="de_editor_widget",
    column_config={
        "線類型": st.column_config.SelectboxColumn(options=["MEDIA", "PRODUCTION", "INTERCOMPANY"], required=True),
        "業績年月": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "平台": st.column_config.SelectboxColumn(options=PLATFORM_NAMES),
        "電台/項目": st.column_config.SelectboxColumn(options=CHANNEL_NAMES),
        "節目": st.column_config.SelectboxColumn(options=PROGRAM_NAMES),
        "區域": st.column_config.SelectboxColumn(options=REGION_DISPLAY),
        "實收金額": st.column_config.NumberColumn(format="%d"),
        "除佣實收": st.column_config.NumberColumn(format="%d", help="留空自動 = 實收×(1−退佣%)×(1−現折%)"),
        "實付金額": st.column_config.NumberColumn(format="%d"),
        "電台實付": st.column_config.NumberColumn(format="%d"),
        "聯網": st.column_config.CheckboxColumn(),
        "指定電台": st.column_config.CheckboxColumn(),
    },
)
st.session_state["de_editor"] = edited

# ------------------------------------------------------------------ 動作
b1, b2, b3 = st.columns(3)

if b2.button("🔁 產生子公司轉撥線", use_container_width=True):
    lines = _editor_to_lines(edited, header)
    all_lines, new_ic = deals.generate_intercompany(lines, data.intercompany_rules())
    if not new_ic:
        st.info("沒有需要產生的轉撥線（非子公司線、或已存在轉撥線）。")
    else:
        prev = pd.DataFrame([{"組別": r["group_name"], "客戶": r["customer_name"],
                              "轉撥金額": r["net_amount"], "折數": r["_rate"]} for r in new_ic])
        st.write("將新增以下轉撥線（原線實付會設為同額）：")
        st.dataframe(prev, hide_index=True, use_container_width=True)
        st.session_state["de_pending_ic"] = all_lines

if st.session_state.get("de_pending_ic") and st.button("✅ 確認加入轉撥線"):
    st.session_state["de_editor"] = _lines_to_editor(st.session_state.pop("de_pending_ic"))
    st.success("已加入轉撥線到下方表格，請確認後按「儲存」。")
    st.rerun()

with b3:
    copy_no = st.text_input("複製來源合約", key="de_copy_no", placeholder="輸入合約編號")
    if st.button("📋 複製內容", use_container_width=True):
        _, src = deals.load_deal(copy_no)
        if src is None or src.empty:
            st.warning("找不到來源合約")
        else:
            st.session_state["de_editor"] = _flat_to_editor(src)
            st.success("已複製，請調整後儲存。")
            st.rerun()

# 儲存
if b1.button("💾 儲存", type="primary", use_container_width=True):
    errors = []
    if not header.get("contract_no"):
        errors.append("缺合約編號")
    for fld, lab in [("company_id", "公司別"), ("customer_id", "客戶"), ("salesperson_id", "業務"),
                     ("sales_category_id", "業績類別")]:
        if not header.get(fld):
            errors.append(f"缺{lab}")
    lines = _editor_to_lines(edited, header)
    if not lines:
        errors.append("至少要有一條業績線")
    limit = (date.today().replace(day=1) + relativedelta(months=12))
    neg = False
    for i, ln in enumerate(lines, 1):
        if not ln.get("perf_ym"):
            errors.append(f"第{i}列缺業績年月")
        elif ln["perf_ym"] > limit:
            errors.append(f"第{i}列業績年月不可晚於今天+12月")
        if _num(ln.get("gross_amount")) < 0 or _num(ln.get("cost_amount")) < 0:
            neg = True
    if errors:
        st.error("；".join(errors))
    else:
        if neg:
            st.warning("有負數金額（允許，請確認為舊資料調整）。")
        try:
            deal_id, n = deals.save_deal(header, lines, user["username"])
            st.session_state["de_mode"] = "修改"
            _, saved = deals.load_deal(header["contract_no"])
            tot = deals.deal_totals(saved)
            st.success(f"已儲存，稽核以 deal #{deal_id} 記錄（{n} 條線）。")
            m = st.columns(4)
            m[0].metric("實收", f"{tot['gross_amount']:,.0f}")
            m[1].metric("除佣", f"{tot['net_amount']:,.0f}")
            m[2].metric("實付", f"{tot['cost_amount']:,.0f}")
            m[3].metric("毛利", f"{tot['gross_profit']:,.0f}")
        except Exception as e:  # noqa: BLE001
            st.error(f"儲存失敗：{e}")

feedback_widget("deal_entry")
