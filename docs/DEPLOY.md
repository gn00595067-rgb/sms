# 部署說明 — DEPLOY.md

目標：GitHub 私有 repo → Streamlit Community Cloud（免費）＋ Supabase（免費）。

## 0. 前置

- Supabase 專案已建立，**Session pooler** 連線字串已填入 `.streamlit/secrets.toml`（見 secrets.toml.example）。
- `python scripts/db_apply.py`、`python scripts/etl_legacy.py` 已在本機跑過、對帳相符。

## 1. 建 GitHub 私有 repo 並推上去

```powershell
git init
git add .
git status        # 確認沒有 secrets.toml / seed_passwords.local.txt / legacy_csv/（.gitignore 已排除）
git commit -m "階段F: 初始版本"
```

有 GitHub CLI（`gh`）：

```powershell
gh repo create perf-mvp --private --source . --push
```

沒有 `gh`：先到 github.com 手動建立私有 repo `perf-mvp`，再：

```powershell
git branch -M main
git remote add origin https://github.com/<你的帳號>/perf-mvp.git
git push -u origin main
```

> ⚠️ `legacy_csv/`（公司資料）、`.streamlit/secrets.toml`、`seed_passwords.local.txt` 都在 `.gitignore`，**不會**進版控。

## 2. Streamlit Community Cloud 部署

1. https://share.streamlit.io → **New app** → 選你的 repo、branch `main`、主檔 `app.py`、Python 版本 **3.11**。
2. **Advanced settings → Secrets**：把本機 `.streamlit/secrets.toml` 的內容整段貼上：
   ```toml
   [db]
   url = "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   ```
3. Deploy。第一次啟動要裝套件，約 1–2 分鐘。

## 3. keepalive（避免 Supabase 免費方案 7 天沒活動被暫停）

`.github/workflows/supabase_keepalive.yml` 每天 ping 一次資料庫，需要 repo secret：

- GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**
- Name = `DATABASE_URL`，Value = 同上那條 Session pooler 連線字串。

## 4. 每週備份

`.github/workflows/weekly_backup.yml` 每週日備份所有非 legacy 表成 zip（artifact 保留 90 天），
同樣需要上面的 `DATABASE_URL` secret。也可手動：Actions → weekly-backup → Run workflow。
本機備份：`python scripts/backup.py`（產生 `backup_YYYYMMDD.zip`）。

## 5. 更新流程

改完程式 → `git add . && git commit -m "..." && git push` → Streamlit Cloud 自動重新部署。
改了 SQL（新增 view）→ 在本機 `python scripts/db_apply.py`（線上 app 直接讀新 view，不需重部署）。

## 常見問題

- **連不上 DB**：確認用的是 **Session pooler**（不是 Direct connection，Streamlit Cloud 只有 IPv4）；密碼特殊字元要 URL 編碼（`@` → `%40`）。
- **app 閒置後第一次開很慢**：Streamlit Cloud 免費方案閒置會休眠，第一次喚醒要等 30–60 秒，屬正常。
- **ETL 很慢**：跨網對遠端 Supabase 逐筆寫入會慢（首爾約每筆 0.1–0.2 秒）；建議在本機一次跑完再部署，線上不需重跑 ETL。
