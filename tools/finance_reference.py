"""
tools/finance_reference.py — 財務報表專區的參考產出器（驗收用）

    python tools/finance_reference.py --from 2026/08 --to 2026/08 --out samples/finance_2026-08
    python tools/finance_reference.py --from 2026/09 --to 2026/09 --out samples/finance_2026-09 --contract 1150622 --prepay 2026-09-07 2026-09-13

讀 DATABASE_URL（或 --db）的 v_finance_line / v_channel_prepay / v_invoice_request，
把六個功能（含成本毛利分析的 5 種）各產一份 HTML、Excel（有 Chromium 時再產 PDF），並印出關鍵合計（給 tests 對照）。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reports.finance import compute as C, grid as G, layout as L  # noqa: E402


def _ym(s: str) -> date:
    y, m = s.split("/")
    return date(int(y), int(m), 1)


def _prev_year(d: date) -> date:
    return date(d.year - 1, d.month, 1)


def load(db: str, ym_from: date, ym_to: date) -> pd.DataFrame:
    import psycopg
    with psycopg.connect(db) as conn:
        return pd.read_sql("select * from v_finance_line where perf_ym between %s and %s order by perf_ym, contract_no, line_no", conn, params=(ym_from, ym_to))


def load_sql(db: str, sql: str, params=()) -> pd.DataFrame:
    import psycopg
    with psycopg.connect(db) as conn:
        return pd.read_sql(sql, conn, params=params)


def write(out: Path, name: str, grids: list, *, title: str, pdf: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    html = G.to_html(grids, title=title)
    (out / f"{name}.html").write_text(html, encoding="utf-8")
    (out / f"{name}.xlsx").write_bytes(G.to_xlsx(grids, title=title))
    if pdf:
        try:
            from reports.export.pdf import html_to_pdf
            data = html_to_pdf(html, orientation="landscape" if grids[0].landscape else "portrait", title=title)
            if data:
                (out / f"{name}.pdf").write_bytes(data)
        except Exception as e:  # noqa: BLE001
            print(f"  (PDF 略過：{e})")
    print(f"  寫出 {name}.html / .xlsx")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/perfmvp"))
    ap.add_argument("--from", dest="ym_from", required=True)
    ap.add_argument("--to", dest="ym_to", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", default=None, help="三單查詢的合約編號")
    ap.add_argument("--prepay", nargs=2, default=None, help="電台預付日期區間 yyyy-mm-dd yyyy-mm-dd")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    ym_from, ym_to = _ym(a.ym_from), _ym(a.ym_to)
    raw = C.prepare(load(a.db, ym_from, ym_to))
    prev = C.prepare(load(a.db, _prev_year(ym_from), _prev_year(ym_to)))
    period = dict(ym_from=a.ym_from, ym_to=a.ym_to)
    print(f"期間 {a.ym_from}~{a.ym_to}：{len(raw)} 線；同期 {len(prev)} 線")

    # 1. 業績成本報表(區間)
    rep = C.cost_report(raw)
    write(out, "1_月業績成本報表", L.layout_cost_report(rep, **period), title="月業績成本報表", pdf=a.pdf)
    fin = rep.final.set_index("label")
    print("  合計 實收 %.0f 除佣 %.0f 成本 %.0f 毛利 %.0f；差額 %.0f；廣播成本 %.0f" % (
        fin.loc["(1)-(7) 合計", "gross"], fin.loc["(1)-(7) 合計", "net"], fin.loc["(1)-(7) 合計", "cost"], fin.loc["(1)-(7) 合計", "profit"], rep.diff_gross_net, rep.radio_cost))

    # 2. 媒體發稿量分析（五種版本 × 依實收排序）
    for ver in ("客戶版", "業務版", "明細版", "電台總表", "業務總表"):
        groups = C.media_volume(raw, ver, "實收金額")
        write(out, f"2_電台發稿量_{ver}", L.layout_media_volume(groups, version=ver, sort_by="實收金額", **period), title=f"電台發稿量{ver}", pdf=a.pdf and ver == "客戶版")
    g0 = C.media_volume(raw, "客戶版", "實收金額")
    if g0:
        print(f"  電台第 1 名 {g0[0]['channel']}：實收 {g0[0]['totals']['gross']:,.0f}，客戶 {len(g0[0]['rows'])} 家")

    # 3a. 綜合分析
    comb = C.combined_analysis(raw)
    write(out, "3a_綜合成本毛利分析", L.layout_combined(comb, **period), title="綜合成本毛利分析", pdf=a.pdf)
    ch = comb["channel"].set_index("label")
    print("  綜合分析 實收：全家 %.0f 家樂福 %.0f 新鮮視 %.0f 健康視 %.0f 廣播 %.0f 其他 %.0f 營運 %.0f 總計 %.0f" % tuple(
        ch.loc["實收金額", c] for c in ("全家", "家樂福", "新鮮視", "健康視", "廣播", "其他", "營運", "總計")))

    # 3b. 客戶同期比較表（全部 / 企頻 / 廣播 / 新鮮視）
    for variant in ("全部", "企頻", "廣播", "新鮮視"):
        pc = C.period_compare(raw, prev, variant)
        write(out, f"3b_客戶同期比較表_{variant}", L.layout_period_compare(pc, year=ym_from.year, plat_text=variant if variant != "全部" else "*", **period),
              title=f"客戶同期比較表({variant})", pdf=a.pdf and variant == "全部")
    pc = C.period_compare(raw, prev, "全部")
    t = pc["platform"].set_index("label").loc["總計"]
    print("  同期比較 總計：當期除佣 %.0f 去年 %.0f；當期毛利 %.0f 去年 %.0f；客戶 %d" % (t["net_cur"], t["net_prev"], t["profit_cur"], t["profit_prev"], len(pc["customers"])))

    # 3c. 業績認定表
    rec = C.recognition_table(raw)
    write(out, "3c_月業績認定表", L.layout_recognition(rec, **period), title="月業績認定表", pdf=a.pdf)

    # 3d. 月獎金計算總表
    bs = C.bonus_summary(raw)
    write(out, "3d_月獎金計算總表", L.layout_bonus_summary(bs, **period), title="月獎金計算總表", pdf=a.pdf)

    # 3e. 業務發稿統計 A3
    ws = C.sales_wave_stats(raw)
    write(out, "3e_業務發稿統計A3", L.layout_wave_stats(ws, **period), title="業務發稿統計報表", pdf=a.pdf)
    top = ws["top"].set_index("salesperson")
    for sp in ("陳絜心", "洪佳琪"):
        if sp in top.index:
            r = top.loc[sp]
            print(f"  發稿統計 {sp}：客戶數 {r['customers']} 波段 {r['waves']} 實收 {r['gross']:,.0f} 除佣 {r['net']:,.0f} 毛利 {r['profit']:,.0f} 企頻波段 {r['企頻_waves']}")

    # 4. 月責任檔業績達成表
    ach = C.achievement(raw)
    write(out, "4_月責任檔業績達成表", L.layout_achievement(ach, **period), title="月責任檔業績達成表", pdf=a.pdf)
    for grp in ach:
        print(f"  達成表 {grp['group']} 總計：實收 {grp['total']['gross']:,.0f} 製作 {grp['total']['prod_cost']:,.0f} 認定 {grp['total']['recognized']:,.0f}")

    # 5. 三單
    if a.contract:
        lines = C.prepare(load_sql(a.db, "select * from v_finance_line where contract_no = %s order by line_no", (a.contract,)))
        if len(lines):
            head = lines.iloc[0]
            media = lines[~lines["is_intercompany"].astype(bool)] if "is_intercompany" in lines.columns else lines
            first = (media if len(media) else lines).iloc[0]
            pr = C.purchase_request(lines)
            write(out, f"5_採購申請單_{a.contract}", L.layout_purchase_request(
                pr, contract_no=a.contract, customer=first["customer"], group=first["business_group"], ad_name=first["ad_name"],
                salesperson=first["salesperson"]), title="廣告時段採購申請單", pdf=a.pdf)   # 表頭一律聲活（舊表單寫死）
            print(f"  採購申請單 {a.contract}：{len(pr['rows'])} 列，實際成本合計 {pr['totals']['actual']:,.0f}，除佣 {pr['net']:,.0f} 毛利 {pr['profit']:,.0f}")
            inv = load_sql(a.db, "select * from v_invoice_request where contract_no = %s order by request_no", (a.contract,))
            write(out, f"5_發票開立申請單_{a.contract}", L.layout_invoice_request(
                inv, contract_no=a.contract, customer=first["customer"], group=first["business_group"], ad_name=first["ad_name"],
                salesperson=first["salesperson"], air_text=first["air_period_text"]), title="發票開立申請單", pdf=a.pdf)

    # 6. 電台預付明細表
    if a.prepay:
        pp = load_sql(a.db, "select * from v_channel_prepay where prepay_on between %s and %s order by prepay_on, media_channel, contract_no", tuple(a.prepay))
        groups = C.prepay_groups(pp)
        write(out, "6_電台預付明細表", L.layout_prepay(groups, d_from=a.prepay[0].replace("-", "/"), d_to=a.prepay[1].replace("-", "/")), title="電台預付明細表", pdf=a.pdf)
        for grp in groups:
            print(f"  電台預付 {grp['channel']}：{len(grp['rows'])} 筆，小計 {grp['total']:,.0f}")


if __name__ == "__main__":
    main()
