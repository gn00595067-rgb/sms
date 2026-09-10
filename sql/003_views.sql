-- =====================================================================
-- 003_views.sql  報表用 view
-- 所有商業邏輯集中在這裡；Streamlit 報表頁只做「select ... from v_xxx where 篩選」。
-- 新增一張報表 = 新增一個 view + reports/registry.py 一筆設定。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. 平面化：一列 = 一條 deal_line + 所有維度名稱 + 衍生值
--    （形狀刻意對齊舊系統「業績資料表」，舊報表都能從這個 view 重建）
-- ---------------------------------------------------------------------
create or replace view v_deal_line_flat as
select
  l.id                              as line_id,
  d.id                              as deal_id,
  d.contract_no,
  l.line_no,
  l.line_type,
  l.perf_ym,
  to_char(l.perf_ym, 'YYYY/MM')     as perf_ym_text,
  extract(year from l.perf_ym)::int as perf_year,
  extract(quarter from l.perf_ym)::int as perf_quarter,
  l.blink_ym,
  l.order_ym,
  c.name                            as company,
  c.is_parent                       as company_is_parent,
  cu.name                           as customer,
  l.legacy_customer_name,
  d.ad_name,
  sp.name                           as salesperson,
  g.name                            as business_group,
  g.is_intercompany                 as group_is_intercompany,
  sc.name                           as sales_category,
  sc.parent_category                as sales_item,
  sc.recognition_ratio,
  cc.name                           as customer_category,
  ind.name                          as industry,
  p.name                            as platform,
  p.platform_group,
  mc.name                           as media_channel,
  mc.channel_type,
  pr.name                           as program,
  l.region_codes,
  array_to_string(l.region_codes, ',') as region_text,
  l.is_network,
  l.is_designated,
  d.air_start,
  d.air_end,
  l.gross_amount,
  l.rebate_pct,
  l.cash_discount_pct,
  l.net_amount,
  l.cost_amount,
  l.channel_cost_amount,
  l.media_benefit,
  (l.net_amount - l.cost_amount)    as gross_profit,
  case when l.net_amount <> 0 then round((l.net_amount - l.cost_amount) / l.net_amount, 4) end as margin_pct,
  round(l.net_amount * coalesce(sc.recognition_ratio, 1), 0) as recognized_amount,
  l.material_seconds,
  l.total_frames,
  l.total_seconds,
  l.purchased_slots,
  l.bonus_slots,
  l.bonus_amount,
  l.blink_slots,
  l.daling_count,
  l.responsibility_slots,
  l.is_channel_paid,
  l.payment_received_on,
  l.planned_invoice_on,
  l.low_margin_handled,
  l.low_margin_reason,
  l.exclude_cs_bonus,
  l.notes,
  l.legacy_source,
  l.legacy_row_no,
  l.created_by,
  l.created_at,
  l.updated_by,
  l.updated_at,
  l.company_id, l.customer_id, l.salesperson_id, l.group_id, l.sales_category_id,
  l.customer_category_id, l.industry_id, l.platform_id, l.media_channel_id, l.program_id
from deal_line l
join deal d                    on d.id = l.deal_id
left join company c            on c.id = l.company_id
left join customer cu          on cu.id = l.customer_id
left join salesperson sp       on sp.id = l.salesperson_id
left join business_group g     on g.id = l.group_id
left join sales_category sc    on sc.id = l.sales_category_id
left join customer_category cc on cc.id = l.customer_category_id
left join industry ind         on ind.id = l.industry_id
left join platform p           on p.id = l.platform_id
left join media_channel mc     on mc.id = l.media_channel_id
left join program pr           on pr.id = l.program_id;

-- 有資料的月份清單（給篩選器與固定成本展開用）
create or replace view v_months as
select distinct perf_ym from deal_line order by perf_ym;

-- ---------------------------------------------------------------------
-- 1. 成本毛利分析（月 × 公司 × 平台歸類 × 平台）
-- ---------------------------------------------------------------------
create or replace view v_cost_profit_monthly as
select
  perf_ym, perf_ym_text, perf_year, perf_quarter,
  company, platform_group, platform,
  count(*)                    as line_count,
  count(distinct contract_no) as deal_count,
  sum(gross_amount)           as gross_amount,
  sum(net_amount)             as net_amount,
  sum(cost_amount)            as cost_amount,
  sum(gross_profit)           as gross_profit,
  case when sum(net_amount) <> 0 then round(sum(gross_profit) / sum(net_amount), 4) end as margin_pct
from v_deal_line_flat
group by perf_ym, perf_ym_text, perf_year, perf_quarter, company, platform_group, platform;

