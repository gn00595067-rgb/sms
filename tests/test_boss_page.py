"""
test_boss_page.py — 「常用分析」頁的資料來源 v_boss_line 與頁面接線（TASK_6 §5 步 5）

- v_boss_line 2025 三家合計 = 134,303,021（老闆工作簿口徑）。
- 2026 起（有健康視）plats 含「健康視」。
- 頁面註冊排除 SALES（三公司全貌）。
黃金測試（逐格重現原檔）在 tests/test_boss_workbook.py。
"""
from __future__ import annotations

import pathlib
from datetime import date

from tests.conftest import requires_db

ROOT = pathlib.Path(__file__).resolve().parent.parent


@requires_db
def test_boss_line_2025_company_totals():
    from core.data import query_df
    df = query_df('select "公司別" co, round(sum("除佣實收")) net from v_boss_line where perf_year=2025 group by 1')
    m = {r["co"]: float(r["net"]) for _, r in df.iterrows()}
    assert round(m["聲活"]) == 71533523
    assert round(m["東吳"]) == 50861982
    assert round(m["鉑霖"]) == 11907516
    assert round(sum(m.values())) == 134303021


@requires_db
def test_boss_plats_2026_has_health_channel():
    from core.data import query_df
    from reports.boss_workbook import compute as C
    raw = query_df('select * from v_boss_line where perf_ym between %s and %s', (date(2026, 1, 1), date(2026, 8, 1)))
    assert not raw.empty
    assert "健康視" in C.plats_in(raw)          # 2026 起自媒體多一欄健康視


@requires_db
def test_boss_html_key_numbers_from_db():
    from core.data import query_df
    from reports.boss_workbook.html import page_html
    raw = query_df('select * from v_boss_line where perf_ym between %s and %s order by perf_ym, "合約編號"',
                   (date(2025, 1, 1), date(2025, 12, 1)))
    html = page_html(["平台總計總覽", "客戶數統計與客戶排名", "鉑霖_年度發稿明細"], raw,
                     year_label="2025年度", notes_lines=[])
    for needle in ("$134,303,021", "$71,533,523", "$66,886,688", "50.2%", "$31,958,702",
                   "77.84%", "$11,431,326", "43.79%", "蔡伊閔Heidi"):
        assert needle in html, needle


def test_boss_page_hidden_from_sales():
    txt = (ROOT / "app.py").read_text(encoding="utf-8")
    line = next(l for l in txt.splitlines() if '"boss_workbook"' in l and "pages_app/boss_workbook.py" in l)
    assert "SALES" not in line                   # 三公司全貌，SALES 不顯示
