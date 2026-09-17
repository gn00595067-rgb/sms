"""
core/pack.py — 月報包（board pack）組裝（不碰 streamlit）

依 PACK 順序呼叫各頁 build_doc，產出：一個連續頁碼的 PDF + 每頁一個 Excel，打包成 zip。
首頁「📦 產生本月月報包」按鈕與 scripts/export_pack.py 都呼叫這裡，邏輯只有一份。

沒有瀏覽器引擎時（Streamlit Cloud 第一次前 / 純 CLI 無 chromium），PDF 換成合併 HTML。
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime

from reports import export as X

# (檔名, "模組:函式", kwargs)。順序 = PDF 內的順序。缺的模組（如 annual_detail 尚未做）自動跳過。
PACK = [
    ("00_首頁摘要", "core.docs.home:build_doc", {}),
    ("01_公司分析", "core.docs.analysis_company:build_doc", {}),
    ("02_客戶分析", "core.docs.analysis_customer:build_doc", {}),
    ("03_業務分析", "core.docs.analysis_salesperson:build_doc", {}),
    ("04_銷售分析", "core.docs.analysis_sales:build_doc", {}),
    ("05_年度發稿明細_聲活", "core.docs.annual_detail:build_doc", {"company": "聲活"}),
    ("06_年度發稿明細_東吳", "core.docs.annual_detail:build_doc", {"company": "東吳"}),
    ("07_年度發稿明細_鉑霖", "core.docs.annual_detail:build_doc", {"company": "鉑霖"}),
]


def _load(path: str):
    mod, fn = path.split(":")
    try:
        return getattr(__import__(mod, fromlist=[fn]), fn)
    except (ImportError, AttributeError):
        return None


def pack_filter(ym_from: date, ym_to: date, *, scope: str = "media") -> dict:
    """月報包的 f dict（headless，不經 filter_bar）。"""
    return {"ym_from": ym_from, "ym_to": ym_to, "scope": scope, "exclude_barter": scope != "media",
            "company": None, "platform_group": None, "industry": None, "salesperson": None,
            "customer": "", "include_house": True, "includes_open": False}


def build_docs(f: dict, user: dict | None = None, *, stamp: datetime | None = None,
               who: str = "") -> list[tuple[str, X.Doc]]:
    """回傳 [(檔名, Doc), …]；缺模組或某頁查無資料時自動跳過，不擋整包。"""
    out: list[tuple[str, X.Doc]] = []
    for name, path, kw in PACK:
        fn = _load(path)
        if fn is None:
            continue
        try:
            doc = fn(f, user, **kw)
        except Exception:  # noqa: BLE001
            continue
        if who:
            doc.generated_by = who
        if stamp is not None:
            doc.generated_at = stamp
        out.append((name, doc))
    return out


def build_pack(f: dict, user: dict | None = None, *, who: str = "", stamp: datetime | None = None) -> bytes:
    """回傳 zip bytes：月報包.pdf（或 .html）+ 每頁一個 Excel。"""
    who = who or (user or {}).get("display_name") or (user or {}).get("username") or ""
    pairs = build_docs(f, user, stamp=stamp, who=who)
    docs = [d for _n, d in pairs]
    title = f"月報包 {f['ym_from']:%Y/%m}–{f['ym_to']:%Y/%m}"
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, doc in pairs:
            z.writestr(f"{name}.xlsx", X.to_xlsx(doc))
        stamp_txt = f"{(stamp or datetime.now()):%Y/%m/%d %H:%M}"
        pdf = X.to_pdf_multi(docs, title, who=who, stamp=stamp_txt) if docs else None
        if pdf:
            z.writestr("月報包.pdf", pdf)
        else:
            z.writestr("月報包.html", X.to_html_multi(docs, title, plotly_js="cdn"))
    return zbuf.getvalue()