-- ---------------------------------------------------------------------
-- 2. 固定成本按月展開（規則表 × 有資料的月份）
-- ---------------------------------------------------------------------
create or replace view v_fixed_cost_monthly as
select
  m.perf_ym,
  r.id                                  as rule_id,
  coalesce(r.platform_group, p.platform_group, '其它') as platform_group,
  p.name                                as platform,
  mc.name                               as media_channel,
  coalesce(c.name, '聲活')              as company,
  r.monthly_amount,
  r.note
from v_months m
join fixed_cost_rule r on m.perf_ym >= r.ym_from and (r.ym_to is null or m.perf_ym <= r.ym_to)
left join platform p       on p.id = r.platform_id
left join media_channel mc on mc.id = r.media_channel_id
left join company c        on c.id = r.company_id;

-- ---------------------------------------------------------------------
-- 3. 雙層毛利（月 × 平台歸類）
--    第一層（實務毛利）：子公司（東吳/鉑霖/瑞迪）對客戶線的 除佣實收 − 實付（實付已含付給聲活的 65 折）
--    第二層（聲活帳面）：聲活線 + 轉撥線（聲活-東/聲活-鉑）的 除佣實收 − 實付 − 該月平台固定成本
--    ※ 假設，需與公司確認（docs/ASSUMPTIONS.md）
-- ---------------------------------------------------------------------
create or replace view v_profit_two_layer as
with base as (
  select
    perf_ym, perf_ym_text, platform_group,
    sum(case when not company_is_parent and line_type <> 'INTERCOMPANY' and not coalesce(group_is_intercompany,false) then net_amount  else 0 end) as layer1_revenue,
    sum(case when not company_is_parent and line_type <> 'INTERCOMPANY' and not coalesce(group_is_intercompany,false) then cost_amount else 0 end) as layer1_cost,
    sum(case when company_is_parent or line_type = 'INTERCOMPANY' or coalesce(group_is_intercompany,false) then net_amount  else 0 end) as layer2_revenue,
    sum(case when company_is_parent or line_type = 'INTERCOMPANY' or coalesce(group_is_intercompany,false) then cost_amount else 0 end) as layer2_direct_cost
  from v_deal_line_flat
  group by perf_ym, perf_ym_text, platform_group
),
fc as (
  select perf_ym, platform_group, sum(monthly_amount) as fixed_cost
  from v_fixed_cost_monthly
  group by perf_ym, platform_group
)
select
  b.perf_ym, b.perf_ym_text, b.platform_group,
  b.layer1_revenue, b.layer1_cost,
  (b.layer1_revenue - b.layer1_cost)                                   as layer1_profit,
  b.layer2_revenue, b.layer2_direct_cost,
  coalesce(fc.fixed_cost, 0)                                           as fixed_cost,
  (b.layer2_revenue - b.layer2_direct_cost - coalesce(fc.fixed_cost,0)) as layer2_profit
from base b
left join fc on fc.perf_ym = b.perf_ym and fc.platform_group = b.platform_group;

-- ---------------------------------------------------------------------
-- 4. 媒體發稿量與秒數控管（月 × 平台 × 區域）
-- ---------------------------------------------------------------------
create or replace view v_media_volume as
select
  f.perf_ym, f.perf_ym_text, f.company, f.platform_group, f.platform,
  rg.code as region_code, rg.name as region,
  count(*)                          as line_count,
  count(distinct f.contract_no)     as deal_count,
  sum(f.total_frames)               as total_frames,
  sum(f.total_seconds)              as total_seconds,
  sum(f.purchased_slots)            as purchased_slots,
  sum(f.bonus_slots)                as bonus_slots,
  sum(f.blink_slots)                as blink_slots,
  sum(f.net_amount)                 as net_amount
from v_deal_line_flat f
cross join lateral unnest(f.region_codes) as u(code)
join region rg on rg.code = u.code
where f.line_type = 'MEDIA'
group by f.perf_ym, f.perf_ym_text, f.company, f.platform_group, f.platform, rg.code, rg.name, rg.sort_order;

-- ---------------------------------------------------------------------
-- 5. 業績認定表（月 × 業務 × 業績項目）
-- ---------------------------------------------------------------------
create or replace view v_sales_recognition as
select
  perf_ym, perf_ym_text, perf_year,
  salesperson, business_group, company, sales_item, sales_category, recognition_ratio,
  count(distinct contract_no) as deal_count,
  sum(gross_amount)           as gross_amount,
  sum(net_amount)             as net_amount,
  sum(cost_amount)            as cost_amount,
  sum(gross_profit)           as gross_profit,
  sum(recognized_amount)      as recognized_amount
