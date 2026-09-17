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

## 階段 L — 兩張老闆版報表（CLAUDE_CODE_TASK_4）
- **registry `custom` 模式**：報表中心（P7）新增分支——mode=custom 的報表由指定模組 `render(user)` 自己畫 UI 與匯出，不走 run_report。
- **年度發稿明細（喬商版型）`reports/annual_detail.py`**：口徑＝發稿口徑，一家公司一個工作表，三段——第一段各業務客戶數與四平台發稿總計、第二段各業務每客戶（分平台）、第三段逐筆明細（金額落對應平台欄、末列各平台小計＋總計）。`include_group_profit` 可加集團毛利/利率欄。畫面預覽第一段＋第二段，第三段只在 Excel。**驗收**：2025 鉑霖 許雅婷 11,431,326／4,949,150／43.3%／54 家；末列 11,907,516／6,932,238／4,975,277——對到元。
- **平台總計總覽（老闆版 Excel）`reports/platform_overview.py`**：八區塊（除佣／成本／帳上毛利／利率 × 含廣播／不含廣播）＋集團毛利＋客戶數（含／不含廣播），公司×報表平台、三公司合計列。**驗收**：2025 區塊一 134,303,021、區塊五 98,408,698、客戶數 265／259。
- **測試** `tests/test_boss_reports.py`（4 tests）＋ `test_reports.py` 略過 custom 模式；報表中心 custom 兩報表 headless 煙霧零例外；全套 `pytest -q` = **52 passed、零回歸**。

## 階段 M — 自訂條件報表產生器（CLAUDE_CODE_TASK_4 §5）
- **`sql/008_report_builder.sql`**：`v_report_line` 加 `group_profit_alloc`（線層看集團毛利＝line.net / deal.ext_net × deal.group_profit）；`saved_report` 表（JSON 定義、owner、is_shared、audit trigger）。
- **引擎 `reports/builder.py`**：`DIMENSIONS`（17）／`MEASURES`（14）／`FILTER_COLS` 全白名單；`build_sql` 值全參數化、SALES 自動限縮、維度空→明細模式（limit 50000）；`run`→長表、`shape`→樞紐（欄維度＋合計欄群）＋比率事後算（Σ毛利÷Σ除佣）＋合計列＋佔比＋前 N（每第一層）；`build_excel` 兩層表頭；`save_saved/list_saved/delete_saved/load_definition` CRUD（SALES 不能分享、載回仍白名單清洗）。
- **頁面 `pages_app/report_builder.py`**（側欄「📐 自訂報表」）：期間 / 口徑 / 篩選 / 列(≤3)·欄·指標 / 合計·佔比·前 N / 查詢 / 下載 Excel / 存成我的報表（我的＋同仁分享下拉）。
- **種子 `scripts/seed_saved_reports.py`**：老闆工作簿六張表的定義（is_shared、owner=EXEC），一登入即可重跑，也是產生器驗收。
- **測試** `tests/test_builder.py`（9 tests）：白名單丟未知維度/指標、注入→明細模式、參數化、SALES 限縮；重現 平台總覽 134,303,021 / 聲活利率 59.2% / 月樞紐 2025/01 16,050,639 且合計仍 134,303,021 / 前 N / 明細模式 / 六個種子含·不含廣播 134,303,021·98,408,698。全套 `pytest -q` = **61 passed、零回歸**；自訂報表頁 headless 煙霧零例外。

## 階段 K/M 收尾（TASK_4 §3.5 / §5.6）
- **§3.5 客戶/業務頁接口徑切換**：`core.analysis.agg_customers_lines / agg_salespeople_lines`（線層彙總，含四平台/集團毛利率/跨公司業務/同期）；客戶、業務分析頁加 `show_scope=True`——分析口徑走原本完整互動頁；**發稿口徑／自訂口徑改用線層聚焦排名**（KPI＋四平台排名＋Excel），避免與分析口徑圖表混口徑。測試 `test_agg_lines_reconcile_to_boss`：2025 發稿口徑客戶/業務彙總加總 = 134,303,021、四平台加總相符。
- **§5.6 報表中心列出自訂報表**：P7 頂部加「📐 自訂報表（我的／同仁分享）」展開清單，選一個 → 跳「自訂報表」頁並載入定義。
- 全套 `pytest -q` = **62 passed、零回歸**；客戶/業務頁（分析＋發稿口徑）與報表中心 headless 煙霧零例外。銷售分析頁（訂單級距分佈本質為合約層）維持分析口徑。

