-- =====================================================================
-- 005_analysis.sql  四大分析報表（客戶 / 業務 / 銷售 / 公司）的資料層
--
-- 設計原則（詳見 docs/REPORT_DESIGN.md）：
--   1. 三層毛利，全系統同一套定義：
--        帳上毛利 booked_profit = 除佣實收 − 實付            （各公司帳上看到的）
--        集團毛利 group_profit  = 除佣實收 − 對外成本        （把子公司付給聲活的內部轉撥還原）
--        集團淨利 net_profit    = 集團毛利 − 平台固定成本    （只在月/公司層計算）
--   2. 內部轉撥線（聲活-東 / 聲活-鉑）永遠不算客戶、不算業務、不算訂單；只在集團層還原成本。
--   3. 交換（barter）預設排除，另欄顯示：業務名稱結尾「換」或廣告名稱含「交換」。
--   4. 同期比較（YoY / 同期 YTD）是每張表的標準欄位，不是額外報表。
--   5. 所有排名附「佔比」與「累計佔比」，集中度一眼看出。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. 新增資料表：目標、預估
-- ---------------------------------------------------------------------
create table if not exists sales_target (
  id             serial primary key,
  year           int  not null,
  period_type    text not null check (period_type in ('Y','Q','M')),   -- 年 / 季 / 月
  period_no      int  not null default 1,                             -- Q:1-4  M:1-12  Y:1
  company_id     int references company(id),                          -- null = 集團
  salesperson_id int references salesperson(id),                      -- null = 不分業務
  platform_groups text[],                                             -- null = 不分平台；老闆儀表板用 {企頻,新鮮視}
  include_house  boolean not null default false,                      -- 是否含公司戶（業務 = Company）；老闆儀表板不含
  target_amount  numeric(14,2) not null,                              -- 除佣實收目標
  note           text,
  updated_at     timestamptz not null default now(),
  updated_by     text,
  unique nulls not distinct (year, period_type, period_no, company_id, salesperson_id, platform_groups)
);
comment on table sales_target is '業績目標（除佣實收）。老闆的儀表板是目標導向的，這張表讓達成率不用再手算。';

create table if not exists forecast (
  id             bigserial primary key,
  perf_ym        date not null,                                        -- 預估落在哪個業績年月
  company_id     int references company(id),
  salesperson_id int references salesperson(id),
  customer_id    int references customer(id),
  customer_text  text,                                                 -- 尚未建檔的潛在客戶
  ad_name        text,
  platform_group text,
  amount         numeric(14,2) not null,                               -- 預估除佣實收
  probability    numeric(5,2) not null default 100,                    -- 成交機率 %
  status         text not null default 'OPEN' check (status in ('OPEN','WON','LOST')),
  deal_id        bigint references deal(id),                           -- 成交後回填
  note           text,
  created_at     timestamptz not null default now(),
  created_by     text,
  updated_at     timestamptz not null default now(),
  updated_by     text
);
comment on table forecast is '業績預估（取代線上表單）。「進單 + 預估」大總表的來源。';
create index if not exists ix_forecast_ym on forecast(perf_ym);

do $$
begin
  execute 'drop trigger if exists trg_sales_target_audit on sales_target';
  execute 'create trigger trg_sales_target_audit after insert or update or delete on sales_target for each row execute function fn_audit()';
  execute 'drop trigger if exists trg_forecast_audit on forecast';
  execute 'create trigger trg_forecast_audit after insert or update or delete on forecast for each row execute function fn_audit()';
  execute 'drop trigger if exists trg_forecast_updated_at on forecast';
  execute 'create trigger trg_forecast_updated_at before update on forecast for each row execute function fn_set_updated_at()';
end $$;

-- 分析 view 只在本檔定義；因為欄位會隨設計調整，先整組 drop 再建（可重複執行）
drop view if exists v_booked_vs_forecast, v_target_progress, v_group_month, v_company_month,
                    v_salesperson_year, v_salesperson_month, v_industry_year,
                    v_customer_year, v_customer_month, v_deal_summary, v_as_of, v_line_ext cascade;

-- ---------------------------------------------------------------------
-- 1. 擴充的平面 view：加上 內部轉撥 / 交換 / 業務基底名 / 帳上毛利
-- ---------------------------------------------------------------------
create or replace view v_line_ext as
select
  f.*,
  (f.line_type = 'INTERCOMPANY' or coalesce(f.group_is_intercompany, false))          as is_intercompany,
  (coalesce(f.salesperson, '') ~ '[-‐]?換$' or coalesce(f.ad_name, '') ~ '交換')     as is_barter,
  regexp_replace(coalesce(f.salesperson, ''), '[-‐]?換$', '')                        as salesperson_base,
  (coalesce(f.salesperson, '') in ('Company', '公司', '東吳', '鉑霖', '聲活', '瑞迪')) as is_house,
  (f.net_amount - f.cost_amount)                                                      as booked_profit
