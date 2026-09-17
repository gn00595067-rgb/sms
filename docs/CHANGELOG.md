# 變更紀錄 — CHANGELOG.md

## 階段 A — 環境與資料庫
- 建立 .venv、安裝 requirements。
- 填入 `.streamlit/secrets.toml`（Supabase Session pooler，region ap-northeast-2）。
- `db_apply.py` 套用 sql/001–004；驗證 platform = 20。

## 階段 B — 匯入舊資料
- `etl_legacy.py` 匯入 legacy_csv（61 個 CSV）→ legacy_* + 主檔 + deal/deal_line + invoice/writeoff + bonus_rule + app_user。
- 對帳 100 組（年月 × 公司別），詳見 ACCEPTANCE.md。
- 初始密碼寫入 seed_passwords.local.txt（未進版控）。

## 階段 C — 共用層與頁面
- `core/`：format（中文標籤/格式化/顯示 Styler）、auth（bcrypt 登入/角色）、data（主檔快取/客戶搜尋）、
  deals（load/save_deal、除佣公式、子公司轉撥線 make/generate_intercompany）、finance（發票/銷帳）、
  masters（主檔通用 CRUD、合併客戶）、ui（頁首/篩選列/問題回報/表格）、admin（使用者/回報/稽核）。
- `scripts/create_user.py`：建帳號印初始密碼。
- `app.py`：登入 → st.navigation 依角色分組載入 12 個頁面。
- `pages_app/`：P1 首頁、P2 業績登打、P3 業績查詢、P4 客戶、P5 主檔維護、P6 發票與銷帳、
  P7 報表中心、P8 業務獎金、P9 問題回報、P10 稽核、P11 使用者、P12 修改密碼。

## 階段 D — 報表引擎
- `reports/`：registry（8 張報表定義）、query（依 registry 組參數化 SQL、group by 白名單、比率重算）、
  render_excel（格式化 Excel）、render_html（A4 列印 HTML）。

## 階段 E — 測試
- 純 Python：test_etl_rules（ym/num/line_type/除佣公式）、test_auth（bcrypt）。
- 連 DB：test_views（對帳 vs CSV、合約 1130825-6-6 雙層、洪佳琪獎金、應收結清不變式）、
  test_reports（每張報表產 DataFrame+Excel+HTML）、test_deals（save_deal + 轉撥線往返，TEST- 前綴 teardown）。

## 階段 F — 部署
- `scripts/backup.py` + `.github/workflows/weekly_backup.yml`（每週備份，artifact 90 天）。
- `.github/workflows/supabase_keepalive.yml`（每日 ping）。
- git init 與首次 commit；部署步驟見 DEPLOY.md。

## 階段 G — 文件
- README、USER_GUIDE、ASSUMPTIONS、HOW_TO_ADD_REPORT、DEPLOY、ACCEPTANCE、CHANGELOG。

## 階段 H — 分析報表（客戶 / 業務 / 銷售 / 公司）
- **資料層** `sql/005_analysis.sql`：新增 `sales_target`、`forecast` 兩表；12 個 view
  （`v_line_ext`、`v_as_of`、`v_deal_summary`、`v_customer_month/year`、`v_industry_year`、
  `v_salesperson_month/year`、`v_company_month`、`v_group_month`、`v_target_progress`、
  `v_booked_vs_forecast`）。三層毛利（帳上 / 集團 / 淨利）全系統同一套定義；種子含 2026 Q3 目標。
- **參考實作 / 樣稿** `tools/mockup_generator.py`：四張分析表每個數字的規格；產出 `docs/report_design_mockup.html`。
  設計文字版見 `docs/REPORT_DESIGN.md`。
- **共用層** `core/analysis.py`：`load_deals` / `agg_customers` / `agg_salespeople` / `agg_industries` /
  `size_buckets` / `margin_bands` / `customer_trends` / `filter_bar_analysis` / `kpi_row` / `show_ranking`；
  彙總邏輯逐一對齊 mockup_generator。`core/format.py` 新增 `COLORS`（公司 / 平台歸類 / 狀態 / 警示）與附錄 C 標籤。
