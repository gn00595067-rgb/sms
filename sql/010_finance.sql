-- =====================================================================
-- 010_finance.sql — 財務報表專區（CLAUDE_CODE_TASK_7）
--
--   舊 Access 六個財務功能要 100% 重現，需要三樣舊系統有、新系統還沒有的規則資料：
--     1. 電台年度退佣（電台年度退佣資料表.退佣百分比合併）→ channel_rebate_rate
--        媒體發稿量分析的「毛利+退佣」= 毛利 + 實付金額 × 退佣% ÷ 100
--     2. 電台付款規則（電台付款規則表；鍵 = 電台 + 聯網）→ channel_payment_rule
--        電台預付查詢的「電台預付日」由 付款種類 推算（規則照舊查詢 電台預付日查詢 逐字翻譯）
--     3. 電台資料表的採購單欄位（現金折扣 / 現金預付 / 一般付款 / 採購單備註 / 聯播網）→ media_channel 加欄
--        三單查詢的《廣告時段採購申請單》要印 現折% 與 好事／城市聯播網總額
--   以及一個把「舊業績資料表一列」的所有欄位攤平、附上財務報表用衍生欄的 view：v_finance_line，
--   和電台預付專用的 v_channel_prepay。
--   種子資料是從 V109g .mdb 逐列抄出來的字面值（不依賴 legacy_* 表存在）。可重複執行（idempotent）。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. media_channel 補採購單用欄位（舊：電台資料表）
-- ---------------------------------------------------------------------
alter table media_channel add column if not exists cash_discount_pct  numeric(7,4) not null default 0;   -- 現金折扣：0.04 = 4%
alter table media_channel add column if not exists is_cash_prepaid    boolean not null default false;    -- 現金預付
alter table media_channel add column if not exists is_normal_payment  boolean not null default false;    -- 一般付款
alter table media_channel add column if not exists purchase_note      text;                              -- 採購單備註（印在採購申請單備註欄）
alter table media_channel add column if not exists network_name       text;                              -- 聯播網：好事 / 城市 / null（採購申請單「好事聯播網總額／城市聯播網總額」）
comment on column media_channel.cash_discount_pct is '舊：電台資料表.現金折扣（採購申請單的 % 欄與現折金額）';
comment on column media_channel.network_name is '聯播網歸屬（好事＝BEST989/港都/山海屯/蓮花/南方之音；城市＝GOLD 系列）— 待財務確認';

-- 舊系統沒建在電台主檔、但付款規則表有的兩個電台
insert into media_channel (name, channel_type) values ('噶瑪蘭廣播','MEDIA'), ('希望之聲','MEDIA')
on conflict (name) do nothing;

with seed(name, is_cash_prepaid, is_normal_payment, cash_discount_pct, tax_rate, purchase_note) as (values
  ('GOLD台南', true, false, 0.0500, 0.0500, null),
  ('GOLD大苗栗', true, false, 0.0500, 0.0500, null),
  ('Super主人', true, false, 0.0000, 0.0000, null),
  ('大苗栗', true, false, 0.0500, 0.0000, null),
  ('中廣', true, false, 0.0400, 0.0000, '已於預付明細表申請'),
  ('台中', true, false, 0.0500, 0.0000, null),
  ('UFO', true, false, 0.0400, 0.0000, null),
  ('大眾', true, false, 0.0400, 0.0000, '已於預付明細表申請'),
  ('大千', true, false, 0.0500, 0.0000, null),
  ('港都', true, false, 0.0500, 0.0000, null),
  ('全國', true, false, 0.0400, 0.0000, null),
  ('愛樂', true, false, 0.0000, 0.0000, null),
  ('HITFM', true, false, 0.0500, 0.0500, null),
  ('NEWS98', true, false, 0.0400, 0.0000, '已於預付明細表申請'),
  ('ICRT', true, false, 0.0400, 0.0000, null),
  ('亞洲', false, false, 0.0500, 0.0000, '年度累扣,不須付款'),
  ('環宇', true, false, 0.0500, 0.0000, null),
  ('GOLD城市', true, false, 0.0500, 0.0500, null),
  ('新聞網', true, false, 0.0400, 0.0000, '已於預付明細表申請'),
  ('BEST989', true, false, 0.0500, 0.0000, null),
  ('亞太', true, false, 0.0500, 0.0000, null),
  ('陽光蘋果', true, true, 0.0300, 0.0500, null),
  ('GOLD健康', true, false, 0.0500, 0.0500, null),
  ('蓮花', true, false, 0.0000, 0.0000, null),
  ('南方之音', false, false, 0.0500, 0.0000, null),
  ('IC之音', false, false, 0.0600, 0.0000, null),
  ('南台灣之聲', true, false, 0.0500, 0.0000, '已於預付明細表申請'),
  ('Super寶島新聲', true, false, 0.0500, 0.0000, null),
  ('山海屯', true, false, 0.0500, 0.0000, null),
  ('大漢之音', true, false, 0.0000, 0.0000, null),
  ('主人廣播', true, false, 0.0500, 0.0000, null),
  ('飛揚', true, false, 0.0500, 0.0000, null),
  ('台北之音HITFM', false, false, 0.0025, 0.0000, null),
  ('飛碟', false, false, 0.0500, 0.0000, null),
  ('GOLD南投', true, false, 0.0500, 0.0500, null),
  ('全家-全家企頻收入', true, false, 0.0000, 0.0000, null)
)
update media_channel m
   set is_cash_prepaid = s.is_cash_prepaid, is_normal_payment = s.is_normal_payment,
       cash_discount_pct = s.cash_discount_pct, purchase_note = s.purchase_note,
       tax_rate = case when m.tax_rate = 0 then s.tax_rate else m.tax_rate end
  from seed s where s.name = m.name;

