"""
uimode.py — 介面顯示模式開關（本階段測試用）

ANALYSIS_ONLY = True 時，側欄只顯示「分析」頁群（客戶 / 業務 / 銷售 / 公司分析 + 客戶頁 / 業務頁）；
其餘頁面（首頁 / 登打 / 查詢 / 主檔 / 發票 / 報表 / 獎金 / 管理…）隱藏。
測試完成後把 ANALYSIS_ONLY 改回 False 即恢復完整選單，不需動其他程式。

跨頁連結（如 業務頁 → 報表中心 / 獎金、銷售分析 → 業績登打）會用 page_available() 判斷
目標頁是否在選單內，避免連到被隱藏的頁面而報錯。
"""
from __future__ import annotations

ANALYSIS_ONLY = False

# 分析頁群（含兩個下鑽頁，下鑽靠 st.switch_page，必須保持註冊）
ANALYSIS_KEYS = {
    "analysis_customer", "analysis_salesperson", "analysis_sales", "analysis_company",
    "customer_detail", "salesperson_detail",
}


def page_available(key: str) -> bool:
    """該頁在目前模式下是否出現在導覽（可被 switch_page / page_link 指向）。"""
    return (not ANALYSIS_ONLY) or key in ANALYSIS_KEYS
