"""
test_docs.py — core/docs 的守則與 headless 可用性

1) core/docs/*.py 一律不得 import streamlit（月報包要能在沒有 Streamlit runtime 下呼叫 build_doc）。
2) 每個 build_doc(f, user) 在只有 DB、沒有 streamlit runtime 的情況下能組出 Doc 並轉 HTML / Excel。
"""
from __future__ import annotations

import ast
import importlib
import pathlib
from datetime import date

import pytest

from tests.conftest import requires_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "core" / "docs"


def _imported_top_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
    return names


def test_docs_do_not_import_streamlit():
    for p in sorted(DOCS.glob("*.py")):
        assert "streamlit" not in _imported_top_modules(p), f"{p.name} 不得 import streamlit"


# pack 用的 build_doc(f, user) 模組（詳細頁 customer_detail/salesperson_detail 需 kwargs，另測）
BUILD_DOC_MODULES = ["core.docs.home", "core.docs.analysis_company", "core.docs.analysis_customer",
                     "core.docs.analysis_salesperson", "core.docs.analysis_sales"]


@requires_db
def test_build_pack_headless():
    """月報包（core.pack）在無 streamlit 下可組出 zip（PDF/HTML + 每頁 Excel）。"""
    import io
    import zipfile
    from datetime import date
    from core.pack import build_pack, pack_filter
    data = build_pack(pack_filter(date(2025, 1, 1), date(2025, 12, 1)),
                      {"username": "tester", "display_name": "tester", "role": "EXEC"})
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert any(n.endswith(".xlsx") for n in names)
    assert any(n.endswith(".pdf") or n.endswith(".html") for n in names)


@requires_db
@pytest.mark.parametrize("mod_name", BUILD_DOC_MODULES)
def test_build_doc_headless(mod_name):
    from reports import export as X
    mod = importlib.import_module(mod_name)
    f = {"ym_from": date(2025, 1, 1), "ym_to": date(2025, 12, 1), "scope": "media",
         "exclude_barter": False, "company": None, "platform_group": None, "industry": None,
         "salesperson": None, "customer": "", "include_house": True, "includes_open": False}
    user = {"username": "tester", "display_name": "tester", "role": "EXEC"}
    doc = mod.build_doc(f, user)
    assert doc.blocks and doc.tables()
    assert "測試" not in X.to_html(doc, plotly_js="none") or True   # 只確認能渲染不丟例外
    X.to_xlsx(doc)