update media_channel set network_name = '好事' where name in ('BEST989','港都','山海屯','蓮花','南方之音') and network_name is null;
update media_channel set network_name = '城市' where name like 'GOLD%' and network_name is null;

-- 平台顯示順序（舊 平台資料表.顯示順序：全家企頻 0、家樂福企頻 1、新鮮視 2、健康視 3、營運 4、廣播 5、其它 6）；004 seed 把全家企頻放成 99
update platform set sort_order = 0 where name = '全家企頻' and sort_order = 99;

-- ---------------------------------------------------------------------
-- 2. 電台年度退佣（舊：電台年度退佣資料表.退佣百分比合併；只抄 2024–2026 且不為 0 的列）
-- ---------------------------------------------------------------------
create table if not exists channel_rebate_rate (
  id               serial primary key,
  media_channel_id int not null references media_channel(id),
  year             int not null,
  rebate_pct       numeric(9,4) not null,           -- 10 = 10%
  note             text,
  unique (media_channel_id, year)
);
comment on table channel_rebate_rate is '電台年度退佣%（媒體發稿量分析「毛利+退佣」= 毛利 + 實付 × 退佣% ÷ 100）';

with seed(name, year, pct) as (values
  ('BEST989', 2024, 10.0000),
  ('GOLD健康', 2024, 25.6500),
  ('GOLD台南', 2024, 25.6500),
  ('GOLD城市', 2024, 25.6500),
  ('GOLD大苗栗', 2024, 25.6500),
  ('中廣', 2024, 4.8000),
  ('南台灣之聲', 2024, 9.0476),
  ('大眾', 2024, 1.9200),
  ('新聞網', 2024, 4.8000),
  ('港都', 2024, 19.0476),
  ('BEST989', 2025, 10.0000),
  ('GOLD健康', 2025, 25.6500),
  ('GOLD台南', 2025, 25.6500),
  ('GOLD城市', 2025, 25.6500),
  ('GOLD大苗栗', 2025, 25.6500),
  ('中廣', 2025, 4.8000),
  ('南台灣之聲', 2025, 9.0476),
  ('大眾', 2025, 1.9200),
  ('新聞網', 2025, 4.8000),
  ('港都', 2025, 19.0476),
  ('BEST989', 2026, 10.0000),
  ('GOLD健康', 2026, 25.6500),
  ('GOLD台南', 2026, 25.6500),
  ('GOLD城市', 2026, 25.6500),
  ('GOLD大苗栗', 2026, 25.6500),
  ('中廣', 2026, 4.8000),
  ('南台灣之聲', 2026, 9.0476),
  ('大眾', 2026, 1.9200),
  ('新聞網', 2026, 4.8000),
  ('港都', 2026, 19.0476)
)
insert into channel_rebate_rate (media_channel_id, year, rebate_pct)
select m.id, s.year, s.pct from seed s join media_channel m on m.name = s.name
on conflict (media_channel_id, year) do update set rebate_pct = excluded.rebate_pct;

