"""
reports.export — 每一頁的「列印版」：Doc → HTML / PDF / Excel

用法（頁面端）：
    from reports import export as X
    doc = X.Doc("客戶分析", subtitle="誰在養公司、依賴多高", period_text="2026/01–2026/08", ...)
    X.ui.kpis(doc, items)                     # 畫 KPI 卡 + 記進 doc
    X.ui.chart(doc, "各公司月業績", fig, excel={...})
    X.ui.table(doc, "客戶排名", df, X.cols(("customer","客戶","text"), ("ext_net","除佣實收","money")), totals=tot)
    X.ui.export_bar(doc, key="ac")            # 📄 PDF ／ 📊 Excel ／ 🖨 列印版 HTML

渲染端：
    X.to_html(doc) / X.to_pdf(doc) / X.to_xlsx(doc)
"""
from .doc import Chart, Col, Doc, Heading, Kpis, PageBreak, Row, Table, Text, cols
from .html import to_html, to_html_multi
from .pdf import available as pdf_available, to_pdf, to_pdf_multi
from .xlsx import to_xlsx

__all__ = ["Doc", "Col", "cols", "Heading", "Text", "Kpis", "Table", "Chart", "Row", "PageBreak",
           "to_html", "to_html_multi", "to_pdf", "to_pdf_multi", "to_xlsx", "pdf_available"]

try:  # streamlit 只有在 app 內才需要；離線腳本（月報包）不載入
    from . import ui  # noqa: F401
except Exception:  # noqa: BLE001
    ui = None  # type: ignore[assignment]
