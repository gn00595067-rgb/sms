"""
export_pack.py — 月報包 CLI：把老闆每月要看的頁面一次產出（一個 PDF + 每頁一個 Excel + zip）

用法：
    python scripts/export_pack.py --ym-to 2026-08                 # 起月預設當年 1 月、發稿口徑
    python scripts/export_pack.py --ym-from 2026-01 --ym-to 2026-08 --scope media --out pack/

邏輯集中在 core/pack.py（首頁「📦 產生本月月報包」按鈕呼叫同一支）。
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pack import build_pack, pack_filter  # noqa: E402


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
    f = pack_filter(ym_from, ym_to, scope=a.scope)
    user = {"username": a.who, "display_name": a.who, "role": "EXEC"}

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"組月報包 {ym_from:%Y/%m}–{ym_to:%Y/%m}（{a.scope}）…")
    data = build_pack(f, user, who=a.who, stamp=datetime.now())
    zip_path = out / "月報包.zip"
    zip_path.write_bytes(data)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
        names = z.namelist()
    print("完成 →", out)
    for n in names:
        print("  -", n)


if __name__ == "__main__":
    main()
