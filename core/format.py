"""
format.py — 顯示格式化與中文標籤

規則（CLAUDE_CODE_TASK §1.8）：
  - 金額：千分位、無小數
  - 比率：百分比一位小數
  - 年月：2026/09
所有欄位中文標籤集中在 LABELS（附錄 C）。
"""
from __future__ import annotations

import math
from datetime import date, datetime

# ---------------------------------------------------------------------
# 附錄 C：欄位中文標籤
# ---------------------------------------------------------------------
LABELS = {
    "contract_no": "合約編號", "line_no": "線號", "line_type": "線類型", "perf_ym_text": "業績年月",
    "perf_year": "年", "perf_quarter": "季",
    "blink_ym": "BLINK認列年月", "order_ym": "進單年月", "company": "公司別", "customer": "客戶名稱",
    "legacy_customer_name": "原始客戶名稱",
    "ad_name": "廣告名稱", "salesperson": "業務", "business_group": "組別", "sales_category": "業績類別",
    "sales_item": "業績項目",
    "recognition_ratio": "認定比例", "customer_category": "客戶類別", "industry": "產業別", "platform": "平台",
    "platform_group": "平台歸類",
    "media_channel": "電台/項目", "program": "節目", "region": "區域", "region_text": "區域",
    "is_network": "聯網", "is_designated": "指定電台",
    "air_start": "上檔起始", "air_end": "上檔結束", "gross_amount": "實收金額", "rebate_pct": "退佣%",
    "cash_discount_pct": "現折%",
    "net_amount": "除佣實收", "cost_amount": "實付金額", "channel_cost_amount": "電台實付",
    "media_benefit": "媒體效益",
    "gross_profit": "毛利", "margin_pct": "毛利率", "recognized_amount": "認定業績",
    "material_seconds": "素材秒數", "total_frames": "總檔數",
    "total_seconds": "總秒數", "purchased_slots": "購買檔次", "bonus_slots": "搭贈檔次",
    "bonus_amount": "搭贈金額", "blink_slots": "BLINK檔數",
    "line_count": "筆數", "deal_count": "合約數", "layer1_revenue": "第一層收入",
    "layer1_cost": "第一層成本", "layer1_profit": "第一層毛利",
    "layer2_revenue": "第二層收入", "layer2_direct_cost": "第二層直接成本", "fixed_cost": "固定成本",
    "layer2_profit": "第二層毛利",
    "invoice_no": "發票號碼", "customer_title": "抬頭", "payment_method": "收款方式",
    "invoice_issued_on": "開立日", "invoice_due_on": "應交付日",
    "expected_cash_on": "預定兌現日", "amount_total": "帳款金額", "allowance_note_amount": "折讓單金額",
    "received_amount": "已收金額",
    "last_received_on": "最近收款日", "outstanding_amount": "未收金額", "is_settled": "已結清",
    "overdue_days": "逾期天數",
    "bonus_pct": "獎金%", "threshold_amount": "門檻", "rule_note": "規則備註", "rank_in_company": "名次",
    "share_in_company": "佔比",
    "low_margin_handled": "低毛利已處理", "low_margin_reason": "低毛利原因", "notes": "備註",
    "created_by": "建立者", "updated_at": "更新時間",
    # 補充（頁面會用到，但不在附錄 C）
    "region_code": "區域代碼", "settled_manually": "手動結清", "category_dc": "直客/廣代",
    "invoice_delivered_on": "發票交付日", "settled_note": "結清備註", "region_codes": "區域",
    # ---- 附錄 C 補充（CLAUDE_CODE_TASK_2 §3.9 分析報表）----
    "ext_net": "除佣實收", "ext_gross": "實收金額", "booked_profit": "帳上毛利",
    "group_profit": "集團毛利", "net_profit": "集團淨利", "ic_add_back": "轉撥加回",
    "ic_in": "收到轉撥", "ic_out": "轉撥金額", "booked_cost": "實付", "group_cost": "集團成本",
    "production_cost": "製作費", "alloc_fixed_cost": "分攤固定成本", "company_net_profit": "公司淨利",
    "booked_margin": "帳上毛利率", "group_margin": "集團毛利率", "net_margin": "集團淨利率",
    "status": "狀態", "abc_tier": "ABC", "freq_tier": "頻率", "months_since_last": "距上次交易(月)",
    "yoy_pct": "同期%", "share": "佔比", "cum_share": "累計佔比", "top3_share": "前3大依賴度",
    "top1_share": "最大客戶依賴度", "new_customers": "新客數", "avg_deal": "平均單筆",
    "target_amount": "目標", "actual": "進單", "remaining": "待追", "achieved_pct": "達成率",
    "achieved_pct_with_forecast": "加預估後達成率", "required_monthly": "每月需達",
    "forecast_amount": "預估", "forecast_weighted": "加權預估", "booked_plus_forecast": "進單＋預估",
    "barter_net": "交換", "is_house": "公司戶", "size_bucket": "金額級距", "strategy_hint": "策略提示",
    "net_cp": "企頻", "net_fresh": "新鮮視", "net_radio": "廣播", "net_other": "其他",
    "deals": "訂單數", "active_months": "活躍月數", "customers": "客戶數", "net_per_customer": "客均產值",
    "main_salesperson": "主要業務", "main_company": "主要公司", "main_group": "組別",
    "main_platform_group": "主要平台", "platform_groups": "平台組合", "rank_in_year": "名次",
    "top_customer": "最大客戶", "period_label": "期間", "months_left": "剩餘月份",
    "active_salespeople": "業務人數", "perf_ym_text": "業績年月", "low_margin_reason": "低毛利原因",
}

