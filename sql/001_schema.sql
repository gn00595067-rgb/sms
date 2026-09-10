-- =====================================================================
-- 001_schema.sql  新業績系統 MVP — 資料表
-- 目標資料庫：PostgreSQL 15+（Supabase）
-- 設計原則：
--   1. 所有維度用 id 關聯，名稱只是屬性（客戶改名不影響歷史）。
--   2. 只存輸入值；除佣實收/毛利/總秒數/獎金等衍生值放 view（003_views.sql）。
--   3. deal_line 的粒度 = 舊系統「業績資料表」一列（合約 × 平台/電台/製作費 × 節目），
--      每條 line 自帶公司/客戶/業務/組別，因為舊資料同一合約內這些會不同（見 docs/legacy_profile.md）。
--   4. 金額 numeric(14,2)（新台幣），比率 numeric(7,4)（0.65 = 65 折；退佣 10% 存 10.0000）。
--   5. 年月一律用 date 存該月 1 日（2026-09-01），不要用 '2026/09' 文字。
-- =====================================================================

create table if not exists schema_migrations (
  filename   text primary key,
  applied_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 主檔
-- ---------------------------------------------------------------------
create table if not exists company (
  id          serial primary key,
  name        text not null unique,                 -- 聲活 / 東吳 / 鉑霖 / 瑞迪 / 錄音室
  is_parent   boolean not null default false,       -- 聲活 = true（第二層毛利的主體）
  sort_order  int not null default 0,
  is_active   boolean not null default true
);
comment on table company is '公司別（舊：公司資料表）';

create table if not exists business_group (
  id          serial primary key,
  name        text not null unique,                 -- 聲活組 / 東吳組 / 鉑霖組 / 聲活-東 / 聲活-鉑 / 南辦組 / 業務行銷組 / 公司 / 錄音室
  company_id  int references company(id),
  is_intercompany boolean not null default false,   -- 聲活-東、聲活-鉑 = true（子公司轉撥線）
  sort_order  int not null default 0,
  is_active   boolean not null default true
);
comment on table business_group is '組別（舊：組別資料表）';

create table if not exists salesperson (
  id            serial primary key,
  name          text not null unique,               -- 舊系統的「業務」文字
  group_id      int references business_group(id),
  manager_name  text,
  is_active     boolean not null default true,
  notes         text
);
comment on table salesperson is '業務（舊：業務資料表）';

create table if not exists staff (
  id          serial primary key,
  name        text not null unique,
  roles       text[] not null default '{}',         -- MEDIA 媒體 / PLANNER 企劃 / COPY 文案 / ASSIST 協辦 / CS 客服 / BILLING 請款 / CLOSING 結案
  is_active   boolean not null default true
);
comment on table staff is '非業務人員（舊：媒體/企劃/文案/協辦人員資料表 合併）';

create table if not exists industry (
  id   serial primary key,
  name text not null unique
);
comment on table industry is '產業別';

create table if not exists customer_category (
  id   serial primary key,
  name text not null unique                         -- 開發 / 服務 / 直客
);

create table if not exists sales_category (
  id                serial primary key,
  name              text not null unique,           -- 開發直客 / 服務公司 / 既有建案 …
  parent_category   text,                           -- 開發 / 既有 / 服務 / 4A（舊：業績類別資料表.類別）
  recognition_ratio numeric(7,4) not null default 1, -- 毛利認定比例（開發 1.0、既有 0.8、服務/4A 0.5）
  is_active         boolean not null default true
);
comment on table sales_category is '業績類別（舊：業績類別資料表）— 業績認定表的核心規則';

create table if not exists region (
  code text primary key,                            -- ALL / N / C / S
  name text not null,                               -- 全區域 / 北區 / 中區 / 南區
  sort_order int not null default 0
);

create table if not exists platform (
  id             serial primary key,
  name           text not null unique,              -- 廣播 / 新鮮視 / 全家企頻 / 家樂福企頻 / 健康視 / 全家北企 …
  platform_group text not null default '其它',      -- 廣播 / 新鮮視 / 企頻 / 診所 / 分區 / 營運 / 其它（舊：平台歸類）
  default_region text references region(code) default 'ALL',
  sort_order     int not null default 0,
  is_active      boolean not null default true
);
comment on table platform is '平台（舊：平台資料表）';

create table if not exists media_channel (
  id            serial primary key,
  name          text not null unique,               -- 電台名稱 / 製作費-錄音室 / 製作費-配音員 / 全家全企 …
  channel_type  text not null default 'MEDIA' check (channel_type in ('MEDIA','PRODUCTION','OTHER')),
  is_designated boolean not null default false,     -- 指定電台
  tax_rate      numeric(7,4) not null default 0,
  sort_order    int not null default 0,
  is_active     boolean not null default true,
  notes         text
);
comment on table media_channel is '電台 / 成本項目（舊：電台資料表 + 業績資料表.電台 的所有值）';

create table if not exists program (
  id               serial primary key,
  name             text not null,
  media_channel_id int references media_channel(id),
  unique (name, media_channel_id)
);
comment on table program is '節目（舊：節目資料表）';

create table if not exists customer (
  id                   serial primary key,
  name                 text not null unique,
  customer_category_id int references customer_category(id),
  industry_id          int references industry(id),
  tax_id               text,                        -- 統一編號
  contact_person       text,
  phone                text,
  email                text,
  is_new_case          boolean not null default false,  -- 新案
  is_top1000           boolean not null default false,  -- 千大
  notes                text,
  is_active            boolean not null default true,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  updated_by           text
);
comment on table customer is '客戶主檔（舊：客戶資料表）';

create table if not exists customer_alias (
  id          serial primary key,
  customer_id int not null references customer(id) on delete cascade,
  alias       text not null unique                  -- 舊資料裡的異名（家福股份有限公司 → 家樂福）
);

-- ---------------------------------------------------------------------
-- 交易：合約（deal）與線（deal_line）
-- ---------------------------------------------------------------------
create table if not exists deal (
  id                   bigserial primary key,
  contract_no          text not null unique,        -- 合約編號，如 1150224-12-5 / K1141206
  company_id           int references company(id),
  customer_id          int references customer(id),
  ad_name              text,                        -- 廣告名稱
  salesperson_id       int references salesperson(id),
  group_id             int references business_group(id),
  sales_category_id    int references sales_category(id),
  customer_category_id int references customer_category(id),
  industry_id          int references industry(id),
  category_dc          text check (category_dc in ('直客','廣代')),  -- PDF 新增：直客 / 廣代
  air_start            date,                        -- 上檔起始日期
  air_end              date,                        -- 上檔結束日期
  order_ym             date,                        -- 進單年月（該月 1 日）
  contract_term        text,                        -- 合約期限
  media_staff_id       int references staff(id),
  planner_staff_id     int references staff(id),
  copy_staff_id        int references staff(id),
  assist_staff_id      int references staff(id),
  cs_staff_id          int references staff(id),
  billing_staff_id     int references staff(id),
  closing_staff_id     int references staff(id),
  is_original_received boolean not null default false,  -- 正本
  is_copy_received     boolean not null default false,  -- 影本
  is_sales_signed      boolean not null default false,  -- 業務簽名
  notes                text,
  legacy_source        text,                        -- 'ACCESS_2026_V109g' 等；null = 新系統登打
  created_at           timestamptz not null default now(),
  created_by           text,
  updated_at           timestamptz not null default now(),
  updated_by           text
);
comment on table deal is '合約 / 專案主檔（PDF: performance_main）。header 只是登打時的預設值，報表一律以 deal_line 為準。';

create table if not exists deal_line (
  id                   bigserial primary key,
  deal_id              bigint not null references deal(id) on delete cascade,
  line_no              int not null default 1,
  line_type            text not null default 'MEDIA' check (line_type in ('MEDIA','PRODUCTION','INTERCOMPANY')),
  perf_ym              date not null,               -- 業績年月份（該月 1 日）
  blink_ym             date,                        -- BLINK認列年月
  order_ym             date,                        -- 進單年月
  -- 每條線自帶維度（登打時由 deal 帶入預設，可改）
  company_id           int references company(id),
  customer_id          int references customer(id),
  salesperson_id       int references salesperson(id),
  group_id             int references business_group(id),
  sales_category_id    int references sales_category(id),
  customer_category_id int references customer_category(id),
  industry_id          int references industry(id),
  platform_id          int references platform(id),
  media_channel_id     int references media_channel(id),
  program_id           int references program(id),
  region_codes         text[] not null default '{ALL}',  -- {ALL} 或 {N,C,S} 的子集合
  is_network           boolean not null default false,   -- 聯網
  is_designated        boolean not null default false,   -- 指定電台
  -- 金額
  gross_amount         numeric(14,2) not null default 0, -- 實收金額
  rebate_pct           numeric(7,4)  not null default 0, -- 退佣折扣 %（10 = 10%）
  cash_discount_pct    numeric(7,4)  not null default 0, -- 現折 %（PDF 新增）
  net_amount           numeric(14,2) not null default 0, -- 除佣實收（登打時自動算，可手動覆蓋；舊資料原值匯入）
  cost_amount          numeric(14,2) not null default 0, -- 實付金額
  channel_cost_amount  numeric(14,2) not null default 0, -- 電台實付金額
  media_benefit        numeric(14,2) not null default 0, -- 媒體效益
  -- 檔次 / 秒數
  material_seconds     int,                              -- 素材秒數（PDF 新增）
  total_frames         int,                              -- 總檔數（PDF 新增）
  total_seconds        int generated always as (coalesce(material_seconds,0) * coalesce(total_frames,0)) stored,
  purchased_slots      int,                              -- 購買檔次
  bonus_slots          int,                              -- 搭贈檔次
  bonus_amount         numeric(14,2),                    -- 搭贈金額
  bonus_combo          text,                             -- 搭贈組合
  edited_bonus_slots   int,                              -- 編播贈檔
  is_bonus_plan        boolean not null default false,   -- 搭贈方案
  blink_slots          int,                              -- BLINK檔數
  daling_count         int,                              -- 達鈴通數
  responsibility_slots numeric(10,2),                    -- 責任檔
  -- 狀態
  is_channel_paid      boolean not null default false,   -- 電台已付款
  payment_received_on  date,                             -- 收款日期
  planned_invoice_on   date,                             -- 預計發票日
  low_margin_handled   boolean not null default false,   -- 低毛利已處理
  low_margin_reason    text,                             -- 低毛利原因
  exclude_cs_bonus     boolean not null default false,   -- 不計客服獎金
  notes                text,
  -- 追溯
  legacy_source        text,
  legacy_row_no        int,                              -- legacy_csv 的列號（從 1 起算，不含表頭）
  legacy_customer_name text,                             -- 舊資料原始客戶名稱（對帳用）
  created_at           timestamptz not null default now(),
  created_by           text,
  updated_at           timestamptz not null default now(),
  updated_by           text,
  unique (deal_id, line_no)
);
comment on table deal_line is '業績線（PDF: performance_detail；舊：業績資料表 一列）';
create index if not exists ix_deal_line_perf_ym on deal_line(perf_ym);
create index if not exists ix_deal_line_company on deal_line(company_id);
create index if not exists ix_deal_line_salesperson on deal_line(salesperson_id);
create index if not exists ix_deal_line_customer on deal_line(customer_id);
create index if not exists ix_deal_line_platform on deal_line(platform_id);
create index if not exists ix_deal_line_deal on deal_line(deal_id);

-- ---------------------------------------------------------------------
-- 發票 / 銷帳（財務模組）
-- ---------------------------------------------------------------------
create table if not exists invoice (
  id                      bigserial primary key,
  legacy_seq              int,                      -- 舊：單號
  deal_id                 bigint references deal(id) on delete set null,
  contract_no             text,
  customer_id             int references customer(id),
  customer_title          text,                     -- 客戶公司抬頭
  customer_tax_id         text,                     -- 客戶統一編號
  salesperson_id          int references salesperson(id),
  group_id                int references business_group(id),
  ad_name                 text,
  air_start               date,
  air_end                 date,
  invoice_due_on          date,                     -- 發票應交付日
  expected_cash_on        date,                     -- 預定兌現日（逾期判斷基準）
  payment_method          text,                     -- 匯款 / 支票 / 收現
  ad_income               numeric(14,2) not null default 0,   -- 廣告收入
  production_income       numeric(14,2) not null default 0,   -- 製作收入
  sales_allowance         numeric(14,2) not null default 0,   -- 銷貨折讓金額
  cash_discount_pct       numeric(14,4) not null default 0,  -- 舊資料混用 %/金額（見 legacy_profile.md），故放寬
  cash_discount_amount    numeric(14,2) not null default 0,
  rebate_pct              numeric(14,4) not null default 0,  -- 同上
  rebate_amount           numeric(14,2) not null default 0,
  discount_method         text,                     -- 先現折 再退 / 退+現折 / 先退 再現折
  allowance_note_amount   numeric(14,2) not null default 0,   -- 折讓單金額
  invoice_allowance_amount numeric(14,2) not null default 0,  -- 發票折讓金額
  invoice_no              text,
  invoice_issued_on       date,                     -- 發票開立日
  invoice_delivered_on    date,                     -- 發票交付日
  invoice_signed          boolean not null default false,
  invoice_signed_by       text,
  invoice_signed_at       timestamptz,
  finance_signed          boolean not null default false,
  finance_signed_by       text,
  finance_signed_at       timestamptz,
  settled_manually        boolean not null default false,  -- 財務手動標記已結清（舊資料的銷帳幾乎沒登錄，需要這個開關）
  settled_note            text,
  notes                   text,
  notes2                  text,
  legacy_source           text,
  legacy_row_no           int,
  created_at              timestamptz not null default now(),
  created_by              text,
  updated_at              timestamptz not null default now(),
  updated_by              text
);
comment on table invoice is '發票開立（舊：發票開立資料表）';
create index if not exists ix_invoice_contract on invoice(contract_no);
create index if not exists ix_invoice_expected on invoice(expected_cash_on);

create table if not exists writeoff (
  id              bigserial primary key,
  invoice_id      bigint references invoice(id) on delete cascade,
  deal_id         bigint references deal(id) on delete set null,
  received_on     date not null,                    -- 實際收款 / 銷帳日期
  received_amount numeric(14,2) not null,           -- 實際收款金額
  method          text,                             -- 匯款 / 支票 / 收現
  bank_ref        text,                             -- 匯款末五碼 / 支票號碼
  entered_role    text,                             -- FINANCE / ASSIST（舊系統分業助/財務兩組欄位）
  remark          text,
  legacy_source   text,
  created_at      timestamptz not null default now(),
  created_by      text
);
comment on table writeoff is '銷帳紀錄（PDF: payment_writeoff）— 一張發票可分多次銷帳';

-- ---------------------------------------------------------------------
-- 規則表（都有生效區間，改數字不用改程式）
-- ---------------------------------------------------------------------
create table if not exists fixed_cost_rule (
  id               serial primary key,
  platform_group   text,                            -- 企頻 / 新鮮視 …（對 platform.platform_group）
  platform_id      int references platform(id),     -- 或指定單一平台（二擇一）
  media_channel_id int references media_channel(id),-- 或指定單一電台（舊：BLINK固定成本 / 固定成本資料表）
  company_id       int references company(id),      -- 成本歸屬公司，預設聲活
  ym_from          date not null,
  ym_to            date,                            -- null = 持續有效
  monthly_amount   numeric(14,2) not null,
  note             text,
  check (platform_group is not null or platform_id is not null or media_channel_id is not null)
);
comment on table fixed_cost_rule is '固定成本認列規則（PDF：企頻 75 萬/月、新鮮視 100 萬/月）';

create table if not exists intercompany_rule (
  id              serial primary key,
  from_company_id int not null references company(id),  -- 東吳 / 鉑霖（付款方）
  to_company_id   int not null references company(id),  -- 聲活（收款方）
  platform_group  text,                                  -- null = 所有平台
  rate            numeric(7,4) not null,                 -- 0.65 = 65 折
  ym_from         date not null,
  ym_to           date,
  note            text
);
comment on table intercompany_rule is '子公司付給聲活的轉撥比率（PDF：65 折）';

create table if not exists bonus_rule (
  id               serial primary key,
  salesperson_id   int references salesperson(id),  -- null = 適用所有業務
  platform_group   text,                            -- null = 所有平台歸類
  sales_item       text,                            -- 開發 / 既有 / 服務 / 4A（對 sales_category.parent_category）；null = 全部
  ym_from          date not null,
  ym_to            date,
  bonus_pct        numeric(7,4) not null,           -- 3 = 3%
  threshold_amount numeric(14,2) not null default 0,-- 當月除佣實收門檻，未達 = 0 獎金
  note             text
);
comment on table bonus_rule is 'MVP 簡易業務獎金規則（舊：獎金百分比資料表 的第一層）';

-- ---------------------------------------------------------------------
-- 系統
-- ---------------------------------------------------------------------
create table if not exists app_user (
  id                   serial primary key,
  username             text not null unique,
  password_hash        text not null,               -- bcrypt
  display_name         text,
  role                 text not null check (role in ('MEDIA','FINANCE','EXEC','SALES')),
  salesperson_id       int references salesperson(id),  -- SALES 角色綁定的業務（只看自己的）
  is_active            boolean not null default true,
  must_change_password boolean not null default true,
  last_login_at        timestamptz,
  created_at           timestamptz not null default now()
);

create table if not exists audit_log (
  id           bigserial primary key,
  at           timestamptz not null default now(),
  user_name    text,
  action       text not null,                       -- INSERT / UPDATE / DELETE
  table_name   text not null,
  row_pk       text,
  changed_cols text[],
  old_data     jsonb,
  new_data     jsonb
);
create index if not exists ix_audit_table_pk on audit_log(table_name, row_pk);
create index if not exists ix_audit_at on audit_log(at desc);

create table if not exists feedback (
  id         bigserial primary key,
  created_at timestamptz not null default now(),
  user_name  text,
  page       text,                                  -- 回報時所在頁面
  category   text not null default '其他',           -- BUG / 建議 / 欄位不對 / 報表 / 其他
  message    text not null,
  status     text not null default 'NEW',           -- NEW / DOING / DONE / WONTFIX
  reply      text,
  updated_at timestamptz not null default now()
);
comment on table feedback is '同仁邊用邊回報問題（MVP 迭代的來源）';

create table if not exists etl_run (
  id          serial primary key,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  source      text not null,                        -- legacy_csv 資料夾名 / 檔名
  rows_in     int,
  rows_out    int,
  note        text
);

create table if not exists etl_issue (
  id         bigserial primary key,
  run_id     int references etl_run(id) on delete cascade,
  table_name text,
  row_ref    text,
  issue      text not null,
  detail     jsonb,
  created_at timestamptz not null default now()
);

-- updated_at 自動更新
create or replace function fn_set_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['customer','deal','deal_line','invoice','feedback'] loop
    execute format('drop trigger if exists trg_%s_updated_at on %I', t, t);
    execute format('create trigger trg_%s_updated_at before update on %I for each row execute function fn_set_updated_at()', t, t);
  end loop;
end $$;
