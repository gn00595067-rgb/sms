-- =====================================================================
-- 004_seed.sql  基本種子資料（可重複執行）
-- 其餘主檔（客戶/業務/電台/平台/節目/產業別…）由 scripts/etl_legacy.py 從 legacy_csv 建立。
-- =====================================================================

insert into region(code, name, sort_order) values
  ('ALL','全區域',0), ('N','北區',1), ('C','中區',2), ('S','南區',3)
on conflict (code) do update set name = excluded.name, sort_order = excluded.sort_order;

insert into company(name, is_parent, sort_order) values
  ('聲活', true, 1), ('東吳', false, 2), ('鉑霖', false, 3), ('瑞迪', false, 4), ('錄音室', false, 9)
on conflict (name) do update set is_parent = excluded.is_parent, sort_order = excluded.sort_order;

insert into customer_category(name) values ('開發'), ('服務'), ('直客')
on conflict (name) do nothing;

-- 組別：聲活-東 / 聲活-鉑 是子公司付給聲活的轉撥線
insert into business_group(name, is_intercompany, sort_order) values
  ('聲活組', false, 1), ('東吳組', false, 2), ('鉑霖組', false, 3), ('業務行銷組', false, 4),
  ('南辦組', false, 5), ('公司', false, 6), ('錄音室', false, 7),
  ('聲活-東', true, 8), ('聲活-鉑', true, 9), ('業務開發組', false, 10)
on conflict (name) do update set is_intercompany = excluded.is_intercompany;

-- 平台（舊：平台資料表 + 資料中出現但主檔沒有的值）
insert into platform(name, platform_group, default_region, sort_order) values
  ('廣播',        '廣播',  'ALL', 5),
  ('新鮮視',      '新鮮視','ALL', 2),
  ('全家企頻',    '企頻',  'ALL', 0),
  ('家樂福企頻',  '企頻',  'ALL', 1),
  ('健康視',      '診所',  'ALL', 3),
  ('其它',        '其它',  'ALL', 6),
  ('全家全企',    '分區',  'ALL', 10),
  ('全家北企',    '分區',  'N',   11),
  ('全家桃企',    '分區',  'N',   12),   -- 桃園歸北區：假設，待確認
  ('全家中企',    '分區',  'C',   13),
  ('全家南企',    '分區',  'S',   14),
  ('營運',        '營運',  'ALL', 4),
  ('企頻',        '企頻',  'ALL', 20),
  ('企頻-年度維運費','企頻','ALL', 21),
  ('Podcast',     '其它',  'ALL', 22),
  ('健康視-年度代理','診所','ALL', 23),
  ('製作收入',    '其它',  'ALL', 24),
  ('全家南頻',    '分區',  'S',   25),
  ('萬家福',      '企頻',  'ALL', 26),   -- PDF 提到的新平台（家樂福更名）
  ('麥當勞',      '企頻',  'ALL', 27)    -- PDF 提到的新平台
on conflict (name) do update set platform_group = excluded.platform_group, default_region = excluded.default_region;

-- 業績類別（舊：業績類別資料表）
insert into sales_category(name, parent_category, recognition_ratio) values
  ('開發直客','開發',1.0), ('開發建案','開發',1.0), ('開發合作','開發',1.0), ('開發比稿','開發',1.0), ('開發4A','開發',1.0),
  ('既有直客','既有',0.8), ('既有建案','既有',0.8), ('既有合作','既有',0.8), ('既有比稿','既有',0.8),
  ('既有4A','4A',0.5), ('服務公司','服務',0.5), ('服務建案','服務',0.5), ('服務4A','4A',0.5),
  ('直客',null,0), ('統一',null,0), ('廣代',null,0), ('服務','服務',0), ('開發','開發',1.0)
on conflict (name) do update set parent_category = excluded.parent_category, recognition_ratio = excluded.recognition_ratio;

-- 固定成本（PDF 第三節；民國 115/3–116/2 = 2026-03 ~ 2027-02；新鮮視「1–12 月」假設為 2026 年）
insert into fixed_cost_rule(platform_group, company_id, ym_from, ym_to, monthly_amount, note)
select '企頻', c.id, date '2026-03-01', date '2027-02-01', 750000, 'PDF：企頻年度成本 115/3–116/2 每月固定認列 75 萬（待確認）'
from company c where c.name = '聲活'
and not exists (select 1 from fixed_cost_rule where platform_group = '企頻' and ym_from = date '2026-03-01');

insert into fixed_cost_rule(platform_group, company_id, ym_from, ym_to, monthly_amount, note)
select '新鮮視', c.id, date '2026-01-01', date '2026-12-01', 1000000, 'PDF：新鮮視成本 1–12 月每月固定認列 100 萬（年份為假設，待確認）'
from company c where c.name = '聲活'
and not exists (select 1 from fixed_cost_rule where platform_group = '新鮮視' and ym_from = date '2026-01-01');

-- 子公司 → 聲活 65 折（PDF 第三節）
insert into intercompany_rule(from_company_id, to_company_id, rate, ym_from, note)
select f.id, t.id, 0.65, date '2024-01-01', 'PDF：東吳/鉑霖付給聲活 65 折（待確認起始年月與平台範圍）'
from company f, company t
where f.name in ('東吳','鉑霖') and t.name = '聲活'
and not exists (select 1 from intercompany_rule r where r.from_company_id = f.id and r.to_company_id = t.id);
