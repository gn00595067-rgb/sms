# CLAUDE_CODE_TASK.md — 新業績系統 MVP 建置指令

> 給 Claude Code 的完整工作說明。請從頭到尾讀完再開始，依「階段 A → G」順序執行，每個階段結尾依 §1 的格式回報。

---

## 0. 任務一句話

把一套用 Microsoft Access 寫的「業績統計系統」（廣告媒體代理商：聲活 / 東吳 / 鉑霖 / 瑞迪）重建成 **Streamlit + Supabase(PostgreSQL)** 的網頁 MVP，讓公司同仁（媒體人員、財務、高階主管）可以立刻開始用、邊用邊回報問題；舊系統的資料要完整匯入且對得上帳。

這個資料夾（kit）裡的資料庫 schema、view、ETL 腳本**已經寫好並用真實資料驗證過**（見 §2），你的主要工作是：跑起資料庫 → 匯入舊資料 → 做 Streamlit 應用程式與報表引擎 → 測試 → 部署設定 → 交付文件。

---

## 1. 工作原則

1. **不要停下來問問題。** 遇到不確定的地方，選最合理的做法，把假設寫進 `docs/ASSUMPTIONS.md`（一行一條，附影響範圍），繼續做。只有在 §3 的前置條件缺少時才停下來。
2. **每個階段結束時輸出一段簡短回報**：做了什麼、跑了哪些驗證、結果數字、新增的假設。不要貼大段程式碼。
3. **執行環境是 Windows 10/11，沒有 WSL、沒有 Docker。** 用 PowerShell 語法（`py -3.11`、`.\.venv\Scripts\Activate.ps1`、路徑用反斜線或 pathlib）。所有 Python 檔案開頭不需要 shebang；讀寫檔案一律指定 `encoding="utf-8"`；執行前設定 `$env:PYTHONUTF8 = "1"`。
4. **部署目標是 Streamlit Community Cloud（Linux）**，所以 `requirements.txt` 只能放跨平台、有 wheel 的套件；不要用需要編譯器或系統套件的東西（WeasyPrint、LibreOffice 之類都不行）。
5. **UI 全部用繁體中文**，欄位名稱用附錄 C 的對照表；程式碼、資料庫欄位、變數名稱用英文。
6. **不要修改 `sql/`、`scripts/db.py`、`scripts/db_apply.py`、`scripts/etl_legacy.py` 的商業邏輯**（可以修 bug，修了要在回報裡說明）。要新增資料表或 view，新增 `sql/005_xxx.sql` 之後的檔案，不要改 001–004。
7. **Git**：每個階段結束 commit 一次，訊息用繁體中文，格式 `階段X: 摘要`。`.gitignore` 已列出不能進版控的檔案（secrets、seed_passwords.local.txt、.venv、legacy_csv/ 之外的暫存）。`legacy_csv/` **不要**進版控（含公司資料）——已在 .gitignore。
8. **金額顯示**：千分位、無小數；比率顯示為百分比一位小數；年月顯示 `2026/09`。
9. 所有寫入資料庫的動作都經過 `scripts/db.py` 的 `transaction(user_name)`，這樣稽核 trigger 才記得到操作者。

---

## 2. 這個資料夾裡已經有的東西（已驗證，直接用）

```
perf-mvp-kit/
├── CLAUDE_CODE_TASK.md          ← 本檔
├── README.md                    ← 給 Jonathan 的操作說明（你在階段 G 補完）
├── requirements.txt             ← 已列好基本套件，可加不可減
├── .gitignore
├── .streamlit/
│   ├── config.toml              ← 主題與 server 設定
│   └── secrets.toml.example     ← 複製成 secrets.toml 填連線字串（不進版控）
├── .github/workflows/
│   └── supabase_keepalive.yml   ← 每天 ping 一次資料庫，避免 Supabase 免費方案 7 天沒活動被暫停
├── sql/                         ← 依檔名順序套用（scripts/db_apply.py）
│   ├── 001_schema.sql           ← 26 張表：主檔、deal/deal_line、invoice/writeoff、規則表、系統表
│   ├── 002_audit.sql            ← 通用稽核 trigger（記操作者與前後差異）
│   ├── 003_views.sql            ← 10 個報表 view（所有商業邏輯都在這）
│   └── 004_seed.sql             ← 區域/公司/組別/平台/業績類別 + PDF 裡的固定成本與 65 折規則
├── scripts/
│   ├── db.py                    ← 連線（DATABASE_URL 或 .streamlit/secrets.toml）、transaction()、fetch_df()
│   ├── db_apply.py              ← 套用 sql/*.sql（不需要 supabase CLI）
│   └── etl_legacy.py            ← 匯入 legacy_csv/ → legacy_* 原樣表 + 主檔 + deal/deal_line + invoice/writeoff + bonus_rule + app_user，最後自動對帳
├── legacy_csv/                  ← 舊 Access 檔匯出的 61 個 CSV（UTF-8 BOM；PASSWORD 表已去掉密碼改為 legacy_users.csv）
├── tools/
│   └── export_mdb_windows.py    ← 之後拿到往年 .mdb 時用（pyodbc）
└── docs/
    ├── legacy_schema.md         ← 舊系統 61 張表的欄位、506 個查詢、65 個表單、134 張報表清單
    ├── legacy_profile.md        ← 舊資料剖析：粒度、值域、關鍵發現、對帳目標值 ← **務必先讀**
    ├── reconciliation_targets.csv ← 年月 × 公司別 的實收/除佣/實付合計（ETL 會自動比對）
    └── requirements_gap.md      ← 公司資訊人員的需求 PDF 摘要 + 與舊系統的落差分析
```