# ---------------------------------------------------------------------
# 顏色（CLAUDE_CODE_TASK_2 §1.3）— 所有 plotly 圖一律從這裡拿色，不用 plotly 預設色。
# 公司藍綠橘沿用老闆儀表板；平台歸類同色系深淺；狀態沿用公司色；紅黃綠只用在警示。
# ---------------------------------------------------------------------
COLORS = {
    # 公司別
    "company": {"聲活": "#2a78d6", "東吳": "#1baf7a", "鉑霖": "#eb6834", "瑞迪": "#4a3aa7"},
    # 平台歸類
    "platform_group": {"企頻": "#4a3aa7", "新鮮視": "#6353bc", "廣播": "#8377cf", "其他": "#a49bdf"},
    # 客戶狀態
    "status": {"新客": "#1baf7a", "回流": "#eb6834", "既有": "#2a78d6"},
    # 警示
    "alert": {"red": "#d03b3b", "yellow": "#fab219", "green": "#0ca30c"},
    # 通用強調色（與聲活同藍）
    "accent": "#2a78d6", "accent2": "#6da7ec", "accent3": "#b7d3f6",
}

# 平台歸類固定順序（表格與堆疊圖用）
PLATFORM_GROUP_ORDER = ["企頻", "新鮮視", "廣播", "其他"]


def company_color(name: str) -> str:
    return COLORS["company"].get(name, COLORS["accent"])


def platform_group_color(name: str) -> str:
    return COLORS["platform_group"].get(name, COLORS["platform_group"]["其他"])


def status_color(name: str) -> str:
    return COLORS["status"].get(name, "#8b95a3")


# 區域代碼 → 中文（core/deals 與頁面顯示用）
REGION_LABELS = {"ALL": "全區域", "N": "北區", "C": "中區", "S": "南區"}

# 線類型中文
LINE_TYPE_LABELS = {"MEDIA": "媒體", "PRODUCTION": "製作", "INTERCOMPANY": "轉撥"}

# 角色中文
ROLE_LABELS = {"MEDIA": "媒體人員", "FINANCE": "財務", "EXEC": "高階管理", "SALES": "業務"}

# feedback 狀態中文
FEEDBACK_STATUS_LABELS = {"NEW": "新進", "DOING": "處理中", "DONE": "已完成", "WONTFIX": "不處理"}


def label(col: str) -> str:
    """欄位英文名 → 中文標籤（找不到就原樣回傳）。"""
    return LABELS.get(col, col)


# ---------------------------------------------------------------------
# 值格式化
# ---------------------------------------------------------------------
def _is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


def money(v) -> str:
    """金額：千分位、無小數。None → ''。"""
    if _is_missing(v):
        return ""
    try:
        return f"{round(float(v)):,}"
    except (ValueError, TypeError):
        return str(v)


def pct(v, *, already_ratio: bool = True) -> str:
    """
    比率 → 百分比一位小數。
    already_ratio=True：v 是 0.16 這種比值（view 的 margin_pct / share_in_company）。
    already_ratio=False：v 已是百分比數字（10 = 10%，如 rebate_pct）。
    """
    if _is_missing(v):
        return ""
    try:
        x = float(v)
    except (ValueError, TypeError):
        return str(v)
    if already_ratio:
        x *= 100
    return f"{x:.1f}%"


def ym_text(v) -> str:
    """date / datetime / 'YYYY-MM-DD' → '2026/09'。"""
    if _is_missing(v):
        return ""
    if isinstance(v, (date, datetime)):
        return f"{v.year}/{v.month:02d}"
    s = str(v)
    # 可能是 '2026-09-01' 或 '2026/09'
    s = s.replace("-", "/")
    parts = s.split("/")
    if len(parts) >= 2 and parts[0].isdigit():
        return f"{int(parts[0])}/{int(parts[1]):02d}"
    return s


