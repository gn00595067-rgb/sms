-- =====================================================================
-- 008_report_builder.sql — 階段 M：自訂條件報表產生器（CLAUDE_CODE_TASK_4 §5）
--   - v_report_line 補 group_profit_alloc（線層看集團毛利：line.net / deal.ext_net × deal.group_profit）
--   - saved_report：使用者存下來的報表定義（JSON），SALES 只看自己、不能分享
--   可重複執行（idempotent）。
-- =====================================================================

-- v_report_line 加集團毛利分攤欄（create or replace，末尾 append 一欄）
create or replace view v_report_line as
select l.*,
       case when l.is_barter then l.salesperson_base else l.salesperson end            as salesperson_merged,
       l.perf_year::text || '/' || lpad(extract(month from l.perf_ym)::text, 2, '0')    as ym,
       to_char(l.air_start, 'FMMM/FMDD') || '-' || to_char(l.air_end, 'FMMM/FMDD')       as air_period_text,
       (l.net_amount / nullif(ds.ext_net, 0) * ds.group_profit)                          as group_profit_alloc
from v_line_ext l
left join v_deal_summary ds on ds.deal_id = l.deal_id;

create table if not exists saved_report (
  id          serial primary key,
  name        text not null,
  owner_id    int  not null references app_user(id),
  is_shared   boolean not null default false,
  definition  jsonb not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  updated_by  text,
  unique (owner_id, name)
);
comment on table saved_report is '自訂報表定義（產生器）。SALES 可存、只看自己，不能分享。';
create index if not exists ix_saved_report_shared on saved_report(is_shared) where is_shared;

do $$
begin
  execute 'drop trigger if exists trg_saved_report_audit on saved_report';
  execute 'create trigger trg_saved_report_audit after insert or update or delete on saved_report for each row execute function fn_audit()';
  execute 'drop trigger if exists trg_saved_report_updated_at on saved_report';
  execute 'create trigger trg_saved_report_updated_at before update on saved_report for each row execute function fn_set_updated_at()';
end $$;