在本地 PostgreSQL 16 上已驗證：4 個 SQL 檔可重複套用；ETL 匯入 8,535 條線 / 2,216 個合約 / 3,237 張發票，100 組（年月 × 公司別）對帳全部相符，重跑兩次結果一致。

---

## 3. 開始前 Jonathan 要準備的（缺一項就停下來，用一段話說明怎麼補）

1. **Supabase 專案**（免費方案）：region 選 Singapore 或 Tokyo；記下資料庫密碼。
   到 Supabase 後台 → Connect → 選 **Session pooler**（不是 Direct connection，Streamlit Cloud 只有 IPv4）→ 複製 URI，長這樣：
   `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
2. 把 `.streamlit/secrets.toml.example` 複製成 `.streamlit/secrets.toml`，填入上面的 URI。
3. Python 3.11 或 3.12（`py -3.11 --version` 有輸出）。
4. Git 已安裝；GitHub 帳號可建私有 repo（Streamlit Cloud 部署用）。
5. Streamlit Community Cloud 帳號（Jonathan 已有，newcue 專案在用）。

檢查方式：`python scripts/db_apply.py` 能連上並印出 `applied 001_schema.sql …` 就代表 1–3 都好了。

---

## 4. 技術架構

| 層 | 選擇 | 理由 |
|---|---|---|
| 資料庫 | Supabase PostgreSQL（免費方案） | 真正的關聯式資料庫、主鍵外鍵、trigger 稽核、SQL view 放商業邏輯；免費 |
| 應用程式 | Streamlit 1.38+（`st.navigation` 多頁） | Jonathan 與同仁已熟（newcue）；Claude Code 一次做完成功率高；部署免費 |
| 資料存取 | `psycopg` 3 + pandas，直接 SQL（不用 ORM） | 報表都是 view，SQL 最直接 |
| 登入 | 自建：`app_user` 表 + bcrypt，`st.session_state` 保存登入狀態 | 30 個使用者，不需要 OAuth；首次登入強制改密碼 |
| 報表輸出 | `reports/` 套件：DataFrame → 畫面表格 / Excel（openpyxl，含格式）/ 列印用 HTML | **與 Streamlit 解耦**，之後換前端或要做精美 PDF 都不用重寫 |
| 部署 | GitHub 私有 repo → Streamlit Community Cloud | 免費 |
| 稽核 | PostgreSQL trigger（`002_audit.sql`） | 應用程式忘了記也記得到 |

**關於「精美報表」**：畫面上的表格用 Streamlit 就夠；要給老闆看/列印的報表走 `reports/render_excel.py`（Excel 標題列、篩選條件列、千分位、合計列、凍結窗格、欄寬）和 `reports/render_html.py`（A4 列印樣式）。這兩個模組只吃 DataFrame + 欄位規格，跟 UI 框架無關。PDF 之後可以用 newcue 已驗證可行的 openpyxl + reportlab 路線加上去，本次不做。

---

## 5. 目標專案結構（你要建的）

```
perf-mvp-kit/
├── app.py                       ← 入口：登入 → st.navigation 依角色組頁面
├── core/
│   ├── auth.py                  ← login(), logout(), current_user(), require_role(), hash/verify password
│   ├── data.py                  ← 主檔快取（platforms(), customers()…，st.cache_data ttl=60）、常用查詢
│   ├── deals.py                 ← deal / deal_line 的讀寫（save_deal(header, lines, user)、產生轉撥線）
│   ├── finance.py               ← invoice / writeoff 讀寫
│   ├── masters.py               ← 主檔 CRUD 通用函式
│   ├── format.py                ← 金額/比率/年月格式化、附錄 C 的中文標籤字典
│   └── ui.py                    ← 共用元件：頁首、篩選列、問題回報側欄、確認對話框
├── pages_app/                   ← 每個頁面一個檔（st.navigation 用 st.Page 載入）
│   ├── home.py                  ← 首頁儀表板
│   ├── deal_entry.py            ← 業績登打
│   ├── deal_search.py           ← 業績查詢 / 修改
│   ├── customers.py             ← 客戶主檔
│   ├── masters.py               ← 主檔維護（平台/電台/節目/業務/人員/產業別/業績類別/規則表）
│   ├── invoices.py              ← 發票與銷帳（財務）
│   ├── reports.py               ← 報表中心
│   ├── bonus.py                 ← 簡易業務獎金
│   ├── feedback.py              ← 問題回報清單（管理）
│   ├── audit.py                 ← 稽核紀錄查詢
│   ├── users.py                 ← 使用者管理
│   └── account.py               ← 修改密碼
├── reports/
│   ├── registry.py              ← 報表定義（key、標題、view、篩選、欄位、合計、預設排序）
│   ├── query.py                 ← 依篩選組 SQL（只用參數化查詢）
│   ├── render_excel.py          ← DataFrame → 格式化 Excel bytes
│   └── render_html.py           ← DataFrame → 列印用 HTML
├── scripts/                     ← （既有）+ backup.py、keepalive.py
├── sql/                         ← （既有）+ 你新增的 005_… 
├── tests/
│   ├── conftest.py
│   ├── test_etl_rules.py        ← 純 Python：line_type 判斷、ym 解析、num 解析
│   ├── test_views.py            ← 連 DB：每個 view 可查、對帳目標相符、雙層毛利範例合約數字
│   ├── test_auth.py
│   └── test_reports.py          ← registry 每張報表能產生 DataFrame 與 Excel
└── docs/                        ← （既有）+ ASSUMPTIONS.md、USER_GUIDE.md、HOW_TO_ADD_REPORT.md、CHANGELOG.md
```

---

## 6. 階段 A：環境與資料庫

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
python scripts/db_apply.py          # 套用 sql/001–004
```

