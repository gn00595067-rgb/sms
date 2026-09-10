"""P6 發票與銷帳 invoices.py — 應收列表、發票編輯、銷帳、批次標記已結清。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core.auth import require_role
from core.finance import (add_writeoff, deal_defaults_for_invoice, list_ar,
                          load_invoice, mark_settled, save_invoice, writeoffs_for)
from core.ui import feedback_widget, page_header, show_df

user = require_role("MEDIA", "FINANCE", "EXEC")
can_edit = user["role"] in ("FINANCE", "EXEC")

page_header("發票與銷帳", "應收帳款、發票開立與銷帳。媒體人員為唯讀。")

AR_COLS = ["invoice_id", "invoice_no", "contract_no", "customer", "salesperson", "ad_name",
           "payment_method", "invoice_issued_on", "expected_cash_on", "amount_total",
           "received_amount", "outstanding_amount", "overdue_days", "is_settled"]

tab_ar, tab_edit, tab_wo, tab_settle = st.tabs(["應收帳款", "發票開立/編輯", "銷帳登錄", "批次標記已結清"])

# --------------------------------------------------------------- 應收列表
with tab_ar:
    only_open = st.checkbox("只看未結清", value=True, key="ar_only_open")
    df = list_ar(only_open=only_open)
    c1, c2, c3 = st.columns(3)
    f_cust = c1.text_input("客戶（模糊）", key="ar_cust")
    f_sp = c2.text_input("業務（模糊）", key="ar_sp")
    f_no = c3.text_input("合約編號（模糊）", key="ar_no")
    if not df.empty:
        if f_cust.strip():
            df = df[df["customer"].fillna("").str.contains(f_cust.strip(), case=False)]
        if f_sp.strip():
            df = df[df["salesperson"].fillna("").str.contains(f_sp.strip(), case=False)]
        if f_no.strip():
            df = df[df["contract_no"].fillna("").str.contains(f_no.strip(), case=False)]
    st.caption(f"共 {len(df)} 筆；未收合計 "
               f"{int(pd.to_numeric(df['outstanding_amount'], errors='coerce').fillna(0).sum()):,}" if not df.empty else "共 0 筆")
    show_df(df, cols=[c for c in AR_COLS if not df.empty and c in df.columns])

# --------------------------------------------------------------- 發票編輯
with tab_edit:
    if not can_edit:
        st.caption("唯讀角色不可開立或編輯發票")
    else:
        mode = st.radio("模式", ["新增發票", "編輯既有發票"], horizontal=True, key="inv_mode")
        existing = None
        if mode == "編輯既有發票":
            inv_id = st.number_input("發票 ID（invoice_id，見應收列表）", min_value=1, step=1, key="inv_id")
            if st.button("載入", key="load_inv"):
                st.session_state["_inv"] = load_invoice(int(inv_id))
            existing = st.session_state.get("_inv")
            if existing:
                st.caption(f"編輯發票 #{existing['id']}（{existing.get('invoice_no') or '無號'}）")

        contract_no = st.text_input("合約編號", (existing or {}).get("contract_no") or "", key="inv_contract")
        defaults = deal_defaults_for_invoice(contract_no) if contract_no.strip() else None
        if defaults:
            st.caption(f"帶出合約：客戶#{defaults.get('customer_id')}／業務#{defaults.get('salesperson_id')}／{defaults.get('ad_name') or ''}")

        base = existing or {}
        with st.form("inv_form"):
            c1, c2 = st.columns(2)
            customer_title = c1.text_input("抬頭", base.get("customer_title") or "")
            customer_tax_id = c2.text_input("統編", base.get("customer_tax_id") or "")
            payment_method = c1.selectbox("收款方式", ["", "匯款", "支票", "收現"],
                                          index=["", "匯款", "支票", "收現"].index(base.get("payment_method"))
                                          if base.get("payment_method") in ["匯款", "支票", "收現"] else 0)
            invoice_no = c2.text_input("發票號碼", base.get("invoice_no") or "")
            ad_income = c1.number_input("廣告收入", value=float(base.get("ad_income") or 0), step=1000.0)
            production_income = c2.number_input("製作收入", value=float(base.get("production_income") or 0), step=1000.0)
            allowance = c1.number_input("折讓單金額", value=float(base.get("allowance_note_amount") or 0), step=1000.0)
            issued = c2.date_input("開立日", base.get("invoice_issued_on") or date.today())
            due = c1.date_input("應交付日", base.get("invoice_due_on") or date.today())
            expected = c2.date_input("預定兌現日", base.get("expected_cash_on") or date.today())
            notes = st.text_area("備註", base.get("notes") or "")
            submitted = st.form_submit_button("儲存發票")
        if submitted:
            data = {
                "deal_id": (defaults or {}).get("deal_id"),
                "contract_no": contract_no.strip() or None,
                "customer_id": (defaults or {}).get("customer_id") or base.get("customer_id"),
                "customer_title": customer_title or None, "customer_tax_id": customer_tax_id or None,
                "salesperson_id": (defaults or {}).get("salesperson_id") or base.get("salesperson_id"),
                "group_id": (defaults or {}).get("group_id") or base.get("group_id"),
                "ad_name": (defaults or {}).get("ad_name") or base.get("ad_name"),
                "payment_method": payment_method or None,
                "ad_income": ad_income, "production_income": production_income,
                "allowance_note_amount": allowance, "invoice_no": invoice_no or None,
                "invoice_issued_on": issued, "invoice_due_on": due, "expected_cash_on": expected,
                "settled_manually": base.get("settled_manually", False), "settled_note": base.get("settled_note"),
                "notes": notes or None,
            }
            new_id = save_invoice(data, user["username"], invoice_id=base.get("id"))
            st.success(f"已儲存發票 #{new_id}")
            st.session_state.pop("_inv", None)

# --------------------------------------------------------------- 銷帳
with tab_wo:
    if not can_edit:
        st.caption("唯讀角色不可登錄銷帳")
    else:
        inv_id = st.number_input("發票 ID", min_value=1, step=1, key="wo_inv_id")
        ar = list_ar(where_sql="invoice_id = %s", params=(int(inv_id),))
        if ar.empty:
            st.info("查無此發票")
        else:
            r = ar.iloc[0]
            st.metric("未收餘額", f"{int(r['outstanding_amount']):,}")
            st.write(f"客戶：{r['customer']}｜合約：{r['contract_no']}｜帳款：{int(r['amount_total']):,}")
            hist = writeoffs_for(int(inv_id))
            st.caption("銷帳歷史")
            show_df(hist if not hist.empty else hist)
            with st.form("wo_form"):
                c1, c2 = st.columns(2)
                received_on = c1.date_input("收款日", date.today())
                received_amount = c2.number_input("金額", min_value=0.0, step=1000.0)
                method = c1.selectbox("方式", ["", "匯款", "支票", "收現"])
                bank_ref = c2.text_input("匯款末五碼 / 支票號")
                remark = st.text_input("備註")
                ok = st.form_submit_button("新增銷帳")
            if ok:
                if received_amount <= 0:
                    st.warning("金額需大於 0")
                else:
                    add_writeoff(int(inv_id), {
                        "received_on": received_on, "received_amount": received_amount,
                        "method": method or None, "bank_ref": bank_ref or None, "remark": remark or None,
                    }, user["username"])
                    st.success("已新增銷帳")
                    st.rerun()

# --------------------------------------------------------------- 批次結清
with tab_settle:
    if not can_edit:
        st.caption("唯讀角色不可標記結清")
    else:
        st.info("舊資料的銷帳幾乎沒登錄，可對已實際收款的舊發票批次標記已結清。")
        df = list_ar(only_open=True)
        if df.empty:
            st.success("目前沒有未結清發票")
        else:
            c1, c2, c3 = st.columns(3)
            f_cust = c1.text_input("客戶（模糊）", key="settle_cust")
            f_no = c2.text_input("合約編號（模糊）", key="settle_no")
            older_than = c3.date_input("僅列開立日早於", date.today(), key="settle_before")
            sel = df.copy()
            if f_cust.strip():
                sel = sel[sel["customer"].fillna("").str.contains(f_cust.strip(), case=False)]
            if f_no.strip():
                sel = sel[sel["contract_no"].fillna("").str.contains(f_no.strip(), case=False)]
            sel = sel[pd.to_datetime(sel["invoice_issued_on"], errors="coerce").dt.date <= older_than]
            sel = sel.copy()
            sel.insert(0, "選取", False)
            edited = st.data_editor(sel[["選取", "invoice_id", "invoice_no", "contract_no", "customer",
                                         "amount_total", "outstanding_amount"]],
                                    hide_index=True, use_container_width=True, key="settle_editor")
            note = st.text_input("結清備註", "舊資料批次結清", key="settle_note")
            chosen = edited[edited["選取"]]["invoice_id"].tolist() if not edited.empty else []
            st.caption(f"已選 {len(chosen)} 張")
            if st.button("標記已結清", disabled=not chosen):
                n = mark_settled([int(x) for x in chosen], note, user["username"])
                st.success(f"已標記 {n} 張為已結清")
                st.rerun()

feedback_widget("invoices")
