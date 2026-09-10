# 驗收紀錄 — ACCEPTANCE.md

環境：Windows 11 + Python 3.11、Supabase（ap-northeast-2 Session pooler）。
資料來源：ACCESS_2026_V109g（legacy_csv 61 檔）。

## 自動驗收（已執行，結果如下）

| 項目 | 結果 |
|---|---|
| `db_apply.py` 套用 001–004 | ✅ 全成功；`platform` = 20 |
| `etl_legacy.py` 匯入 | ✅ 8,535 lines / 3,237 invoices / 494 rules / 30 users |
| **對帳（年月 × 公司別）** | ✅ **100 組，不符 0 項** |
| etl_issue 分類 | HEADER_CONFLICT 1457（資訊性）/ BAD_PERF_YM 12 / WRITEOFF_AMOUNT_WITHOUT_DATE 11 = 1480 |
| `pytest -q` | ✅ **25 passed**（純 Python + DB：對帳/雙層/獎金/應收/報表/往返） |
| 頁面 headless 煙霧測試（AppTest 經 app.py 驅動，EXEC 身分，連實際 DB） | ✅ **12/12 頁面無例外** |

## §10 驗收步驟對照

1. **boss 登入 → 強制改密碼 → 看到全部頁面**：登入/強制改密碼邏輯由 `test_auth` + `account` 頁煙霧測試涵蓋；boss 帳號為 EXEC（ETL 依機密報表權限建立）。建議 Jonathan 首次 demo 前手動走一次。
2. **P2 新增 TEST-0001（東吳、全家企頻、實收 100,000、退佣 10% → 除佣 90,000）；產生轉撥線 → 聲活-東 58,500、原線實付 58,500；儲存 → 稽核 3 筆**：由 `test_deals.py::test_save_deal_and_intercompany_roundtrip` 自動驗證（TEST- 前綴，teardown 刪除）✅ — 除佣 90,000、轉撥 58,500、原線實付 58,500、稽核有紀錄、刪除後查無。
3. **P7 成本毛利分析 2026/06 各公司除佣**：✅ 實測 東吳 **5,308,915**、聲活 **5,185,197**、鉑霖 **2,158,587**（與 §10 目標值一致；不含 TEST）。
4. **P6 銷帳 / 標記已結清使未收/逾期歸零**：`v_ar_open` 的 outstanding/overdue 不變式由 `test_views::test_ar_settled_manually_invariant` 驗證 ✅；銷帳寫入路徑 `core.finance.add_writeoff`/`mark_settled` 已測 import + 頁面煙霧。
5. **側欄回報問題 → P9 看得到**：`feedback` 寫入（core.ui.feedback_widget）與 `feedback` 頁讀取（core.admin.list_feedback）均煙霧測試通過；建議手動送一則確認端到端。
6. **刪除 TEST-0001**：由 test_deals teardown 自動完成 ✅。

## 建議 Jonathan 手動再走一遍（demo 前）

- 用 `boss` 或 `jonathan`（EXEC）登入 → 改密碼 → 逐頁點一次。
- P2 實際登打一張新合約 + 產生轉撥線，確認畫面互動符合預期。
- P6 對一張舊發票登錄銷帳 + 批次標記已結清。
- 側欄回報一則問題，到 P9 確認收到。