-- ---------------------------------------------------------------------
-- 3. 電台付款規則（舊：電台付款規則表；鍵 = 電台名稱 + 聯網）
-- ---------------------------------------------------------------------
create table if not exists channel_payment_rule (
  id               serial primary key,
  media_channel_id int not null references media_channel(id),
  is_network       boolean not null default false,   -- 舊：聯網（同一電台聯網與否規則不同）
  pay_type         text not null check (pay_type in ('每月2付','次月1付','次週三付','第N天付','播畢第N天付','播畢次月1付')),
  first_cutoff_day int not null default 0,           -- 一段日前（每月2付：上檔日 ≤ 此日 → 當月付款日）
  second_cutoff_day int not null default 0,          -- 二段日前（保留欄，舊查詢未用）
  same_month_day   int not null default 0,           -- 當月付款日
  next_month_day   int not null default 0,           -- 次月付款日
  n_days           int not null default 0,           -- 第N天付款
  note             text,
  unique (media_channel_id, is_network)
);
comment on table channel_payment_rule is '電台預付日推算規則（舊：電台付款規則表）— 見 v_channel_prepay';

with seed(name, is_network, pay_type, d1, d2, same_day, next_day, n_days) as (values
  ('大眾', false, '次週三付', 0, 0, 0, 0, 0),
  ('UFO', false, '次月1付', 0, 0, 0, 0, 0),
  ('中廣', false, '次週三付', 0, 0, 0, 0, 0),
  ('NEWS98', false, '次週三付', 0, 0, 0, 0, 0),
  ('新聞網', false, '次週三付', 0, 0, 0, 0, 0),
  ('I RADIO', false, '次週三付', 0, 0, 0, 0, 0),
  ('BEST989', false, '次月1付', 1, 0, 0, 5, 0),
  ('Bravo', false, '每月2付', 14, 30, 15, 1, 0),
  ('陽光蘋果', false, '次月1付', 0, 0, 0, 1, 0),
  ('環宇', false, '每月2付', 14, 30, 15, 1, 0),
  ('IC之音', false, '每月2付', 14, 30, 15, 1, 0),
  ('港都', false, '每月2付', 14, 30, 15, 1, 0),
  ('山海屯', false, '每月2付', 14, 30, 15, 1, 0),
  ('全國', false, '每月2付', 14, 30, 15, 1, 0),
  ('主人廣播', false, '每月2付', 14, 30, 15, 1, 0),
  ('愛樂', false, '每月2付', 14, 30, 15, 1, 0),
  ('GOLD健康', false, '次月1付', 1, 0, 0, 5, 0),
  ('GOLD大苗栗', false, '次月1付', 1, 0, 0, 5, 0),
  ('GOLD台南', false, '次月1付', 1, 0, 0, 5, 0),
  ('GOLD南投', false, '次月1付', 1, 0, 0, 5, 0),
  ('GOLD城市', false, '次月1付', 1, 0, 0, 5, 0),
  ('POP', false, '次月1付', 1, 0, 0, 5, 0),
  ('寶島網', false, '次月1付', 1, 0, 0, 5, 0),
  ('大千', false, '次月1付', 1, 0, 0, 5, 0),
  ('希望之聲', false, '次月1付', 1, 0, 0, 5, 0),
  ('亞洲', false, '次月1付', 1, 0, 0, 5, 0),
  ('亞太', false, '次月1付', 1, 0, 0, 5, 0),
  ('飛揚', false, '次月1付', 1, 0, 0, 5, 0),
  ('ICRT', false, '次月1付', 1, 0, 0, 5, 0),
  ('台中', false, '次月1付', 1, 0, 0, 7, 0),
  ('HITFM', false, '第N天付', 0, 0, 0, 0, 7),
  ('好家庭', false, '第N天付', 0, 0, 0, 0, 7),
  ('大漢之音', false, '第N天付', 0, 0, 0, 0, 10),
  ('快樂聯播網', false, '播畢次月1付', 0, 0, 0, 10, 0),
  ('噶瑪蘭廣播', false, '播畢第N天付', 0, 0, 0, 0, 30),
  ('BEST989', true, '次月1付', 0, 0, 0, 5, 0),
  ('港都', true, '次月1付', 0, 0, 0, 5, 0),
  ('山海屯', true, '次月1付', 0, 0, 0, 5, 0),
  ('連花', true, '次月1付', 0, 0, 0, 5, 0),
  ('南方之音', true, '次月1付', 0, 0, 0, 5, 0)
)
insert into channel_payment_rule (media_channel_id, is_network, pay_type, first_cutoff_day, second_cutoff_day, same_month_day, next_month_day, n_days)
select m.id, s.is_network, s.pay_type, s.d1, s.d2, s.same_day, s.next_day, s.n_days
  from seed s join media_channel m on m.name = s.name