- **頁面**（app.py 新增「分析」頁群）：客戶分析、業務分析、銷售分析、公司分析，客戶頁、業務頁（下鑽）。
  圖用 plotly（色一律取自 COLORS），表用 `st.dataframe` + `column_config`
  （ProgressColumn 佔比 / 達成率、BarChartColumn 平台組合、LineChartColumn 月趨勢），每表可下載 Excel。
- **主檔維護** P5 新增「目標 / 預估」兩個 tab（寫 sales_target / forecast）。
- **報表中心** 新增 6 筆整年表 registry：客戶年度、業務年度、產業年度、集團三層毛利月表、目標達成、進單＋預估。
- **首頁** KPI 改集團口徑（v_group_month / v_company_month）+ 加集團合併卡 + 當季目標達成列。
- **測試** `tests/test_analysis.py`：對 2026/01–09 視窗核對 §7 驗收數字（集團三層毛利、各公司除佣、
  客戶 / 業務彙總、銷售分佈、Q3 目標實績、ABC 年度家數 39/61/76）。全套 `pytest -q` = 40 passed、零回歸。

## 階段 I — 分析頁檢視後修正（CLAUDE_CODE_TASK_3）
- **P0-1** 業務排名「除佣實收」原用 progress（顯示成天文數字 %）→ 改 money + 佔比 progress；`show_ranking` progress 分支改吃 `opts["format"]`。
- **P0-2** 各頁「帳上毛利率」口徑統一：新增 `core.analysis.margin_kpis`（含成本單），三頁主數字一致（27.5%），副標「只看有收入 41.9%」。
- **P0-3** `sql/006_review_fixes.sql`：`v_as_of` 改「最後已結束的月」（本月進行中不算）+ 新增 `v_open_month`；篩選列預設迄月=上月，並顯示「本月進行中、未納入預設區間」提示（迄月含未結月時加警語）。
- **P0-4** 流失風險 KPI 與清單同口徑（`churn_list`：去年同段 ≥ 門檻且本期無收入）；「去年業務」改從去年同段訂單取金額最大者，不再是空值。
- **P0-5** 客戶排名「產業」改用訂單產業眾數（主檔為空才 fallback）→ 前 20 名無未分類；`scripts/backfill_customer_industry.py` 用眾數補齊主檔（已跑，273 客戶、稽核在案）。
- **P0-6** 下鑽頁預設本期金額最大者（非字母序 / 非「+」）；`sql/006` 停用單字垃圾業務名；空資料改 `st.info` 不畫全 0 圖。
- **P1** 金額軸與長條文字改「萬」（`format.wan` / `axis_wan`、`cliponaxis`）、熱圖加數字與合計、排名表精簡欄 +「顯示全部欄位」toggle + None/年欄清理、篩選列跨頁保留（共用 key）+ 快捷區間鈕、公司月堆疊圖加總計與月毛利率折線、目標表無預估時隱藏該欄 + 集團合計列 + 未設目標提示、進單＋預估每家三列（進單/預估/合計）、`.streamlit/config.toml` toolbarMode=minimal。
- **P2** 客戶價值矩陣毛利率口徑切換（EXEC 預設集團淨利率）+ 前 5 大標名；低毛利清單排除營運結構成本單（可勾回）；資料品質面板（缺產業/異常業務名/疑似異名）；客戶頁加最近交易/平均回購間隔 KPI、圖只畫有資料月份、歷年表去未來年；業務頁加同期 KPI、客戶組合空狀態；Excel 標「單位：元」。
- **關鍵 bug**：未來預登月份（2027）混進期間選單、且 as_of 與月清單型別不一致（date vs Timestamp）→ 預設迄月落到最新月造成空視窗；已於 `analysis_months` 排除未來月並統一為 date。
- 全套 `pytest -q` = 44 passed、零回歸；6 個分析頁經 app.py 導覽 headless 煙霧零例外。

