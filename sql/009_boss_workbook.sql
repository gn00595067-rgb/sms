-- 009_boss_workbook.sql — 老闆工作簿（年度發稿明細分析）的資料來源：v_boss_line
-- 一列 = 一條媒體上稿線；欄名 = 工作簿「原始資料_發稿分析」的 30 欄（中文），另加 perf_ym / perf_year 供期間篩選。
-- 規則：只留 MEDIA 線（製作費線排除）、不含內部轉撥線、平台限 全家企頻/家樂福企頻/新鮮視/廣播/健康視、
--       交換併回原業務（先查別名表，再去「換」字尾）、瑞迪併入東吳。

create table if not exists salesperson_alias (
  alias       text primary key,           -- 出現在資料裡的寫法（例：蔡伊閔）
  canonical   text not null,              -- 主檔名（例：蔡伊閔Heidi）
  note        text
);
insert into salesperson_alias(alias, canonical, note) values ('蔡伊閔', '蔡伊閔Heidi', '交換線「蔡伊閔換」去字尾後')
on conflict (alias) do nothing;

create or replace view v_boss_line as
with base as (
  select l.*,
    case when l.platform in ('全家企頻','全家全企','全家北企','全家桃企','全家中企','全家南企','全家南頻') then '全家企頻'
         when l.platform in ('家樂福企頻','萬家福') then '家樂福企頻'
         when l.platform = '新鮮視' then '新鮮視'
         when l.platform = '廣播' then '廣播'
         when l.platform in ('健康視','健康視-年度代理') then '健康視'
         else null end as boss_platform,
    coalesce(a.canonical, l.salesperson_base) as sp_final
  from v_line_ext l
  left join salesperson_alias a on a.alias = l.salesperson_base
)
select
  perf_ym, perf_year,
  case when company = '瑞迪' then '東吳' else company end                as "公司別",
  perf_ym_text                                                            as "業績年月份",
  to_char(blink_ym, 'YYYY/MM')                                            as "BLINK認列年月",
  to_char(order_ym, 'YYYY/MM')                                            as "進單年月",
  boss_platform                                                           as "平台",
  contract_no                                                             as "合約編號",
  customer                                                                as "客戶名稱",
  ad_name                                                                 as "廣告名稱",
  to_char(air_start, 'YYYY/FMMM/FMDD')                                    as "上檔起始日期",
  to_char(air_end, 'YYYY/FMMM/FMDD')                                      as "上檔結束日期",
  program                                                                 as "節目名稱",
  gross_amount                                                            as "實收金額",
  net_amount                                                              as "除佣實收",
  cost_amount                                                             as "實付金額",
  business_group                                                          as "組別",
  salesperson                                                             as "業務",
  null::text                                                              as "客服",
  customer_category                                                       as "客戶類別",
  industry                                                                as "產業別",
  media_channel                                                           as "電台",
  notes                                                                   as "備註",
  purchased_slots                                                         as "購買檔次",
  bonus_slots                                                             as "搭贈檔次",
  bonus_amount                                                            as "搭贈金額",
  null::text                                                              as "搭贈組合",
  blink_slots                                                             as "編播贈檔",
  null::text                                                              as "合約期限",
  sp_final                                                                as "業務_final",
  case when boss_platform = '家樂福企頻' then '萬家福' else boss_platform end as "平台_顯示",
  to_char(air_start, 'FMMM/FMDD') || '-' || to_char(air_end, 'FMMM/FMDD')  as "走期",
  air_start, air_end
from base
where line_type = 'MEDIA' and not is_intercompany and boss_platform is not null;

comment on view v_boss_line is '老闆工作簿口徑的媒體上稿線（欄名同工作簿原始資料_發稿分析）';