from v_deal_line_flat f;

-- 分析用的「截止月」：有資料且不晚於本月的最大業績年月
create or replace view v_as_of as
select max(perf_ym) as as_of_ym,
       extract(year  from max(perf_ym))::int as as_of_year,
       extract(month from max(perf_ym))::int as as_of_month
from deal_line
where perf_ym <= date_trunc('month', current_date)::date;

-- ---------------------------------------------------------------------
-- 2. 訂單層：一列 = 一個合約（銷售分析的粒度；客戶/業務/公司都從這裡往上加總）
-- ---------------------------------------------------------------------
create or replace view v_deal_summary as
with l as (
  select * from v_line_ext
),
pg as (  -- 每個合約各平台歸類的除佣實收（對外線）
  select deal_id, platform_group, sum(net_amount) as net
  from l where not is_intercompany
  group by deal_id, platform_group
),
pg_agg as (
  select deal_id,
         string_agg(platform_group, '+' order by net desc)            as platform_groups,
         (array_agg(platform_group order by net desc))[1]              as main_platform_group,
         sum(net) filter (where platform_group = '企頻')               as net_cp,
         sum(net) filter (where platform_group = '新鮮視')             as net_fresh,
         sum(net) filter (where platform_group = '廣播')               as net_radio,
         sum(net) filter (where platform_group not in ('企頻','新鮮視','廣播')) as net_other
  from pg group by deal_id
),
fixed_alloc as (  -- 平台固定成本依「該月該平台歸類的對外除佣實收」比例分攤到每個合約
  select l.deal_id, sum(fc.fixed_cost * l.net / nullif(tot.net,0)) as alloc_fixed_cost
  from (select deal_id, perf_ym, platform_group, sum(net_amount) net from l where not is_intercompany and not is_barter group by 1,2,3) l
  join (select perf_ym, platform_group, sum(monthly_amount) fixed_cost from v_fixed_cost_monthly group by 1,2) fc
    on fc.perf_ym = l.perf_ym and fc.platform_group = l.platform_group
  join (select perf_ym, platform_group, sum(net_amount) net from l where not is_intercompany and not is_barter group by 1,2) tot
    on tot.perf_ym = l.perf_ym and tot.platform_group = l.platform_group
  group by l.deal_id
),
agg as (
  select
    deal_id,
    min(perf_ym)                                                     as perf_ym,
    bool_or(is_house)                                                as is_house,
    count(*)                                                         as line_count,
    count(distinct perf_ym)                                          as active_months,
    bool_or(is_barter)                                               as is_barter,
    sum(gross_amount)  filter (where not is_intercompany)            as ext_gross,
    sum(net_amount)    filter (where not is_intercompany)            as ext_net,
    sum(cost_amount)   filter (where not is_intercompany)            as booked_cost,
    sum(cost_amount)   filter (where line_type = 'PRODUCTION')       as production_cost,
    sum(net_amount)    filter (where is_intercompany)                as ic_net,
    sum(cost_amount)   filter (where is_intercompany)                as ic_cost,
    sum(recognized_amount) filter (where not is_intercompany)        as recognized_amount,
    sum(purchased_slots) filter (where not is_intercompany)          as purchased_slots,
    sum(total_seconds) filter (where not is_intercompany)            as total_seconds
  from l
  group by deal_id
)
select
  d.id                                   as deal_id,
  d.contract_no,
  d.ad_name,
  c.name                                 as company,
  cu.name                                as customer,
  cu.id                                  as customer_id,
  ind.name                               as industry,
  cc.name                                as customer_category,
  sc.name                                as sales_category,
  sc.parent_category                     as sales_item,
  regexp_replace(coalesce(sp.name,''), '[-‐]?換$', '') as salesperson,
  sp.id                                  as salesperson_id,
  g.name                                 as business_group,
  d.air_start, d.air_end,
  a.perf_ym,
  to_char(a.perf_ym, 'YYYY/MM')          as perf_ym_text,
  extract(year from a.perf_ym)::int      as perf_year,
  extract(quarter from a.perf_ym)::int   as perf_quarter,
  a.line_count, a.active_months, a.is_barter, coalesce(a.is_house,false) as is_house,
  p.platform_groups, p.main_platform_group,
  coalesce(p.net_cp,0) as net_cp, coalesce(p.net_fresh,0) as net_fresh, coalesce(p.net_radio,0) as net_radio, coalesce(p.net_other,0) as net_other,
  coalesce(a.ext_gross,0)                as ext_gross,
  coalesce(a.ext_net,0)                  as ext_net,
  coalesce(a.booked_cost,0)              as booked_cost,
  coalesce(a.production_cost,0)          as production_cost,
  coalesce(a.ic_net,0)                   as ic_net,
  coalesce(a.ic_cost,0)                  as ic_cost,
  (coalesce(a.booked_cost,0) - coalesce(a.ic_net,0) + coalesce(a.ic_cost,0)) as group_cost,
  (coalesce(a.ext_net,0) - coalesce(a.booked_cost,0))                        as booked_profit,
  (coalesce(a.ext_net,0) - (coalesce(a.booked_cost,0) - coalesce(a.ic_net,0) + coalesce(a.ic_cost,0))) as group_profit,
  case when coalesce(a.ext_net,0) <> 0 then round((a.ext_net - a.booked_cost) / a.ext_net, 4) end as booked_margin,
  case when coalesce(a.ext_net,0) <> 0 then round((a.ext_net - (a.booked_cost - coalesce(a.ic_net,0) + coalesce(a.ic_cost,0))) / a.ext_net, 4) end as group_margin,
  coalesce(fa.alloc_fixed_cost,0)        as alloc_fixed_cost,
  (coalesce(a.ext_net,0) - (coalesce(a.booked_cost,0) - coalesce(a.ic_net,0) + coalesce(a.ic_cost,0)) - coalesce(fa.alloc_fixed_cost,0)) as net_profit,
  case when coalesce(a.ext_net,0) <> 0 then round((a.ext_net - (a.booked_cost - coalesce(a.ic_net,0) + coalesce(a.ic_cost,0)) - coalesce(fa.alloc_fixed_cost,0)) / a.ext_net, 4) end as net_margin,
  coalesce(a.recognized_amount,0)        as recognized_amount,
  a.purchased_slots, a.total_seconds,
  case when coalesce(a.ext_net,0) >= 1000000 then '1. ≥100萬'
       when a.ext_net >= 500000  then '2. 50–100萬'
       when a.ext_net >= 100000  then '3. 10–50萬'
       when a.ext_net > 0        then '4. <10萬'
       else '5. 零/負' end               as size_bucket,
  (not coalesce(a.is_barter,false) and coalesce(a.ext_net,0) > 0
     and (a.ext_net - a.booked_cost) / a.ext_net < 0.16)                  as is_low_margin,
  d.legacy_source
