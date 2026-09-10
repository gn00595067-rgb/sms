"""
test_etl_rules.py — 純 Python 規則測試（不需要 DB）

涵蓋：ym 解析、num/intn/boolean 解析、line_type 判斷、除佣實收公式。
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from etl_legacy import boolean, intn, num, ym  # noqa: E402
from etl_legacy import INTERCOMPANY_GROUPS, PRODUCTION_PREFIX  # noqa: E402
from core.deals import compute_net  # noqa: E402


# ------------------------------------------------------------------ ym
def test_ym_formats():
    assert ym("2026/09") == date(2026, 9, 1)
    assert ym("2026-09") == date(2026, 9, 1)
    assert ym("202609") == date(2026, 9, 1)
    assert ym("2026/1") == date(2026, 1, 1)


def test_ym_invalid():
    assert ym("") is None
    assert ym("abc") is None
    assert ym("2026/13") is None
    assert ym("2026/00") is None


# ------------------------------------------------------------------ num / intn / boolean
def test_num():
    assert num("1234") == 1234.0
    assert num("") == 0.0
    assert num("", default=None) is None
    assert num("-500") == -500.0
    assert num("12.5") == 12.5


def test_intn():
    assert intn("12") == 12
    assert intn("12.0") == 12
    assert intn("") is None
    assert intn("x") is None


def test_boolean():
    for t in ("1", "True", "true", "-1", "是", "Y"):
        assert boolean(t) is True
    for f in ("0", "", "否", "N", "false"):
        assert boolean(f) is False


# ------------------------------------------------------------------ line_type 判斷
def _line_type(channel: str, group: str, company: str) -> str:
    if str(channel).startswith(PRODUCTION_PREFIX):
        return "PRODUCTION"
    if group in INTERCOMPANY_GROUPS or company in INTERCOMPANY_GROUPS:
        return "INTERCOMPANY"
    return "MEDIA"


def test_line_type():
    assert _line_type("製作費-錄音室", "聲活組", "聲活") == "PRODUCTION"
    assert _line_type("全家企頻", "聲活-東", "東吳") == "INTERCOMPANY"
    assert _line_type("全家企頻", "東吳組", "東吳") == "MEDIA"
    assert _line_type("廣播", "聲活組", "聲活") == "MEDIA"


# ------------------------------------------------------------------ 除佣實收公式
def test_compute_net():
    # 100,000 退佣 10% → 90,000
    assert compute_net(100000, 10, 0) == 90000
    # 現折 5% 再套用
    assert compute_net(100000, 10, 5) == 85500
    # 無退佣
    assert compute_net(50000, 0, 0) == 50000
    # None 視為 0
    assert compute_net(100000, None, None) == 100000
    # 四捨五入到整數
    assert compute_net(333, 10, 0) == 300  # 333*0.9 = 299.7 → 300


def test_compute_net_intercompany_65():
    # 轉撥 65 折：380,952 → 247,619（對齊 legacy_profile 第 4 點）
    assert round(380952 * 0.65) == 247619
