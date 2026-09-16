"""
app.py — 入口：登入 → st.navigation 依角色組頁面

角色：MEDIA 媒體 / FINANCE 財務 / EXEC 高階 / SALES 業務（只看自己）。
權限矩陣見 CLAUDE_CODE_TASK.md 附錄 A。
"""
from __future__ import annotations

import streamlit as st

from core.auth import current_user, is_logged_in, login, logout
from core.format import ROLE_LABELS
from core.uimode import ANALYSIS_ONLY

st.set_page_config(page_title="業績系統", page_icon="📊", layout="wide")

# 每個頁面 (檔案, 標題, 圖示) 與可見角色
PAGES = {
    "home":        ("pages_app/home.py",        "首頁",        "🏠", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "deal_entry":  ("pages_app/deal_entry.py",  "業績登打",    "✍️", ["MEDIA", "EXEC"]),
    "deal_search": ("pages_app/deal_search.py", "業績查詢",    "🔍", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "customers":   ("pages_app/customers.py",   "客戶主檔",    "🏢", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "masters":     ("pages_app/masters.py",     "主檔維護",    "🗂️", ["MEDIA", "EXEC"]),
    "invoices":    ("pages_app/invoices.py",    "發票與銷帳",  "💳", ["MEDIA", "FINANCE", "EXEC"]),
    "analysis_customer":    ("pages_app/analysis_customer.py",    "客戶分析", "👥", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "analysis_salesperson": ("pages_app/analysis_salesperson.py", "業務分析", "🧑‍💼", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "analysis_sales":       ("pages_app/analysis_sales.py",       "銷售分析", "🧾", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "analysis_company":     ("pages_app/analysis_company.py",     "公司分析", "🏛️", ["MEDIA", "FINANCE", "EXEC"]),
    "customer_detail":      ("pages_app/customer_detail.py",      "客戶頁",   "🔎", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "salesperson_detail":   ("pages_app/salesperson_detail.py",   "業務頁",   "🧑", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "reports":     ("pages_app/reports.py",     "報表中心",    "📈", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
    "bonus":       ("pages_app/bonus.py",       "業務獎金",    "🎯", ["EXEC", "SALES"]),
    "feedback":    ("pages_app/feedback.py",    "問題回報清單", "📮", ["EXEC"]),
    "audit":       ("pages_app/audit.py",       "稽核紀錄",    "🕵️", ["EXEC"]),
    "users":       ("pages_app/users.py",       "使用者管理",  "👥", ["EXEC"]),
    "account":     ("pages_app/account.py",     "修改密碼",    "🔑", ["MEDIA", "FINANCE", "EXEC", "SALES"]),
}

# 導覽分組
GROUPS = {
    "業務作業": ["home", "deal_entry", "deal_search", "customers"],
    "財務": ["invoices"],
    "分析": ["analysis_customer", "analysis_salesperson", "analysis_sales", "analysis_company",
             "customer_detail", "salesperson_detail"],
    "報表": ["reports", "bonus"],
    "管理": ["masters", "feedback", "audit", "users"],
    "帳號": ["account"],
}


def _login_screen() -> None:
    st.title("📊 業績系統")
    st.caption("聲活 / 東吳 / 鉑霖 / 瑞迪 — 業績統計 MVP")
    with st.form("login"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        ok = st.form_submit_button("登入", use_container_width=True)
    if ok:
        user = login(username, password)
        if user:
            st.rerun()
        else:
            st.error("帳號或密碼錯誤，或帳號已停用")
    st.info("首次登入請用管理者提供的初始密碼，登入後系統會要求你立即更改。")


def _build_pages(role: str, must_change: bool) -> list:
    if must_change:
        # 只能看修改密碼頁
        f, title, icon, _ = PAGES["account"]
        return [st.Page(f, title=title, icon=icon, default=True)]
    # 本階段測試：只顯示「分析」頁群（見 core/uimode.py）
    groups = {"分析": GROUPS["分析"]} if ANALYSIS_ONLY else GROUPS
    default_key = "analysis_customer" if ANALYSIS_ONLY else "home"
    grouped = {}
    for group, keys in groups.items():
        pages = []
        for k in keys:
            f, title, icon, roles = PAGES[k]
            if role in roles:
                pages.append(st.Page(f, title=title, icon=icon, default=(k == default_key)))
        if pages:
            grouped[group] = pages
    return grouped


def main() -> None:
    if not is_logged_in():
        _login_screen()
        return

    user = current_user()
    with st.sidebar:
        st.markdown(f"**{user['display_name']}**")
        st.caption(f"角色：{ROLE_LABELS.get(user['role'], user['role'])}")
        if st.button("登出", use_container_width=True):
            logout()
            st.rerun()

    if user.get("must_change_password"):
        st.warning("為了安全，請先修改預設密碼才能使用其他功能。")

    pages = _build_pages(user["role"], user.get("must_change_password", False))
    nav = st.navigation(pages)
    nav.run()


main()