驗證：`python -c "from scripts.db import fetch_df; print(fetch_df('select count(*) as n from platform'))"` 應回 20。

若 `db_apply.py` 報連線錯誤：檢查 secrets.toml 是否用 Session pooler URI、密碼裡的特殊字元是否需要 URL 編碼（`@` → `%40`）。

---

## 7. 階段 B：匯入舊資料

```powershell
python scripts/etl_legacy.py --csv legacy_csv --source ACCESS_2026_V109g
```

預期輸出結尾：
```
   8535 lines
   3237 invoices
   494 rules
   30 users
   初始密碼寫到 seed_passwords.local.txt
   etl_issue 1480 筆（HEADER_CONFLICT 為資訊性，不是錯誤）
7) 對帳
  對帳 100 組 (年月 × 公司別)，不符 0 項
完成
```

做完後：
1. 查 `select issue, count(*) from etl_issue group by 1`，把三類 issue 的意義寫進 `docs/ASSUMPTIONS.md`：
   - `HEADER_CONFLICT`：同一合約編號內客戶/業務/組別/公司不一致 → 資訊性，line 自帶維度所以報表正確；只是 deal header 的預設值取第一條 MEDIA 線。
   - `BAD_PERF_YM`：業績年月份空白的 12 列 → 沒匯入 deal_line（仍在 legacy_業績資料表 可查）。
   - `WRITEOFF_AMOUNT_WITHOUT_DATE`：有銷帳金額沒銷帳日 → 沒建 writeoff。
2. 把 `seed_passwords.local.txt` 的內容留給 Jonathan（不要印在回報裡），提醒發給同仁後刪檔。帳號 `boss` 是 EXEC 角色。
3. 另外建一個 Jonathan 自己的 EXEC 帳號：`python scripts/create_user.py jonathan --role EXEC`（這支你要寫，見 §8.1）。

---

## 8. 階段 C：Streamlit 應用程式

### 8.1 共用層

**`core/auth.py`**
- `login(username, password) -> user dict | None`：查 `app_user`（`is_active`），bcrypt 驗證；成功後更新 `last_login_at`，把 `{id, username, display_name, role, salesperson_id, must_change_password}` 放進 `st.session_state["user"]`。
- `require_role(*roles)`：不符就 `st.error("沒有權限")` + `st.stop()`。
- `must_change_password` 為 true 時，登入後只能看到「修改密碼」頁。
- `scripts/create_user.py <username> --role EXEC|MEDIA|FINANCE|SALES [--salesperson 名稱]`：建帳號並印出隨機密碼。

**`core/data.py`**
- 主檔讀取函式全部 `@st.cache_data(ttl=60)`；任何寫入主檔後呼叫 `st.cache_data.clear()`。
- `options(table)` 回傳 `[(id, name)]` 供 selectbox。
- `customer_lookup(text)`：`name ilike` + `customer_alias.alias ilike`，回傳前 20 筆（登打時「自動搜尋帶出舊資料」用）。

