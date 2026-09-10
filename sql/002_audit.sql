-- =====================================================================
-- 002_audit.sql  通用稽核 trigger（PDF: system_audit_log）
-- 應用程式在每個交易開頭執行（scripts/db.py 的 transaction() 已做）：
--   select set_config('app.user_name', '<登入者帳號>', true);
-- trigger 會把操作者、前後差異（jsonb）寫進 audit_log。
-- =====================================================================

create or replace function fn_audit() returns trigger language plpgsql as $$
declare
  v_user text := coalesce(nullif(current_setting('app.user_name', true), ''), session_user::text);
  v_old  jsonb;
  v_new  jsonb;
  v_pk   text;
  v_changed text[];
begin
  -- 大量匯入（ETL）時可略過稽核：select set_config('app.skip_audit','on',true)
  if current_setting('app.skip_audit', true) = 'on' then
    if tg_op = 'DELETE' then return old; end if;
    return new;
  end if;
  if tg_op = 'INSERT' then
    v_new := to_jsonb(new);
  elsif tg_op = 'UPDATE' then
    v_old := to_jsonb(old);
    v_new := to_jsonb(new);
    -- 只記真正改變的欄位（忽略 updated_at）
    select array_agg(k) into v_changed
    from jsonb_each(v_new) n(k, v)
    where v is distinct from (v_old -> k) and k not in ('updated_at');
    if v_changed is null then
      return new;  -- 沒有實質變更就不記
    end if;
  else
    v_old := to_jsonb(old);
  end if;

  -- 永遠不要把密碼雜湊寫進稽核表
  if tg_table_name = 'app_user' then
    v_old := v_old - 'password_hash';
    v_new := v_new - 'password_hash';
  end if;

  v_pk := coalesce(v_new ->> 'id', v_old ->> 'id');

  insert into audit_log(user_name, action, table_name, row_pk, changed_cols, old_data, new_data)
  values (v_user, tg_op, tg_table_name, v_pk, v_changed, v_old, v_new);

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array[
    'customer','customer_alias','deal','deal_line','invoice','writeoff',
    'fixed_cost_rule','intercompany_rule','bonus_rule','app_user',
    'platform','media_channel','program','salesperson','staff','sales_category'
  ] loop
    execute format('drop trigger if exists trg_%s_audit on %I', t, t);
    execute format('create trigger trg_%s_audit after insert or update or delete on %I for each row execute function fn_audit()', t, t);
  end loop;
end $$;
