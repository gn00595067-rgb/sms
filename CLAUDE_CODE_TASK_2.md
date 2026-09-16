# CLAUDE_CODE_TASK_2.md — 分析報表（客戶 / 業務 / 銷售 / 公司）

> 接續 CLAUDE_CODE_TASK.md 完成的 MVP（階段 A–G 已 commit）。本次新增「分析」頁群與目標 / 預估兩張表。
> 讀完 docs/REPORT_DESIGN.md 再開始；每個數字的算法都以 `sql/005_analysis.sql` 與 `tools/mockup_generator.py` 為準。

---

## 0. 任務一句話

在現有 Streamlit 系統加四個分析頁（客戶、業務、銷售、公司）與兩個下鑽頁（客戶頁、業務頁），資料層用 `sql/005_analysis.sql` 的 view；老闆看到的畫面要與樣稿（docs/REPORT_DESIGN.md 描述的 v1 樣稿）一致，數字要與 §7 的驗收值完全相同。

## 1. 工作原則（沿用第一份指令的 §1，另加）

1. **數字先對再做畫面。** 先用 `python tools/mockup_generator.py` 跑出樣稿 HTML（需要 DATABASE_URL），確認你的環境算出的數字 = §7；再開始寫頁面。頁面上任何一個數字都必須能對回 view 或 generator 的某一行。
2. **不要改 `sql/005_analysis.sql` 的商業邏輯**；要加欄位就加 `sql/006_*.sql`。
3. **同一套顏色**：公司 聲活 `#2a78d6`、東吳 `#1baf7a`、鉑霖 `#eb6834`、瑞迪 `#4a3aa7`；平台歸類 企頻 `#4a3aa7`、新鮮視 `#6353bc`、廣播 `#8377cf`、其他 `#a49bdf`；狀態 新客 `#1baf7a`、回流 `#eb6834`、既有 `#2a78d6`；警示 紅 `#d03b3b`、黃 `#fab219`、綠 `#0ca30c`。放在 `core/format.py` 的 `COLORS` 字典，所有 plotly 圖都從這裡拿。
4. 圖用 plotly（已在 requirements）；表用 `st.dataframe` + `column_config`（`ProgressColumn` 做佔比 / 達成率、`LineChartColumn` 做月趨勢、`BarChartColumn` 做平台組合）。
5. 每張表都有「下載 Excel」（沿用 `reports/render_excel.py`）。

## 2. 資料層：套用 005

```powershell
python scripts/db_apply.py
```

新增：`sales_target`、`forecast` 兩張表；view：`v_line_ext`、`v_as_of`、`v_deal_summary`、`v_customer_month`、`v_customer_year`、`v_industry_year`、`v_salesperson_month`、`v_salesperson_year`、`v_company_month`、`v_group_month`、`v_target_progress`、`v_booked_vs_forecast`。005 會先 drop 這些 view 再建，可重複執行。種子：2026 Q3 三家公司目標（企頻＋新鮮視、不含公司戶）。

**粒度與口徑（一定要懂）**
- `v_deal_summary`：一列 = 一個合約。`ext_net` = 對外除佣實收（不含內部轉撥線）；`booked_profit` = 帳上毛利；`group_profit` = 集團毛利（加回轉撥）；`net_profit` = 集團淨利（再減分攤的平台固定成本）；`is_barter` 交換；`is_house` 公司戶（業務 = Company）；`is_low_margin` 帳上毛利率 < 16%。
- 分析頁的「期間」是 **業績年月區間**，預設 今年 1 月 → `v_as_of.as_of_ym`。KPI / 排名 / 分佈全部從 `v_deal_summary where perf_ym between … and not is_barter` 在 Python 端彙總（`tools/mockup_generator.py` 的 `agg_customers` / `agg_sp` 就是規格）；`v_customer_year` / `v_salesperson_year` 只用來拿 狀態（新客/既有/回流/流失風險）、ABC、距上次交易月數，以及「年度」快速檢視。
- **同期** = 去年同一段月份（例如 2026/01–09 對 2025/01–09），不是去年全年。
- **排除交換** 預設勾選；**公司戶** 在客戶 / 銷售 / 公司分析預設含、在業務排名預設另列（不排名）。

## 3. 頁面：新增「分析」頁群（app.py 的 st.navigation 加一組）

所有分析頁：MEDIA / FINANCE / EXEC 可看；SALES 只看自己（客戶分析、銷售分析限縮到自己的客戶與訂單）。

