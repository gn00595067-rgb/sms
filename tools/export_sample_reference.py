"""
export_sample_reference.py — 樣本產生器（原型驗證用，產出 samples/ 裡那三個檔）

直接連本機 DB、用臨時 SQL 做 report_platform 對照；階段 J 做完後把 RL 換成 select * from v_report_line where in_media_scope。
這支不是給 app 用的：它示範「一份 Doc 怎麼組」——KPI / Row(兩張半寬圖) / 表 / 分頁 / 長表 / callout。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reports import export as X  # noqa: E402
from reports.export.theme import COMPANY, PLATFORM  # noqa: E402

DB = "postgresql://postgres:postgres@localhost:5432/perfmvp"
OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

RL = """
with rl as (
  select l.*,
    case when platform in ('全家企頻','全家全企','全家北企','全家桃企','全家中企','全家南企','全家南頻') then '全家企頻'
         when platform in ('家樂福企頻','萬家福') then '萬家福'
         when platform='新鮮視' then '新鮮視' when platform='廣播' then '廣播'
         when platform in ('健康視','健康視-年度代理') then '健康視'
         when platform in ('營運','企頻','企頻-年度維運費') then '營運' else '其它' end report_platform,
    salesperson_base salesperson_merged,
    case when company='瑞迪' then '東吳' else company end co
  from v_line_ext l)
select * from rl where line_type='MEDIA' and not is_intercompany
  and report_platform in ('全家企頻','萬家福','新鮮視','廣播','健康視') and perf_year in (2024, 2025)