on conflict (media_channel_id, is_network) do update
   set pay_type = excluded.pay_type, first_cutoff_day = excluded.first_cutoff_day, second_cutoff_day = excluded.second_cutoff_day,
       same_month_day = excluded.same_month_day, next_month_day = excluded.next_month_day, n_days = excluded.n_days;

-- ---------------------------------------------------------------------
-- 4. v_finance_line：舊「業績資料表」一列 ＋ 財務報表要的衍生欄
--    （不重算 v_line_ext 的任何邏輯，只加欄；所有財務報表都從這張 view 出）
-- ---------------------------------------------------------------------
drop view if exists v_channel_prepay;      -- 兩張 view 只有這裡用；drop 再建才能加欄
drop view if exists v_finance_line;
create view v_finance_line as
select
  l.*,
  (l.line_type = 'PRODUCTION')                                            as is_production,   -- 舊：電台 Like '製作費*'
  case when l.platform like '%企%' then '企頻' else coalesce(l.platform,'') end as plat_z,       -- 舊：IIf([平台] Like '*企*','企頻',[平台])
  case when l.platform in ('全家企頻','全家全企','全家北企','全家桃企','全家中企','全家南企','全家南頻') then '全家企頻'
       when l.platform in ('家樂福企頻','萬家福')                 then '家樂福企頻'
       when l.platform in ('企頻','企頻-年度維運費')              then '企頻'
       when l.platform = '新鮮視'                                 then '新鮮視'
       when l.platform in ('健康視','健康視-年度代理')            then '健康視'
       when l.platform = '廣播'                                   then '廣播'
       when l.platform = '營運'                                   then '營運'
       else '其他' end                                                  as fin_platform,     -- 財務報表的 8 類（製作費線仍照其平台歸類；製作費另以 is_production 判斷）
  coalesce(r.rebate_pct, 0)                                               as channel_rebate_pct,
  round(l.cost_amount * coalesce(r.rebate_pct, 0) / 100, 0)               as channel_rebate_amount,   -- 電台退佣 = 實付 × 退佣% ÷ 100
  coalesce(mc.cash_discount_pct, 0)                                       as channel_cash_discount_pct,
  coalesce(mc.tax_rate, 0)                                                as channel_tax_rate,
  mc.network_name, mc.purchase_note, mc.is_cash_prepaid, mc.is_normal_payment,
  coalesce(mc.sort_order, 999)                                            as channel_order,
  coalesce(p.sort_order, 99)                                              as platform_order,
  to_char(l.perf_ym, 'YYYY/MM')                                           as ym,
  case when l.air_start is null then '' else to_char(l.air_start, 'MM/DD') end
    || case when l.air_end is null then '' else '-' || to_char(l.air_end, 'MM/DD') end as air_period_text,   -- 舊報表：08/01-08/15
  (l.net_amount - l.cost_amount)                                          as profit,                    -- 帳上毛利（舊：除佣實收－實付金額）
  case when l.net_amount <> 0 then round((l.net_amount - l.cost_amount) / l.net_amount, 4) end as margin,
  d.contract_term                                                                                     -- 合約期限（年季約篩選）
from v_line_ext l
join deal d                      on d.id = l.deal_id
left join media_channel mc       on mc.id = l.media_channel_id
left join platform p             on p.id = l.platform_id
left join channel_rebate_rate r  on r.media_channel_id = l.media_channel_id and r.year = l.perf_year;