## 階段 J — 列印級 PDF / Excel 匯出層（CLAUDE_CODE_TASK_5）
每一頁都能一鍵匯出列印級 PDF（給老闆印）＋ Excel（給同仁再算），版面固定不跑掉。核心＝一個中間格式 `Doc` → 三輸出（列印版 HTML / Chromium 經 Playwright 的 PDF / openpyxl 的 Excel）。**用戶追加需求：全站容易看不懂的欄位/數字都加說明**（放 `Col.help` + 表 note，畫面／PDF／Excel 三處一致）。
- **J-1 地基**：`reports/export/`（doc/html/pdf/xlsx/theme/ui 六檔）；本機 Windows 走內建 Edge、Cloud 走自帶 chromium（第一次按 PDF 才裝）、都沒有時退回列印版 HTML。`requirements` 加 `playwright>=1.47`；根目錄 `packages.txt`（Cloud apt：chromium 程式庫 + fonts-noto-cjk）。`tests/test_export.py` 5 綠。
- **J-2 公司分析**：`core/docs/`（無 streamlit 的 `build_doc`）＋ `_base.py`（headless 表頭 + 同期/毛利等統一說明字串）。頁面改 Doc 優先（`build_doc → X.ui.render → export_bar`）。防呆：公司別 2024→2025 重整同期除爆 → 顯示「同期不可比」；固定成本未設註明淨利＝集團毛利。
- **J-3 客戶/業務/銷售分析 + 客戶頁/業務頁**：五頁接匯出層，保留原互動（點列鑽研、切換），只把乾淨靜態版組成 Doc；刪各頁 `render_excel` 下載鈕。熱圖進 Doc、Excel 對應 matrix。
- **J-4 記錄式頁面**：報表中心/業績查詢/獎金/應收改 `reports/export/compat.py`（df + 欄位鍵 → Doc/Col，型別對照 `MONEY_COLS/RATIO_PCT_COLS/…`，與舊 render 同源）＋ `export_bar`；**刪 `reports/render_excel.py`、`render_html.py`**。應收加 KPI3（未收/逾期/逾 90 天）。
- **J-5 首頁老闆一頁 + 月報包**：`core/docs/home.py`（KPI4/各公司 vs 目標/近 12 月/待處理提醒，portrait）＋ `core/pack.py`（`build_pack`→zip：連續頁碼 PDF + 每頁 Excel）；`scripts/export_pack.py` 與首頁「📦 產生本月月報包」按鈕共用。**資料把關**：逾期未收原 6.7 億是舊帳銷帳未登錄假象 → 改標「帳列未收（未銷帳）」+ 濾未來日 + 明講僅供參考；流失客戶原查 `status='流失風險'` 回 0（實際值 `'流失'`）→ 修正 35 家。
- **J-6 老闆版兩報表 + single sheet**：`Doc.xlsx_layout="single"`＋`xlsx._single_sheet`（三段同一工作表）；`core/docs/annual_detail.py`（§4.1 到元：許雅婷 11,431,326/4,949,150/43.3%/54 家）、`core/docs/platform_overview.py`（§4.2：區塊一 134,303,021、區塊五 98,408,698、客戶 265/259）。報表中心 custom 兩報表 render() 加 export_bar；月報包 PACK 05-07 接上。
- **J-7 文件**：DEPLOY 補「列印級 PDF/Excel 匯出」章（packages.txt / playwright install / EXPORT_CHROMIUM 備援）；USER_GUIDE 補「怎麼印」；本紀錄。
- **測試**：`tests/test_docs.py`（core/docs 不得 import streamlit + 各 build_doc headless 可渲染 + 月報包 zip + 年度發稿明細單一工作表）；全套 `pytest -q` = **72 passed（+2 慢速 PDF/pack 測試）、零回歸**。
- **欄位/數字說明**：同期＝去年同段月份、集團/淨利定義、佔比/累計/前 3 大依賴度/低毛利/認定業績/三層毛利率、帳列未收 caveat 等一律進 `Col.help` + note。
- **樣本**：`samples/` 與 `pack/` 進 `.gitignore`（含真實客戶資料，`tools/export_sample_reference.py` 可重跑）。

## 階段 K — 「常用分析」頁：老闆工作簿精準重現（CLAUDE_CODE_TASK_6）
把老闆工作簿 `2025年度_三公司發稿明細分析.xlsx` 的 7 張表用資料庫即時算出、畫面／Excel／PDF 三處逐格一致，期間可選。計算層與版面來自已驗證的 `perf-boss-kit`（不重寫）。
- **`sql/009_boss_workbook.sql`**：`salesperson_alias`（別名→主檔名，seed 蔡伊閔→蔡伊閔Heidi）＋ `v_boss_line`（一列＝一條媒體上稿線，欄名＝工作簿原始資料 30 欄；規則：只留 MEDIA 線、不含轉撥、平台限四種＋健康視、交換併回原業務、瑞迪併入東吳）。驗收：2025 聲活 881／71,533,523、東吳 541／50,861,982、鉑霖 163／11,907,516。
- **`reports/boss_workbook/`**（compute/layout/xlsx/html）：一份原始資料 → 每張表；同一份 layout 出 Excel（openpyxl，原檔樣式）與 HTML（畫面 st.html＋PDF 共用）。
- **`pages_app/boss_workbook.py`**（側欄「⭐ 常用分析」，分析群組第一個，EXEC/FINANCE/MEDIA、SALES 不顯示）：期間 `st.radio`（去年整年／今年至今／自訂）；7 個 `st.tabs` 用 `st.html` 呈現原檔樣式；年度發稿明細逐筆明細放 expander；原始資料用 `st.dataframe`＋CSV。整本 Excel／PDF／列印版 HTML 三顆鈕＋每張表單獨印。
- **`tools/build_boss_workbook.py`**：CLI（`--year 2025` 或 `--ym-from/--ym-to`）從 DB 產 Excel；改用專案 `db.connect()`（讀 Supabase secrets）。`compare_boss_workbook.py` 逐格比對。
- **測試**：`tests/test_boss_workbook.py`（黃金：原檔原始資料→每張表逐格相等，**7 綠**）＋ `tests/test_boss_page.py`（v_boss_line 2025 合計 134,303,021、2026 含健康視、HTML 關鍵數字、SALES 隱藏，**4 綠**）。
- **已知資料差異**（非邏輯，見 `docs/ASSUMPTIONS.md §H`）：3 個客戶名寫法致客戶數 262→265／257→259；同額客戶先後原檔無規則、kit 定死名稱遞增。