### 3.1 共用：`core/analysis.py`
- `window_defaults()` → (今年 1 月, as_of)。
- `load_deals(ym_from, ym_to, filters, exclude_barter=True)` → DataFrame（`v_deal_summary`，參數化 where；篩選：company、platform_group（用 main_platform_group）、industry、salesperson、customer ilike）。
- `prev_window(ym_from, ym_to)` → 去年同段。
- `agg_customers(df)`, `agg_salespeople(df)`, `agg_industries(df)`, `size_buckets(df)`, `margin_bands(df)`：照 generator 的規則，回傳排名 / 佔比 / 累計佔比 / ABC / YoY / 依賴度 / 新客數。
- `kpi_row(items)`：一列 KPI 卡（值、副標、同期 chip）。
- `filter_bar_analysis(key)`：期間起迄（月選單，來源 `v_months`）、公司、平台歸類、產業、業務、排除交換、含公司戶。

### 3.2 P13 客戶分析 `pages_app/analysis_customer.py`
由上而下（與樣稿相同）：
1. KPI：活躍客戶數（同期 chip）、新客戶、流失風險（去年有今年尚無）、客戶平均貢獻（同期 chip）、前 10 大佔比（副標同期）、帳上毛利率（副標集團毛利率）。
2. 兩張圖並排：ABC 分級橫條（A/B/C 各金額、家數）；產業別橫條（前 8 + 其他：金額、家數、毛利率）。
3. 客戶價值矩陣：plotly scatter，x = 除佣實收（**x 軸用平方根刻度**：`fig.update_xaxes(type="log")` 不行，改把 x 值開平方根後畫、刻度標籤用原值），y = 帳上毛利率，點大小 = 訂單數，顏色 = 狀態（既有 / 新客 / 回流，同時用符號 circle / diamond / square），hover 顯示客戶、金額、毛利率、筆數、狀態；畫 16% 與 35% 兩條虛線；右上、右下加象限文字。
4. 客戶排名表（可捲動、前 50，Excel 下載全部）：# / 客戶（副行：產業・主要業務）/ 狀態 tag / 除佣實收 / 同期 % / 佔比（副行累計）/ 帳上毛利 / 毛利率 / 集團淨利率 / 頻率（筆數、活躍月數）/ 平均單筆 / 平台組合（BarChartColumn，四段）/ 月趨勢（LineChartColumn，期間內各月）/ 策略提示。點列 → 3.6 客戶頁（用 `st.session_state["customer_focus"]` + `st.switch_page`）。
5. 流失風險清單：去年同段 ≥ 30 萬、今年期間內無業績，欄位：客戶 / 產業・去年業務 / 去年除佣實收 / 距上次交易月數；門檻可調（number_input，預設 30 萬）。

### 3.3 P14 業務分析 `pages_app/analysis_salesperson.py`
1. KPI：有業績的業務人數（副標：公司戶另計 X）、人均除佣實收（副標人均帳上毛利）、人均客戶數（副標人均新客）、業務業績合計（副標帳上毛利率）、交換另計。
2. 排名表：# / 業務（副行：公司・組別）/ 除佣實收（ProgressColumn 相對最大值，顏色依公司）/ 同期 % / 佔比 / 帳上毛利 / 毛利率 / 集團淨利率 / 認定業績 / 客戶數（副行新客）/ 訂單數（副行平均單筆）/ 前 3 大客戶依賴度（≥70% 紅、≥50% 黃；副行最大客戶）/ 平台組合 / 交換。公司戶（Company）列在表格最下方灰底、不排名。
3. 熱圖：業務（前 8）× 月，值 = 除佣實收，`px.imshow` 用 Blues，格內顯示 `萬`，右側合計。
4. 點列 → 3.7 業務頁。

### 3.4 P15 銷售分析 `pages_app/analysis_sales.py`
1. KPI：有收入的訂單數（同期）、平均單筆（副標中位數）、大單 ≥100 萬（筆數、佔業績）、低毛利訂單 <16%（筆數、佔業績）、零收入成本單（筆數、成本合計）、帳上毛利率含成本單（副標只看有收入訂單）。
2. 兩張圖並排：訂單金額分佈（級距 ≥100萬 / 50–100 / 10–50 / <10 / 零收入：金額、筆數、毛利率）；毛利率分佈（<0 紅、0–16 黃、16–35、35–50、>50：金額、筆數）。
3. 產業 × 平台歸類熱圖（前 9 產業 × 企頻 / 新鮮視 / 廣播 / 其他，右側合計）。
4. 訂單排名表（排序可選：除佣實收 / 帳上毛利 / 毛利率 / 集團淨利率）：# / 合約（副行廣告）/ 客戶（副行產業）/ 業務（副行公司）/ 平台歸類組合 / 年月 / 除佣實收 / 實付 / 帳上毛利 / 毛利率 / 集團淨利率 / 製作費。點列 → P2 業績登打（修改模式）。
5. 低毛利清單：≥10 萬、毛利率最低 N 筆（預設 10），最後一欄「低毛利原因」可直接編輯（寫回 `deal_line.low_margin_reason` 與 `low_margin_handled`，該合約所有線同值）。