**`core/deals.py`**
- `load_deal(contract_no)` → header dict + lines DataFrame（用 `v_deal_line_flat`）。
- `save_deal(header, lines_df, user)`：一個交易內 upsert `deal`、以 `deal_id` 為單位 **先刪後插** `deal_line`（MVP 最簡單且稽核表會記到）；`net_amount` 若使用者沒改就依公式 `gross × (1 − rebate_pct/100) × (1 − cash_discount_pct/100)` 四捨五入到整數。
- `make_intercompany_line(line, rules)`：給一條子公司（東吳/鉑霖）的 MEDIA 線，依 `intercompany_rule`（生效區間、平台歸類）產生一條 `INTERCOMPANY` 線：同公司別、`group` = 聲活-東 / 聲活-鉑（依公司）、`customer` = 「東吳廣告」/「鉑霖廣告」（若客戶主檔沒有就建）、`gross = net = round(原線 net × rate)`、`cost = 0`、其他維度複製；同時把原線 `cost_amount` 設為同一金額（若原線 cost 為 0）。這完全對齊舊資料的做法（docs/legacy_profile.md 第 4 點）。

**`core/ui.py`**
- `page_header(title, help_text)`。
- `feedback_widget()`：每一頁側欄都有「回報問題」展開區：類別（BUG / 建議 / 欄位不對 / 報表 / 其他）+ 文字 → 寫 `feedback`（帶 `page` = 目前頁名、`user_name`）。這是 MVP 迭代的核心機制，一定要每頁都有。
- `filters_bar(spec)`：依報表定義畫出篩選器（年月起迄、公司、平台歸類、平台、區域、業務、組別、業績類別、客戶、產業別），回傳 dict。年月選項來自 `v_months`；預設起迄 = 最近 12 個月。

### 8.2 頁面規格

角色代號：M = MEDIA 媒體人員、F = FINANCE 財務、E = EXEC 高階、S = SALES 業務（只看自己）。權限矩陣見附錄 A。

**P1 首頁 `home.py`（全部角色）**
- 本月與上月 KPI 卡：實收、除佣實收、毛利、毛利率，依公司別分欄（S 角色只看自己業務的數字）。
- 兩張圖：近 12 個月除佣實收趨勢（依公司堆疊）、本月平台歸類佔比。
- 「最近回報的問題」列表（E 看全部，其他看自己的）。

**P2 業績登打 `deal_entry.py`（M、E）**
- 上方：輸入合約編號 → 若存在則載入（進入修改模式），否則新建。
- Header 表單（兩欄）：公司別*、客戶*（搜尋式 selectbox，找不到可「新增客戶」小表單：名稱、客戶類別、產業別）、廣告名稱、業務*、組別（選業務後自動帶入）、業績類別*、客戶類別（選客戶後自動帶入）、產業別（同）、直客/廣代、上檔起始/結束、進單年月、七種人員（媒體/企劃/文案/協辦/客服/請款/結案，可空）、正本/影本/業務簽名、備註。
- Lines 表格（`st.data_editor`，可新增列、刪除列），每列欄位：線類型（MEDIA/PRODUCTION/INTERCOMPANY，預設 MEDIA）、業績年月*、平台*、電台/成本項目、節目、區域（多選：全區域/北/中/南；預設用平台的 default_region）、素材秒數、總檔數、（總秒數自動）、購買檔次、搭贈檔次、實收金額*、退佣%、現折%、除佣實收（自動、可改）、實付金額、電台實付金額、聯網、指定電台、備註。
- 每列的公司/客戶/業務/組別/業績類別/產業別預設 = header，進階展開才顯示可改（舊資料需要）。
- 按鈕：「儲存」、「產生子公司轉撥線」（對所有 company ≠ 聲活 且尚未有對應 INTERCOMPANY 線的 MEDIA 線執行 `make_intercompany_line`，先預覽再確認）、「複製上一筆合約的內容」。
- 儲存後顯示合計（實收 / 除佣 / 實付 / 毛利）並提示「已儲存，稽核編號 #…」。
- 驗證：必填、金額 ≥ 0 或允許負數（舊資料有負數，允許但顯示警告）、業績年月不可晚於今天 + 12 個月。

**P3 業績查詢 `deal_search.py`（M、E；S 只看自己）**
- 篩選：年月起迄、公司、業務、客戶（模糊）、合約編號、平台、線類型。
- 結果：`v_deal_line_flat` 表格（附錄 C 標籤），可下載 Excel；點合約編號 → 跳到 P2 修改。
- 「低毛利」快速篩選：毛利率 < 16%（舊系統的規則：非「瑞*」「製作*」電台且毛利率 ≤ 15.99% 標記）。

**P4 客戶主檔 `customers.py`（M、E）**
- 列表 + 搜尋；編輯：名稱、客戶類別、產業別、統編、聯絡人、電話、email、新案、千大、備註、啟用。
- 別名管理：新增/刪除 `customer_alias`。
- 「合併客戶」：把 A 併入 B → `deal_line.customer_id`、`deal.customer_id`、`invoice.customer_id` 全部改為 B，A 的名稱變成 B 的別名，A 停用。要二次確認。