## 階段 J — 發稿口徑與報表平台（CLAUDE_CODE_TASK_4，`sql/007_report_platform.sql`）
- **報表平台 `report_platform`**：platform 主檔加欄 + seed，把 20 個平台歸成老闆的七欄（全家企頻／萬家福／新鮮視／廣播／健康視／營運／其它）。全家分區線（全家全企/北/桃/中/南/南頻）→ 全家企頻。
- **P0 修正**：`v_deal_summary` 的四平台欄原以 `platform_group='企頻'` 彙總，2024–2025 的全家分區線（platform_group='分區'）全掉進 `net_other`；改以 `report_platform` 彙總。`net_cp` 語意 = 企頻合計（全家企頻＋萬家福）；新增 `net_cp_family / net_cp_carrefour / net_clinic / report_platforms / main_report_platform`。例：東吳 2025 全家企頻由 0 → 2,985 萬（合約層、不含交換）。
- **口徑旗標**：`v_line_ext` 加 `report_platform / in_media_scope（只 MEDIA、非轉撥、屬四欄+健康視）/ is_own_media（不含廣播）`。
- **集團毛利橋收斂**：`v_group_month.ic_add_back` 改為「集團毛利 − 帳上毛利」（一定收斂），另加 `ic_transfer_gross`（轉撥收入總額明細）供瀑布圖 hover；公司/集團月表補七欄報表平台。
- **新增 `v_report_line`**：老闆口徑的線層 view（交換併回原業務 `salesperson_merged`、走期文字 `air_period_text`、`ym`），給階段 K/L/M 用。
- **驗收**（`tests/test_analysis.py::test_boss_workbook_2025`）：2025 發稿口徑 聲活 71,533,523／東吳 50,325,792／瑞迪 536,190／鉑霖 11,907,516；合計 134,303,021、帳上毛利 67,416,333、客戶 265；不含廣播 98,408,698／259 家；東吳+瑞迪 全家企頻 32,378,519／萬家福 5,630,860／新鮮視 9,535,360／廣播 3,317,243——全部對到元。全套 `pytest -q` = **45 passed、零回歸**。

## 階段 K — 併入現有分析頁（CLAUDE_CODE_TASK_4）
- **口徑（scope）模型**：`core.analysis.SCOPE_PRESETS / resolve_scope`——分析口徑（現狀、預設）/ 發稿口徑（老闆版）/ 自訂（五個旗標可逐項勾）；`scope_bar` 元件併入 `filter_bar_analysis(show_scope=)`，向後相容。
- **線層載入 `load_lines`**：`v_report_line` 期間切片、依 scope 過濾、交換併回原業務（`salesperson_merged`）、`merge_ruidi` 併瑞迪→東吳。`scope_bridge`：分析口徑→發稿口徑的收斂橋（回答老闆「為什麼數字不一樣」）。`line_group_profit`：線層依合約比例分回集團毛利（§4.1）。
- **公司分析（§3.1/§3.2）**：新增「平台總計總覽」表（公司 × 報表平台、指標切換 除佣/成本/帳上毛利/利率/集團毛利/利率、平台範圍快選 全部/自媒體/只看廣播、客戶數不重複、佔比、三公司合計列），取代舊「平台歸類」表；公司卡加客戶數；發稿口徑顯示口徑差異對照行。
- **業務分析（§3.3）**：業務 × 平台矩陣加「報表平台（老闆四欄+健康視）」細度選項（`salesperson_platform` 支援 `by="report_platform"`，固定欄序）。
- **客戶分析（§3.4）**：排名「顯示全部欄位」加「公司(多)／業務(多)／全家企頻／萬家福／新鮮視／廣播」欄（`agg_customers` 加 `companies_multi/salespeople_multi`，NUM 補三欄）；公司篩選時標題標公司、佔比＝佔該公司總計。
- 說明：分析頁排名主體維持合約層（分析口徑、既有 40+ 測試不動）；scope 切換與四平台欄為新增，客戶/業務頁全面改線層為後續（§3.5）。四個分析頁 headless 煙霧零例外；全套 `pytest -q` = **48 passed、零回歸**。
