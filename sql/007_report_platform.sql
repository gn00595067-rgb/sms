-- =====================================================================
-- 007_report_platform.sql — 階段 J：老闆「發稿口徑」與報表平台（CLAUDE_CODE_TASK_4）
--
--   不改 sql/005 的商業邏輯；只在這裡 create or replace 覆蓋指定的幾個 view，
--   並新增報表平台欄位（report_platform）與發稿口徑旗標（in_media_scope）。
--   可重複執行（idempotent）。
--
--   老闆工作簿口徑（2025年度_三公司發稿明細分析）：
--     只算媒體上稿線（MEDIA）、不含內部轉撥、平台切成
--       全家企頻 / 萬家福 / 新鮮視 / 廣播 / 健康視 五欄，
--     營運（企頻年度維運）與其它（Podcast/POS/製作收入…）另列、不進四欄。
--   驗收：2025 發稿口徑 除佣實收 134,303,021、帳上毛利 67,416,333、客戶 265。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. 報表平台 report_platform（platform 主檔加欄 + seed）
-- ---------------------------------------------------------------------
alter table platform add column if not exists report_platform text not null default '其它';
comment on column platform.report_platform is
  '老闆報表的平台欄：全家企頻 / 萬家福 / 新鮮視 / 廣播 / 健康視 / 營運 / 其它';

update platform set report_platform = case
  when name in ('全家企頻','全家全企','全家北企','全家桃企','全家中企','全家南企','全家南頻') then '全家企頻'
  when name in ('家樂福企頻','萬家福')                                                    then '萬家福'
  when name = '新鮮視'                                                                     then '新鮮視'
  when name = '廣播'                                                                       then '廣播'
  when name in ('健康視','健康視-年度代理')                                               then '健康視'
  when name in ('營運','企頻','企頻-年度維運費')                                          then '營運'
  else '其它' end;   -- 麥當勞 / Podcast / 製作收入 / 其它 → 其它（麥當勞待 Peggy 確認是否獨立一欄）

-- ---------------------------------------------------------------------
-- 2. v_line_ext 補口徑欄位（照 005 定義，末尾加 report_platform / 兩個口徑旗標）
--    create or replace：既有欄位順序不變，只在最後 append 三欄（可安全覆蓋）。
-- ---------------------------------------------------------------------
create or replace view v_line_ext as
select
  f.*,
  (f.line_type = 'INTERCOMPANY' or coalesce(f.group_is_intercompany, false))          as is_intercompany,
  (coalesce(f.salesperson, '') ~ '[-‐]?換$' or coalesce(f.ad_name, '') ~ '交換')     as is_barter,
  regexp_replace(coalesce(f.salesperson, ''), '[-‐]?換$', '')                        as salesperson_base,
  (coalesce(f.salesperson, '') in ('Company', '公司', '東吳', '鉑霖', '聲活', '瑞迪')) as is_house,
  (f.net_amount - f.cost_amount)                                                      as booked_profit,
  coalesce(p.report_platform, '其它')                                                 as report_platform,
  -- 發稿口徑：只 MEDIA、非內部轉撥、平台屬四欄+健康視（老闆年度表的範圍）
  (f.line_type = 'MEDIA'
     and not (f.line_type = 'INTERCOMPANY' or coalesce(f.group_is_intercompany, false))
     and coalesce(p.report_platform, '其它') in ('全家企頻','萬家福','新鮮視','廣播','健康視')) as in_media_scope,
  -- 自媒體（不含廣播）：老闆「不含廣播」區塊用
  (coalesce(p.report_platform, '其它') in ('全家企頻','萬家福','新鮮視','健康視'))       as is_own_media
from v_deal_line_flat f
left join platform p on p.id = f.platform_id;