def date_text(v) -> str:
    """date → '2026-09-01'。None → ''。"""
    if _is_missing(v):
        return ""
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def region_text(codes) -> str:
    """['N','C'] → '北區,中區'。"""
    if _is_missing(codes):
        return ""
    if isinstance(codes, str):
        codes = [c for c in codes.replace("{", "").replace("}", "").split(",") if c]
    return ",".join(REGION_LABELS.get(c, c) for c in codes)


# ---------------------------------------------------------------------
# 欄位顯示型別（給表格自動格式化用）
# ---------------------------------------------------------------------
MONEY_COLS = {
    "gross_amount", "net_amount", "cost_amount", "channel_cost_amount", "media_benefit",
    "gross_profit", "recognized_amount", "bonus_amount", "layer1_revenue", "layer1_cost",
    "layer1_profit", "layer2_revenue", "layer2_direct_cost", "fixed_cost", "layer2_profit",
    "amount_total", "allowance_note_amount", "received_amount", "outstanding_amount",
    "threshold_amount", "ad_income", "production_income",
    # 分析報表
    "ext_net", "ext_gross", "booked_profit", "group_profit", "net_profit", "ic_add_back",
    "ic_in", "ic_out", "booked_cost", "group_cost", "production_cost", "alloc_fixed_cost",
    "company_net_profit", "avg_deal", "target_amount", "actual", "remaining", "amount",
    "forecast_amount", "forecast_weighted", "booked_plus_forecast", "booked_net", "barter_net",
    "required_monthly", "net_per_customer", "net_cp", "net_fresh", "net_radio", "net_other",
    "top3_net", "top1_net", "prev_year_net", "prev_net",
}
RATIO_PCT_COLS = {"margin_pct", "share_in_company", "recognition_ratio", "rate",
                  "booked_margin", "group_margin", "net_margin", "share", "cum_share",
                  "top3_share", "top1_share", "yoy_pct", "achieved_pct",
                  "achieved_pct_with_forecast", "target_pct"}   # 0.16 → 16.0%
PERCENT_NUM_COLS = {"rebate_pct", "cash_discount_pct", "bonus_pct", "probability"}  # 10 → 10.0%
INT_COLS = {
    "line_count", "deal_count", "total_frames", "total_seconds", "material_seconds",
    "purchased_slots", "bonus_slots", "blink_slots", "daling_count", "overdue_days",
    "rank_in_company", "line_no", "perf_year", "perf_quarter",
    "deals", "active_months", "customers", "active_salespeople", "new_customers",
    "salesperson_count", "months_since_last", "rank_in_year", "months_left",
}
YM_COLS = {"perf_ym", "order_ym", "blink_ym"}
DATE_COLS = {"air_start", "air_end", "invoice_issued_on", "invoice_due_on", "expected_cash_on",
             "invoice_delivered_on", "last_received_on", "payment_received_on", "planned_invoice_on",
             "received_on", "ym_from", "ym_to"}


def display_frame(df, cols=None):
    """
    回傳一個 pandas Styler：欄位改中文標籤、金額千分位、比率百分比、數字右對齊。
    直接丟給 st.dataframe(display_frame(df))。
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return df
    if cols is not None:
        cols = [c for c in cols if c in df.columns]
        df = df[cols]
    df = df.copy()

    # ym / date / region 欄位先轉成文字（避免 Styler 對非數字報錯）
    for c in df.columns:
        if c in YM_COLS:
            df[c] = df[c].map(ym_text)
        elif c in DATE_COLS:
            df[c] = df[c].map(date_text)
        elif c in ("region_codes", "region_text", "region"):
            if c == "region_codes":
                df[c] = df[c].map(region_text)

    fmt = {}
    for c in df.columns:
        if c in MONEY_COLS:
            fmt[c] = lambda v: money(v)
        elif c in RATIO_PCT_COLS:
            fmt[c] = lambda v: pct(v, already_ratio=True)
        elif c in PERCENT_NUM_COLS:
            fmt[c] = lambda v: pct(v, already_ratio=False)
        elif c in INT_COLS:
            fmt[c] = lambda v: "" if _is_missing(v) else f"{int(v):,}"

    renamed = {c: label(c) for c in df.columns}
    styler = df.rename(columns=renamed).style
    if fmt:
        styler = styler.format({label(c): f for c, f in fmt.items()})
    return styler