from deal d
join agg a            on a.deal_id = d.id
left join pg_agg p    on p.deal_id = d.id
left join fixed_alloc fa on fa.deal_id = d.id
left join company c   on c.id = d.company_id
left join customer cu on cu.id = d.customer_id
left join industry ind on ind.id = d.industry_id
left join customer_category cc on cc.id = d.customer_category_id
left join sales_category sc on sc.id = d.sales_category_id
left join salesperson sp on sp.id = d.salesperson_id
left join business_group g on g.id = d.group_id;

-- ---------------------------------------------------------------------
-- 3. 客戶 × 月（趨勢、活躍月數、最近交易的來源）
-- ---------------------------------------------------------------------
create or replace view v_customer_month as
select customer, customer_id, perf_ym, perf_ym_text, perf_year,
       extract(month from perf_ym)::int as perf_month,
       count(*) as deals,
       sum(ext_net)      filter (where not is_barter) as ext_net,
       sum(booked_profit) filter (where not is_barter) as booked_profit,
       sum(group_profit) filter (where not is_barter) as group_profit,
       sum(net_profit)   filter (where not is_barter) as net_profit,
       sum(ext_net)      filter (where is_barter)     as barter_net
from v_deal_summary
group by customer, customer_id, perf_ym, perf_ym_text, perf_year;