-- ---------------------------------------------------------------------
-- 3. v_deal_summary：修四個平台欄（P0，改以 report_platform 彙總）
--    - net_cp 語意改為「企頻合計 = 全家企頻 + 萬家福」（舊欄名保留、下游沿用）
--    - net_other 改為只含 營運 / 其它（分區→全家企頻、健康視→net_clinic，不再掉進 net_other）
--    - 末尾 append：net_cp_family / net_cp_carrefour / net_clinic / report_platforms / main_report_platform
--    平台歸類欄（platform_groups / main_platform_group）仍以 platform_group 彙總，供目標達成表沿用。
-- ---------------------------------------------------------------------
create or replace view v_deal_summary as
with l as (
  select * from v_line_ext
),
pg as (   -- 平台歸類層（沿用）
  select deal_id, platform_group, sum(net_amount) as net
  from l where not is_intercompany
  group by deal_id, platform_group
),
pg_agg as (
  select deal_id,
         string_agg(platform_group, '+' order by net desc)  as platform_groups,
         (array_agg(platform_group order by net desc))[1]    as main_platform_group
  from pg group by deal_id
),
pgr as (  -- 報表平台層（新）
  select deal_id, report_platform, sum(net_amount) as net
  from l where not is_intercompany
  group by deal_id, report_platform
),
pgr_agg as (
  select deal_id,
         string_agg(report_platform, '+' order by net desc)  as report_platforms,
         (array_agg(report_platform order by net desc))[1]    as main_report_platform,
         sum(net) filter (where report_platform in ('全家企頻','萬家福')) as net_cp,
         sum(net) filter (where report_platform = '全家企頻')            as net_cp_family,
         sum(net) filter (where report_platform = '萬家福')              as net_cp_carrefour,
         sum(net) filter (where report_platform = '新鮮視')              as net_fresh,
         sum(net) filter (where report_platform = '廣播')                as net_radio,
         sum(net) filter (where report_platform = '健康視')              as net_clinic,
         sum(net) filter (where report_platform in ('營運','其它'))       as net_other
  from pgr group by deal_id
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
  coalesce(pr.net_cp,0) as net_cp, coalesce(pr.net_fresh,0) as net_fresh, coalesce(pr.net_radio,0) as net_radio, coalesce(pr.net_other,0) as net_other,
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
  d.legacy_source,
  -- ↓↓↓ 007 append：報表平台明細（老闆四欄+健康視）
  coalesce(pr.net_cp_family,0)     as net_cp_family,
  coalesce(pr.net_cp_carrefour,0)  as net_cp_carrefour,
  coalesce(pr.net_clinic,0)        as net_clinic,
  pr.report_platforms,
  pr.main_report_platform
from deal d
join agg a            on a.deal_id = d.id
left join pg_agg p    on p.deal_id = d.id
left join pgr_agg pr  on pr.deal_id = d.id
left join fixed_alloc fa on fa.deal_id = d.id
left join company c   on c.id = d.company_id
left join customer cu on cu.id = d.customer_id
left join industry ind on ind.id = d.industry_id
left join customer_category cc on cc.id = d.customer_category_id
left join sales_category sc on sc.id = d.sales_category_id
left join salesperson sp on sp.id = d.salesperson_id
left join business_group g on g.id = d.group_id;

-- ---------------------------------------------------------------------
-- 4. 公司 × 月 / 集團 × 月：加報表平台欄 + 修集團毛利橋
--    v_group_month 依賴 v_company_month、v_booked_vs_forecast 也依賴 v_company_month，
--    因為要在 e.* 中插欄（改變欄序），改用 drop + recreate（三張一起重建）。
-- ---------------------------------------------------------------------
drop view if exists v_booked_vs_forecast, v_group_month, v_company_month cascade;

create view v_company_month as
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
         sum(net_cp_family) filter (where not is_barter) as net_cp_family,
         sum(net_cp_carrefour) filter (where not is_barter) as net_cp_carrefour,
         sum(net_fresh) filter (where not is_barter) as net_fresh,
         sum(net_radio) filter (where not is_barter) as net_radio,
         sum(net_clinic) filter (where not is_barter) as net_clinic,
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
       (coalesce(e.booked_profit,0) + case when c.is_parent then coalesce(ii.ic_in,0) else 0 end - coalesce(f.fixed_cost,0)) as company_net_profit,
       case when e.ext_net <> 0 then round(e.booked_profit / e.ext_net, 4) end as booked_margin
from ext e
left join company c on c.name = e.company
left join ic i on i.company = e.company and i.perf_ym = e.perf_ym
left join ic_in ii on ii.perf_ym = e.perf_ym
left join fc f on f.company = e.company and f.perf_ym = e.perf_ym;

create view v_group_month as
select perf_ym, perf_ym_text, perf_year, perf_month, perf_quarter,
       sum(deals) as deals, sum(customers) as customers,
       sum(ext_net) as ext_net, sum(ext_gross) as ext_gross,
       sum(booked_cost) as booked_cost,
       sum(booked_profit) as booked_profit,                       -- 第 1 層：各公司帳上毛利合計
       -- 加回：橋一定收斂（帳上毛利 + 加回 = 集團毛利）；ic_transfer_gross 是明細（轉撥收入總額）
       (sum(group_profit) - sum(booked_profit)) as ic_add_back,
       sum(ic_in)         as ic_transfer_gross,                    -- 明細：內部轉撥收入（聲活收到）
       sum(group_profit) as group_profit,                          -- 第 2 層：集團毛利（對外收入 − 對外成本）
       sum(fixed_cost) as fixed_cost,
       (sum(group_profit) - sum(fixed_cost)) as net_profit,        -- 第 3 層：集團淨利（扣平台固定成本）
       sum(barter_net) as barter_net,
       sum(net_cp) as net_cp, sum(net_cp_family) as net_cp_family, sum(net_cp_carrefour) as net_cp_carrefour,
       sum(net_fresh) as net_fresh, sum(net_radio) as net_radio, sum(net_clinic) as net_clinic, sum(net_other) as net_other,
       case when sum(ext_net) <> 0 then round(sum(booked_profit) / sum(ext_net), 4) end as booked_margin,
       case when sum(ext_net) <> 0 then round(sum(group_profit) / sum(ext_net), 4) end  as group_margin,
       case when sum(ext_net) <> 0 then round((sum(group_profit) - sum(fixed_cost)) / sum(ext_net), 4) end as net_margin
from v_company_month
group by perf_ym, perf_ym_text, perf_year, perf_month, perf_quarter;

create view v_booked_vs_forecast as
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
-- 5. v_report_line：老闆口徑的線層彙總 view（給階段 K/L/M 用，不重算商業邏輯）
--    交換併回原業務（salesperson_merged）、走期文字（air_period_text）、ym 文字。
-- ---------------------------------------------------------------------
create or replace view v_report_line as
select l.*,
       case when l.is_barter then l.salesperson_base else l.salesperson end            as salesperson_merged,
       l.perf_year::text || '/' || lpad(extract(month from l.perf_ym)::text, 2, '0')    as ym,
       to_char(l.air_start, 'FMMM/FMDD') || '-' || to_char(l.air_end, 'FMMM/FMDD')       as air_period_text
from v_line_ext l;
