# 新業績系統 MVP（perf-mvp）

舊 Access「業績統計系統」的重建版：Streamlit + Supabase(PostgreSQL)。
公司：聲活 / 東吳 / 鉑霖 / 瑞迪。給同仁邊用邊回報、快速迭代。

- 同仁怎麼用 → `docs/USER_GUIDE.md`
- 部署到雲端 → `docs/DEPLOY.md`
- 新增報表 → `docs/HOW_TO_ADD_REPORT.md`
- 假設與待確認 → `docs/ASSUMPTIONS.md`

---

## 本機啟動

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# 首次：把 .streamlit/secrets.toml.example 複製成 secrets.toml，填 Supabase Session pooler 連線字串
python scripts/db_apply.py        # 建表 / 更新 view（idempotent，可重跑）
python scripts/etl_legacy.py      # 匯入 legacy_csv/ 並自動對帳（首次或要重灌時才跑）
streamlit run app.py
```

> 遠端對 Supabase 逐筆寫入較慢（首爾約每筆 0.1–0.2 秒，全量 ETL 可能 30–45 分鐘）。建議在本機一次跑完；線上不需重跑 ETL。

## 重跑 ETL

`etl_legacy.py` 可重複執行：同一個 `--source` 會先清掉上次匯入的 deal/deal_line/invoice/writeoff 再重匯，
legacy_* 原樣表也會以 `_source` 清掉重灌。對帳不符會自動 rollback 並印出差異。

```powershell
python scripts/etl_legacy.py --csv legacy_csv --source ACCESS_2026_V109g
```

## 加報表

見 `docs/HOW_TO_ADD_REPORT.md`：`sql/005_*.sql` 加 view → `db_apply.py` → `reports/registry.py` 加一筆 → `core/format.py` 補標籤。

## 加使用者

```powershell
python scripts/create_user.py jonathan --role EXEC
python scripts/create_user.py amy --role SALES --salesperson 洪佳琪
```

或用 app 內「👥 使用者管理」頁（EXEC）。角色：EXEC / MEDIA / FINANCE / SALES。
初始密碼只顯示一次，請安全交付；本人首次登入強制改密碼。

## 部署

見 `docs/DEPLOY.md`：GitHub 私有 repo → Streamlit Community Cloud，Secrets 貼 secrets.toml 內容；
設 repo secret `DATABASE_URL` 供 keepalive 與每週備份 workflow 使用。

## 備份

```powershell
python scripts/backup.py          # 產生 backup_YYYYMMDD.zip（所有非 legacy 表）
```

`.github/workflows/weekly_backup.yml` 每週日自動備份，artifact 保留 90 天。

## 測試

```powershell
pytest -q                          # 純 Python 測試永遠跑；連得到 DB 時 view/報表/往返測試也跑
```

## 常見錯誤

| 症狀 | 解法 |
|---|---|
| `找不到資料庫連線字串` | 沒建 `.streamlit/secrets.toml`，或格式不對（要 `[db]` / `url = "..."`）。 |
| 連線逾時 / 連不上 | 必須用 Supabase **Session pooler**（不是 Direct connection）；密碼特殊字元要 URL 編碼（`@`→`%40`）。 |
| ETL 對帳不符 | 會自動 rollback；看印出的 `年月 公司別 欄位: db=… csv=…` 差異，多半是 legacy_csv 被改動。 |
| 中文變亂碼 | 執行前 `$env:PYTHONUTF8 = "1"`；讀寫檔一律 `encoding="utf-8"`。 |
| app 第一次開很慢 | Streamlit Cloud 免費方案閒置休眠，喚醒要 30–60 秒，正常。 |

## 專案結構

```
app.py            入口（登入 + 導覽）
core/             共用層（auth/data/deals/finance/masters/format/ui/admin）
pages_app/        12 個頁面
reports/          報表引擎（registry/query/render_excel/render_html）
scripts/          db/db_apply/etl_legacy/create_user/backup/keepalive
sql/              001–004（勿改）＋ 005 以後（你的新 view）
tests/            pytest
docs/             說明文件
legacy_csv/       舊系統匯出（不進版控）
```
