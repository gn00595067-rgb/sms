"""
_base.py — core.docs 共用底座（不碰 streamlit）

提供：
  header(...)      建 X.Doc 並填好 期間 / 口徑 / 篩選 / 產出（等同 X.ui.new_doc，但 headless）
  open_month_note  「2026/09 進行中，未納入同期比較」黃 chip 文字
  同期 / 口徑 等「容易看不懂的欄位數字」的統一說明字串（GLOSSARY）——畫面、PDF、Excel 共用

同期（同期比較）到底跟哪個時點比：**去年的同一段月份**（見 core/analysis 檔頭口徑）。
例：期間 2025/01–2025/08，同期就是 2024/01–2024/08。這句話由 SAME_PERIOD 提供，
各頁 KPI / 表下 note 直接引用，三處（畫面 / PDF / Excel）文字一致。
"""
from __future__ import annotations

from reports import export as X


# ---- 統一名詞解釋（欄位 / 數字說明）----
SAME_PERIOD = "同期＝去年的同一段月份（例：期間 2025/01–08，同期為 2024/01–08）"
BOOKED_MARGIN = "帳上毛利＝該公司自己認列的毛利（除佣實收 − 實付成本）；帳上利率＝Σ帳上毛利 ÷ Σ除佣實收"
GROUP_MARGIN = "集團毛利＝把公司間轉撥（母子公司互開）加回後的合併毛利；集團利率＝Σ集團毛利 ÷ Σ除佣實收"
NET_PROFIT = "淨利＝集團毛利再扣掉固定成本（人事、租金等）"
EXT_NET = "除佣實收＝客戶實付金額扣掉退佣後、公司真正收到的營業額（非牌價、非含稅）"
SHARE = "佔比＝該列除佣實收 ÷ 期間合計除佣實收"
CUM = "累計＝依排名由大到小累加的佔比（看前幾名吃掉多少業績）"
GLOSSARY = {
    "same_period": SAME_PERIOD, "booked_margin": BOOKED_MARGIN, "group_margin": GROUP_MARGIN,
    "net_profit": NET_PROFIT, "ext_net": EXT_NET, "share": SHARE, "cum": CUM,
}


def _ym_text(v) -> str:
    from core.format import ym_text
    return ym_text(v)


def period_text(f: dict | None) -> str:
    if not f:
        return ""
    return f"{_ym_text(f['ym_from'])}–{_ym_text(f['ym_to'])}"


def _scope_text(f: dict | None) -> str:
    """把 f['scope']（可能是 dict 或 'media'/'analysis' 字串）轉成人看得懂的口徑句。"""
    if not f:
        return ""
    from core.analysis import resolve_scope
    s = f.get("scope")
    preset = s.get("preset") if isinstance(s, dict) else s
    if preset == "media":
        return "發稿口徑（老闆版：媒體上稿線、四平台＋健康視、交換併回原業務、不含轉撥）"
    if preset in (None, "analysis"):
        r = resolve_scope(s)
        return "分析口徑（對外收入全部" + ("、排除交換）" if not r.get("include_barter", False) else "、含交換）")
    return "自訂口徑"


def filter_text(f: dict | None) -> str:
    """篩選文字，去掉開頭的期間（期間已單獨顯示）。"""
    if not f:
        return ""
    from core.analysis import filter_text as _ft
    txt = _ft(f)
    return txt.replace(period_text(f), "").strip("　 ")


def open_month_note() -> str | None:
    """本月進行中月份的黃 chip 文字；沒有進行中月份回 None。"""
    from core.analysis import open_month
    om = open_month()
    if not om:
        return None
    return f"{_ym_text(om['perf_ym'])} 進行中，未納入同期比較"


def header(title: str, *, subtitle: str | None = None, f: dict | None = None, user: dict | None = None,
           orientation: str = "landscape", scope_text: str | None = None,
           as_of_note: str | None = None, footer_note: str | None = None) -> X.Doc:
    """建立填好表頭的 Doc（headless 版 X.ui.new_doc）。"""
    from datetime import datetime
    doc = X.Doc(
        title=title, subtitle=subtitle, period_text=period_text(f),
        scope_text=scope_text if scope_text is not None else _scope_text(f),
        filter_text=filter_text(f), orientation=orientation,  # type: ignore[arg-type]
        generated_by=(user or {}).get("display_name") or (user or {}).get("username") or "",
        generated_at=datetime.now(), as_of_note=as_of_note)
    if footer_note:
        doc.footer_note = footer_note
    return doc