**P5 主檔維護 `masters.py`（E；M 可維護平台/電台/節目）**
- 一個頁面用 tabs：公司、組別、業務、人員、平台、電台/成本項目、節目、產業別、客戶類別、業績類別、區域、固定成本規則、轉撥規則、獎金規則。
- 每個 tab 用 `st.data_editor` 直接編輯 + 儲存按鈕（通用 `core/masters.py`：比對差異後 insert/update；不允許刪除有被引用的列，改用 `is_active=false`）。

**P6 發票與銷帳 `invoices.py`（F、E）**
- 上：發票列表（篩選：客戶、業務、合約編號、開立日期區間、只看未結清）；欄位來自 `v_ar_open`。
- 新增/編輯發票：合約編號（可帶出 deal 的客戶/業務/組別/廣告名稱）、抬頭、統編、收款方式、廣告收入、製作收入、折讓、發票號碼、開立日、應交付日、預定兌現日、備註。
- 銷帳：選一張發票 → 新增 writeoff（收款日*、金額*、方式、匯款末五碼/支票號、備註）；顯示該發票的銷帳歷史與剩餘未收。
- 「標記已結清」：對舊資料（銷帳幾乎沒登錄）提供 `settled_manually` 勾選 + 備註，可批次（勾選多張）。

**P7 報表中心 `reports.py`（全部；S 只看自己）** → 見 §9。

**P8 簡易業務獎金 `bonus.py`（E；S 只看自己）**
- 選年月 → 顯示 `v_bonus_simple`（業務 × 平台歸類 × 業績項目 → 除佣實收、規則%、門檻、獎金），底部依業務小計；沒有規則的列顯示「未設定規則」。
- 連結到 P5 的獎金規則 tab。
- 頁面上方固定提示：「MVP 只實作第一層業務獎金（業務 × 平台歸類 × 業績項目 × 生效區間 × %、門檻），主管/協辦/客服/專案/加碼獎金尚未實作。」

**P9 問題回報清單 `feedback.py`（E）**
- 列表（狀態篩選）、可改狀態（NEW/DOING/DONE/WONTFIX）與回覆。

**P10 稽核紀錄 `audit.py`（E）**
- 篩選：表、操作者、日期、合約編號（`row_pk` 或 `new_data->>'contract_no'`）；顯示變更欄位與前後值（把 jsonb 攤成「欄位：舊值 → 新值」）。

**P11 使用者管理 `users.py`（E）**
- 列表、新增、停用、重設密碼（產生隨機密碼並顯示一次）、改角色、綁定業務（SALES）。

**P12 修改密碼 `account.py`（全部）**

---

## 9. 階段 D：報表引擎與報表

### 9.1 `reports/registry.py`

每張報表是一個 dict（或 dataclass）：

```python
REPORTS = {
  "cost_profit": {
    "title": "成本毛利分析",
    "view": "v_deal_line_flat",
    "filters": ["ym_range", "company", "platform_group", "platform", "region", "salesperson", "business_group", "sales_category", "customer", "industry", "line_type"],
    "group_by_options": {"月": ["perf_ym_text"], "月×公司": ["perf_ym_text","company"], "月×公司×平台": [...], "季×公司": ["perf_year","perf_quarter","company"], "客戶": ["customer"], "業務": ["salesperson"], "明細": None},
    "measures": ["gross_amount", "net_amount", "cost_amount", "gross_profit", "margin_pct"],
    "detail_columns": [...],       # 明細模式顯示的欄位
    "default_sort": [("perf_ym_text", "asc")],
    "totals": True,
    "roles": ["MEDIA","FINANCE","EXEC","SALES"],
    "sales_scope": "salesperson_id",   # S 角色自動加 where salesperson_id = 自己
  },
  ...
}
```

`reports/query.py`：依 registry + 篩選值組 SQL（**只用參數化查詢**，group by 欄位白名單來自 registry），回傳 DataFrame；`margin_pct` 這類比率在彙總模式要重算（Σ毛利 / Σ除佣），不能平均。

### 9.2 MVP 的 8 張報表

| key | 標題 | 來源 view | 說明 |
|---|---|---|---|
| cost_profit | 成本毛利分析 | v_deal_line_flat | 月/季/自訂區間，多維度 group by，可切明細 |
| two_layer | 雙層毛利（平台 × 月） | v_profit_two_layer | 第一層/第二層/固定成本；附說明文字（§14 假設） |
| media_volume | 媒體發稿量與秒數 | v_media_volume | 平台 × 區域 × 月：檔數、秒數、購買/搭贈檔次 |
| recognition | 業績認定表 | v_sales_recognition | 選單一業務 → 個人月報；或全部業務 → 每人一個區塊；顯示認定比例 |
| custom_range | 業績成本報表（自訂區間） | v_deal_line_flat | 同 cost_profit 但預設跨月/跨季比較（本期 vs 同期） |
| ar_aging | 應收 / 逾期帳款 | v_ar_open | 只看未結清、逾期天數分桶（0-30/31-60/61-90/90+），依業務/客戶小計 |
| bonus | 業務獎金（簡易） | v_bonus_simple | 同 P8 |
| customer_rank | 客戶排名與佔比 | v_customer_ranking | 年 × 公司，前 N 名 + 佔比，可切「業務版」（只列該業務客戶） |

