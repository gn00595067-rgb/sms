# 如何新增一張報表 — HOW_TO_ADD_REPORT.md

新增報表 = 3 步：(1) SQL 加 view → 套用；(2) registry 加一筆；(3) 附錄 C 補中文標籤。
報表頁（P7）會自動出現這張報表，篩選、下載 Excel、列印版都免額外寫。

---

## 步驟 1：加一個 view（若沿用既有 view 可跳過）

在 `sql/` 新增 **005 以後**的檔案（不要改 001–004），例如 `sql/005_report_channel.sql`：

```sql
-- 電台別發稿量（月 × 電台）
create or replace view v_channel_volume as
select
  perf_ym, perf_ym_text, company, media_channel,
  count(*)              as line_count,
  sum(total_frames)     as total_frames,
  sum(net_amount)       as net_amount
from v_deal_line_flat
where line_type = 'MEDIA'
group by perf_ym, perf_ym_text, company, media_channel;
```

套用（idempotent，可重複跑）：

```powershell
python scripts/db_apply.py
```

---

## 步驟 2：在 `reports/registry.py` 的 `REPORTS` 加一筆

**彙總型**（來源是 row-level 的 `v_deal_line_flat`，要動態 group by）用 `mode="aggregate"`；
**直接型**（來源是已彙總 view）用 `mode="direct"`。上面的例子是直接型：

```python
"channel_volume": {
    "title": "電台別發稿量",
    "view": "v_channel_volume",
    "mode": "direct",
    "filters": ["ym_range", "company"],          # 見 core/ui.filters_bar 支援清單
    "columns": ["perf_ym_text", "company", "media_channel", "line_count", "total_frames", "net_amount"],
    "default_sort": [("perf_ym_text", "asc")],
    "sum_cols": ["line_count", "total_frames", "net_amount"],   # 合計列要加總的欄
    "totals": True,
    "roles": ["MEDIA", "EXEC"],                  # 誰看得到
    "sales_scope": False,                        # True 時 SALES 只看自己
},
```

若某個新篩選欄該 view 也支援，去 `reports/query.py` 的 `_view_filters()` 幫這個 view 補上對應的
`filter_key: ("SQL 片段 %s", 值轉換)`（**一定用 %s 參數綁定，不要字串拼接**）。

彙總型範例（可切多種 group by、可切明細）：

```python
"my_agg": {
    "title": "我的彙總報表", "view": "v_deal_line_flat", "mode": "aggregate",
    "filters": ["ym_range", "company", "platform_group"],
    "group_by_options": {
        "月×公司": ["perf_ym_text", "company"],
        "平台歸類": ["platform_group"],
        "明細": None,          # None = 顯示 detail_columns 明細
    },
    "measures": ["line_count", "net_amount", "gross_profit", "margin_pct"],  # 見 query.MEASURE_SQL
    "detail_columns": ["perf_ym_text", "contract_no", "company", "net_amount", "gross_profit"],
    "default_sort": [("perf_ym_text", "asc")], "totals": True,
    "roles": ["EXEC"], "sales_scope": True,
},
```

---

## 步驟 3：在 `core/format.py` 的 `LABELS` 補中文標籤

任何 view 新出現、還沒有中文標籤的欄位加進去，表格與 Excel 才會顯示中文：

```python
"media_channel": "電台/項目",   # 已有就不用加
```

金額/比率/整數欄若要自動格式化，順手把欄名加進 `MONEY_COLS / RATIO_PCT_COLS / INT_COLS` 對應集合。

---

## 完成

重新整理 P7 報表中心，新報表就在下拉選單裡，且自帶篩選列、合計列、Excel 下載、列印版。
別忘了把新假設寫進 `docs/ASSUMPTIONS.md`。
