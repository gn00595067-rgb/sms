"""
core/docs/glossary.py — 欄位/數字說明的單一真相源 + 自動加註

問題：`Col.help` 只在畫面 hover 看得到；PDF 印出來、Excel 裡都看不到。使用者看報表時
像「前3大依賴度」這種自訂欄位沒有解釋。

解法：
  FIELD_HELP  一份欄位鍵/中文名 → 白話定義的詞典（單一真相源）。
  annotate(doc)  在每個 build_doc 收尾呼叫：①把每個 Col 缺的 help 從詞典補上；
                 ②在報表最後自動加一張「欄位說明」表（欄位｜說明）——這張表會照一般
                 表格渲染，所以 **PDF 印得出來、Excel 也有一張工作表**，畫面/PDF/Excel 三處一致。

只解釋「自訂／不一目了然」的欄位；公司、客戶、產業、年、廣告 這種不進詞典、不列說明。
"""
from __future__ import annotations

from ._base import CUM, EXT_NET, GROUP_MARGIN, NET_PROFIT, SAME_PERIOD, SHARE

_MARGIN = "帳上利率＝Σ帳上毛利 ÷ Σ除佣實收（合計列為重算，非各列平均）"

# 欄位鍵 或 中文表頭 → 白話定義。同義鍵指向同一句。
FIELD_HELP: dict[str, str] = {
    # 金額
    "ext_net": EXT_NET, "net": EXT_NET, "net_amount": EXT_NET, "全年除佣實收": "全年除佣實收＝該年一整年的除佣實收",
    "ext_net_same_period": "同段除佣實收＝該年 1 月到今年同一個月的除佣實收，讓不同年份用相同月份區間公平比較",
    "booked_profit": "帳上毛利＝除佣實收 − 實付成本（該公司自己認列的毛利）",
    "gross_profit": "毛利＝收入 − 成本",
    "booked_cost": "實付＝實際付給媒體／通路的成本", "cost_amount": "實付＝實際付給媒體／通路的成本",
    "成本": "成本＝實際付給媒體／通路的實付金額", "實付": "實付＝實際付給媒體／通路的成本",
    "production_cost": "製作費＝廣告製作相關成本（非媒體採購）",
    "group_profit": GROUP_MARGIN.split("；")[0], "集團毛利": GROUP_MARGIN.split("；")[0],
    "net_profit": NET_PROFIT,
    "recognized_amount": "認定業績＝交換併回原業務、依認列比例分給該業務的業績",
    "barter_net": "交換＝以廣告換廣告（易物）的金額，不計入排名與毛利",
    "avg_deal": "平均單筆＝除佣實收 ÷ 筆數",
    "prev_net": "去年除佣實收＝去年同一段月份的除佣實收",
    "實收": EXT_NET, "總計": "總計＝該列的除佣實收合計",
    # 比率／佔比
    "booked_margin": _MARGIN, "margin": _MARGIN, "margin_pct": _MARGIN, "毛利率": _MARGIN,
    "帳上利率": _MARGIN, "利率": _MARGIN,
    "group_margin": "集團利率＝Σ集團毛利 ÷ Σ除佣實收（集團毛利＝公司間轉撥加回後的合併毛利）",
    "net_margin": "集團淨利率＝集團毛利扣掉固定成本後 ÷ 除佣實收",
    "share": SHARE, "佔比": SHARE, "佔該業務": "佔該業務＝該客戶除佣實收 ÷ 該業務總額",
    "佔該業務%": "佔該業務%＝該客戶 ÷ 該業務前 10 大合計",
    "cum_share": CUM, "cum": CUM,
    "top3_share": "前3大依賴度＝前 3 大客戶佔該業務總業績的比重（越高＝越依賴少數客戶、風險越大）",
    "top1_share": "最大客戶依賴度＝最大客戶佔該業務的比重",
    "發稿佔比": "發稿佔比＝該業務除佣實收 ÷ 公司發稿口徑總額",
    "yoy_pct": "同期%＝對去年同一段月份的成長率（今年才第一次有業績顯示「新」）。" + SAME_PERIOD,
    "yoy": "同期%＝對去年同一段月份的成長率。" + SAME_PERIOD,
    "yoy_text": "同期%＝對去年同一段月份的成長率（新客顯示「新」）。" + SAME_PERIOD,
    # 目標／預估
    "target_amount": "目標＝主檔維護設定的業績目標（當季為 Q 口徑）",
    "當季目標": "當季目標＝該季的業績目標",
    "actual": "進單＝期間內已成立的除佣實收（不含預估）",
    "remaining": "待追＝目標 − 進單，還差多少",
    "required_monthly": "每月需達＝待追 ÷ 剩餘月份，平均每月要進多少才達標",
    "months_left": "剩餘月份＝到期間結束還剩幾個月",
    "achieved_pct": "達成率＝進單 ÷ 目標", "當季達成率": "當季達成率＝當季進單 ÷ 當季目標",
    "achieved_pct_with_forecast": "加預估後達成率＝（進單＋預估）÷ 目標",
    "amount": "預估＝尚未成立、OPEN pipeline 的預估金額",
    "forecast_amount": "預估＝尚未成立、OPEN pipeline 的預估金額",
    "prob_ratio": "機率%＝成交機率（業務自評）", "probability": "機率%＝成交機率（業務自評）",
    # 計數／狀態／人
    "customers": "客戶數＝不重複客戶數", "客戶數": "客戶數＝不重複客戶數",
    "new_customers": "新客＝今年第一次有業績的客戶數",
    "deals": "筆數＝訂單（合約線）筆數",
    "months_since_last": "距上次交易＝離最近一次實際交易幾個月（不含未來預登單）",
    "msl": "距上次交易＝離最近一次實際交易幾個月",
    "status": "狀態＝新客／既有／回流／流失（依年度交易狀態）",
    "abc_tier": "ABC＝A（累計到 80% 的大客戶）／B（80–95%）／C（最後 5%）",
    "strategy_hint": "策略提示＝依金額×毛利率自動給的維護建議（核心／可擴大／一般）",
    "companies_multi": "公司(多)＝該客戶跨哪些公司做（依金額大到小）",
    "salespeople_multi": "業務(多)＝經手該客戶的業務（依金額大到小，最多 5 位）",
    "main_salesperson": "主要業務＝該客戶金額最大的業務",
    "main_company": "主要公司＝該業務金額最大的公司",
    "top_customer": "最大客戶＝該業務金額最大的客戶",
    "reason": "低毛利原因＝業務／主管在畫面上回填的說明",
    "low_margin_reason": "低毛利原因＝業務／主管回填的說明",
    # 報表平台（老闆版）
    "net_cp_family": "全家企頻＝該報表平台的除佣實收（老闆版四欄之一）",
    "net_cp_carrefour": "萬家福＝該報表平台（家樂福企頻）的除佣實收",
    "全家企頻": "全家企頻＝該報表平台的除佣實收（老闆版四欄之一）",
    "萬家福": "萬家福＝家樂福企頻的除佣實收", "新鮮視": "新鮮視＝該報表平台的除佣實收",
    "廣播": "廣播＝該報表平台的除佣實收", "健康視": "健康視＝該報表平台的除佣實收（發稿口徑第五欄）",
    # 應收 / 獎金（報表中心）
    "overdue_days": "逾期天數＝距應交付日已逾期幾天（>0 才算逾期）",
    "outstanding_amount": "未收金額＝帳款金額 − 已收金額",
    "amount_total": "帳款金額＝應收帳款總額",
    "received_amount": "已收金額＝已銷帳收回的金額",
    "bonus_pct": "獎金%＝適用的業務獎金百分比（依規則）",
    "threshold_amount": "門檻＝達到才計獎金的金額門檻",
    # 雙層毛利報表
    "layer1_revenue": "第一層收入＝媒體發稿層（自家版位）的收入",
    "layer1_profit": "第一層毛利＝第一層收入 − 第一層成本",
    "layer2_revenue": "第二層收入＝專案／代購層的收入",
    "layer2_profit": "第二層毛利＝第二層收入 − 直接成本 − 分攤固定成本",
    "fixed_cost": "固定成本＝人事、租金等分攤的固定支出",
}


def _lookup(col) -> str | None:
    return col.help or FIELD_HELP.get(col.key) or FIELD_HELP.get(col.label)


def annotate(doc):
    """補齊各 Col.help，並在報表最後加一張「欄位說明」表（PDF/Excel 都看得到）。"""
    if any(getattr(t, "title", "") == "欄位說明" for t in doc.tables()):
        return doc
    seen: dict[str, str] = {}
    for t in doc.tables():
        for c in t.columns:
            h = _lookup(c)
            if h:
                if not c.help:
                    c.help = h
                seen.setdefault(c.label, h)
    if seen:
        import pandas as pd
        from reports.export.doc import Col
        gdf = pd.DataFrame({"欄位": list(seen.keys()), "說明": list(seen.values())})
        doc.heading("欄位說明")
        doc.table("欄位說明", gdf, [Col("欄位", "欄位", "text"), Col("說明", "說明", "text")],
                  note="本報表各欄位／數字的定義；同一欄位在畫面、PDF、Excel 三處定義一致。")
    return doc
