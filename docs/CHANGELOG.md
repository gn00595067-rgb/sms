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
