# -*- coding: utf-8 -*-
"""mockup_generator.py — 用資料庫實際數字產生「分析報表設計」樣稿（HTML，含 inline SVG）。
也是四張分析表每個數字的參考實作：agg_customers / agg_sp / size_bucket / band 等函式就是規格。
用法：  $env:DATABASE_URL="postgresql://..."; python tools/mockup_generator.py   → docs/report_design_mockup.html
"""
import os, sys, math, html, json
import pandas as pd
import psycopg
from psycopg.rows import dict_row

URL = os.environ.get("DATABASE_URL") or __import__("sys").exit("請先設定 DATABASE_URL")
OUT = os.environ.get("OUT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "report_design_mockup.html"))

def q(sql, params=None):
    with psycopg.connect(URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())

YEAR, PY, M = 2026, 2025, 9   # as-of 2026/09

# ----------------------------------------------------------------- formats
def wan(v, d=0):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "–"
    v = float(v) / 10000
    s = f"{v:,.{d}f}"
    return f"{s}萬"
def money(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "–"
    return f"{int(round(float(v))):,}"
def pct(v, d=1, sign=False):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "–"
    v = float(v) * 100
    return (f"{v:+.{d}f}%" if sign else f"{v:.{d}f}%")
def esc(s):
    if s is None or (isinstance(s, float) and math.isnan(s)): return ""
    return html.escape(str(s))
def delta_cls(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")

# ----------------------------------------------------------------- SVG helpers
def svg_hbars(rows, label, value, width=560, bar_h=16, gap=8, label_w=150, color="var(--acc)", vfmt=wan, extra=None, max_v=None, rowcls=None):
    """Horizontal bars, one per row. rows: list of dicts. extra: fn(row)->text right of bar."""
    n = len(rows)
    h = n * (bar_h + gap) + 4
    mv = max_v or max(float(r[value] or 0) for r in rows) or 1
    plot_w = width - label_w - 250
    out = [f'<svg class="chart" viewBox="0 0 {width} {h}" width="100%" role="img">']
    for i, r in enumerate(rows):
        y = i * (bar_h + gap) + 2
        v = float(r[value] or 0)
        w = max(0, v / mv * plot_w)
        c = color(r) if callable(color) else color
        out.append(f'<text x="{label_w-8}" y="{y+bar_h*0.72}" text-anchor="end" class="lbl">{esc(r[label])}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="0" style="fill:{c}"><title>{esc(r[label])}: {vfmt(v)}</title></rect>')
        if w > 0:
            out.append(f'<rect x="{label_w+w-3:.1f}" y="{y}" width="3" height="{bar_h}" rx="1.5" style="fill:{c}"/>')
        t = extra(r) if extra else vfmt(v)
        out.append(f'<text x="{label_w+w+6:.1f}" y="{y+bar_h*0.72}" class="val">{esc(t)}</text>')
    out.append('</svg>')
    return "".join(out)

def svg_stacked_columns(cats, series, width=720, height=260, vfmt=wan, totals=True, ylab=""):
    """series: list of (name, css_color, [values per cat])."""
    L, R, T, B = 56, 12, 28, 34
    pw, ph = width - L - R, height - T - B
    n = len(cats)
    tot = [sum(float(s[2][i] or 0) for s in series) for i in range(n)]
    mv = max(tot) or 1
    # nice ticks
    step = 10 ** math.floor(math.log10(mv));
    for m in (1, 2, 5, 10):
        if mv / (step * m) <= 5: step = step * m; break
    ymax = math.ceil(mv / step) * step
    slot = pw / n; bw = min(slot * 0.62, 48)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img">']
    yv = 0
    while yv <= ymax + 1e-9:
        y = T + ph - yv / ymax * ph
        out.append(f'<line x1="{L}" x2="{width-R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{L-6}" y="{y+4:.1f}" text-anchor="end" class="tick">{wan(yv)}</text>')
        yv += step
    for i, c in enumerate(cats):
        x = L + i * slot + (slot - bw) / 2
        yb = T + ph
        for name, col, vals in series:
            v = float(vals[i] or 0)
            if v <= 0: continue
            hh = v / ymax * ph
            yb -= hh
            out.append(f'<rect x="{x:.1f}" y="{yb+1:.1f}" width="{bw:.1f}" height="{max(hh-2,0):.1f}" style="fill:{col}"><title>{esc(c)} {esc(name)}: {vfmt(v)}</title></rect>')
        if totals and tot[i] > 0:
            out.append(f'<text x="{x+bw/2:.1f}" y="{yb-5:.1f}" text-anchor="middle" class="val">{vfmt(tot[i])}</text>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{T+ph+16}" text-anchor="middle" class="tick">{esc(c)}</text>')
    out.append(f'<line x1="{L}" x2="{width-R}" y1="{T+ph}" y2="{T+ph}" class="axis"/>')
    out.append('</svg>')
    legend = '<div class="legend">' + "".join(f'<span><i style="background:{col}"></i>{esc(name)}</span>' for name, col, _ in series) + '</div>'
    return legend + "".join(out)

def svg_scatter(points, width=720, height=340, xmax=None, ymin=-0.2, ymax=1.0, labels_top=6):
    """points: dicts with x (net), y (margin), r (deals), cls (status), name."""
    L, R, T, B = 50, 16, 14, 40
    pw, ph = width - L - R, height - T - B
    xmax = xmax or max(p["x"] for p in points) * 1.05
    def X(v): return L + (math.sqrt(max(v, 0)) / math.sqrt(xmax)) * pw
    def Y(v): return T + ph - (min(max(v, ymin), ymax) - ymin) / (ymax - ymin) * ph
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img">']
    for yv in (-0.2, 0, 0.16, 0.35, 0.5, 0.75, 1.0):
        if yv < ymin or yv > ymax: continue
        y = Y(yv)
        cls = "grid strong" if yv in (0.16, 0.35) else "grid"
        out.append(f'<line x1="{L}" x2="{width-R}" y1="{y:.1f}" y2="{y:.1f}" class="{cls}"/>')
        out.append(f'<text x="{L-6}" y="{y+4:.1f}" text-anchor="end" class="tick">{int(yv*100)}%</text>')
    for xt in (0, 250_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000):
        if xt > xmax: break
        x = X(xt)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T+ph}" y2="{T+ph+4}" class="axis"/>')
        out.append(f'<text x="{x:.1f}" y="{T+ph+16}" text-anchor="middle" class="tick">{wan(xt)}</text>')
    out.append(f'<text x="{width-R}" y="{T+ph+32}" text-anchor="end" class="tick">除佣實收（平方根刻度，讓小客戶不會擠成一團）→</text>')
    out.append(f'<text x="{L-6}" y="{T+8}" text-anchor="end" class="tick">毛利率</text>')
    # zone labels
    out.append(f'<text x="{width-R-4}" y="{Y(0.9)-6:.1f}" text-anchor="end" class="zone">大額・高毛利：核心維護</text>')
    out.append(f'<text x="{width-R-4}" y="{Y(0.02)-6:.1f}" text-anchor="end" class="zone">大額・低毛利：檢討報價與成本</text>')
    pts = sorted(points, key=lambda p: -p["r"])
    for p in pts:
        r = 4 + math.sqrt(p["r"]) * 1.6
        x, y = X(p["x"]), Y(p["y"])
        title = f'{p["name"]}｜除佣 {wan(p["x"])}｜帳上毛利率 {pct(p["y"])}｜交易 {p["r"]} 筆｜{p["cls"]}'
        shape = {"既有": f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"', "新客": f'<path d="M{x:.1f} {y-r:.1f} L{x+r:.1f} {y:.1f} L{x:.1f} {y+r:.1f} L{x-r:.1f} {y:.1f}Z"', "回流": f'<rect x="{x-r*0.85:.1f}" y="{y-r*0.85:.1f}" width="{r*1.7:.1f}" height="{r*1.7:.1f}"'}
        out.append(shape.get(p["cls"], shape["既有"]) + f' class="pt st-{p["cls"]}"><title>{esc(title)}</title>' + ("</circle>" if p["cls"] == "既有" else ("</path>" if p["cls"] == "新客" else "</rect>")))
    for p in sorted(points, key=lambda p: -p["x"])[:labels_top]:
        x, y = X(p["x"]), Y(p["y"])
        nm = p["name"][:8]
        out.append(f'<text x="{x+8:.1f}" y="{y-8:.1f}" class="plabel">{esc(nm)}</text>')
    out.append('</svg>')
    legend = '<div class="legend"><span><i class="sw c" style="background:var(--co-sh)"></i>既有客戶（圓）</span><span><i class="sw d" style="background:var(--co-dw)"></i>新客（菱形）</span><span><i class="sw s" style="background:var(--co-bl)"></i>回流（方）</span><span class="muted">大小 = 交易筆數；虛線 = 16%（低毛利門檻）與 35%（標準毛利）</span></div>'
    return legend + "".join(out)

def svg_heatmap(rows, cols, get, width=760, cell_h=26, label_w=110, vfmt=wan, rowtotals=True):
    """rows: list of row labels; cols: list of col labels; get(r,c)->value or None."""
    vals = [float(get(r, c) or 0) for r in rows for c in cols]
    mv = max(vals) or 1
    n, m = len(rows), len(cols)
    tot_w = 90 if rowtotals else 0
    cw = (width - label_w - tot_w) / m
    h = (n + 1) * cell_h + 6
    ramp = ["#e8f0fb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
    def col(v):
        if v <= 0: return "var(--cell0)"
        t = v / mv
        i = min(len(ramp) - 1, int(t ** 0.7 * (len(ramp) - 1) + 0.999))
        return ramp[i]
    out = [f'<svg class="chart" viewBox="0 0 {width} {h}" width="100%" role="img">']
    for j, c in enumerate(cols):
        out.append(f'<text x="{label_w + j*cw + cw/2:.1f}" y="{cell_h*0.7:.1f}" text-anchor="middle" class="tick">{esc(c)}</text>')
    if rowtotals:
        out.append(f'<text x="{width-4}" y="{cell_h*0.7:.1f}" text-anchor="end" class="tick">合計</text>')
    for i, r in enumerate(rows):
        y = (i + 1) * cell_h
        out.append(f'<text x="{label_w-8}" y="{y+cell_h*0.68:.1f}" text-anchor="end" class="lbl">{esc(r)}</text>')
        rt = 0
        for j, c in enumerate(cols):
            v = float(get(r, c) or 0); rt += v
            x = label_w + j * cw
            fc = col(v)
            dark = v / mv > 0.45
            out.append(f'<rect x="{x+1:.1f}" y="{y+1}" width="{cw-2:.1f}" height="{cell_h-2}" rx="3" style="fill:{fc}"><title>{esc(r)} / {esc(c)}: {vfmt(v)}</title></rect>')
            if v > 0:
                out.append(f'<text x="{x+cw/2:.1f}" y="{y+cell_h*0.68:.1f}" text-anchor="middle" class="cellv{" inv" if dark else ""}">{vfmt(v)}</text>')
        if rowtotals:
            out.append(f'<text x="{width-4}" y="{y+cell_h*0.68:.1f}" text-anchor="end" class="val">{vfmt(rt)}</text>')
    out.append('</svg>')
    return "".join(out)

def svg_bridge(steps, width=720, bar_h=22, gap=10, label_w=170):
    """Horizontal waterfall. steps: list of (label, value, kind) kind in total/add/sub."""
    total_max = max(abs(sum(v for _, v, k in steps if k != 'total')), max(abs(v) for _, v, _ in steps)) or 1
    pw = width - label_w - 120
    h = len(steps) * (bar_h + gap) + 4
    out = [f'<svg class="chart" viewBox="0 0 {width} {h}" width="100%" role="img">']
    run = 0
    for i, (lab, v, kind) in enumerate(steps):
        y = i * (bar_h + gap) + 2
        if kind == 'total':
            x0, w, run = 0, abs(v), v
            col = "var(--acc)"
        elif kind == 'add':
            x0, w = run, v; run += v; col = "var(--good)"
        else:
            x0, w = run - v, v; run -= v; col = "var(--crit)"
        X = lambda val: label_w + val / total_max * pw
        out.append(f'<text x="{label_w-8}" y="{y+bar_h*0.7}" text-anchor="end" class="lbl">{esc(lab)}</text>')
        out.append(f'<rect x="{X(x0):.1f}" y="{y}" width="{max(w/total_max*pw,1):.1f}" height="{bar_h}" rx="2" style="fill:{col};opacity:{1 if kind=="total" else .85}"><title>{esc(lab)}: {wan(v)}</title></rect>')
        sign = "" if kind == 'total' else ("+" if kind == 'add' else "−")
        out.append(f'<text x="{X(x0 + w)+6:.1f}" y="{y+bar_h*0.7}" class="val">{sign}{wan(v)}</text>')
        if i < len(steps) - 1:
            out.append(f'<line x1="{X(run):.1f}" x2="{X(run):.1f}" y1="{y+bar_h}" y2="{y+bar_h+gap}" class="connector"/>')
    out.append('</svg>')
    return "".join(out)

def mini_stack(vals, cols, width=96, height=8):
    tot = sum(max(float(v or 0), 0) for v in vals) or 1
    x = 0; out = [f'<svg class="mini" viewBox="0 0 {width} {height}" width="{width}" height="{height}">']
    for v, c in zip(vals, cols):
        w = max(float(v or 0), 0) / tot * width
        if w <= 0: continue
        out.append(f'<rect x="{x:.1f}" y="0" width="{max(w-1,0):.1f}" height="{height}" style="fill:{c}"/>'); x += w
    out.append('</svg>'); return "".join(out)

def meter(p, width=88, height=8, cap=1.0):
    p = 0 if p is None else float(p)
    w = min(p, cap) / cap * width
    col = "var(--good)" if p >= 1 else ("var(--acc)" if p >= 0.6 else "var(--warn)")
    return f'<span class="meter"><svg viewBox="0 0 {width} {height}" width="{width}" height="{height}"><rect x="0" y="0" width="{width}" height="{height}" rx="4" class="track"/><rect x="0" y="0" width="{w:.1f}" height="{height}" rx="4" style="fill:{col}"/></svg><b>{pct(p,0)}</b></span>'

def sparkline(vals, width=84, height=22):
    vals = [float(v or 0) for v in vals]
    mv = max(vals) or 1
    n = len(vals); step = width / max(n - 1, 1)
    pts = " ".join(f"{i*step:.1f},{height-2 - v/mv*(height-4):.1f}" for i, v in enumerate(vals))
    last = vals[-1]
    return f'<svg class="mini" viewBox="0 0 {width} {height}" width="{width}" height="{height}"><polyline points="{pts}" class="spark"/><circle cx="{(n-1)*step:.1f}" cy="{height-2 - last/mv*(height-4):.1f}" r="2.5" class="sparkdot"/></svg>'

def yoy_chip(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return '<span class="chip flat">新</span>'
    return f'<span class="chip {delta_cls(v)}">{pct(v,0,True)}</span>'

# ----------------------------------------------------------------- data
ao = q("select * from v_as_of").iloc[0]
grp = q("select perf_year, sum(ext_net) ext_net, sum(booked_profit) booked_profit, sum(ic_add_back) ic_add_back, sum(group_profit) group_profit, sum(fixed_cost) fixed_cost, sum(net_profit) net_profit, sum(barter_net) barter_net, sum(deals) deals from v_group_month where perf_month<=%s and perf_year in (%s,%s) group by perf_year order by perf_year", (M, PY, YEAR)).set_index("perf_year")
gm = q("select * from v_group_month where perf_year=%s and perf_month<=%s order by perf_month", (YEAR, M))
comp = q("select company, perf_year, sum(ext_net) ext_net, sum(booked_profit) booked_profit, sum(ic_out) ic_out, sum(ic_in) ic_in, sum(fixed_cost) fixed_cost, sum(company_net_profit) company_net_profit, sum(net_cp) net_cp, sum(net_fresh) net_fresh, sum(net_radio) net_radio, sum(net_other) net_other, sum(barter_net) barter_net, max(active_salespeople) sp from v_company_month where perf_month<=%s and perf_year in (%s,%s) and company in ('聲活','東吳','鉑霖') group by 1,2", (M, PY, YEAR))
compm = q("select company, perf_month, ext_net, barter_net from v_company_month where perf_year=%s and perf_month<=%s and company in ('聲活','東吳','鉑霖') order by perf_month", (YEAR, M))

W0, W1 = f"{YEAR}-01-01", f"{YEAR}-{M:02d}-01"
P0, P1 = f"{PY}-01-01", f"{PY}-{M:02d}-01"
dw = q("select * from v_deal_summary where not is_barter and perf_ym between %s and %s", (W0, W1))
dp = q("select * from v_deal_summary where not is_barter and perf_ym between %s and %s", (P0, P1))
cy = q("select customer, status, months_since_last, industry, customer_category from v_customer_year where perf_year=%s", (YEAR,)).set_index("customer")
cyp = q("select customer, status from v_customer_year where perf_year=%s", (PY,)).set_index("customer")
NUM = ["ext_net","booked_profit","group_profit","net_profit","net_cp","net_fresh","net_radio","net_other"]
for c in NUM:
    dw[c] = dw[c].astype(float); dp[c] = dp[c].astype(float)

def agg_customers(df):
    g = df.groupby("customer")
    out = g[NUM].sum()
    out["deals"] = g.size(); out["active_months"] = g.perf_ym.nunique()
    out["main_salesperson"] = g.apply(lambda x: x.groupby("salesperson").ext_net.sum().idxmax())
    return out
cw = agg_customers(dw[dw.ext_net > 0]); cp = agg_customers(dp[dp.ext_net > 0])
cw["prev_net"] = cp.ext_net.reindex(cw.index)
cw["yoy_pct"] = (cw.ext_net - cw.prev_net) / cw.prev_net.abs()
cw = cw.join(cy[["status","months_since_last","industry","customer_category"]], how="left")
cw["status"] = cw["status"].fillna("既有")
cw = cw.sort_values("ext_net", ascending=False)
cw["rank_in_year"] = range(1, len(cw)+1)
cw["share"] = cw.ext_net / cw.ext_net.sum(); cw["cum_share"] = cw.share.cumsum()
cw["abc_tier"] = cw.cum_share.map(lambda s: "A" if s <= 0.8 else ("B" if s <= 0.95 else "C"))
cw["booked_margin"] = cw.booked_profit / cw.ext_net; cw["group_margin"] = cw.group_profit / cw.ext_net; cw["net_margin"] = cw.net_profit / cw.ext_net
cw["avg_deal"] = cw.ext_net / cw.deals
def hint(r):
    if r.booked_margin >= 0.35 and r.rank_in_year <= 20: return "核心：大額高毛利，優先維護"
    if r.booked_margin < 0.16 and r.rank_in_year <= 20: return "大額低毛利：檢討報價/成本"
    if r.booked_margin >= 0.35: return "小額高毛利：可擴大"
    if r.booked_margin < 0.16: return "小額低毛利：評估是否續做"
    return "一般"
cw["strategy_hint"] = cw.apply(hint, axis=1)
cw = cw.reset_index()
cust = cw
lost = cy[(cy.status == "流失風險")].copy()
lost["prev_year_net"] = cp.ext_net.reindex(lost.index)
lost["main_salesperson"] = cp.main_salesperson.reindex(lost.index)
churn = lost[lost.prev_year_net >= 300000].sort_values("prev_year_net", ascending=False).head(6).reset_index()
custcnt = dict(active=len(cw), newc=int((cw.status == "新客").sum()), back=int((cw.status == "回流").sum()), lost=int((cy.status == "流失風險").sum()), top10=float(cw.head(10).ext_net.sum()), total=float(cw.ext_net.sum()))
custcnt_py = dict(active=len(cp), newc=int((cyp.reindex(cp.index).status == "新客").sum()), top10=float(cp.sort_values("ext_net", ascending=False).head(10).ext_net.sum()), total=float(cp.ext_net.sum()))
custm_top = q("select customer, perf_month, ext_net from v_customer_month where perf_year=%s and perf_month<=%s and customer = any(%s) order by perf_month", (YEAR, M, cust.head(12)["customer"].tolist()))
abc = cw.groupby("abc_tier").agg(n=("customer","count"), net=("ext_net","sum"), gp=("booked_profit","sum")).reset_index()
ind_w = dw[dw.ext_net > 0].assign(industry=dw.industry.fillna("(未分類)"))
ind_p = dp[dp.ext_net > 0].assign(industry=dp.industry.fillna("(未分類)"))
ig = ind_w.groupby("industry").agg(customers=("customer","nunique"), deals=("deal_id","count"), ext_net=("ext_net","sum"), booked_profit=("booked_profit","sum")).reset_index()
ig["booked_margin"] = ig.booked_profit / ig.ext_net; ig["share"] = ig.ext_net / ig.ext_net.sum()
ig["prev"] = ig.industry.map(ind_p.groupby("industry").ext_net.sum()); ig["yoy_pct"] = (ig.ext_net - ig.prev) / ig.prev.abs()
ind = ig.sort_values("ext_net", ascending=False).reset_index(drop=True); ind["rank_in_year"] = range(1, len(ind)+1)
# salespeople
def agg_sp(df):
    g = df.groupby("salesperson")
    out = g[NUM + ["recognized_amount"]].sum()
    out["deals"] = g.size(); out["customers"] = g.customer.nunique()
    out["main_company"] = g.apply(lambda x: x.groupby("company").ext_net.sum().idxmax())
    out["main_group"] = g.apply(lambda x: x.groupby("business_group").ext_net.sum().idxmax())
    out["is_house"] = g.is_house.any()
    def top3(x):
        s = x.groupby("customer").ext_net.sum().sort_values(ascending=False); return pd.Series({"top3_net": s.head(3).sum(), "top_customer": s.index[0] if len(s) else None})
    out = out.join(g.apply(top3))
    return out
dw["recognized_amount"] = dw.recognized_amount.astype(float); dp["recognized_amount"] = dp.recognized_amount.astype(float)
sw = agg_sp(dw[dw.ext_net > 0]); spp = agg_sp(dp[dp.ext_net > 0])
sw["prev_net"] = spp.ext_net.reindex(sw.index); sw["yoy_pct"] = (sw.ext_net - sw.prev_net) / sw.prev_net.abs()
newc_by_sp = cw[cw.status == "新客"].groupby("main_salesperson").size()
sw["new_customers"] = newc_by_sp.reindex(sw.index).fillna(0).astype(int)
sw["barter_net"] = q("select salesperson, sum(ext_net) barter from v_deal_summary where is_barter and perf_ym between %s and %s group by 1", (W0, W1)).set_index("salesperson").barter.reindex(sw.index).fillna(0).astype(float)
sw["booked_margin"] = sw.booked_profit / sw.ext_net; sw["net_margin"] = sw.net_profit / sw.ext_net
sw["avg_deal"] = sw.ext_net / sw.deals; sw["top3_share"] = sw.top3_net / sw.ext_net
sw = sw.sort_values(["is_house","ext_net"], ascending=[True, False]).reset_index()
sw["rank_in_year"] = sw.groupby("is_house").cumcount() + 1
sw["share"] = sw.ext_net / sw.ext_net.sum()
sp = sw
spm = q("select salesperson, perf_month, ext_net from v_salesperson_month where perf_year=%s and perf_month<=%s and not is_house", (YEAR, M))
deals = q("select * from v_deal_summary where perf_year=%s and perf_ym<=%s and not is_barter", (YEAR, f"{YEAR}-{M:02d}-01"))
tgt = q("select * from v_target_progress order by company")
ipm = q("select coalesce(industry,'(未分類)') industry, main_platform_group pg, sum(ext_net) net from v_deal_summary where perf_year=%s and perf_ym<=%s and not is_barter and ext_net>0 group by 1,2", (YEAR, f"{YEAR}-{M:02d}-01"))

CO = {"聲活": "var(--co-sh)", "東吳": "var(--co-dw)", "鉑霖": "var(--co-bl)", "瑞迪": "var(--co-rd)"}
PG_COLS = ["var(--pg-1)", "var(--pg-2)", "var(--pg-3)", "var(--pg-4)"]
PG_NAMES = ["企頻", "新鮮視", "廣播", "其他"]

# ----------------------------------------------------------------- pieces
def kpi(label, value, sub=None, delta=None, cls=""):
    d = "" if delta is None else f'<span class="chip {delta_cls(delta)}">{pct(delta,1,True)} 同期</span>'
    s = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f'<div class="kpi {cls}"><div class="kpi-l">{label}</div><div class="kpi-v">{value}</div>{d}{s}</div>'

def yoy(cur, prev):
    if prev in (None, 0) or pd.isna(prev): return None
    return (float(cur) - float(prev)) / abs(float(prev))

def screen(title, chips, body):
    ch = "".join(f'<span class="fchip">{c}</span>' for c in chips)
    return f'<div class="screen"><div class="sbar"><span class="stitle">{title}</span><span class="sfilters">{ch}</span></div><div class="sbody">{body}</div></div>'

def table(headers, rows, cls=""):
    th = "".join(f'<th class="{a}">{h}</th>' for h, a in headers)
    trs = "".join("<tr>" + "".join(f'<td class="{headers[i][1]}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="tbl {cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'

# ================================================================= Section A 客戶分析
g26, g25 = grp.loc[YEAR], grp.loc[PY]
A_kpis = "".join([
    kpi("活躍客戶數", f"{int(custcnt['active'])}", f"同期 {int(custcnt_py['active'])}", yoy(custcnt['active'], custcnt_py['active'])),
    kpi("新客戶", f"{int(custcnt['newc'])}", "今年第一次有業績", None),
    kpi("流失風險", f"{int(custcnt['lost'])}", "去年有、今年尚無", None, "warn"),
    kpi("客戶平均貢獻", wan(float(custcnt['total'])/float(custcnt['active'])), f"同期 {wan(float(custcnt_py['total'])/float(custcnt_py['active']))}", yoy(float(custcnt['total'])/float(custcnt['active']), float(custcnt_py['total'])/float(custcnt_py['active']))),
    kpi("前 10 大客戶佔比", pct(float(custcnt['top10'])/float(custcnt['total'])), f"同期 {pct(float(custcnt_py['top10'])/float(custcnt_py['total']))}", None),
    kpi("帳上毛利率", pct(float(g26.booked_profit)/float(g26.ext_net)), f"集團毛利率 {pct(float(g26.group_profit)/float(g26.ext_net))}", None),
])
abc_rows = [{"lab": f"{r.abc_tier} 級（{'累計 80%' if r.abc_tier=='A' else ('80–95%' if r.abc_tier=='B' else '最後 5%')}）", "n": int(r.n), "net": float(r.net)} for r in abc.itertuples()]
A_abc = svg_hbars(abc_rows, "lab", "net", width=560, label_w=150, extra=lambda r: f"{wan(r['net'])}｜{r['n']} 家", color=lambda r: "var(--acc)" if r["lab"].startswith("A") else ("var(--acc-2)" if r["lab"].startswith("B") else "var(--acc-3)"))
ind_top = ind.head(8)
others = ind.iloc[8:]
ind_rows = [{"lab": r.industry, "net": float(r.ext_net), "bm": r.booked_margin, "c": int(r.customers), "yoy": r.yoy_pct} for r in ind_top.itertuples()]
if len(others): ind_rows.append({"lab": f"其他 {len(others)} 類", "net": float(others.ext_net.sum()), "bm": float(others.booked_profit.sum())/float(others.ext_net.sum()), "c": int(others.customers.sum()), "yoy": None})
A_ind = svg_hbars(ind_rows, "lab", "net", width=560, label_w=110, extra=lambda r: f"{wan(r['net'])}｜{r['c']} 家｜毛利率 {pct(r['bm'])}", color="var(--acc)")
pts = [{"x": float(r.ext_net), "y": float(r.booked_margin if r.booked_margin is not None else 0), "r": int(r.deals), "cls": r.status if r.status in ("新客","回流") else "既有", "name": r.customer} for r in cust.itertuples()]
A_scatter = svg_scatter(pts, width=1140, height=380, xmax=float(cust.ext_net.max()) * 1.06)
sp_months = {}
for r in custm_top.itertuples(): sp_months.setdefault(r.customer, [0]*M)[int(r.perf_month)-1] = float(r.ext_net or 0)
A_rows = []
for r in cust.head(12).itertuples():
    A_rows.append([
        f"{r.rank_in_year}", f'<b>{esc(r.customer)}</b><div class="sub">{esc(r.industry or "未分類")}・{esc(r.main_salesperson)}</div>',
        f'<span class="tag {esc(r.status)}">{esc(r.status)}</span>',
        money(r.ext_net), yoy_chip(r.yoy_pct), f'{pct(r.share)}<div class="sub">累計 {pct(r.cum_share)}</div>',
        money(r.booked_profit), pct(r.booked_margin), pct(r.net_margin),
        f"{int(r.deals)} 筆<div class='sub'>{int(r.active_months)} 個月</div>", money(r.avg_deal),
        mini_stack([r.net_cp, r.net_fresh, r.net_radio, r.net_other], PG_COLS), sparkline(sp_months.get(r.customer, [0]*M)),
        f'<span class="hint">{esc(r.strategy_hint)}</span>'
    ])
A_table = table([("#","n"),("客戶 / 產業 / 主要業務","t"),("狀態","t"),("除佣實收","n"),("同期","n"),("佔比","n"),("帳上毛利","n"),("毛利率","n"),("集團淨利率","n"),("頻率","n"),("平均單筆","n"),("平台組合","t"),("月趨勢","t"),("策略提示","t")], A_rows)
churn_rows = [[f'<b>{esc(r.customer)}</b><div class="sub">{esc(r.industry or "未分類")}・{esc(r.main_salesperson)}</div>', money(r.prev_year_net), f"{int(r.months_since_last)} 個月"] for r in churn.itertuples()]
A_churn = table([("客戶","t"),("去年除佣實收","n"),("距上次交易","n")], churn_rows, "compact")
A_screen = screen("客戶分析", [f"期間 {YEAR}/01–{YEAR}/{M:02d}", "同期 2025/01–09", "公司 全部", "產業 全部", "排除交換 ✓", "排除內部轉撥 ✓"], f"""
<div class="kpis">{A_kpis}</div>
<div class="grid2">
  <figure><figcaption>客戶分級（ABC）：多少客戶貢獻了 80% 業績</figcaption>{A_abc}</figure>
  <figure><figcaption>產業別：業績、客戶數、毛利率</figcaption>{A_ind}</figure>
</div>
<figure><figcaption>客戶價值矩陣：金額 × 毛利率 × 頻率 × 狀態（每個點是一個客戶，滑鼠移上去看名字）</figcaption>{A_scatter}</figure>
<figure><figcaption>客戶排名（前 12；完整表可捲動、可下載）</figcaption>{A_table}
<div class="legend pg"><span><i style="background:var(--pg-1)"></i>企頻</span><span><i style="background:var(--pg-2)"></i>新鮮視</span><span><i style="background:var(--pg-3)"></i>廣播</span><span><i style="background:var(--pg-4)"></i>其他</span></div></figure>
<div class="grid2">
  <figure><figcaption>⚠ 流失風險：去年 ≥ 30 萬、今年尚無業績</figcaption>{A_churn}</figure>
  <div class="note-box"><b>點任一客戶 → 客戶頁</b><ul><li>24 個月業績與毛利趨勢</li><li>歷年同期比較（沿用舊「客戶同期比較表」邏輯）</li><li>訂單清單（連到銷售分析）</li><li>經手業務變動、平台組合變化</li></ul></div>
</div>""")

# ================================================================= Section B 業務分析
spn = sp[~sp.is_house]
house = sp[sp.is_house]
B_kpis = "".join([
    kpi("有業績的業務", f"{len(spn)} 人", f"公司戶另計 {wan(float(house.ext_net.sum()))}", None),
    kpi("人均除佣實收", wan(float(spn.ext_net.sum())/len(spn)), f"人均帳上毛利 {wan(float(spn.booked_profit.sum())/len(spn))}", None),
    kpi("人均客戶數", f"{spn.customers.sum()/len(spn):.1f}", f"人均新客 {spn.new_customers.sum()/len(spn):.1f}", None),
    kpi("業務業績合計", wan(float(spn.ext_net.sum())), f"帳上毛利率 {pct(float(spn.booked_profit.sum())/float(spn.ext_net.sum()))}", None),
    kpi("交換（另計）", wan(float(sp.barter_net.sum())), "不計入排名與毛利", None, "muted"),
])
mx = float(spn.ext_net.max())
B_rows = []
for r in spn.head(10).itertuples():
    bar = f'<div class="bar"><i style="width:{float(r.ext_net)/mx*100:.0f}%;background:{CO.get(r.main_company,"var(--acc)")}"></i></div>'
    dep = float(r.top3_share or 0)
    depcls = "crit" if dep >= 0.7 else ("warn" if dep >= 0.5 else "")
    B_rows.append([
        f"{r.rank_in_year}", f'<b>{esc(r.salesperson)}</b><div class="sub">{esc(r.main_company)}・{esc(r.main_group)}</div>',
        f"{money(r.ext_net)}{bar}", yoy_chip(r.yoy_pct), pct(r.share),
        money(r.booked_profit), pct(r.booked_margin), pct(r.net_margin), money(r.recognized_amount),
        f"{int(r.customers)}<div class='sub'>新客 {int(r.new_customers)}</div>", f"{int(r.deals)}<div class='sub'>{money(r.avg_deal)}/筆</div>",
        f'<span class="dep {depcls}">{pct(dep,0)}</span><div class="sub">{esc((r.top_customer or "")[:8])}</div>',
        mini_stack([r.net_cp, r.net_fresh, r.net_radio, r.net_other], PG_COLS),
        money(r.barter_net) if r.barter_net else "–",
    ])
B_table = table([("#","n"),("業務 / 公司 / 組別","t"),("除佣實收","n"),("同期","n"),("佔比","n"),("帳上毛利","n"),("毛利率","n"),("集團淨利率","n"),("認定業績","n"),("客戶數","n"),("訂單數","n"),("前 3 大客戶依賴度","n"),("平台組合","t"),("交換","n")], B_rows)
top8 = spn.head(8).salesperson.tolist()
hm = {(r.salesperson, int(r.perf_month)): float(r.ext_net or 0) for r in spm.itertuples()}
B_heat = svg_heatmap(top8, [f"{m}月" for m in range(1, M+1)], lambda r, c: hm.get((r, int(c[:-1])), 0), width=1140, cell_h=24)
B_screen = screen("業務分析", [f"期間 {YEAR}/01–{YEAR}/{M:02d}", "同期 2025/01–09", "公司 全部", "排除交換 ✓", "公司戶（Company）另列"], f"""
<div class="kpis">{B_kpis}</div>
<figure><figcaption>業務排名：量（金額、佔比）與質（毛利率、新客、依賴度）並列</figcaption>{B_table}</figure>
<figure><figcaption>業務 × 月 熱圖：一眼看出季節性與穩定度（顏色深 = 金額大）</figcaption>{B_heat}</figure>
<div class="note-box"><b>點任一業務 → 個人頁</b><ul><li>月業績認定表（沿用舊格式，可列印）</li><li>客戶組合：前 10 大客戶與同期比較、新客 / 流失清單</li><li>目標達成：年度 / 季目標、達成率、剩餘月份每月需達</li><li>預估（pipeline）：進單 + 預估 vs 目標</li><li>獎金試算（沿用簡易獎金）</li></ul></div>""")

# ================================================================= Section C 銷售分析
d_all = deals.copy()
for c in ["ext_net","booked_profit","net_profit","booked_cost"]: d_all[c] = d_all[c].astype(float)
d = d_all[d_all.ext_net > 0].copy()
zero = d_all[d_all.ext_net <= 0]
C_kpis = "".join([
    kpi("有收入的訂單", f"{len(d)}", f"同期 {int(g25.deals)}", None),
    kpi("平均單筆", wan(float(d.ext_net.mean())), f"中位數 {wan(float(d.ext_net.median()))}", None),
    kpi("大單（≥100 萬）", f"{int((d.ext_net>=1_000_000).sum())} 筆", f"佔業績 {pct(float(d[d.ext_net>=1_000_000].ext_net.sum())/float(d.ext_net.sum()))}", None),
    kpi("低毛利訂單（<16%）", f"{int(d.is_low_margin.sum())} 筆", f"佔業績 {pct(float(d[d.is_low_margin].ext_net.sum())/float(d.ext_net.sum()))}", None, "warn"),
    kpi("零收入成本單", f"{len(zero)} 筆", f"成本 {wan(float(zero.booked_cost.sum()))}（製作費、營運）", None, "warn"),
    kpi("帳上毛利率（含成本單）", pct(float(d_all.booked_profit.sum())/float(d_all.ext_net.sum())), f"只看有收入訂單 {pct(float(d.booked_profit.sum())/float(d.ext_net.sum()))}", None),
])
sb = d.groupby("size_bucket").agg(n=("deal_id","count"), net=("ext_net","sum"), gp=("booked_profit","sum")).reset_index().sort_values("size_bucket")
sb_rows = [{"lab": r.size_bucket[3:], "net": float(r.net), "n": int(r.n), "bm": float(r.gp)/float(r.net)} for r in sb.itertuples()]
sb_rows.append({"lab": "零收入", "net": 0.0, "n": len(zero), "bm": float("nan")})
C_size = svg_hbars(sb_rows, "lab", "net", width=560, label_w=80, extra=lambda r: (f"{wan(r['net'])}｜{r['n']} 筆｜毛利率 {pct(r['bm'])}" if r["net"] > 0 else f"{r['n']} 筆（只有成本，見 KPI）"))
def band(m):
    m = float(m or 0)
    return "1. <0%（虧損）" if m < 0 else "2. 0–16%（低毛利）" if m < 0.16 else "3. 16–35%" if m < 0.35 else "4. 35–50%" if m < 0.5 else "5. >50%"
d = d.assign(band=d.booked_margin.map(band))
mb = d.groupby("band").agg(n=("deal_id","count"), net=("ext_net","sum")).reset_index().sort_values("band")
mb_rows = [{"lab": r.band[3:], "net": float(r.net), "n": int(r.n)} for r in mb.itertuples()]
C_band = svg_hbars(mb_rows, "lab", "net", width=560, label_w=110, extra=lambda r: f"{wan(r['net'])}｜{r['n']} 筆", color=lambda r: "var(--crit)" if r["lab"].startswith("<0") else ("var(--warn)" if r["lab"].startswith("0–16") else "var(--acc)"))
ind_order = ipm.groupby("industry").net.sum().sort_values(ascending=False).head(9).index.tolist()
ipm_map = {(r.industry, r.pg): float(r.net) for r in ipm.itertuples()}
pgs = ["企頻", "新鮮視", "廣播"]
C_matrix = svg_heatmap(ind_order, pgs + ["其他"], lambda r, c: ipm_map.get((r, c), 0) if c != "其他" else sum(v for (i, p), v in ipm_map.items() if i == r and p not in pgs), width=1140, label_w=130, cell_h=24)
top = d.sort_values("ext_net", ascending=False).head(10)
C_rows = []
for i, r in enumerate(top.itertuples(), 1):
    C_rows.append([f"{i}", f'<b>{esc(r.contract_no)}</b><div class="sub">{esc((r.ad_name or "")[:16])}</div>', f'{esc(r.customer)}<div class="sub">{esc(r.industry or "未分類")}</div>', f'{esc(r.salesperson)}<div class="sub">{esc(r.company)}</div>', esc(r.platform_groups), r.perf_ym_text, money(r.ext_net), money(r.booked_cost), money(r.booked_profit), pct(r.booked_margin), pct(r.net_margin), money(r.production_cost) if r.production_cost else "–"])
C_top = table([("#","n"),("合約 / 廣告","t"),("客戶 / 產業","t"),("業務 / 公司","t"),("平台","t"),("年月","t"),("除佣實收","n"),("實付","n"),("帳上毛利","n"),("毛利率","n"),("集團淨利率","n"),("製作費","n")], C_rows)
low = d[(d.ext_net >= 100000)].sort_values("booked_margin").head(6)
L_rows = [[f'<b>{esc(r.contract_no)}</b><div class="sub">{esc((r.ad_name or "")[:16])}</div>', f'{esc(r.customer)}<div class="sub">{esc(r.salesperson)}・{esc(r.company)}</div>', esc(r.platform_groups), money(r.ext_net), money(r.booked_cost), f'<span class="dep crit">{pct(r.booked_margin)}</span>', "已處理" if r.deal_id in set() else '<span class="tag 流失風險">待說明</span>'] for r in low.itertuples()]
C_low = table([("合約 / 廣告","t"),("客戶 / 業務","t"),("平台","t"),("除佣實收","n"),("實付","n"),("毛利率","n"),("低毛利原因","t")], L_rows, "compact")
C_screen = screen("銷售分析", [f"期間 {YEAR}/01–{YEAR}/{M:02d}", "公司 全部", "平台 全部", "產業 全部", "金額級距 全部", "排除交換 ✓", "公司戶 含"], f"""
<div class="kpis">{C_kpis}</div>
<div class="grid2">
  <figure><figcaption>訂單金額分佈：錢集中在哪個級距</figcaption>{C_size}</figure>
  <figure><figcaption>毛利率分佈：有多少業績是在低毛利下做的</figcaption>{C_band}</figure>
</div>
<figure><figcaption>產業 × 平台歸類：業績矩陣（除佣實收；產業取前 9）</figcaption>{C_matrix}</figure>
<figure><figcaption>訂單排名（依除佣實收，前 10；可切換依毛利 / 毛利率 / 產業排序）</figcaption>{C_top}</figure>
<figure><figcaption>⚠ 低毛利訂單（≥10 萬、毛利率最低 6 筆）— 對應舊系統的「低毛利原因登錄」</figcaption>{C_low}</figure>""")

# ================================================================= Section D 公司分析
c26 = comp[comp.perf_year == YEAR].set_index("company"); c25 = comp[comp.perf_year == PY].set_index("company")
def cokpi(name):
    r = c26.loc[name]; p = c25.loc[name] if name in c25.index else None
    yy = yoy(r.ext_net, p.ext_net) if p is not None else None
    extra = f"轉撥給聲活 {wan(r.ic_out)}" if float(r.ic_out) > 0 else (f"收到轉撥 {wan(r.ic_in)}・固定成本 {wan(r.fixed_cost)}" if float(r.ic_in) > 0 else "")
    return f'<div class="kpi co" style="--co:{CO[name]}"><div class="kpi-l"><i class="dot"></i>{name}</div><div class="kpi-v">{wan(r.ext_net)}</div><span class="chip {delta_cls(yy)}">{pct(yy,1,True)} 同期</span><div class="kpi-sub">帳上毛利 {wan(r.booked_profit)}（{pct(float(r.booked_profit)/float(r.ext_net))}）<br>{extra}</div></div>'
D_kpis = "".join([cokpi("聲活"), cokpi("東吳"), cokpi("鉑霖"),
    f'<div class="kpi total"><div class="kpi-l">集團合併</div><div class="kpi-v">{wan(g26.ext_net)}</div><span class="chip {delta_cls(yoy(g26.ext_net,g25.ext_net))}">{pct(yoy(g26.ext_net,g25.ext_net),1,True)} 同期</span><div class="kpi-sub">集團毛利 {wan(g26.group_profit)}（{pct(float(g26.group_profit)/float(g26.ext_net))}）<br>扣固定成本後淨利 {wan(g26.net_profit)}（{pct(float(g26.net_profit)/float(g26.ext_net))}）</div></div>'])
months = [f"{m}月" for m in range(1, M+1)]
series = []
for name in ["聲活", "東吳", "鉑霖"]:
    vals = [0]*M
    for r in compm[compm.company == name].itertuples(): vals[int(r.perf_month)-1] = float(r.ext_net or 0)
    series.append((name, CO[name], vals))
D_cols = svg_stacked_columns(months, series, width=560, height=250)
bridge = [("各公司帳上毛利合計", float(g26.booked_profit), "total"), ("＋ 加回子公司付聲活的轉撥", float(g26.ic_add_back), "add"), ("＝ 集團毛利", float(g26.group_profit), "total"), ("－ 平台固定成本", float(g26.fixed_cost), "sub"), ("＝ 集團淨利", float(g26.net_profit), "total")]
D_bridge = svg_bridge(bridge, width=560, label_w=190)
T_rows = []
for r in tgt.itertuples():
    T_rows.append([f'<b style="color:{CO.get(r.company,"inherit")}">{esc(r.company)}</b>', esc(r.period_label), "企頻＋新鮮視・不含公司戶", money(r.target_amount), money(r.actual), money(r.remaining), meter(r.achieved_pct), "已結束" if r.months_left == 0 else f"{r.months_left} 個月・每月需 {money(r.required_monthly)}"])
D_target = table([("公司","t"),("期間","t"),("範圍","t"),("目標","n"),("進單","n"),("待追","n"),("達成率","t"),("剩餘 / 每月需達","t")], T_rows, "compact")
rows_pg = []
for name in ["聲活", "東吳", "鉑霖"]:
    r = c26.loc[name]
    tot = float(r.ext_net)
    rows_pg.append([f'<b style="color:{CO[name]}">{name}</b>', money(r.net_cp), money(r.net_fresh), money(r.net_radio), money(r.net_other), money(tot), mini_stack([r.net_cp, r.net_fresh, r.net_radio, r.net_other], PG_COLS, width=120), pct(float(r.booked_profit)/tot), f"{int(r.sp)} 人", wan(tot/max(int(r.sp),1))])
D_pg = table([("公司","t"),("企頻","n"),("新鮮視","n"),("廣播","n"),("其他","n"),("合計","n"),("組合","t"),("帳上毛利率","n"),("業務人數","n"),("人均產值","n")], rows_pg, "compact")
D_screen = screen("公司分析", [f"期間 {YEAR}/01–{YEAR}/{M:02d}", "同期 2025/01–09", "排除交換 ✓", "內部轉撥：集團層還原"], f"""
<div class="kpis co4">{D_kpis}</div>
<div class="grid2">
  <figure><figcaption>各公司月業績（除佣實收，對外）</figcaption>{D_cols}</figure>
  <figure><figcaption>三層毛利橋：帳上 → 集團 → 淨利（{YEAR} 1–{M} 月）</figcaption>{D_bridge}<p class="fig-note">2025 尚未設定固定成本規則，淨利同期比較待規則補齊後顯示。</p></figure>
</div>
<figure><figcaption>目標達成（老闆儀表板的口徑：企頻＋新鮮視、不含公司戶、不含交換）</figcaption>{D_target}</figure>
<figure><figcaption>公司 × 平台歸類：業績結構與人均產值</figcaption>{D_pg}
<div class="legend pg"><span><i style="background:var(--pg-1)"></i>企頻</span><span><i style="background:var(--pg-2)"></i>新鮮視</span><span><i style="background:var(--pg-3)"></i>廣播</span><span><i style="background:var(--pg-4)"></i>其他</span></div></figure>""")

# ================================================================= common definitions block
DEF = f"""
<div class="defs">
  <div class="def"><div class="def-k">帳上毛利</div><div class="def-v">除佣實收 − 實付</div><div class="def-n">各公司帳上看到的數字，等於舊系統的「帳上毛利」。子公司的實付裡含付給聲活的 65 折。<br><b>{YEAR} 1–{M} 月：{wan(g26.booked_profit)}（{pct(float(g26.booked_profit)/float(g26.ext_net))}）</b></div></div>
  <div class="def"><div class="def-k">集團毛利</div><div class="def-v">對外收入 − 對外成本</div><div class="def-n">把子公司付給聲活的轉撥加回來（那是集團內部的錢）。就是喬商年度發稿明細裡「聲活」那一組欄位的集團版。<br><b>{wan(g26.group_profit)}（{pct(float(g26.group_profit)/float(g26.ext_net))}）</b></div></div>
  <div class="def"><div class="def-k">集團淨利</div><div class="def-v">集團毛利 − 平台固定成本</div><div class="def-n">企頻 75 萬/月、新鮮視 100 萬/月依規則表扣除；訂單與客戶層按當月該平台業績比例分攤，所以每張訂單都有「集團淨利率」。<br><b>{wan(g26.net_profit)}（{pct(float(g26.net_profit)/float(g26.ext_net))}）</b></div></div>
</div>
<div class="defs small">
  <div class="def"><div class="def-k">預設排除</div><div class="def-n"><b>內部轉撥線</b>（組別 聲活-東 / 聲活-鉑）不算客戶、業務、訂單；<b>交換</b>（業務名稱結尾「換」或廣告名稱含「交換」，{YEAR} 1–{M} 月 {wan(g26.barter_net)}）另欄顯示；<b>公司戶</b>（業務 = Company）在業務分析另列，不參與排名。</div></div>
  <div class="def"><div class="def-k">同期比較</div><div class="def-n">今年 YTD（1–{M} 月）一律對比去年同一段（2025 1–{M} 月），不是對比去年全年；每張表的「同期」欄都是這個口徑。</div></div>
  <div class="def"><div class="def-k">狀態定義</div><div class="def-n"><b>新客</b> = 今年第一次有業績；<b>既有</b> = 去年也有；<b>回流</b> = 更早有、去年沒有、今年又有；<b>流失風險</b> = 去年有、今年到目前為止沒有（年度結束後轉為「流失」）。</div></div>
</div>"""

MAP_rows = [
 ["公司業績儀表板（Q3 目標 / 達成率 / 月堆疊）", "公司分析：KPI + 月業績堆疊 + 目標達成表", "目標改由系統存放，加「剩餘月份每月需達」"],
 ["進單＋預估 大總表 / 進單總表分業務", "公司分析（進單＋預估 view）／業務分析熱圖", "預估改進系統，不再靠線上表單彙整"],
 ["企頻 1–9 月實收帳上毛利報表", "公司分析：公司 × 平台歸類矩陣", "交換另欄，不混在合計裡"],
 ["統一週報（單一客戶年度進單 vs 預估）", "客戶頁：24 個月趨勢 + 預估", "任何客戶都能看，不用另外做表"],
 ["喬商・彥星年度發稿明細（三組毛利欄）", "客戶頁訂單清單：帳上 / 集團 / 淨利三欄", "同一套定義自動算，不用手填 65 折"],
 ["舊系統：綜合成本毛利分析", "公司分析：公司 × 平台歸類；銷售分析：明細", "保留列印版"],
 ["舊系統：客戶同期比較表", "客戶分析排名表的「同期」欄 + 客戶頁", ""],
 ["舊系統：業務發稿統計報表", "業務分析排名表（客戶數、訂單數、平均單筆、毛利率）", "加新客數、依賴度"],
 ["舊系統：業績認定表 / 責任檔達成表", "業務個人頁（沿用格式）", ""],
 ["舊系統：媒體發稿量客戶版 / 電台總表", "銷售分析：平台 / 電台維度篩選", ""],
 ["舊系統：低毛利原因登錄", "銷售分析：低毛利訂單清單（可直接填原因）", ""],
]
MAP = table([("現在的報表","t"),("新系統對應","t"),("差異","t")], [[esc(a), esc(b), esc(c)] for a, b, c in MAP_rows], "compact")

# ================================================================= page
CSS = r"""
:root{
  --bg:#f5f7fa; --panel:#ffffff; --panel-2:#eef2f7; --ink:#151a21; --ink-2:#5a6472; --ink-3:#8b95a3; --line:#dfe4ec; --line-2:#cbd3de;
  --acc:#2a78d6; --acc-2:#6da7ec; --acc-3:#b7d3f6; --acc-ink:#1c5cab;
  --co-sh:#2a78d6; --co-dw:#1baf7a; --co-bl:#eb6834; --co-rd:#4a3aa7;
  --pg-1:#4a3aa7; --pg-2:#6353bc; --pg-3:#8377cf; --pg-4:#a49bdf;
  --good:#0ca30c; --warn:#fab219; --crit:#d03b3b; --cell0:#f0f2f5;
  --serif:"Noto Serif TC","Songti TC","PMingLiU",serif; --sans:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif; --num:"IBM Plex Sans","Noto Sans TC",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#12161c; --panel:#191e26; --panel-2:#222932; --ink:#eef2f7; --ink-2:#aab4c2; --ink-3:#7b8695; --line:#2b333e; --line-2:#3a4450;
  --acc:#3987e5; --acc-2:#5598e7; --acc-3:#1c5cab; --acc-ink:#9ec5f4;
  --co-sh:#3987e5; --co-dw:#199e70; --co-bl:#d95926; --co-rd:#9085e9;
  --pg-1:#6f62cf; --pg-2:#8a7fdf; --pg-3:#a59ceb; --pg-4:#c2bbf3; --cell0:#1f2530;
}}
:root[data-theme="dark"]{
  --bg:#12161c; --panel:#191e26; --panel-2:#222932; --ink:#eef2f7; --ink-2:#aab4c2; --ink-3:#7b8695; --line:#2b333e; --line-2:#3a4450;
  --acc:#3987e5; --acc-2:#5598e7; --acc-3:#1c5cab; --acc-ink:#9ec5f4;
  --co-sh:#3987e5; --co-dw:#199e70; --co-bl:#d95926; --co-rd:#9085e9;
  --pg-1:#6f62cf; --pg-2:#8a7fdf; --pg-3:#a59ceb; --pg-4:#c2bbf3; --cell0:#1f2530;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.6;padding-block:0 64px;padding-inline:clamp(16px,4vw,40px)}
.wrap{max-width:1180px;margin:0 auto}
h1,h2,h3{font-family:var(--serif);font-weight:700;letter-spacing:.01em;text-wrap:balance;margin:0}
h1{font-size:clamp(28px,4vw,40px);line-height:1.2}
h2{font-size:24px;line-height:1.3}
h3{font-size:17px}
p{margin:0}
.masthead{padding-block:44px 28px;border-bottom:1px solid var(--line-2);display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2);font-family:var(--num);margin-bottom:10px}
.masthead p.lede{max-width:64ch;color:var(--ink-2);margin-top:12px;font-size:15px}
.meta{font-family:var(--num);font-size:12px;color:var(--ink-3);text-align:right;line-height:1.7}
section{padding-block:40px 8px}
.sec-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:28px;align-items:start;margin-bottom:22px}
.sec-head .no{font-family:var(--num);font-size:12px;letter-spacing:.14em;color:var(--acc-ink);margin-bottom:6px}
.sec-head .why{color:var(--ink-2);font-size:14px}
.qa{border-left:2px solid var(--acc);padding-left:14px;display:grid;gap:8px}
.qa div{display:grid;grid-template-columns:auto 1fr;gap:10px;font-size:13.5px}
.qa b{font-family:var(--serif);color:var(--ink)}
.qa span{color:var(--ink-2)}
.principles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:20px}
.pr{background:var(--panel);border:1px solid var(--line);padding:16px 18px}
.pr b{display:block;font-family:var(--serif);font-size:15px;margin-bottom:6px}
.pr span{color:var(--ink-2);font-size:13px}
.defs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:18px}
.defs.small .def-n{font-size:12.5px}
.def{background:var(--panel);border:1px solid var(--line);padding:16px 18px}
.def-k{font-family:var(--serif);font-size:16px}
.def-v{font-family:var(--num);color:var(--acc-ink);margin:4px 0 8px;font-weight:600}
.def-n{color:var(--ink-2);font-size:13px}
.screen{background:var(--panel);border:1px solid var(--line-2);box-shadow:0 1px 0 var(--line), 0 12px 32px -20px rgba(0,0,0,.35);margin-top:8px}
.sbar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel-2)}
.stitle{font-weight:700;font-size:14px}
.sfilters{display:flex;flex-wrap:wrap;gap:6px}
.fchip{font-size:11.5px;font-family:var(--num);border:1px solid var(--line-2);border-radius:999px;padding:1px 9px;color:var(--ink-2);background:var(--panel)}
.sbody{padding:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--panel-2);padding:12px 14px;border-top:2px solid var(--line-2)}
.kpi.warn{border-top-color:var(--warn)} .kpi.muted{opacity:.8} .kpi.total{border-top-color:var(--ink)}
.kpi.co{border-top-color:var(--co)}
.kpi .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--co);margin-right:6px;vertical-align:1px}
.kpi-l{font-size:12px;color:var(--ink-2)}
.kpi-v{font-family:var(--num);font-size:24px;font-weight:600;line-height:1.2;margin:4px 0 4px;font-variant-numeric:tabular-nums}
.kpi-sub{font-size:11.5px;color:var(--ink-3);margin-top:4px;font-family:var(--num)}
.chip{display:inline-block;font-family:var(--num);font-size:11.5px;padding:0 6px;border-radius:4px;font-variant-numeric:tabular-nums;background:var(--panel)}
.chip.up{color:#0a7a0a;background:rgba(12,163,12,.12)} .chip.down{color:#b32d2d;background:rgba(208,59,59,.12)} .chip.flat{color:var(--ink-2)}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
figure{margin:0 0 18px;min-width:0}
figcaption{font-size:13px;font-weight:600;margin-bottom:8px;color:var(--ink)}
.fig-note{font-size:12px;color:var(--ink-3);margin-top:6px}
.chart{display:block;max-width:100%;height:auto;font-family:var(--num)}
.chart .lbl{font-size:12px;fill:var(--ink);font-family:var(--sans)}
.chart .val{font-size:11.5px;fill:var(--ink-2);font-variant-numeric:tabular-nums}
.chart .tick{font-size:11px;fill:var(--ink-3)}
.chart .grid{stroke:var(--line);stroke-width:1} .chart .grid.strong{stroke:var(--line-2);stroke-dasharray:3 3}
.chart .axis{stroke:var(--line-2)}
.chart .zone{font-size:11px;fill:var(--ink-3);font-family:var(--sans)}
.chart .plabel{font-size:11px;fill:var(--ink);font-family:var(--sans)}
.chart .cellv{font-size:10.5px;fill:var(--ink-2)} .chart .cellv.inv{fill:#fff}
.chart .connector{stroke:var(--line-2);stroke-dasharray:2 2}
.chart .pt{opacity:.85;stroke:var(--panel);stroke-width:1.5} .chart .pt:hover{opacity:1}
.st-既有{fill:var(--co-sh)} .st-新客{fill:var(--co-dw)} .st-回流{fill:var(--co-bl)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--ink-2);margin:6px 0 4px;font-family:var(--num)}
.legend i{display:inline-block;width:10px;height:10px;margin-right:5px;vertical-align:-1px;border-radius:2px}
.legend .sw.c{border-radius:50%} .legend .sw.d{transform:rotate(45deg) scale(.8)} .legend .sw.s{border-radius:1px}
.legend .muted{color:var(--ink-3)}
.tbl-wrap{overflow-x:auto}
.tbl{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
.tbl th{font-weight:600;color:var(--ink-2);text-align:left;padding:6px 8px;border-bottom:1px solid var(--line-2);white-space:nowrap;font-size:11.5px}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
.tbl th.n,.tbl td.n{text-align:right;font-family:var(--num)}
.tbl tbody tr:hover td{background:var(--panel-2)}
.tbl .sub{font-size:11px;color:var(--ink-3);font-weight:400}
.tbl.compact td{padding:5px 8px}
.tag{font-size:11px;padding:0 6px;border-radius:3px;border:1px solid var(--line-2);color:var(--ink-2)}
.tag.新客{border-color:var(--co-dw);color:var(--co-dw)} .tag.回流{border-color:var(--co-bl);color:var(--co-bl)} .tag.流失風險{border-color:var(--warn);color:#8a5d00}
.hint{font-size:11px;color:var(--ink-2);white-space:normal;display:inline-block;max-width:150px;line-height:1.35}
.bar{height:5px;background:var(--panel-2);margin-top:3px;width:120px}
.bar i{display:block;height:100%}
.dep{font-weight:600} .dep.warn{color:#8a5d00} .dep.crit{color:var(--crit)}
.meter{display:inline-flex;align-items:center;gap:6px} .meter .track{fill:var(--panel-2)} .meter b{font-family:var(--num);font-size:12px}
.mini{vertical-align:middle}
.spark{fill:none;stroke:var(--acc);stroke-width:1.5} .sparkdot{fill:var(--acc)}
.note-box{background:var(--panel-2);padding:14px 16px;font-size:13px;color:var(--ink-2)}
.note-box b{color:var(--ink)} .note-box ul{margin:6px 0 0;padding-left:18px} .note-box li{margin:2px 0}
.caveats{background:var(--panel);border:1px solid var(--line);padding:18px 22px;margin-top:18px;font-size:13.5px;color:var(--ink-2)}
.caveats ol{margin:8px 0 0;padding-left:20px} .caveats li{margin:4px 0}
.impl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:16px}
.impl .pr{padding:16px 18px}
code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;background:var(--panel-2);padding:0 4px;border-radius:3px}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line-2);font-size:12px;color:var(--ink-3);font-family:var(--num)}
@media (max-width:820px){ .masthead,.sec-head,.grid2,.impl{grid-template-columns:1fr} .principles,.defs{grid-template-columns:1fr} .meta{text-align:left} }
@media (prefers-reduced-motion: no-preference){ .chart .pt{transition:opacity .15s} }
"""

def sec(no, title, why, qas, screen_html):
    qa = "".join(f'<div><b>{q}</b><span>{a}</span></div>' for q, a in qas)
    return f"""<section id="{no}"><div class="sec-head"><div><div class="no">{no}</div><h2>{title}</h2><p class="why">{why}</p></div><div class="qa">{qa}</div></div>{screen_html}</section>"""

A = sec("REPORT A", "客戶分析", "老闆問「客戶」時真正想知道的是價值與風險：誰在養公司、依賴度多高、哪些產業在成長、哪些客戶正在流失。這張表把金額、毛利、頻率、狀態放在同一個座標上看，而不是只排一個金額榜。", [
    ("80% 業績靠幾家？", "ABC 分級 + 前 10 大佔比：A 級客戶就是要指定專人維護的名單。"),
    ("哪個產業值得投資？", "產業別的金額、客戶數、毛利率、同期成長一起看：金額大但毛利低的產業是議價問題，客戶多但金額小的產業是升級問題。"),
    ("每個客戶該用什麼策略？", "價值矩陣四個象限直接對應策略提示：核心維護 / 檢討報價 / 可擴大 / 評估續做。"),
    ("誰快掉了？", "流失風險清單：去年 ≥ 30 萬、今年到目前為止沒有業績，附距上次交易月數，是業務下週要打電話的名單。"),
    ("客戶的交易習慣？", "頻率（筆數、活躍月數）與月趨勢 sparkline：一年做一次大檔期的客戶和每月都下單的客戶，經營方式不同。"),
], A_screen)
B = sec("REPORT B", "業務分析", "現有「進單總表分業務」只回答金額；但金額高的業務可能只靠一個客戶、或用低毛利換來的。這張表把「量」與「質」並排：金額、佔比、同期成長是量，毛利率、新客數、依賴度是質。熱圖取代 業務 × 平台 × 月 的大表格，季節性與穩定度一眼看出。", [
    ("誰做得好？", "排名表同時看金額、毛利率、認定業績；認定業績沿用舊系統的業績類別認定比例（開發 1.0 / 既有 0.8 / 服務 0.5）。"),
    ("誰有風險？", "前 3 大客戶依賴度 ≥ 70% 標紅：這位業務的業績跟著一個客戶走。"),
    ("誰在開發？", "新客數 = 由該業務帶進、今年第一次有業績的客戶數。"),
    ("目標追得到嗎？", "個人頁顯示目標、達成率、剩餘月份每月需達、加上預估 pipeline。"),
    ("交換怎麼算？", "交換另欄顯示，不進排名、不算毛利，和老闆儀表板的做法一致。"),
], B_screen)
C = sec("REPORT C", "銷售分析", "訂單層是定價與成本決策發生的地方。平均值會騙人，所以先看分佈：錢集中在哪個金額級距、有多少業績是在低毛利下做的；再看產業 × 平台矩陣找出真正賺錢的組合；最後是排名與低毛利清單，直接接到舊系統的「低毛利原因登錄」。", [
    ("大單重要還是小單重要？", "金額分佈：13 筆 ≥100 萬的訂單佔了多少業績、毛利率如何，一眼看到。"),
    ("低毛利是個案還是常態？", "毛利率分佈以 16%（舊系統低毛利門檻）和 35%（標準）切段，顯示筆數與金額。"),
    ("哪裡最賺？", "產業 × 平台歸類熱圖：同一個產業在企頻和新鮮視的表現可能完全不同。"),
    ("這張單到底賺不賺？", "每筆訂單三個毛利率：帳上、集團、分攤固定成本後的淨利率；子公司在企頻的單子帳上 25%、集團看起來卻可能是 60%，這是老闆一直要的「第二層」。"),
    ("要處理什麼？", "低毛利清單可直接填原因，取代另開表單。"),
], C_screen)
D = sec("REPORT D", "公司分析", "三家公司的比較之所以難，是因為東吳、鉑霖付給聲活的 65 折同時是子公司的成本和聲活的收入，帳上毛利加總不等於集團毛利。這張表用「三層毛利橋」把帳上、集團、淨利一次講清楚，並把老闆儀表板的目標達成搬進系統，用同樣的口徑（企頻＋新鮮視、不含公司戶）算。", [
    ("集團到底賺多少？", "帳上毛利合計 → 加回轉撥 → 集團毛利 → 扣固定成本 → 淨利，每一步都有數字。"),
    ("哪家公司在成長？", "三家 KPI 卡各附同期成長、帳上毛利與轉撥金額；月堆疊圖看節奏。"),
    ("目標追不追得到？", "達成率之外加「剩餘月份每月需達」：這才是下個月會議要盯的數字。"),
    ("業績結構？", "公司 × 平台歸類矩陣 + 人均產值：鉑霖 3 個業務做出的人均和東吳 5 個業務的人均可以直接比。"),
], D_screen)

html_out = f"""<title>聲活・東吳・鉑霖 分析報表設計</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="masthead">
  <div><div class="eyebrow">Report design proposal · 新業績系統</div><h1>聲活・東吳・鉑霖 分析報表設計</h1>
  <p class="lede">四張給老闆看的分析表：客戶、業務、銷售、公司。每張都用真實資料（2024/01–2026/09 舊系統匯入）做成樣稿，數字是 {YEAR} 年 1–{M} 月 YTD，同期 = 2025 年 1–{M} 月。先講共同定義，再一張一張說設計理由。</p></div>
  <div class="meta">資料截止 {ao['as_of_ym'].strftime('%Y/%m')}<br>訂單 {int(g26.deals):,} 筆・除佣實收 {wan(g26.ext_net)}<br>樣稿為靜態頁；正式版在 Streamlit 報表中心</div>
</header>

<section id="principles">
  <h2>六個設計原則</h2>
  <div class="principles">
    <div class="pr"><b>一頁回答一個問題</b><span>每張表由上而下：KPI（結論）→ 圖（結構）→ 排名表（誰）→ 警示清單（該做什麼）。老闆看前 10 秒就有答案，想追再往下捲。</span></div>
    <div class="pr"><b>同期比較是標準欄位</b><span>員工現在每月手做的「客戶同期比較表」邏輯內建到每張表：今年 YTD 對去年同一段，不是對去年全年。</span></div>
    <div class="pr"><b>三層毛利，一套定義</b><span>帳上、集團、淨利三個數字全系統相同算法，表頭寫清楚是哪一層；不再出現同一個「毛利」在不同報表對不起來。</span></div>
    <div class="pr"><b>排除干擾，但看得到</b><span>內部轉撥、交換、公司戶預設排除排名，另欄顯示金額；不會消失，也不會灌水。</span></div>
    <div class="pr"><b>排名一定附佔比與累計</b><span>「第 1 名 2,485 萬」沒有意義，「第 1 名佔 24%、前 10 名佔 62%」才是集中度。</span></div>
    <div class="pr"><b>顏色跟著實體走</b><span>聲活藍、東吳綠、鉑霖橘沿用老闆儀表板；平台歸類用同一色系深淺；紅黃只用在警示。四張表的色彩語言一致。</span></div>
  </div>
  <h3 style="margin-top:28px">共同定義（以 {YEAR} 年 1–{M} 月實際數字示範）</h3>
  {DEF}
</section>

{A}
{B}
{C}
{D}

<section id="mapping">
  <h2>現有報表怎麼對應</h2>
  <p class="why" style="color:var(--ink-2);margin:8px 0 14px;max-width:70ch">員工現在整理給老闆的六份文件和舊系統財務仍在用的報表，都能在四張分析表或它們的下鑽頁裡找到；沒有任何一張是需要另外維護的。</p>
  {MAP}
  <div class="caveats"><b>樣稿數字的注意事項</b>
    <ol>
      <li>固定成本規則（企頻 75 萬、新鮮視 100 萬/月）依需求文件自 2026 年起設定；2025 未設定，所以淨利的同期比較先不顯示，規則補齊即自動出現。</li>
      <li>目標值取自 0730 儀表板的 Q3 數字（聲活 1,000 萬、東吳 2,000 萬、鉑霖 1,000 萬），口徑為企頻＋新鮮視、不含公司戶。用同一口徑算出 7 月 東吳 372 萬、鉑霖 197 萬與儀表板完全一致，聲活 139 萬 vs 儀表板 147 萬有小差異，待對帳。</li>
      <li>「新客 / 流失」判斷從 2025 年起才可靠（資料自 2024/01 開始，2024 全部是起始年）。</li>
      <li>舊資料沒有區域欄位，區域維度在新登打資料累積後才有意義，樣稿未放。</li>
      <li>客戶名稱沿用舊系統原文（如「香港商群邑-2008」），合併別名後排名會更準。</li>
    </ol></div>
</section>

<section id="impl">
  <h2>怎麼做進現有系統</h2>
  <div class="impl">
    <div class="pr"><b>資料層：一個 SQL 檔</b><span><code>sql/005_analysis.sql</code> 新增 <code>sales_target</code>、<code>forecast</code> 兩張表與 12 個 view（<code>v_deal_summary</code>、<code>v_customer_year</code>、<code>v_salesperson_year</code>、<code>v_industry_year</code>、<code>v_company_month</code>、<code>v_group_month</code>、<code>v_target_progress</code>…）。已在本地 PostgreSQL 用全部舊資料跑過，樣稿的每個數字都來自這些 view。</span></div>
    <div class="pr"><b>應用層：四個分析頁</b><span>報表中心之外新增「分析」頁群，每頁 = 篩選列 + KPI + 圖（plotly）+ 排名表（可下載 Excel）+ 下鑽。指令書 <code>CLAUDE_CODE_TASK_2.md</code> 已寫好頁面規格、圖表規格與驗收數字（例如客戶分析前 10 大佔比 {pct(float(custcnt['top10'])/float(custcnt['total']))}）。</span></div>
    <div class="pr"><b>主檔維護新增兩個 tab</b><span>目標（年 / 季 / 月 × 公司 / 業務 / 平台）與預估（月 × 公司 × 業務 × 客戶 × 金額 × 機率）。老闆儀表板與「進單＋預估大總表」就從這兩張表自動產生。</span></div>
    <div class="pr"><b>先確認三件事</b><span>三層毛利定義是否如上；固定成本歸屬與 2025 的數字；瑞迪是否仍在營運（2025 起無業績）。確認後把 <code>docs/ASSUMPTIONS.md</code> 對應條目改為「已確認」。</span></div>
  </div>
</section>
<footer>樣稿產生時間依資料庫 as-of {ao['as_of_ym'].strftime('%Y/%m')}；所有金額為新台幣、除佣實收口徑；本頁為私人連結，內含公司實際客戶與業績數字，分享前請確認對象。</footer>
</div>
"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write("<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body>" + html_out + "</body></html>")
print("written", OUT, len(html_out)//1024, "KB")
