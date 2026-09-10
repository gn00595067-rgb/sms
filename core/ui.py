"""
ui.py — 共用 UI 元件：頁首、問題回報側欄、篩選列、表格顯示
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db import transaction  # noqa: E402

from core import data
from core.auth import current_user
from core.format import display_frame, ym_text

LINE_TYPES = [("MEDIA", "媒體"), ("PRODUCTION", "製作"), ("INTERCOMPANY", "轉撥")]


def page_header(title: str, help_text: str | None = None) -> None:
    st.title(title)
    if help_text:
        st.caption(help_text)


def show_df(df, cols=None, **kwargs) -> None:
    """統一表格顯示（中文標籤 + 金額格式 + 右對齊）。"""
    kwargs.setdefault("use_container_width", True)
    kwargs.setdefault("hide_index", True)
    if df is None or len(df) == 0:
        st.info("查無資料")
        return
    st.dataframe(display_frame(df, cols=cols), **kwargs)


# ------------------------------------------------------------------ 問題回報
def feedback_widget(page: str) -> None:
    """每一頁側欄的「回報問題」展開區（MVP 迭代核心）。"""
    user = current_user()
    with st.sidebar:
        with st.expander("💬 回報問題", expanded=False):
            with st.form(f"feedback_{page}", clear_on_submit=True):
                category = st.selectbox("類別", ["BUG", "建議", "欄位不對", "報表", "其他"], key=f"fb_cat_{page}")
                message = st.text_area("說明", placeholder="請描述問題或建議…", key=f"fb_msg_{page}")
                submitted = st.form_submit_button("送出")
            if submitted:
                if not message.strip():
                    st.warning("請輸入說明")
                else:
                    uname = user["username"] if user else None
                    with transaction(uname) as cur:
                        cur.execute(
                            "insert into feedback(user_name, page, category, message) values (%s,%s,%s,%s)",
                            (uname, page, category, message.strip()),
                        )
                    st.success("已送出，謝謝回報！")


# ------------------------------------------------------------------ 篩選列
def _selectbox_id(label: str, table: str, key: str, *, all_label: str = "全部"):
    opts = data.options(table)
    values = [None] + [o[0] for o in opts]
    names = {None: all_label, **{o[0]: o[1] for o in opts}}
    return st.selectbox(label, values, format_func=lambda v: names.get(v, str(v)), key=key)


def filters_bar(spec: list[str], key_prefix: str = "flt") -> dict:
    """
    依 spec（欄位名清單）畫出篩選器，回傳 dict。
    支援：ym_range, company, platform_group, platform, region, salesperson,
          business_group, sales_category, customer, industry, line_type, contract_no
    """
    out: dict = {}
    months = data.months()  # 新到舊
    with st.container():
        if "ym_range" in spec:
            c1, c2 = st.columns(2)
            if months:
                default_to = months[0]
                default_from = months[min(len(months) - 1, 11)]  # 最近 12 個月
                labels = {m: ym_text(m) for m in months}
                out["ym_from"] = c1.selectbox("業績年月（起）", months, index=months.index(default_from),
                                              format_func=lambda m: labels[m], key=f"{key_prefix}_ymf")
                out["ym_to"] = c2.selectbox("業績年月（迄）", months, index=months.index(default_to),
                                            format_func=lambda m: labels[m], key=f"{key_prefix}_ymt")
            else:
                today = date.today().replace(day=1)
                out["ym_from"] = c1.date_input("業績年月（起）", today - relativedelta(months=11), key=f"{key_prefix}_ymf")
                out["ym_to"] = c2.date_input("業績年月（迄）", today, key=f"{key_prefix}_ymt")

        row = [s for s in spec if s not in ("ym_range", "contract_no")]
        # 每行三個
        for i in range(0, len(row), 3):
            cols = st.columns(3)
            for col, field in zip(cols, row[i:i + 3]):
                with col:
                    if field == "company":
                        out["company"] = _selectbox_id("公司別", "company", f"{key_prefix}_company")
                    elif field == "platform_group":
                        pgs = data.platform_groups()
                        out["platform_group"] = st.selectbox("平台歸類", [None] + pgs,
                                                             format_func=lambda v: "全部" if v is None else v,
                                                             key=f"{key_prefix}_pg")
                    elif field == "platform":
                        out["platform"] = _selectbox_id("平台", "platform", f"{key_prefix}_platform")
                    elif field == "region":
                        rs = data.regions()
                        codes = [None] + (rs["code"].tolist() if not rs.empty else [])
                        rnames = {None: "全部", **({r["code"]: r["name"] for _, r in rs.iterrows()} if not rs.empty else {})}
                        out["region"] = st.selectbox("區域", codes, format_func=lambda v: rnames.get(v, str(v)),
                                                     key=f"{key_prefix}_region")
                    elif field == "salesperson":
                        out["salesperson"] = _selectbox_id("業務", "salesperson", f"{key_prefix}_sp")
                    elif field == "business_group":
                        out["business_group"] = _selectbox_id("組別", "business_group", f"{key_prefix}_bg")
                    elif field == "sales_category":
                        out["sales_category"] = _selectbox_id("業績類別", "sales_category", f"{key_prefix}_sc")
                    elif field == "industry":
                        out["industry"] = _selectbox_id("產業別", "industry", f"{key_prefix}_ind")
                    elif field == "customer":
                        out["customer"] = st.text_input("客戶（模糊）", key=f"{key_prefix}_cust")
                    elif field == "line_type":
                        vals = [None] + [t[0] for t in LINE_TYPES]
                        lnames = {None: "全部", **dict(LINE_TYPES)}
                        out["line_type"] = st.selectbox("線類型", vals, format_func=lambda v: lnames.get(v, str(v)),
                                                        key=f"{key_prefix}_lt")
        if "contract_no" in spec:
            out["contract_no"] = st.text_input("合約編號", key=f"{key_prefix}_contract")
    return out


def confirm_dialog(key: str, label: str = "我確認") -> bool:
    """二次確認：回傳勾選狀態。"""
    return st.checkbox(label, key=key)