-- ---------------------------------------------------------------------
-- 4. 客戶 × 年：客戶分析主表
--    含：YoY（同期）、狀態（新客/既有/回流/流失）、排名、佔比、累計佔比、ABC 分級、頻率、最近交易
-- ---------------------------------------------------------------------
create or replace view v_customer_year as
with ao as (select * from v_as_of),
years as (select distinct perf_year from v_deal_summary),
custs as (select distinct customer, customer_id from v_deal_summary where customer is not null),
grid as (select c.customer, c.customer_id, y.perf_year from custs c cross join years y),
m as (  -- 月層先算，才能做「同期」比較
  select cm.*, case when cm.perf_year = ao.as_of_year then cm.perf_month <= ao.as_of_month else true end as in_same_period,
         (cm.perf_ym <= ao.as_of_ym) as is_past
  from v_customer_month cm cross join ao
),
y as (
  select customer, perf_year,
         sum(ext_net)                                        as ext_net,
         sum(ext_net) filter (where in_same_period)          as ext_net_same_period,
         sum(booked_profit)                                  as booked_profit,
         sum(group_profit)                                   as group_profit,
         sum(net_profit)                                     as net_profit,
         sum(barter_net)                                     as barter_net,
         sum(deals)                                          as deals,
         count(*) filter (where coalesce(ext_net,0) > 0)     as active_months,
         min(perf_ym) filter (where coalesce(ext_net,0) > 0) as first_ym,
         max(perf_ym) filter (where coalesce(ext_net,0) > 0 and is_past) as last_ym
  from m group by customer, perf_year
),
dims as (  -- 每客戶每年的主要業務 / 產業 / 公司 / 平台組合
  select customer, perf_year,
         (array_agg(salesperson order by net desc))[1] as main_salesperson,
         count(distinct salesperson) as salesperson_count
  from (select customer, perf_year, salesperson, sum(ext_net) net from v_deal_summary where not is_barter group by 1,2,3) s
  group by customer, perf_year
),
plat as (
  select customer, perf_year,
         sum(net_cp) as net_cp, sum(net_fresh) as net_fresh, sum(net_radio) as net_radio, sum(net_other) as net_other,
         (array_agg(company order by ext_net desc))[1] as main_company
  from v_deal_summary where not is_barter group by customer, perf_year
),
cd as (  -- 客戶主檔屬性
  select cu.id as customer_id, ind.name as industry, cc.name as customer_category, cu.is_new_case, cu.is_top1000
  from customer cu left join industry ind on ind.id = cu.industry_id left join customer_category cc on cc.id = cu.customer_category_id
),
j as (
  select g.customer, g.customer_id, g.perf_year,
         coalesce(y.ext_net,0) as ext_net, coalesce(y.ext_net_same_period,0) as ext_net_same_period,
         coalesce(y.booked_profit,0) as booked_profit, coalesce(y.group_profit,0) as group_profit, coalesce(y.net_profit,0) as net_profit,
         coalesce(y.barter_net,0) as barter_net, coalesce(y.deals,0) as deals, coalesce(y.active_months,0) as active_months,
         y.first_ym, y.last_ym,
         d.main_salesperson, d.salesperson_count,
         coalesce(p.net_cp,0) net_cp, coalesce(p.net_fresh,0) net_fresh, coalesce(p.net_radio,0) net_radio, coalesce(p.net_other,0) net_other,
         p.main_company,
         cd.industry, cd.customer_category, cd.is_new_case, cd.is_top1000
  from grid g
  left join y    on y.customer = g.customer and y.perf_year = g.perf_year
  left join dims d on d.customer = g.customer and d.perf_year = g.perf_year
  left join plat p on p.customer = g.customer and p.perf_year = g.perf_year
  left join cd   on cd.customer_id = g.customer_id
),
w as (
  select j.*,
         lag(ext_net) over (partition by customer order by perf_year)                 as prev_year_net,
         lag(ext_net_same_period) over (partition by customer order by perf_year)     as prev_year_net_same_period,
         lag(booked_profit) over (partition by customer order by perf_year)           as prev_year_booked_profit,
         min(perf_year) filter (where ext_net > 0) over (partition by customer)       as first_active_year,
         sum(ext_net) over (partition by customer order by perf_year rows between unbounded preceding and 1 preceding) as cum_prev_net,
         min(perf_year) over ()                                                        as data_start_year,
         max(last_ym) over (partition by customer)                                     as last_ym_ever
  from j
),
r as (
  select w.*,
         case when ext_net <= 0 and coalesce(prev_year_net,0) > 0 then (case when perf_year >= (select as_of_year from v_as_of) then '流失風險' else '流失' end)
              when ext_net <= 0 then '無交易'
              when perf_year = data_start_year then '起始年'
              when first_active_year = perf_year then '新客'
              when coalesce(prev_year_net,0) > 0 then '既有'
              when coalesce(cum_prev_net,0) > 0 then '回流'
              else '新客' end                                                         as status,
         case when coalesce(prev_year_net_same_period,0) <> 0
              then round((ext_net_same_period - prev_year_net_same_period) / abs(prev_year_net_same_period), 4) end as yoy_pct,
         case when ext_net <> 0 then round(booked_profit / ext_net, 4) end             as booked_margin,
         case when ext_net <> 0 then round(group_profit / ext_net, 4) end              as group_margin,
         case when ext_net <> 0 then round(net_profit / ext_net, 4) end                as net_margin,
         case when deals > 0 then round(ext_net / deals, 0) end                        as avg_deal,
         rank() over (partition by perf_year order by ext_net desc)                    as rank_in_year,
         case when sum(ext_net) over (partition by perf_year) > 0
              then round(ext_net / sum(ext_net) over (partition by perf_year), 4) end  as share,
         case when sum(ext_net) over (partition by perf_year) > 0
              then round(sum(ext_net) over (partition by perf_year order by ext_net desc, customer rows unbounded preceding)
                         / sum(ext_net) over (partition by perf_year), 4) end          as cum_share
  from w
)
select r.*,
       case when ext_net <= 0 then null when cum_share <= 0.8 then 'A' when cum_share <= 0.95 then 'B' else 'C' end as abc_tier,
       case when deals >= 6 then '高頻(≥6)' when deals >= 3 then '中頻(3–5)' when deals >= 1 then '低頻(1–2)' end as freq_tier,
       ((ao.as_of_year - extract(year from last_ym_ever)) * 12 + (ao.as_of_month - extract(month from last_ym_ever)))::int as months_since_last,
       case when ext_net > 0 and booked_margin >= 0.35 and rank_in_year <= 20 then '核心：大額高毛利，優先維護'
            when ext_net > 0 and booked_margin <  0.16 and rank_in_year <= 20 then '大額低毛利：檢討報價/成本'
            when ext_net > 0 and booked_margin >= 0.35 then '小額高毛利：可擴大'
            when ext_net > 0 and booked_margin <  0.16 then '小額低毛利：評估是否續做'
            when ext_net > 0 then '一般' end                                          as strategy_hint