"""

with psycopg.connect(DB, row_factory=dict_row) as conn:
    df = pd.DataFrame(conn.execute(RL).fetchall())
for c in ("net_amount", "cost_amount"):
    df[c] = df[c].astype(float)
df["profit"] = df["net_amount"] - df["cost_amount"]
cur, prev = df[df.perf_year == 2025], df[df.perf_year == 2024]
PLATS = ["全家企頻", "萬家福", "新鮮視", "廣播"]
COS = ["聲活", "東吳", "鉑霖"]


def money(v): return f"{v:,.0f}"
def pct(v): return f"{v * 100:.1f}%"


doc = X.Doc("公司分析", subtitle="三家公司加起來到底賺多少：平台結構、業務結構、客戶集中度",
            period_text="2025/01–2025/12", scope_text="發稿口徑（老闆版：媒體上稿線、含交換併回業務、不含轉撥）",
            filter_text="公司=全部　平台範圍=全部", orientation="landscape", generated_by="Jonathan",
            generated_at=datetime(2026, 9, 17, 14, 30), as_of_note="2026/09 進行中，未納入同期比較")

# ---- KPI ----
items = []
for co in COS:
    a, b = cur[cur.co == co], prev[prev.co == co]
    en, pen = a.net_amount.sum(), b.net_amount.sum()
    gp = a.profit.sum()
    items.append({"label": f"{co} 除佣實收", "value": money(en), "delta": "2024 登在瑞迪，公司別不可比",
                  "sub": f"帳上毛利 {money(gp)}（{pct(gp / en)}）・客戶 {a.customer_id.nunique()} 家"})
en, pen = cur.net_amount.sum(), prev.net_amount.sum()
gp = cur.profit.sum()
items.append({"label": "三公司合計（2024 = 瑞迪全部）", "value": money(en), "delta": (en - pen) / pen, "color": "#1d2733",
              "sub": f"帳上毛利 {money(gp)}（{pct(gp / en)}）・不重複客戶 {cur.customer_id.nunique()} 家"})
doc.kpis(items, per_row=4)

# ---- 圖：月 × 公司 堆疊；平台 × 公司 ----
doc.heading("業績結構")
m = cur.groupby(["perf_ym", "co"]).net_amount.sum().unstack(fill_value=0).reindex(columns=COS, fill_value=0) / 1e4
m.index = [f"{d.year}/{d.month:02d}" for d in m.index]
fig1 = go.Figure()
for co in COS:
    fig1.add_bar(x=m.index, y=m[co].round(0), name=co, marker_color=COMPANY[co], marker_line_width=1, marker_line_color="white")
tot = m.sum(axis=1)
fig1.add_scatter(x=m.index, y=tot.round(0), mode="text", text=[f"{v:,.0f}" for v in tot], textposition="top center",
                 textfont=dict(size=10, color="#66717f"), showlegend=False, cliponaxis=False)
fig1.update_layout(barmode="stack", height=300, legend=dict(orientation="h", y=1.1, traceorder="normal"),
                   yaxis=dict(ticksuffix="萬", tickformat=",.0f", gridcolor="#e9edf2", range=[0, tot.max() * 1.18]))
p = cur.groupby(["co", "report_platform"]).net_amount.sum().unstack(fill_value=0).reindex(index=COS, columns=PLATS, fill_value=0) / 1e4
fig2 = go.Figure()
for pl in PLATS:
    fig2.add_bar(x=COS, y=p[pl].round(0), name=pl, marker_color=PLATFORM[pl], text=[f"{v:,.0f}" for v in p[pl]],
                 textposition="outside", cliponaxis=False, textfont=dict(size=9))
fig2.update_layout(barmode="group", height=300, legend=dict(orientation="h", y=1.1),
                   yaxis=dict(ticksuffix="萬", tickformat=",.0f", gridcolor="#e9edf2", range=[0, p.values.max() * 1.2]))
doc.row(X.Chart("各公司月業績（除佣實收，萬）", fig1, height=300, caption="柱頂為三公司合計",
                excel={"type": "stacked", "df": m.round(0).reset_index().rename(columns={"index": "月"}), "x": "月", "series": COS, "unit": "萬"}),
        X.Chart("公司 × 報表平台（除佣實收，萬）", fig2, height=300,
                excel={"type": "bar", "df": p.round(0).reset_index().rename(columns={"co": "公司"}), "x": "公司", "series": PLATS, "unit": "萬"}))

# ---- 表 1：公司 × 平台 ----
rows = []
for co in COS:
    a = cur[cur.co == co]
    r = {"co": co}
    for pl in PLATS:
        r[pl] = a[a.report_platform == pl].net_amount.sum()
    r.update(total=a.net_amount.sum(), cost=a.cost_amount.sum(), profit=a.profit.sum(),
             margin=a.profit.sum() / a.net_amount.sum(), customers=a.customer_id.nunique(), share=a.net_amount.sum() / en)
    rows.append(r)
t1 = pd.DataFrame(rows)
tot1 = {"co": "三公司合計", **{pl: cur[cur.report_platform == pl].net_amount.sum() for pl in PLATS},
        "total": en, "cost": cur.cost_amount.sum(), "profit": gp, "margin": gp / en, "customers": cur.customer_id.nunique(), "share": 1.0}
doc.table("公司 × 報表平台", t1,
          X.cols(("co", "公司", "text"), *[(pl, pl, "money") for pl in PLATS], ("total", "合計", "money"),
                 ("cost", "成本（實付）", "money"), ("profit", "帳上毛利", "money"), ("margin", "帳上利率", "pct"),
                 ("customers", "客戶數", "int"), ("share", "佔比", "progress", {"max": 1.0})),
          totals=tot1, col_groups=[("", 1), ("報表平台（除佣實收）", 4), ("", 6)],
          note="三公司合計的客戶數為跨公司不重複；瑞迪 2025 的 10 筆（536,190）併入東吳，與老闆工作簿一致。")

# ---- 表 2：業務 × 平台 ----
doc.heading("業務結構")
g = cur.groupby("salesperson_merged")
rows = []
for sp, a in g:
    r = {"sp": sp, "cos": "、".join(sorted(a.co.unique(), key=COS.index))}
    for pl in PLATS:
        r[pl] = a[a.report_platform == pl].net_amount.sum()
    r.update(total=a.net_amount.sum(), cost=a.cost_amount.sum(), profit=a.profit.sum(),
             margin=(a.profit.sum() / a.net_amount.sum()) if a.net_amount.sum() else None,
             customers=a.customer_id.nunique(), share=a.net_amount.sum() / en, house=sp in ("Company", "東吳", "聲活", "鉑霖"))
    rows.append(r)
t2 = pd.DataFrame(rows).sort_values("total", ascending=False)
doc.table("業務 × 報表平台（同名業務跨公司合併）", t2,
          X.cols(("sp", "業務", "text"), ("cos", "公司", "text"), *[(pl, pl, "money") for pl in PLATS], ("total", "合計", "money"),
                 ("cost", "成本", "money"), ("profit", "帳上毛利", "money"), ("margin", "利率", "pct"),
                 ("customers", "客戶數", "int"), ("share", "佔比", "progress", {"max": 1.0})),
          totals={"sp": "合計", **{pl: cur[cur.report_platform == pl].net_amount.sum() for pl in PLATS}, "total": en,
                  "cost": cur.cost_amount.sum(), "profit": gp, "margin": gp / en, "share": 1.0},
          row_class=lambda r: "muted" if r["house"] else None,
          note="交換（「換」字業務）已併回原業務；公司戶（Company／東吳）灰字、不排名。")

# ---- 表 3：客戶排名（長表，測分頁）----
doc.page_break()
doc.heading("客戶集中度")
gc = cur.groupby("customer")
rows = []
for cname, a in gc:
    r = {"customer": cname, "cos": "、".join(sorted(a.co.unique(), key=COS.index)),
         "sps": "、".join(a.groupby("salesperson_merged").net_amount.sum().sort_values(ascending=False).index[:3])}
    for pl in PLATS:
        r[pl] = a[a.report_platform == pl].net_amount.sum()
    r.update(total=a.net_amount.sum(), cost=a.cost_amount.sum(), profit=a.profit.sum(),
             margin=(a.profit.sum() / a.net_amount.sum()) if a.net_amount.sum() else None, share=a.net_amount.sum() / en)
    rows.append(r)
t3 = pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)
t3.insert(0, "rank", range(1, len(t3) + 1))
t3["cum"] = t3.share.cumsum()
top = t3.head(80)
doc.table("三公司客戶排名（前 80 名，同一客戶跨公司合併）", top,
          X.cols(("rank", "#", "int"), ("customer", "客戶", "text"), ("cos", "公司", "text"), ("sps", "業務（前 3）", "text"),
                 *[(pl, pl, "money") for pl in PLATS], ("total", "合計", "money"), ("cost", "成本", "money"),
                 ("profit", "帳上毛利", "money"), ("margin", "利率", "pct"), ("share", "佔比", "progress", {"max": float(top.share.max())}),
                 ("cum", "累計", "pct")),
          totals={"customer": f"前 80 名合計（共 {len(t3)} 家）", "total": top.total.sum(), "cost": top.cost.sum(),
                  "profit": top.profit.sum(), "margin": top.profit.sum() / top.total.sum(), "share": top.share.sum()},
          wide=True, note="佔比分母 = 三公司合計；累計 = 依排名累加的佔比（前 10 名 43.8%）。")
doc.text("前 10 大客戶佔 43.8%、前 20 大佔 56%；全家一家佔 13.8%，且 82% 落在廣播——客戶依賴度是策略問題，不是業務問題。", "callout")

# ---- 輸出 ----
(OUT / "公司分析_2025.html").write_text(X.to_html(doc, plotly_js="cdn"), encoding="utf-8")
(OUT / "公司分析_2025.xlsx").write_bytes(X.to_xlsx(doc))
os.environ["EXPORT_DEBUG"] = "1"
pdf = X.to_pdf(doc)
(OUT / "公司分析_2025.pdf").write_bytes(pdf)
print("ok", len(pdf))