### 3.5 P16 公司分析 `pages_app/analysis_company.py`
1. KPI 四卡：聲活 / 東吳 / 鉑霖（除佣實收、同期 chip、帳上毛利與毛利率、轉撥金額或收到轉撥＋固定成本）+ 集團合併（除佣實收、同期、集團毛利、扣固定成本後淨利）。瑞迪若期間內有業績才顯示。
2. 兩張圖並排：各公司月業績堆疊柱（`v_company_month`，顏色依公司，頂端總計標籤）；三層毛利橋（`go.Waterfall`：帳上毛利合計 → ＋轉撥 → ＝集團毛利 → －固定成本 → ＝集團淨利；來源 `v_group_month` 期間加總）。
3. 目標達成表（`v_target_progress`）：公司 / 期間 / 範圍 / 目標 / 進單 / 待追 / 達成率（ProgressColumn）/ 剩餘月份・每月需達 / 加預估後達成率。沒有目標時顯示提示連到主檔維護。
4. 公司 × 平台歸類表：企頻 / 新鮮視 / 廣播 / 其他 / 合計 / 組合（BarChartColumn）/ 帳上毛利率 / 業務人數 / 人均產值。
5. 進單＋預估（`v_booked_vs_forecast`）：公司 × 月 的 進單 / 交換 / 預估 / 合計，對應老闆的大總表（有預估資料才有意義）。

### 3.6 客戶頁 `pages_app/customer_detail.py`
選客戶（selectbox，可由 P13 帶入）：KPI（期間 / 去年同段 / 歷年）、24 個月 除佣實收與帳上毛利 柱+線（單一 y 軸，兩張小圖並排，不要雙軸）、歷年同期比較表（年 / 除佣 / 同期 % / 毛利 / 毛利率 / 業務）、訂單清單（`v_deal_summary` 該客戶，三個毛利率欄）、平台組合變化（年 × 平台歸類）、經手業務（年 × 業務金額）。

### 3.7 業務頁 `pages_app/salesperson_detail.py`
選業務：KPI、月趨勢（期間內）、客戶組合表（前 10 大：金額 / 同期 % / 佔該業務 %）、新客與流失風險清單、目標達成（`v_target_progress where salesperson = …`；沒有就提示）、預估清單（forecast 該業務 OPEN）、連結「月業績認定表」（P7 recognition 帶入業務）與「簡易獎金」。

### 3.8 主檔維護新增兩個 tab（P5）
- **目標**：`sales_target` data_editor（年 / 期間類型 Y-Q-M / 期次 / 公司 / 業務 / 平台歸類（多選，存 text[]）/ 含公司戶 / 目標金額 / 備註）。
- **預估**：`forecast` data_editor（業績年月 / 公司 / 業務 / 客戶（可選主檔或自由文字）/ 廣告名稱 / 平台歸類 / 金額 / 機率 % / 狀態 OPEN-WON-LOST / 備註）。MEDIA、SALES（自己的）可編輯。

### 3.9 報表中心加六筆 registry（direct 模式，給要看整年表的人）
`customer_year`（v_customer_year）、`salesperson_year`、`industry_year`、`group_month`（三層毛利月表）、`target_progress`、`booked_vs_forecast`。附錄 C 補標籤：`ext_net` 除佣實收（對外）、`booked_profit` 帳上毛利、`group_profit` 集團毛利、`net_profit` 集團淨利、`ic_add_back` 轉撥加回、`fixed_cost` 固定成本、`booked_margin` 帳上毛利率、`group_margin` 集團毛利率、`net_margin` 集團淨利率、`status` 狀態、`abc_tier` ABC、`freq_tier` 頻率、`months_since_last` 距上次交易（月）、`yoy_pct` 同期 %、`share` 佔比、`cum_share` 累計佔比、`top3_share` 前 3 大依賴度、`new_customers` 新客數、`avg_deal` 平均單筆、`target_amount` 目標、`actual` 進單、`remaining` 待追、`achieved_pct` 達成率、`required_monthly` 每月需達、`forecast_amount` 預估、`booked_plus_forecast` 進單＋預估、`barter_net` 交換、`is_house` 公司戶、`size_bucket` 金額級距、`strategy_hint` 策略提示。