from r cross join v_as_of ao;

-- ---------------------------------------------------------------------
-- 5. 產業 × 年
-- ---------------------------------------------------------------------
create or replace view v_industry_year as
with base as (
  select coalesce(industry,'(未分類)') as industry, perf_year,
         count(distinct customer) as customers, count(*) as deals,
         sum(ext_net) as ext_net, sum(booked_profit) as booked_profit, sum(group_profit) as group_profit, sum(net_profit) as net_profit
  from v_deal_summary where not is_barter group by 1,2
),
w as (
  select b.*,
         lag(ext_net) over (partition by industry order by perf_year) as prev_year_net,
         sum(ext_net) over (partition by perf_year) as year_total
  from base b
)
select industry, perf_year, customers, deals, ext_net, booked_profit, group_profit, net_profit,
       case when ext_net <> 0 then round(booked_profit / ext_net, 4) end as booked_margin,
       case when ext_net <> 0 then round(group_profit / ext_net, 4) end  as group_margin,
       case when ext_net <> 0 then round(net_profit / ext_net, 4) end    as net_margin,
       case when year_total > 0 then round(ext_net / year_total, 4) end   as share,
       case when customers > 0 then round(ext_net / customers, 0) end     as net_per_customer,
       prev_year_net,
       case when coalesce(prev_year_net,0) <> 0 then round((ext_net - prev_year_net) / abs(prev_year_net), 4) end as yoy_pct,
       rank() over (partition by perf_year order by ext_net desc) as rank_in_year
from w;

-- ---------------------------------------------------------------------
-- 6. 業務 × 月 / 業務 × 年
-- ---------------------------------------------------------------------
create or replace view v_salesperson_month as
select salesperson, perf_ym, perf_ym_text, perf_year, extract(month from perf_ym)::int as perf_month,
       (array_agg(company order by ext_net desc))[1] as main_company,
       count(*) filter (where not is_barter) as deals,
       count(distinct customer) filter (where not is_barter) as customers,
       sum(ext_net) filter (where not is_barter) as ext_net,
       sum(booked_profit) filter (where not is_barter) as booked_profit,
       sum(group_profit) filter (where not is_barter) as group_profit,
       sum(net_profit) filter (where not is_barter) as net_profit,
       sum(recognized_amount) filter (where not is_barter) as recognized_amount,
       sum(ext_net) filter (where is_barter) as barter_net,
       bool_or(is_house) as is_house
from v_deal_summary
group by salesperson, perf_ym, perf_ym_text, perf_year;