每張報表頁面：篩選列 → 「查詢」→ 表格（`st.dataframe`，數字右對齊、千分位）→ 合計列 → 「下載 Excel」「列印版」兩個按鈕。列印版用 `st.components.v1.html` 顯示 `render_html` 的結果（含「列印」按鈕呼叫 `window.print()`）。

### 9.3 `reports/render_excel.py`

輸入：DataFrame、報表標題、篩選條件文字、欄位規格（標籤、型別：text/int/money/pct/ym）。輸出 bytes。
規格：第 1 列標題（粗體 14）、第 2 列篩選條件與產出時間、第 4 列表頭（底色、粗體、置中、凍結）、資料列（money `#,##0`、pct `0.0%`、負數紅色）、最後合計列（粗體、上框線）、欄寬依內容自動、中文字型 微軟正黑體。用 openpyxl。

### 9.4 `docs/HOW_TO_ADD_REPORT.md`

寫清楚：新增一張報表 = (1) `sql/00N_xxx.sql` 加一個 view → `python scripts/db_apply.py`；(2) `reports/registry.py` 加一筆；(3) 附錄 C 補中文標籤。附一個完整範例。

---

## 10. 階段 E：測試與驗收

- `pytest -q` 全綠。測試連線用同一個 `DATABASE_URL`（Supabase），**測試不得寫入 deal/deal_line/invoice**；需要寫入的測試（save_deal、writeoff）用合約編號前綴 `TEST-` 並在 teardown 刪除。
- `tests/test_views.py` 必含：
  - 對帳：`v_deal_line_flat` 依 (perf_ym, company) 的 rows/gross/net/cost 與 `docs/reconciliation_targets.csv` 一致（誤差 ≤ 1）。
  - 合約 `1130825-6-6`（2025/01）：東吳客戶線 net 380,952 / cost 247,619；聲活-東 線 net 247,618；`v_profit_two_layer` 2025-01 企頻 的 layer1_profit 與 layer2_revenue 包含這兩筆。
  - `v_bonus_simple` 2025-06 洪佳琪 廣播 開發：net 670,623、bonus_pct 2、bonus 13,412。
  - `v_ar_open`：`settled_manually=true` 的發票 outstanding = 0 且 overdue_days = 0。
- 手動驗收腳本（寫在 `docs/ACCEPTANCE.md`，你自己跑一遍並記錄結果）：
  1. 用 `boss` 登入 → 被要求改密碼 → 改完看到全部頁面。
  2. P2 新增合約 `TEST-0001`：東吳、任一客戶、全家企頻、實收 100,000、退佣 10% → 除佣 90,000；按「產生子公司轉撥線」→ 出現 聲活-東 線 58,500，原線實付 58,500；儲存 → P10 看到 3 筆稽核（deal、2 條 line）。
  3. P7 成本毛利分析選 2026/06 → 東吳 除佣 5,308,915、聲活 5,185,197、鉑霖 2,158,587（不含 TEST）。
  4. P6 對任一舊發票新增銷帳 → 未收餘額減少；標記已結清 → 從逾期清單消失。
  5. 側欄回報一個問題 → P9 看得到。
  6. 刪除 `TEST-0001`。

---

## 11. 階段 F：部署

1. `git init`，確認 `git status` 沒有 secrets.toml、seed_passwords.local.txt、legacy_csv/。建 GitHub 私有 repo 並 push（用 `gh repo create --private` 若有 gh；否則印出手動步驟）。
2. Streamlit Community Cloud：New app → 選 repo、`app.py`、Python 3.11；Advanced settings → Secrets 貼上 `secrets.toml` 的內容。寫進 `docs/DEPLOY.md`。
3. `.github/workflows/supabase_keepalive.yml` 需要 repo secret `DATABASE_URL`（在 GitHub → Settings → Secrets → Actions 新增）。寫進 DEPLOY.md。
4. `scripts/backup.py`：把所有非 legacy 表 `COPY ... TO STDOUT CSV` 打包成 `backup_YYYYMMDD.zip`；另加 `.github/workflows/weekly_backup.yml` 每週日跑一次，把 zip 當 artifact 保留 90 天。
5. Streamlit Cloud 上的 app 若閒置會休眠，第一次開啟要等 30–60 秒，這是正常的；寫進 USER_GUIDE。

---

## 12. 階段 G：交付文件

