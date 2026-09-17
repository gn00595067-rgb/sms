"""
test_reports.py — registry 每張報表都能產生 DataFrame 與 Excel（需要 DB）
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from conftest import requires_db  # noqa: E402
from reports.registry import REPORTS  # noqa: E402
from reports.query import run_report  # noqa: E402
from reports import export as X  # noqa: E402
from reports.export import compat  # noqa: E402

EXEC_USER = {"id": 0, "username": "test", "role": "EXEC", "salesperson_id": None}


def _filters_for(key: str) -> dict:
    if key == "customer_rank":
        return {"perf_year": 2025}
    return {}


@requires_db
@pytest.mark.parametrize("key", [k for k, v in REPORTS.items() if v.get("mode") != "custom"])
def test_report_runs_and_exports(key):
    # custom 模式報表（老闆版）走自己的模組與 UI，於 tests/test_boss_reports.py 驗收
    r = REPORTS[key]
    filters = _filters_for(key)
    group_label = None
    if r.get("mode") == "aggregate":
        group_label = next(iter(r["group_by_options"]))
    top_n = 20 if r.get("top_n") else None

    df = run_report(key, filters, group_by_label=group_label, user=EXEC_USER, top_n=top_n)
    assert isinstance(df, pd.DataFrame)

    # 記錄式頁面（報表中心）改走匯出層 compat：df → Doc → Excel / 列印版 HTML
    doc = compat.record_doc(r["title"], filter_text="測試", user=EXEC_USER)
    compat.add_table(doc, r["title"], df, columns=list(df.columns))
    xlsx = X.to_xlsx(doc)
    assert isinstance(xlsx, bytes) and len(xlsx) > 0
    html = X.to_html(doc, plotly_js="none")
    assert "<table" in html


@requires_db
def test_reports_for_role_filters():
    from reports.registry import reports_for_role
    exec_reports = dict(reports_for_role("EXEC"))
    sales_reports = dict(reports_for_role("SALES"))
    assert "two_layer" in exec_reports          # 高階可看雙層毛利
    assert "two_layer" not in sales_reports      # 業務不可
    assert "bonus" in sales_reports