create or replace view v_salesperson_year as
with ao as (select * from v_as_of),
m as (
  select sm.*, case when sm.perf_year = ao.as_of_year then sm.perf_month <= ao.as_of_month else true end as in_same_period
  from v_salesperson_month sm cross join ao
),
y as (
  select salesperson, perf_year, bool_or(is_house) as is_house,
         coalesce(sum(ext_net),0) as ext_net, coalesce(sum(ext_net) filter (where in_same_period),0) as ext_net_same_period,
         coalesce(sum(booked_profit),0) as booked_profit, coalesce(sum(group_profit),0) as group_profit, coalesce(sum(net_profit),0) as net_profit,
         coalesce(sum(recognized_amount),0) as recognized_amount, coalesce(sum(barter_net),0) as barter_net,
         coalesce(sum(deals),0) as deals, count(*) filter (where coalesce(ext_net,0) > 0) as active_months
  from m group by salesperson, perf_year
),
cust as (
  select salesperson, perf_year, count(distinct customer) as customers,
         sum(net_cp) net_cp, sum(net_fresh) net_fresh, sum(net_radio) net_radio, sum(net_other) net_other,
         (array_agg(company order by ext_net desc))[1] as main_company,
         (array_agg(business_group order by ext_net desc))[1] as main_group
  from v_deal_summary where not is_barter group by 1,2
),
topc as (  -- 前 3 大客戶佔比（依賴度）
  select salesperson, perf_year, sum(net) filter (where rn <= 3) as top3_net, max(net) as top1_net,
         (array_agg(customer order by net desc))[1] as top_customer
  from (select salesperson, perf_year, customer, sum(ext_net) net,
               row_number() over (partition by salesperson, perf_year order by sum(ext_net) desc) rn
        from v_deal_summary where not is_barter group by 1,2,3) t
  group by salesperson, perf_year
),
newc as (  -- 該年由該業務帶進的新客戶數（客戶第一次有業績的年份 = 該年）
  select main_salesperson as salesperson, perf_year, count(*) as new_customers
  from v_customer_year where status = '新客' group by 1,2
),
tgt as (
  select sp.name as salesperson, t.year as perf_year, sum(t.target_amount) as target_amount
  from sales_target t join salesperson sp on sp.id = t.salesperson_id
  where t.period_type = 'Y' group by 1,2
),
w as (
  select y.*, c.customers, c.net_cp, c.net_fresh, c.net_radio, c.net_other, c.main_company, c.main_group,
         tc.top3_net, tc.top1_net, tc.top_customer, coalesce(n.new_customers,0) as new_customers, t.target_amount,
         lag(y.ext_net) over (partition by y.salesperson order by y.perf_year) as prev_year_net,
         lag(y.ext_net_same_period) over (partition by y.salesperson order by y.perf_year) as prev_year_net_same_period
  from y
  left join cust c on c.salesperson = y.salesperson and c.perf_year = y.perf_year
  left join topc tc on tc.salesperson = y.salesperson and tc.perf_year = y.perf_year
  left join newc n on n.salesperson = y.salesperson and n.perf_year = y.perf_year
  left join tgt t on t.salesperson = y.salesperson and t.perf_year = y.perf_year
)
select w.*,
       case when ext_net <> 0 then round(booked_profit / ext_net, 4) end as booked_margin,
       case when ext_net <> 0 then round(group_profit / ext_net, 4) end  as group_margin,
       case when ext_net <> 0 then round(net_profit / ext_net, 4) end    as net_margin,
       case when deals > 0 then round(ext_net / deals, 0) end            as avg_deal,
       case when ext_net > 0 then round(top3_net / ext_net, 4) end       as top3_share,
       case when ext_net > 0 then round(top1_net / ext_net, 4) end       as top1_share,
       case when coalesce(prev_year_net_same_period,0) <> 0
            then round((ext_net_same_period - prev_year_net_same_period) / abs(prev_year_net_same_period), 4) end as yoy_pct,
       case when target_amount > 0 then round(ext_net / target_amount, 4) end as target_pct,
       rank() over (partition by perf_year, is_house order by ext_net desc) as rank_in_year,   -- 公司戶（Company）另外排
       case when sum(ext_net) over (partition by perf_year) > 0 then round(ext_net / sum(ext_net) over (partition by perf_year), 4) end as share
from w;