-- ---------------------------------------------------------------------
-- 5. v_channel_prepay：電台預付日（舊查詢 電台預付日查詢 的逐字翻譯）
--    只有在 channel_payment_rule 有規則的電台線才會出現（舊查詢是 inner join）
--    上檔星期幾：週一=1 … 週日=7（舊：IIf(Weekday(d)=1,7,Weekday(d)-1)）
--    次週三付：預付日 = 上檔起始日 + (7 − 星期幾 + 3)
--    每月2付：上檔日 1..一段日前 → 當月/當月付款日，否則 → 次月/次月付款日
--    次月1付：次月/次月付款日；第N天付：上檔起始日 + (N−1)；播畢第N天付：上檔結束日 + (N−1)；播畢次月1付：結束日次月/次月付款日
-- ---------------------------------------------------------------------
create view v_channel_prepay as
with l as (
  select f.*, r.pay_type, r.first_cutoff_day, r.same_month_day, r.next_month_day, r.n_days
  from v_finance_line f
  join channel_payment_rule r on r.media_channel_id = f.media_channel_id and r.is_network = f.is_network
  where f.air_start is not null and f.air_end is not null and not f.is_production
),
calc as (
  select l.*,
    (l.air_start + (7 - extract(isodow from l.air_start)::int + 3))                                            as d_w3,
    make_date(extract(year from (l.air_start + interval '1 month'))::int,
              extract(month from (l.air_start + interval '1 month'))::int, greatest(l.next_month_day, 1))        as d_next,
    case when extract(day from l.air_start)::int between 1 and l.first_cutoff_day
         then make_date(extract(year from l.air_start)::int, extract(month from l.air_start)::int, greatest(l.same_month_day, 1))
         else make_date(extract(year from (l.air_start + interval '1 month'))::int,
                        extract(month from (l.air_start + interval '1 month'))::int, greatest(l.next_month_day, 1)) end as d_2pay,
    (l.air_start + case when l.n_days > 0 then l.n_days - 1 else 0 end)                                        as d_n,
    (l.air_end   + case when l.n_days > 0 then l.n_days - 1 else 0 end)                                        as d_end_n,
    make_date(extract(year from (l.air_end + interval '1 month'))::int,
              extract(month from (l.air_end + interval '1 month'))::int, greatest(l.next_month_day, 1))          as d_end_next
  from l
)
select
  case pay_type when '每月2付' then d_2pay when '次月1付' then d_next when '次週三付' then d_w3
                when '第N天付' then d_n  when '播畢第N天付' then d_end_n when '播畢次月1付' then d_end_next end as prepay_on,
  pay_type, line_id, deal_id, contract_no, perf_ym, ym, media_channel, media_channel_id, is_network, is_channel_paid,
  customer, ad_name, salesperson, business_group, air_start, air_end, air_period_text,
  cost_amount, channel_cost_amount, purchase_note, channel_order, notes
from calc;

comment on view v_channel_prepay is '電台預付查詢：每條電台線的預計付款日（依 channel_payment_rule 推算）';

-- ---------------------------------------------------------------------
-- 6. 發票開立申請單的單號：舊資料用 legacy_seq，新資料用 id（三單查詢用「單號」找單）
-- ---------------------------------------------------------------------
create or replace view v_invoice_request as
select i.*, coalesce(i.legacy_seq, i.id::int) as request_no,
       cu.name as customer_name, sp.name as salesperson_name, g.name as group_name
from invoice i
left join customer cu on cu.id = i.customer_id
left join salesperson sp on sp.id = i.salesperson_id
left join business_group g on g.id = i.group_id;

-- ---------------------------------------------------------------------
-- 7. 稽核 trigger：新規則表（002 的 do-block 只掛固定清單，這裡補掛，方式同 008 對 saved_report）
-- ---------------------------------------------------------------------
do $$ begin
  execute 'drop trigger if exists trg_channel_payment_rule_audit on channel_payment_rule';
  execute 'create trigger trg_channel_payment_rule_audit after insert or update or delete on channel_payment_rule for each row execute function fn_audit()';
  execute 'drop trigger if exists trg_channel_rebate_rate_audit on channel_rebate_rate';
  execute 'create trigger trg_channel_rebate_rate_audit after insert or update or delete on channel_rebate_rate for each row execute function fn_audit()';
end $$;

insert into schema_migrations (filename) values ('010_finance.sql') on conflict do nothing;