- `README.md`：Jonathan 用 — 本機啟動、重跑 ETL、加報表、加使用者、部署、備份、常見錯誤。
- `docs/USER_GUIDE.md`：同仁用 — 每個頁面一段話 + 一張截圖（用 `streamlit` 跑起來後以 Playwright 截圖；若環境沒有 Playwright 就略過截圖）。
- `docs/ASSUMPTIONS.md`：所有假設（§14 先放進去，再加你做的）。
- `docs/CHANGELOG.md`：每階段一節。
- 最後回報：一段 10 行以內的總結 + 「Jonathan 下一步要做的 5 件事」。

---

## 13. requirements.txt（已附，可加不可減）

```
streamlit>=1.38
psycopg[binary]>=3.2
pandas>=2.2
openpyxl>=3.1
bcrypt>=4.1
plotly>=5.22
jinja2>=3.1
python-dateutil>=2.9
pytest>=8
```

---

## 14. 已知假設與待公司確認事項（先抄進 docs/ASSUMPTIONS.md）

1. **雙層毛利的定義**（003_views.sql 第 3 段）：第一層 = 子公司（東吳/鉑霖/瑞迪）對客戶線的 除佣實收 − 實付；第二層 = 聲活線 + 轉撥線（組別 聲活-東/聲活-鉑）的 除佣實收 − 實付 − 該月平台歸類固定成本。是否正確待 Peggy 姐確認。
2. **固定成本規則**：企頻 75 萬/月 2026-03～2027-02；新鮮視 100 萬/月「1–12 月」假設為 2026 年。歸屬公司假設為聲活。
3. **65 折**：適用東吳、鉑霖 → 聲活，所有平台，起始 2024-01。瑞迪是否適用未知（PDF 沒提到瑞迪）。
4. **區域**：舊資料沒有區域欄位，ETL 依平台推定（全家北企 → 北、桃企 → 北、中企 → 中、南企 → 南、其他 → 全區域）。新登打由使用者選。
5. **獎金**：只做第一層業務獎金；`bonus_rule` 從舊「獎金百分比資料表」匯入 494 條（只含平台 企頻/廣播/新鮮視），舊表的「數位/單元/VERSE」平台與「直客」業績項目對不到新的分類，未匯入；門檻邏輯為「當月除佣實收 ≥ 門檻才發，否則 0」。
6. **業績認定比例**來自「業績類別資料表」（開發 1.0、既有 0.8、服務/4A 0.5）；舊系統另有「客戶認定業績資料表」（依客戶覆寫）本次未實作。
7. **應收帳款**：舊系統的銷帳幾乎沒登錄（3,237 張發票只有 176 張有銷帳日），所以匯入後幾乎全部顯示未結清/逾期。財務需用「標記已結清」批次處理，或 Jonathan 跟財務確認一個截止日一次標記。
8. **低毛利定義**：沿用舊系統 CUE 毛利計算的規則（非瑞*/製作* 電台且毛利率 ≤ 15.99%）。
9. `業績年月份` 空白的 12 列舊資料未匯入 deal_line。
10. 舊系統帳號密碼為明文，未沿用；所有人拿新密碼首次登入強制更改。
11. PDF 的「業績類別：直客 / 廣代」與舊系統的「業績類別」（開發直客/服務公司…）是兩個不同概念，分別存 `deal.category_dc` 與 `sales_category_id`。
12. 舊系統的「業績預估」「統一商機預估」「客情」「電台付款規則/預付/退佣」「年終試算」未納入 MVP（資料已在 legacy_* 表）。

---

## 附錄 A：角色權限矩陣

| 頁面 | MEDIA | FINANCE | EXEC | SALES |
|---|:-:|:-:|:-:|:-:|
| P1 首頁 | ✔ | ✔ | ✔ | ✔（自己） |
| P2 業績登打 | ✔ | – | ✔ | – |
| P3 業績查詢 | ✔ | ✔（唯讀） | ✔ | ✔（自己，唯讀） |
| P4 客戶主檔 | ✔ | 唯讀 | ✔ | 唯讀 |
| P5 主檔維護 | 平台/電台/節目 | – | ✔ | – |
| P6 發票與銷帳 | 唯讀 | ✔ | ✔ | – |
| P7 報表中心 | ✔ | ✔ | ✔ | ✔（自己） |
| P8 獎金 | – | – | ✔ | ✔（自己） |
| P9 問題回報清單 | – | – | ✔ | – |
| P10 稽核紀錄 | – | – | ✔ | – |
| P11 使用者管理 | – | – | ✔ | – |
| P12 修改密碼 | ✔ | ✔ | ✔ | ✔ |
| 側欄回報問題 | ✔ | ✔ | ✔ | ✔ |

---

## 附錄 B：舊「業績資料表」欄位 → 新欄位

