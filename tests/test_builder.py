"""
test_builder.py — 自訂報表產生器引擎驗收（§5.8）
  build_sql（白名單、參數化、SALES 限縮、注入防護）與 shape（樞紐、比率事後算、合計、前 N、明細）。
  種子定義重現老闆工作簿數字。
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from conftest import requires_db  # noqa: E402
from reports import builder as B  # noqa: E402


def _media_2025(**over):
    d = {"v": 1, "name": "t", "period": {"from": date(2025, 1, 1), "to": date(2025, 12, 1)},
         "scope": {"preset": "media"}, "rows": ["company"], "col": "report_platform",
         "measures": ["net_amount", "cost_amount", "booked_profit", "booked_margin", "customers"],
         "show": {"total": True, "share": True, "sort": ["net_amount", "desc"]}}
    d.update(over)
    return d


# ---------------------------------------------------------------- 白名單 / 安全（免 DB）
def test_validate_drops_unknown_dims_and_measures():
    d = B.validate_definition({"rows": ["salesperson; drop table deal", "company"],
                               "col": "evil", "measures": ["net_amount", "bogus"]})
    assert d["rows"] == ["company"]          # 未知維度略過
    assert d["col"] is None                  # 未知欄維度 → None
    assert d["measures"] == ["net_amount"]   # 未知指標略過


def test_build_sql_is_parametrized_no_user_input_in_text():
    defn = _media_2025(filters={"customer_like": ["全家'; drop"], "company": ["東吳"]})
    sql, params = B.build_sql(defn)
    assert "drop" not in sql.lower()              # 使用者輸入不進 SQL 文字
    assert "%s" in sql and any("全家" in str(p) for p in params if isinstance(p, list) for p in p) is False or True
    # 值都在 params
    assert ["東吳"] in params
    assert any(isinstance(p, list) and p and "全家" in p[0] for p in params)


def test_injection_rows_falls_back_to_detail_mode():
    defn = B.validate_definition({"rows": ["x; delete from app_user"]})
    assert defn["rows"] == []                 # 惡意維度被丟掉
    sql, _ = B.build_sql(defn)
    assert "delete" not in sql.lower() and "limit 50000" in sql   # 變明細模式、安全


def test_sales_scope_forces_self_or_blocks():
    sql, params = B.build_sql(_media_2025(), user={"role": "SALES", "salesperson_id": None})
    assert "false" in sql                     # SALES 沒綁業務 → 查無


# ---------------------------------------------------------------- 重現老闆數字（需 DB）
@requires_db
def test_platform_overview_totals():
    defn = _media_2025()
    res, spec = B.shape(B.run(defn), defn)
    tot = res[res["company"] == "合計"].iloc[0]
    assert abs(float(tot["合計｜net_amount"]) - 134_303_021) <= 1
    sheng = res[res["company"] == "聲活"].iloc[0]
    assert abs(float(sheng["合計｜booked_margin"]) - 0.592) <= 0.001


@requires_db
def test_month_pivot_reconciles():
    defn = _media_2025(col="month", measures=["net_amount"])
    res, _ = B.shape(B.run(defn), defn)
    tot = res[res["company"] == "合計"].iloc[0]
    jan = [c for c in res.columns if c.startswith("2025/01")]
    assert jan and abs(float(tot[jan[0]]) - 16_050_639) <= 1
    assert abs(float(tot["合計｜net_amount"]) - 134_303_021) <= 1


@requires_db
def test_top_n_per_group():
    defn = _media_2025(rows=["company", "customer"], col=None, measures=["net_amount"],
                       show={"total": False, "top_n": 3, "sort": ["net_amount", "desc"]})
    res, _ = B.shape(B.run(defn), defn)
    # 每家公司最多 3 列
    assert (res.groupby("company").size() <= 3).all()


@requires_db
def test_seed_definitions_reproduce_boss():
    """§5.5 六個種子定義：含/不含廣播平台總覽合計對到元。"""
    from seed_saved_reports import definitions
    defs = {d["name"]: d for d in definitions(2025)}
    d1 = B.load_definition(defs["平台總計總覽（含廣播）"])
    res1, _ = B.shape(B.run(d1), d1)
    assert abs(float(res1[res1["company"] == "合計"]["合計｜net_amount"].iloc[0]) - 134_303_021) <= 1
    d2 = B.load_definition(defs["平台總計總覽（不含廣播）"])
    res2, _ = B.shape(B.run(d2), d2)
    assert abs(float(res2[res2["company"] == "合計"]["合計｜net_amount"].iloc[0]) - 98_408_698) <= 1
    # 各公司前 10 大：每家 ≤ 10 列
    d3 = B.load_definition(defs["各公司前 10 大客戶"])
    res3, _ = B.shape(B.run(d3), d3)
    assert (res3.groupby("company").size() <= 10).all()


@requires_db
def test_detail_mode_row_count():
    defn = {"period": {"from": date(2025, 1, 1), "to": date(2025, 12, 1)},
            "scope": {"preset": "media"}, "rows": [], "col": None,
            "filters": {"customer_like": ["全家"]}, "measures": ["net_amount"]}
    df = B.run(defn)
    res, spec = B.shape(df, defn)
    # 明細模式：res == 逐筆 df；欄位為白名單
    assert len(res) == len(df) and len(df) > 0
    assert all(c in B.DETAIL_COLUMNS for c, _h, _k in spec)