-- ---------------------------------------------------------------------
-- 7. 公司 × 月（各公司對外業績）與 集團 × 月（三層毛利）
-- ---------------------------------------------------------------------
create or replace view v_company_month as
with ext as (
  select company, perf_ym, perf_ym_text, perf_year, extract(month from perf_ym)::int as perf_month, extract(quarter from perf_ym)::int as perf_quarter,
         count(*) filter (where not is_barter) as deals,
         count(distinct customer) filter (where not is_barter) as customers,
         count(distinct salesperson) filter (where not is_barter and not (salesperson in ('Company','公司','東吳','鉑霖','聲活','瑞迪'))) as active_salespeople,
         sum(ext_net) filter (where not is_barter) as ext_net,
         sum(ext_gross) filter (where not is_barter) as ext_gross,
         sum(booked_cost) filter (where not is_barter) as booked_cost,
         sum(booked_profit) filter (where not is_barter) as booked_profit,
         sum(group_profit) filter (where not is_barter) as group_profit,
         sum(ext_net) filter (where is_barter) as barter_net,
         sum(net_cp) filter (where not is_barter) as net_cp,
         sum(net_fresh) filter (where not is_barter) as net_fresh,
         sum(net_radio) filter (where not is_barter) as net_radio,
         sum(net_other) filter (where not is_barter) as net_other
  from v_deal_summary group by 1,2,3,4,5,6
),
ic as (  -- 內部轉撥：子公司付出（ic_out）、聲活收到（ic_in）
  select company, perf_ym, sum(net_amount) as ic_out from v_line_ext where is_intercompany group by 1,2
),
ic_in as (
  select perf_ym, sum(net_amount) as ic_in from v_line_ext where is_intercompany group by 1
),
fc as (
  select company, perf_ym, sum(monthly_amount) as fixed_cost from v_fixed_cost_monthly group by 1,2
)
select e.*,
       coalesce(i.ic_out,0) as ic_out,
       case when c.is_parent then coalesce(ii.ic_in,0) else 0 end as ic_in,
       coalesce(f.fixed_cost,0) as fixed_cost,
       -- 該公司自己帳上的最終毛利：帳上毛利 + 收到的轉撥 − 固定成本（子公司的 ic_out 已含在 booked_cost）
       (coalesce(e.booked_profit,0) + case when c.is_parent then coalesce(ii.ic_in,0) else 0 end - coalesce(f.fixed_cost,0)) as company_net_profit,
       case when e.ext_net <> 0 then round(e.booked_profit / e.ext_net, 4) end as booked_margin
from ext e
left join company c on c.name = e.company
left join ic i on i.company = e.company and i.perf_ym = e.perf_ym
left join ic_in ii on ii.perf_ym = e.perf_ym
left join fc f on f.company = e.company and f.perf_ym = e.perf_ym;

create or replace view v_group_month as
select perf_ym, perf_ym_text, perf_year, perf_month, perf_quarter,
       sum(deals) as deals, sum(customers) as customers,
       sum(ext_net) as ext_net, sum(ext_gross) as ext_gross,
       sum(booked_cost) as booked_cost,
       sum(booked_profit) as booked_profit,                       -- 第 1 層：各公司帳上毛利合計
       sum(ic_in) as ic_add_back,                                  -- 加回：內部轉撥（子公司成本 = 聲活收入）
       sum(group_profit) as group_profit,                          -- 第 2 層：集團毛利（對外收入 − 對外成本）
       sum(fixed_cost) as fixed_cost,
       (sum(group_profit) - sum(fixed_cost)) as net_profit,        -- 第 3 層：集團淨利（扣平台固定成本）
       sum(barter_net) as barter_net,
       case when sum(ext_net) <> 0 then round(sum(booked_profit) / sum(ext_net), 4) end as booked_margin,
       case when sum(ext_net) <> 0 then round(sum(group_profit) / sum(ext_net), 4) end  as group_margin,
       case when sum(ext_net) <> 0 then round((sum(group_profit) - sum(fixed_cost)) / sum(ext_net), 4) end as net_margin
from v_company_month
group by perf_ym, perf_ym_text, perf_year, perf_month, perf_quarter;