from v_deal_line_flat
where line_type <> 'INTERCOMPANY' and not coalesce(group_is_intercompany, false)
group by perf_ym, perf_ym_text, perf_year, salesperson, business_group, company, sales_item, sales_category, recognition_ratio;

-- ---------------------------------------------------------------------
-- 6. 應收 / 逾期帳款（發票 − 銷帳）
--    舊系統：帳款金額 = 廣告收入 + 製作收入；未沖金額 = 帳款金額 − 銷帳金額 − 折讓單金額
-- ---------------------------------------------------------------------
create or replace view v_ar_open as
select
  i.id                                   as invoice_id,
  i.contract_no,
  i.invoice_no,
  i.customer_title,
  cu.name                                as customer,
  sp.name                                as salesperson,
  g.name                                 as business_group,
  i.ad_name,
  i.payment_method,
  i.invoice_issued_on,
  i.invoice_due_on,
  i.expected_cash_on,
  (i.ad_income + i.production_income)    as amount_total,
  i.allowance_note_amount,
  coalesce(w.received_amount, 0)         as received_amount,
  w.last_received_on,
  case when i.settled_manually then 0
       else (i.ad_income + i.production_income - i.allowance_note_amount - coalesce(w.received_amount, 0)) end as outstanding_amount,
  (i.settled_manually or (i.ad_income + i.production_income - i.allowance_note_amount - coalesce(w.received_amount, 0)) <= 0) as is_settled,
  i.settled_manually,
  case when i.expected_cash_on is not null
        and not i.settled_manually
        and (i.ad_income + i.production_income - i.allowance_note_amount - coalesce(w.received_amount, 0)) > 0
        and i.expected_cash_on < current_date
       then (current_date - i.expected_cash_on) else 0 end as overdue_days,
  i.legacy_source,
  i.notes, i.notes2, i.settled_note
from invoice i
left join customer cu   on cu.id = i.customer_id
left join salesperson sp on sp.id = i.salesperson_id
left join business_group g on g.id = i.group_id
left join lateral (
  select sum(received_amount) as received_amount, max(received_on) as last_received_on
  from writeoff w where w.invoice_id = i.id
) w on true;

-- ---------------------------------------------------------------------
-- 7. 簡易業務獎金（月 × 業務 × 平台歸類 × 業績項目）
--    規則優先序：指定業務 > 指定平台歸類 > 指定業績項目 > 通用
-- ---------------------------------------------------------------------
create or replace view v_bonus_simple as
with base as (
  select perf_ym, perf_ym_text, salesperson_id, salesperson, business_group, platform_group, sales_item,
         sum(net_amount) as net_amount, sum(gross_profit) as gross_profit
  from v_deal_line_flat
  where line_type = 'MEDIA' and not coalesce(group_is_intercompany, false)
  group by perf_ym, perf_ym_text, salesperson_id, salesperson, business_group, platform_group, sales_item
)
select
  b.perf_ym, b.perf_ym_text, b.salesperson, b.business_group, b.platform_group, b.sales_item,
  b.net_amount, b.gross_profit,
  r.id           as rule_id,
  r.bonus_pct,
  r.threshold_amount,
  case when r.id is null then null
       when b.net_amount >= r.threshold_amount then round(b.net_amount * r.bonus_pct / 100, 0)
       else 0 end as bonus_amount,
  r.note         as rule_note
from base b
left join lateral (
  select * from bonus_rule r
  where b.perf_ym >= r.ym_from and (r.ym_to is null or b.perf_ym <= r.ym_to)
    and (r.salesperson_id is null or r.salesperson_id = b.salesperson_id)
    and (r.platform_group is null or r.platform_group = b.platform_group)
    and (r.sales_item is null or r.sales_item = b.sales_item)
  order by (r.salesperson_id is not null) desc, (r.platform_group is not null) desc, (r.sales_item is not null) desc, r.ym_from desc
  limit 1
) r on true;

-- ---------------------------------------------------------------------
-- 8. 客戶排名與佔比（年 × 公司 × 客戶，依除佣實收）
-- ---------------------------------------------------------------------
create or replace view v_customer_ranking as
with t as (
  select perf_year, company, customer,
         sum(net_amount) as net_amount, sum(gross_profit) as gross_profit, count(distinct contract_no) as deal_count
  from v_deal_line_flat
  where line_type <> 'INTERCOMPANY' and not coalesce(group_is_intercompany, false)
  group by perf_year, company, customer
)
select
  perf_year, company, customer, deal_count, net_amount, gross_profit,
  rank() over (partition by perf_year, company order by net_amount desc) as rank_in_company,
  round(net_amount / nullif(sum(net_amount) over (partition by perf_year, company), 0), 4) as share_in_company
from t;