### 3.10 首頁（P1）微調
KPI 改用 `v_group_month`（集團合併 + 各公司），加一列目標達成（`v_target_progress` 當季）；其餘不動。

## 4. 圖表規格（給 plotly）
- 全部 `fig.update_layout(margin=dict(l=8,r=8,t=8,b=8), legend=dict(orientation="h", y=1.08), font=dict(family="Noto Sans TC, Microsoft JhengHei"))`；金額 hover 用 `,.0f`；比率 `.1%`。
- 不用雙 y 軸；要比兩個量就兩張圖並排。
- 柱狀圖堆疊段之間留 1px 白邊（`marker_line_width=1, marker_line_color="white"`）。
- 顏色永遠從 `COLORS` 拿，不用 plotly 預設色。
- 圖下方一定有對應表格或 hover，不能只有圖。

## 5. 測試
- `tests/test_analysis.py`：對 2026/01–09 視窗，`agg_customers` / `agg_salespeople` 的結果與 §7 完全相同；`v_target_progress` Q3 三家的 actual 相同；`v_group_month` 期間加總相同；ABC 三級家數 39 / 61 / 76 在 **年度**（v_customer_year 2026）口徑、期間口徑以 generator 為準。
- 手動驗收（寫進 docs/ACCEPTANCE.md）：四頁各截一張圖；客戶頁點「全家便利商店股份有限公司」看到 24 個月趨勢；主檔維護新增一筆 2026 Q4 目標後公司分析目標表出現該列；預估新增一筆後進單＋預估表出現。

## 6. 交付
- `docs/CHANGELOG.md` 加「階段 H：分析報表」。
- `docs/USER_GUIDE.md` 加四頁說明（每頁一段 + 「老闆會問的問題 → 看哪裡」）。
- `docs/ASSUMPTIONS.md` 加：交換判斷規則（業務名結尾「換」或廣告名含「交換」）、公司戶清單（Company / 公司 / 東吳 / 鉑霖 / 聲活 / 瑞迪 作為業務名時）、固定成本分攤方式（依當月該平台歸類對外除佣實收比例）、目標口徑（企頻＋新鮮視、不含公司戶、不含交換）、狀態定義、2024 為起始年。
- 回報格式同第一份指令。

## 7. 驗收數字（期間 2026/01–2026/09，排除交換；本地 PostgreSQL 以 legacy_csv 全量匯入後算出）

| 項目 | 值 |
|---|---|
| 集團 對外除佣實收 | 87,443,295 |
| 集團 帳上毛利 / 率 | 24,090,256 / 27.5% |
| 轉撥加回 | 24,681,545 |
| 集團毛利 / 率 | 47,421,861 / 54.2% |
| 平台固定成本（企頻 75 萬 3–9 月 + 新鮮視 100 萬 1–9 月） | 14,250,000 |
| 集團淨利 / 率 | 33,171,861 / 37.9% |
| 聲活 / 東吳 / 鉑霖 對外除佣實收 | 51,116,900 / 23,651,990 / 12,674,406 |
| 聲活 收到轉撥 | 24,681,545 |
| 東吳 / 鉑霖 轉撥給聲活 | 16,702,761 / 7,978,783 |
| 交換（另計） | 2,504,378 |
| 活躍客戶（有收入） | 172（同期 2025/01–09：197） |
| 新客 / 流失風險 | 89 / 162（流失風險 = 去年有業績、今年到 9 月尚無，年度口徑） |
| 前 10 大客戶佔比 | 53.3%（同期 48.8%） |
| 客戶第 1 名 | 全家便利商店股份有限公司 24,850,570（不含 10–12 月的預登） |
| 有業績的業務（非公司戶） | 14 人；人均 448 萬 |
| 業務第 1–3 名 | 洪佳琪、陳絜心、許雅婷 |
| 有收入訂單 / 零收入成本單 | 486 / 97 |
| 大單 ≥100 萬 | 10 筆 |
| 低毛利 <16% | 47 筆 |
| 2026 Q3 目標實績（企頻＋新鮮視、不含公司戶） | 聲活 3,329,960 / 東吳 8,568,577 / 鉑霖 4,765,370 |
| 7 月 企頻＋新鮮視 不含公司戶 | 東吳 3,721,654、鉑霖 1,974,452（與 0730 儀表板一致）；聲活 1,390,740（儀表板 1,467,000，待對帳） |

> 客戶排名表的除佣實收若用 `v_customer_year.ext_net`（整年含 10–12 月預登）會比上表大；分析頁一律用期間口徑。