-- ---------------------------------------------------------------------
-- 8. 目標達成（含「剩餘月份每月需達」）
-- ---------------------------------------------------------------------
create or replace view v_target_progress as
with ao as (select * from v_as_of),
t as (
  select st.*, c.name as company, sp.name as salesperson,
         case st.period_type when 'Y' then make_date(st.year,1,1) when 'Q' then make_date(st.year,(st.period_no-1)*3+1,1) else make_date(st.year,st.period_no,1) end as ym_from,
         case st.period_type when 'Y' then make_date(st.year,12,1) when 'Q' then make_date(st.year,st.period_no*3,1) else make_date(st.year,st.period_no,1) end as ym_to
  from sales_target st left join company c on c.id = st.company_id left join salesperson sp on sp.id = st.salesperson_id
),
act as (
  select t.id as target_id,
         sum(ds.ext_net) filter (where not ds.is_barter) as actual,
         count(distinct ds.perf_ym) as months_with_data
  from t
  left join v_deal_summary ds
    on ds.perf_ym between t.ym_from and t.ym_to
   and (t.company is null or ds.company = t.company)
   and (t.salesperson is null or ds.salesperson = regexp_replace(t.salesperson, '[-‐]?換$', ''))
   and (t.platform_groups is null or ds.main_platform_group = any(t.platform_groups))
   and (t.include_house or not ds.is_house)
  group by t.id
),
fcst as (
  select t.id as target_id, sum(f.amount * f.probability / 100) as forecast_weighted, sum(f.amount) as forecast_amount
  from t left join forecast f
    on f.status = 'OPEN' and f.perf_ym between t.ym_from and t.ym_to
   and (t.company_id is null or f.company_id = t.company_id)
   and (t.salesperson_id is null or f.salesperson_id = t.salesperson_id)
   and (t.platform_groups is null or f.platform_group = any(t.platform_groups))
  group by t.id
)
select t.id as target_id, t.year, t.period_type, t.period_no,
       case t.period_type when 'Y' then t.year::text when 'Q' then t.year || ' Q' || t.period_no else to_char(t.ym_from,'YYYY/MM') end as period_label,
       coalesce(t.company, '集團') as company, t.salesperson, t.platform_groups, t.include_house,
       t.target_amount,
       coalesce(a.actual,0) as actual,
       coalesce(f.forecast_amount,0) as forecast_amount,
       coalesce(f.forecast_weighted,0) as forecast_weighted,
       (t.target_amount - coalesce(a.actual,0)) as remaining,
       case when t.target_amount > 0 then round(coalesce(a.actual,0) / t.target_amount, 4) end as achieved_pct,
       case when t.target_amount > 0 then round((coalesce(a.actual,0) + coalesce(f.forecast_weighted,0)) / t.target_amount, 4) end as achieved_pct_with_forecast,
       -- 剩餘月份（從截止月的下一個月到期末）
       greatest(0, ((extract(year from t.ym_to) - ao.as_of_year) * 12 + (extract(month from t.ym_to) - ao.as_of_month))::int) as months_left,
       case when ((extract(year from t.ym_to) - ao.as_of_year) * 12 + (extract(month from t.ym_to) - ao.as_of_month)) > 0
            then round((t.target_amount - coalesce(a.actual,0)) / ((extract(year from t.ym_to) - ao.as_of_year) * 12 + (extract(month from t.ym_to) - ao.as_of_month)), 0) end as required_monthly,
       t.note
from t
left join act a on a.target_id = t.id
left join fcst f on f.target_id = t.id
cross join ao;

-- ---------------------------------------------------------------------
-- 9. 進單 + 預估（老闆的大總表：公司 × 月）
-- ---------------------------------------------------------------------
create or replace view v_booked_vs_forecast as
with months as (select distinct perf_ym from deal_line union select distinct perf_ym from forecast),
comp as (select id, name from company where is_active),
grid as (select m.perf_ym, c.id as company_id, c.name as company from months m cross join comp c),
b as (select company, perf_ym, ext_net, barter_net from v_company_month),
f as (select company_id, perf_ym, sum(amount) as forecast_amount, sum(amount * probability / 100) as forecast_weighted
      from forecast where status = 'OPEN' group by 1,2)
select g.perf_ym, to_char(g.perf_ym,'YYYY/MM') as perf_ym_text, extract(year from g.perf_ym)::int as perf_year, g.company,
       coalesce(b.ext_net,0) as booked_net, coalesce(b.barter_net,0) as barter_net,
       coalesce(f.forecast_amount,0) as forecast_amount, coalesce(f.forecast_weighted,0) as forecast_weighted,
       (coalesce(b.ext_net,0) + coalesce(f.forecast_amount,0)) as booked_plus_forecast
from grid g
left join b on b.company = g.company and b.perf_ym = g.perf_ym
left join f on f.company_id = g.company_id and f.perf_ym = g.perf_ym;

-- ---------------------------------------------------------------------
-- 10. 種子：老闆儀表板（2026.07.30 版）上的 Q3 目標，方便第一次 demo 就有達成率
-- ---------------------------------------------------------------------
insert into sales_target(year, period_type, period_no, company_id, platform_groups, include_house, target_amount, note)
select 2026, 'Q', 3, c.id, '{企頻,新鮮視}', false, v.amt, '來自 0730 公司業績儀表板：企頻+新鮮視、不含公司戶（待確認）'
from (values ('聲活', 10000000), ('東吳', 20000000), ('鉑霖', 10000000)) as v(name, amt)
join company c on c.name = v.name
on conflict do nothing;
