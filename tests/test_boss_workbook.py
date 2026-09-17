"""
老闆工作簿重現的黃金測試：
把原檔「原始資料_發稿分析」那 1,577 列餵進 compute/xlsx → 產出的每一張表必須和原檔逐格相等（值）。
唯一允許的差異：年度發稿明細第二段／第三段裡「總計相同」的客戶／列的先後順序（原檔沒有規則），所以那兩段以列集合比對。
原檔放 samples/2025年度_三公司發稿明細分析-0917.xlsx（含客戶資料，不進版控：.gitignore）。
"""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from reports.boss_workbook import compute as C
from reports.boss_workbook.xlsx import build_bytes

ORIG = Path(__file__).resolve().parent.parent / "samples" / "2025年度_三公司發稿明細分析-0917.xlsx"
POSITIONAL = ["平台總計總覽", "客戶數統計與客戶排名"]
DETAIL = ["聲活_年度發稿明細", "東吳_年度發稿明細", "鉑霖_年度發稿明細"]


class _Num(float):
    """比對用：金額容差 0.5、比率容差 0.0005。"""
    def __eq__(self, other):
        if not isinstance(other, float):
            return False
        tol = 0.5 if abs(self) >= 2 or abs(other) >= 2 else 0.0005
        return abs(float(self) - float(other)) <= tol
    __hash__ = float.__hash__


def _norm(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return _Num(v)
    return str(v).strip()


def _rows(ws):
    out = []
    for row in ws.iter_rows(values_only=True):
        vals = [_norm(v) for v in row]
        while vals and vals[-1] is None:
            vals.pop()
        out.append(tuple(vals))
    return out


def _key(row):
    """集合比對用的鍵：數字四捨五入到 0.1（金額）／0.001（比率）。"""
    return tuple((round(float(v), 3) if abs(v) < 2 else round(float(v), 0)) if isinstance(v, float) else v for v in row)


@pytest.fixture(scope="module")
def pair():
    if not ORIG.exists():
        pytest.skip("沒有原檔 samples/2025年度_三公司發稿明細分析-0917.xlsx")
    raw = pd.read_excel(ORIG, sheet_name="原始資料_發稿分析")
    notes = C.notes(raw, 2933, 1356, 4318600.3, "2025年度")
    new = openpyxl.load_workbook(io.BytesIO(build_bytes(raw, year_label="2025年度", notes_lines=notes)), data_only=True)
    orig = openpyxl.load_workbook(ORIG, data_only=True)
    return orig, new


@pytest.mark.parametrize("sheet", POSITIONAL)
def test_positional_sheets_identical(pair, sheet):
    orig, new = pair
    a, b = _rows(orig[sheet]), _rows(new[sheet])
    a += [()] * (len(b) - len(a)); b += [()] * (len(a) - len(b))
    bad = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert not bad, f"{sheet} 有 {len(bad)} 列不同，第一個：{bad[0]}"


@pytest.mark.parametrize("sheet", DETAIL)
def test_detail_sheets_identical_up_to_tie_order(pair, sheet):
    orig, new = pair
    a, b = _rows(orig[sheet]), _rows(new[sheet])
    assert len(a) == len(b), f"{sheet} 列數不同 {len(a)} vs {len(b)}"
    # 第一段（到第一個【 之前）逐列相等；其餘以「列集合」相等（同額客戶的先後順序原檔無規則）
    first_block = next(i for i, r in enumerate(a) if r and isinstance(r[0], str) and r[0].startswith("【"))
    assert a[:first_block] == b[:first_block], f"{sheet} 第一段不同"
    assert sorted(map(repr, map(_key, a[first_block:]))) == sorted(map(repr, map(_key, b[first_block:]))), f"{sheet} 第二／三段內容不同"
    # 小計 / 合計 列的位置也要一樣（區塊結構相同）
    marks_a = [(i, r[0]) for i, r in enumerate(a) if r and isinstance(r[0], str) and (r[0].endswith(" 小計") or r[0].startswith("【") or r[0] in ("各平台除佣實收小計", "除佣實收總計"))]
    marks_b = [(i, r[0]) for i, r in enumerate(b) if r and isinstance(r[0], str) and (r[0].endswith(" 小計") or r[0].startswith("【") or r[0] in ("各平台除佣實收小計", "除佣實收總計"))]
    assert marks_a == marks_b, f"{sheet} 區塊結構不同"


def test_raw_sheet_roundtrip(pair):
    orig, new = pair
    assert new["原始資料_發稿分析"].max_row == orig["原始資料_發稿分析"].max_row


def test_html_has_same_numbers(pair):
    """HTML 版（畫面／PDF）和 Excel 版同一份 layout：關鍵數字要出現。"""
    from reports.boss_workbook.html import page_html
    raw = pd.read_excel(ORIG, sheet_name="原始資料_發稿分析")
    html = page_html(["平台總計總覽", "客戶數統計與客戶排名", "鉑霖_年度發稿明細"], raw, year_label="2025年度", notes_lines=[])
    for needle in ("$134,303,021", "$71,533,523", "$66,886,688", "50.2%", "$31,958,702", "77.84%", "$11,431,326", "嘉義縣政府"):
        assert needle in html, needle
    assert html.count("<thead>") >= 20            # 每個區塊自己的表頭（列印時每頁重複）
