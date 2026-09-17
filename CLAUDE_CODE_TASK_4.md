# CLAUDE_CODE_TASK_4.md — 老闆工作簿整併 ＋ 自訂條件報表產生器

> 依據：`2025年度_三公司發稿明細分析-0917.xlsx`（老闆看的版本）對照現行程式（commit cad9fd2，已含 TASK_3 修正清單）。
> 本文件分四個階段：J（口徑與平台，SQL）→ K（併入現有分析頁）→ L（新增兩張老闆版報表）→ M（自訂條件報表產生器）。
> 每階段做完在 `docs/CHANGELOG.md` 記一行；新增 SQL 一律放 `sql/007_report_platform.sql`、`sql/008_report_builder.sql`，不改 005 的商業邏輯（只 `create or replace view` 覆蓋指定的幾個）。
> 「老闆工作簿」在本文件指上面那個 xlsx；「發稿口徑」指它的計算規則（§1.1）。

---

## 0. 結論先講

1. **老闆工作簿的每一個數字，現有資料庫都算得出來、而且對到個位數**（§1.2）。它不是另一套資料，而是同一份資料套了另一套「口徑」：只算媒體上稿線、交換併回原業務、平台切成 全家企頻／萬家福／新鮮視／廣播 四欄、只看帳上毛利。所以**不用另做一套系統，要做的是把「口徑」變成使用者可以選的東西**。
2. **併入現有分析頁的（階段 K）**：四平台欄位、含／不含廣播、客戶數（不重複）、業務 × 平台的成本／毛利／利率、客戶排名的跨公司「公司／業務」欄、發稿口徑切換。
3. **另外新增的（階段 L）**：兩張老闆版「印出來的表」——「年度發稿明細（喬商版型）」與「平台總計總覽（老闆版 Excel）」。
4. **順手發現的 P0**：`v_deal_summary` 的 `net_cp` 只認 `platform_group = '企頻'`，2024–2025 的全家分區線全部掉進 `net_other`。階段 J 第一件事就是修這個。
5. **自訂報表產生器（階段 M）**：一頁完成「期間 → 口徑 → 篩選 → 列／欄維度 → 指標 → 表格 → Excel／儲存成我的報表」。

（完整規格見專案交付對話；本檔為存查版。實作進度見 docs/CHANGELOG.md 階段 J–M。）

---

## 進度追蹤

- **階段 J（完成）**：`sql/007_report_platform.sql`。report_platform 七欄；v_line_ext 加 in_media_scope/is_own_media；v_deal_summary 四平台欄改 report_platform（P0）+ 新增 net_cp_family/carrefour/clinic；v_group_month 集團毛利橋收斂 + ic_transfer_gross；新增 v_report_line。驗收 `tests/test_analysis.py::test_boss_workbook_2025` 對過老闆工作簿黃金數字（全部對到元），pytest 45 passed 零回歸。
- **階段 K（進行中）**：口徑切換元件、分析頁改線層、公司分析平台總覽、業務矩陣加欄、客戶排名加欄。
- **階段 L（待做）**：reports/annual_detail.py、reports/platform_overview.py、registry custom 模式。
- **階段 M（待做）**：reports/builder.py、pages_app/report_builder.py、sql/008 saved_report、seed 六個預設、Excel 多層表頭、tests/test_builder.py。

## §7 給 Peggy 姐確認（見 docs/ASSUMPTIONS.md §G）

1. 「企頻」（李奧貝納年度頻道營運 619 萬）與「企頻-年度維運費」歸「營運」、不進四平台欄？
2. 「麥當勞」平台要獨立一欄，還是併「其它」？
3. 交換：老闆年度表算進業績（併回原業務）、分析頁預設排除，兩種都保留、預設哪個？
4. 瑞迪 2025 的 10 筆（536,190）老闆併在東吳；新系統保留瑞迪，是否提供「併入東吳」選項？
5. 2025 固定成本數字（企頻／新鮮視／健康視）——沒有它 2025 看不到集團淨利。