| 舊欄位 | 新位置 | 備註 |
|---|---|---|
| 業績年月份 | deal_line.perf_ym | `YYYY/MM` → date 當月 1 日 |
| BLINK認列年月 | deal_line.blink_ym | |
| 合約編號 | deal.contract_no | 分組鍵 |
| 客戶名稱 | deal_line.customer_id（+ deal.customer_id 預設）| 原文字另存 legacy_customer_name |
| 客戶類別 / 業績類別 / 產業別 / 新案千大 | *_id | 新案千大全空 |
| 廣告名稱 | deal.ad_name | |
| 上檔起始/結束日期 | deal.air_start / air_end | 取合約內 min/max |
| 公司別 | deal_line.company_id | |
| 達鈴通數 / 責任檔 / BLINK檔數 | daling_count / responsibility_slots / blink_slots | |
| 電台 | deal_line.media_channel_id | 製作費-* → channel_type PRODUCTION、line_type PRODUCTION |
| 聯網 / 指定電台 | is_network / is_designated | |
| 節目名稱 | deal_line.program_id | (名稱, 電台) 唯一 |
| 實收金額 / 實付金額 / 電台實付金額 / 媒體效益 | gross_amount / cost_amount / channel_cost_amount / media_benefit | |
| 退佣折扣 | rebate_pct | 10 = 10% |
| 除佣實收 | net_amount | 原值匯入不重算 |
| 媒體/企劃/文案/協辦/客服/請款/結案人員 | deal.*_staff_id | |
| 組別 | deal_line.group_id | 聲活-東/聲活-鉑 → is_intercompany，line_type INTERCOMPANY |
| 業務 | deal_line.salesperson_id | |
| 平台 | deal_line.platform_id | 主檔沒有的值自動建，歸類依名稱推定 |
| 購買/搭贈檔次、搭贈金額/組合、編播贈檔、搭贈方案 | 同名英文欄位 | |
| 電台已付款 / 收款日期 / 預計發票日 | is_channel_paid / payment_received_on / planned_invoice_on | |
| 低毛利已處理 / 低毛利原因 / 不計客服獎金 | 同名英文欄位 | |
| 正本 / 影本 / 業務簽名 | deal.is_original_received / is_copy_received / is_sales_signed | |
| 建立者/時間、修改者/時間 | created_by（其餘由系統） | |
| 瑞好 / 瑞苦 / 瑞好除佣實收 / 合約期限 | 未搬（全空或已停用），在 legacy_業績資料表 | |

---

## 附錄 C：欄位中文標籤（`core/format.py` 的 LABELS）

```python
LABELS = {
  "contract_no": "合約編號", "line_no": "線號", "line_type": "線類型", "perf_ym_text": "業績年月", "perf_year": "年", "perf_quarter": "季",
  "blink_ym": "BLINK認列年月", "order_ym": "進單年月", "company": "公司別", "customer": "客戶名稱", "legacy_customer_name": "原始客戶名稱",
  "ad_name": "廣告名稱", "salesperson": "業務", "business_group": "組別", "sales_category": "業績類別", "sales_item": "業績項目",
  "recognition_ratio": "認定比例", "customer_category": "客戶類別", "industry": "產業別", "platform": "平台", "platform_group": "平台歸類",
  "media_channel": "電台/項目", "program": "節目", "region": "區域", "region_text": "區域", "is_network": "聯網", "is_designated": "指定電台",
  "air_start": "上檔起始", "air_end": "上檔結束", "gross_amount": "實收金額", "rebate_pct": "退佣%", "cash_discount_pct": "現折%",
  "net_amount": "除佣實收", "cost_amount": "實付金額", "channel_cost_amount": "電台實付", "media_benefit": "媒體效益",
  "gross_profit": "毛利", "margin_pct": "毛利率", "recognized_amount": "認定業績", "material_seconds": "素材秒數", "total_frames": "總檔數",
  "total_seconds": "總秒數", "purchased_slots": "購買檔次", "bonus_slots": "搭贈檔次", "bonus_amount": "搭贈金額", "blink_slots": "BLINK檔數",
  "line_count": "筆數", "deal_count": "合約數", "layer1_revenue": "第一層收入", "layer1_cost": "第一層成本", "layer1_profit": "第一層毛利",
  "layer2_revenue": "第二層收入", "layer2_direct_cost": "第二層直接成本", "fixed_cost": "固定成本", "layer2_profit": "第二層毛利",
  "invoice_no": "發票號碼", "customer_title": "抬頭", "payment_method": "收款方式", "invoice_issued_on": "開立日", "invoice_due_on": "應交付日",
  "expected_cash_on": "預定兌現日", "amount_total": "帳款金額", "allowance_note_amount": "折讓單金額", "received_amount": "已收金額",
  "last_received_on": "最近收款日", "outstanding_amount": "未收金額", "is_settled": "已結清", "overdue_days": "逾期天數",
  "bonus_pct": "獎金%", "threshold_amount": "門檻", "rule_note": "規則備註", "rank_in_company": "名次", "share_in_company": "佔比",
  "low_margin_handled": "低毛利已處理", "low_margin_reason": "低毛利原因", "notes": "備註", "created_by": "建立者", "updated_at": "更新時間",
}
```
