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
