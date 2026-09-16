-- =====================================================================
-- 006_review_fixes.sql — 分析頁檢視後的資料層修正（CLAUDE_CODE_TASK_3）
--   不改 sql/005 的商業邏輯；只調整截止月定義、補進行中月份概況、停用垃圾業務名。
--   可重複執行（idempotent）。
-- =====================================================================

-- ---------------------------------------------------------------------
-- P0-3：分析截止月 = 最後一個「已結束」的月份（本月進行中不算），
--       避免只登到月初的當月被當成完整月，拉低所有同期比較。
--       欄位與 005 相同（as_of_ym / as_of_year / as_of_month），可直接 replace。
-- ---------------------------------------------------------------------
create or replace view v_as_of as
select max(perf_ym) as as_of_ym,
       extract(year  from max(perf_ym))::int as as_of_year,
       extract(month from max(perf_ym))::int as as_of_month
from deal_line
where perf_ym < date_trunc('month', current_date)::date;

-- 進行中（本月）概況：提示「未納入預設區間」用
create or replace view v_open_month as
select date_trunc('month', current_date)::date                                   as perf_ym,
       count(distinct deal_id)                                                    as deals,
       coalesce(sum(net_amount) filter (where line_type <> 'INTERCOMPANY'), 0)    as ext_net,
       max(created_at)                                                            as last_entry
from deal_line
where perf_ym = date_trunc('month', current_date)::date;

-- ---------------------------------------------------------------------
-- P0-6：停用垃圾業務名（如「+」或單一字元），避免出現在下鑽頁預設值。
-- ---------------------------------------------------------------------
update salesperson set is_active = false
where is_active and (name is null or length(btrim(name)) <= 1);
