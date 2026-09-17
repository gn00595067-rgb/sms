"""
export_pack.py — 月報包：把老闆每月要看的頁面一次產出（一個 PDF + 每頁一個 Excel + zip）

用法：
    python scripts/export_pack.py --ym-from 2026-01 --ym-to 2026-08 --scope media --out pack/
    python scripts/export_pack.py --ym-to 2026-08            # 起月預設當年 1 月

前提：分析頁已改成「Doc 優先」——每頁有一個不碰 streamlit 的 build_doc(f, user) 在 core/docs/ 底下。
（CLAUDE_CODE_TASK_5 §1.3）
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports import export as X  # noqa: E402

# 每個項目：(檔名, build 函式匯入路徑, kwargs)。順序 = PDF 內的順序。
PACK = [
    ("00_首頁摘要",   "core.docs.home:build_doc",               {}),
    ("01_公司分析",   "core.docs.analysis_company:build_doc",   {}),
    ("02_客戶分析",   "core.docs.analysis_customer:build_doc",  {}),
    ("03_業務分析",   "core.docs.analysis_salesperson:build_doc", {}),
    ("04_銷售分析",   "core.docs.analysis_sales:build_doc",     {}),
    ("05_年度發稿明細_聲活", "core.docs.annual_detail:build_doc", {"company": "聲活"}),
    ("06_年度發稿明細_東吳", "core.docs.annual_detail:build_doc", {"company": "東吳"}),
    ("07_年度發稿明細_鉑霖", "core.docs.annual_detail:build_doc", {"company": "鉑霖"}),
]


def _load(path: str):
    mod, fn = path.split(":")
    return getattr(__import__(mod, fromlist=[fn]), fn)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ym-from", default=None)
    ap.add_argument("--ym-to", required=True)
    ap.add_argument("--scope", default="media", choices=["media", "analysis"])
    ap.add_argument("--out", default="pack")
    ap.add_argument("--who", default="系統排程")
    a = ap.parse_args()
    ym_to = date.fromisoformat(a.ym_to + "-01")
    ym_from = date.fromisoformat(a.ym_from + "-01") if a.ym_from else date(ym_to.year, 1, 1)
    f = {"ym_from": ym_from, "ym_to": ym_to, "scope": a.scope, "exclude_barter": a.scope != "media",
         "company": None, "platform_group": None, "industry": None, "salesperson": None, "customer": "",
         "include_house": True}
    user = {"username": a.who, "display_name": a.who, "role": "EXEC"}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now()
    docs: list[X.Doc] = []
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path, kw in PACK:
            doc = _load(path)(f, user, **kw)
            doc.generated_by, doc.generated_at = a.who, stamp
            docs.append(doc)
            xlsx = X.to_xlsx(doc)
            (out / f"{name}.xlsx").write_bytes(xlsx)
            z.writestr(f"{name}.xlsx", xlsx)
            print("xlsx", name)
        title = f"月報包 {ym_from:%Y/%m}–{ym_to:%Y/%m}"
        pdf = X.to_pdf_multi(docs, title, who=a.who, stamp=f"{stamp:%Y/%m/%d %H:%M}")
        if pdf:
            (out / "月報包.pdf").write_bytes(pdf)
            z.writestr("月報包.pdf", pdf)
            print("pdf", len(pdf))
        else:
            html = X.to_html_multi(docs, title, plotly_js="cdn")
            (out / "月報包.html").write_text(html, encoding="utf-8")
            z.writestr("月報包.html", html)
            print("沒有瀏覽器引擎：改輸出 月報包.html（開啟後 Ctrl+P 存 PDF）")
    (out / "月報包.zip").write_bytes(zbuf.getvalue())
    print("done →", out)


if __name__ == "__main__":
    main()
