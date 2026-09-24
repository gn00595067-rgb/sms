"""reports/bonus_deal.py — 業務獎金「逐案（逐合約）」分攤（方案 A）

月獎金的唯一真相源是 v_bonus_simple：每「業務 × 組別 × 平台歸類 × 業績項目」一格，
依 bonus_rule 的 % 與「當月除佣實收 ≥ 門檻才發」算出該格月獎金。

逐案作法（方案 A，Pan 拍板）：把每一格的月獎金，依各合約在該格的除佣實收佔比分攤到逐合約；
用最大餘數法讓「逐案加總 == 月獎金」（100% 對得上月獎金總表）。一個合約若橫跨多格
（多平台歸類／業績項目的線），各格分攤後再加總成一列（逐合約，一合約一列）。

門檻是月口徑：若某格當月未達門檻 → 該格月獎金 = 0 → 該格所有合約分攤 = 0（不會出現
「月獎金 0、逐案 > 0」的矛盾）。沒有規則的格標「未設定規則」。
"""
from __future__ import annotations

import pandas as pd

# 一格的鍵（與 v_bonus_simple 的分組一致）
BUCKET_KEY = ["perf_ym", "salesperson", "business_group", "platform_group", "sales_item"]

OUT_COLS = ["perf_ym", "perf_ym_text", "salesperson", "business_group", "contract_no",
            "customer", "platform_group", "net_amount", "bonus_pct", "bonus_amount", "rule_status"]


def _alloc_int(weights: list[float], total) -> list[int]:
    """把整數 total 依 weights 佔比拆成整數、和恰為 total（最大餘數法）。weights 需非負。"""
    total = int(round(float(total)))
    n = len(weights)
    if n == 0:
        return []
    if total == 0:
        return [0] * n
    s = float(sum(weights))
    if s <= 0:                                   # 無正權重 → 盡量平均分，餘數給前面
        base = total // n
        out = [base] * n
        for i in range(total - base * n):
            out[i] += 1
        return out
    raw = [w / s * total for w in weights]
    floor = [int(x // 1) for x in raw]
    rem = total - sum(floor)
    order_desc = sorted(range(n), key=lambda i: raw[i] - floor[i], reverse=True)
    order_asc = sorted(range(n), key=lambda i: raw[i] - floor[i])
    i = 0
    while rem > 0:                               # 餘數大者優先 +1
        floor[order_desc[i % n]] += 1
        rem -= 1
        i += 1
    i = 0
    while rem < 0:                               # 罕見：總和過大 → 餘數小者 -1
        floor[order_asc[i % n]] -= 1
        rem += 1
        i += 1
    return floor


def allocate_bonus_by_deal(bucket_df: pd.DataFrame, contract_df: pd.DataFrame) -> pd.DataFrame:
    """月獎金 → 逐合約分攤。

    bucket_df：v_bonus_simple（含 BUCKET_KEY + net_amount / bonus_amount / bonus_pct）。
    contract_df：v_deal_line_flat 線層彙總到（BUCKET_KEY + contract_no + customer）的 net_amount，
                 只 MEDIA、排除轉撥（與 v_bonus_simple 的口徑一致）。
    回傳逐合約明細（一合約一列，OUT_COLS）。
    """
    contract = contract_df.copy() if contract_df is not None else pd.DataFrame()
    if contract.empty:
        return pd.DataFrame(columns=OUT_COLS)
    contract["net_amount"] = pd.to_numeric(contract["net_amount"], errors="coerce").fillna(0.0)

    b = bucket_df.copy() if bucket_df is not None else pd.DataFrame()
    for c in ("net_amount", "bonus_amount", "bonus_pct", "threshold_amount"):
        if c in b:
            b[c] = pd.to_numeric(b[c], errors="coerce")
    bmap = {tuple(r.get(k) for k in BUCKET_KEY): r for _, r in b.iterrows()}

    parts = []
    for key, g in contract.groupby(BUCKET_KEY, sort=False):
        g = g.copy()
        br = bmap.get(tuple(key) if isinstance(key, tuple) else (key,))
        bonus_total, pct, has_rule = 0.0, None, False
        if br is not None:
            has_rule = pd.notna(br.get("bonus_pct"))
            pct = None if pd.isna(br.get("bonus_pct")) else float(br.get("bonus_pct"))
            ba = br.get("bonus_amount")
            bonus_total = 0.0 if pd.isna(ba) else float(ba)
        weights = [max(x, 0.0) for x in g["net_amount"].tolist()]
        g["bonus_amount"] = _alloc_int(weights, bonus_total)
        g["bonus_pct"] = pct
        g["_has_rule"] = has_rule
        parts.append(g)
    allc = pd.concat(parts, ignore_index=True)

    # 逐合約彙總（跨格加總）
    rows = []
    gcols = ["perf_ym", "salesperson", "business_group", "contract_no"]
    for key, gr in allc.groupby(gcols, sort=False):
        pgs = sorted({str(x) for x in gr["platform_group"] if pd.notna(x)})
        pcts = sorted({round(float(x), 4) for x in gr["bonus_pct"] if pd.notna(x)})
        if len(pcts) > 1:
            status, pct_val = "混合%", None
        elif gr["_has_rule"].any():
            status, pct_val = "", (pcts[0] if pcts else None)
        else:
            status, pct_val = "未設定規則", None
        rows.append({
            "perf_ym": key[0], "salesperson": key[1], "business_group": key[2], "contract_no": key[3],
            "perf_ym_text": gr["perf_ym_text"].iloc[0] if "perf_ym_text" in gr else "",
            "customer": gr["customer"].iloc[0] if "customer" in gr else "",
            "platform_group": "／".join(pgs),
            "net_amount": float(gr["net_amount"].sum()),
            "bonus_pct": pct_val,
            "bonus_amount": float(gr["bonus_amount"].sum()),
            "rule_status": status,
        })
    out = pd.DataFrame(rows, columns=OUT_COLS)
    return out.sort_values(["salesperson", "bonus_amount"], ascending=[True, False]).reset_index(drop=True)
