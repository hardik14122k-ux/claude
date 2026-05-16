-- =====================================================================
-- TalentTrack HRMS — schema v2
-- Adds: companies, users (RBAC), leave management, multi-tenant RLS.
-- Idempotent. Run AFTER schema.sql.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------- COMPANIES ------------------------------------------------
create table if not exists companies (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  domain      text,
  country     text not null default 'IN',
  fiscal_year_start_month smallint not null default 4 check (fiscal_year_start_month between 1 and 12),
  created_at  timestamptz not null default now()
);

-- Seed a default company so existing rows have somewhere to land.
insert into companies (id, name)
values ('00000000-0000-0000-0000-000000000001', 'Default Company')
on conflict (id) do nothing;

-- ---------- USERS (linked to auth.users) -----------------------------
do $$ begin
  create type user_role as enum ('admin','hr','hiring_manager','viewer');
exception when duplicate_object then null; end $$;

create table if not exists users (
  id          uuid primary key,                          -- mirrors auth.users.id
  email       text unique not null,
  full_name   text,
  company_id  uuid not null references companies(id) on delete cascade,
  role        user_role not null default 'hr',
  is_active   bool not null default true,
  created_at  timestamptz not null default now()
);
create index if not exists idx_users_company on users (company_id);

-- ---------- HELPERS that read JWT-bound user -------------------------
create or replace function current_company_id() returns uuid
language sql stable security definer as $$
  select company_id from users where id = auth.uid()
$$;

create or replace function current_user_role() returns user_role
language sql stable security definer as $$
  select role from users where id = auth.uid()
$$;

create or replace function has_role(check_role user_role) returns boolean
language sql stable security definer as $$
  select coalesce(
    (select role = check_role or role = 'admin' from users where id = auth.uid()),
    false)
$$;

-- ---------- ADD company_id TO EXISTING TABLES ------------------------
do $$
declare t text;
begin
  for t in select unnest(array['vacancies','candidates','interviews','employees',
                                'attendance','payroll','activity_logs'])
  loop
    execute format('alter table %I add column if not exists company_id uuid', t);
    execute format('update %I set company_id = ''00000000-0000-0000-0000-000000000001''
                    where company_id is null', t);
    execute format('alter table %I alter column company_id set not null', t);
    execute format('alter table %I add constraint %I foreign key (company_id) references companies(id) on delete cascade',
                   t, t || '_company_fk');
    execute format('create index if not exists idx_%I_company on %I (company_id)', t, t);
  end loop;
exception
  when duplicate_object then null;
end $$;

-- ---------- DEFAULT company_id ON INSERT -----------------------------
create or replace function _default_company_id() returns trigger
language plpgsql as $$
begin
  if new.company_id is null then
    new.company_id := current_company_id();
  end if;
  return new;
end $$;

do $$
declare t text;
begin
  for t in select unnest(array['vacancies','candidates','interviews','employees',
                                'attendance','payroll','activity_logs'])
  loop
    execute format('drop trigger if exists trg_%I_default_company on %I', t, t);
    execute format('create trigger trg_%I_default_company
                    before insert on %I
                    for each row execute function _default_company_id()', t, t);
  end loop;
end $$;

-- ---------- LEAVE MANAGEMENT -----------------------------------------
do $$ begin
  create type leave_request_status as enum ('pending','approved','rejected','cancelled');
exception when duplicate_object then null; end $$;

create table if not exists leave_types (
  id            uuid primary key default gen_random_uuid(),
  company_id    uuid not null references companies(id) on delete cascade,
  code          text not null,
  name          text not null,
  annual_quota  numeric(5,1) not null default 0,
  is_paid       bool not null default true,
  carry_forward bool not null default false,
  created_at    timestamptz not null default now(),
  unique (company_id, code)
);

create table if not exists leave_balances (
  id           uuid primary key default gen_random_uuid(),
  company_id   uuid not null references companies(id) on delete cascade,
  employee_id  uuid not null references employees(id) on delete cascade,
  leave_type_id uuid not null references leave_types(id) on delete cascade,
  fy_start     date not null,
  opening      numeric(5,1) not null default 0,
  accrued      numeric(5,1) not null default 0,
  used         numeric(5,1) not null default 0,
  encashed     numeric(5,1) not null default 0,
  available    numeric(5,1) generated always as (opening + accrued - used - encashed) stored,
  unique (employee_id, leave_type_id, fy_start)
);
create index if not exists idx_leave_bal_emp on leave_balances (employee_id);

create table if not exists leave_requests (
  id            uuid primary key default gen_random_uuid(),
  company_id    uuid not null references companies(id) on delete cascade,
  employee_id   uuid not null references employees(id) on delete cascade,
  leave_type_id uuid not null references leave_types(id) on delete restrict,
  start_date    date not null,
  end_date      date not null check (end_date >= start_date),
  days          numeric(4,1) not null check (days > 0),
  reason        text,
  status        leave_request_status not null default 'pending',
  approver_id   uuid references users(id) on delete set null,
  approved_at   timestamptz,
  created_at    timestamptz not null default now()
);
create index if not exists idx_leave_req_emp    on leave_requests (employee_id);
create index if not exists idx_leave_req_status on leave_requests (status);

-- Auto-default company_id on leave tables too
drop trigger if exists trg_leave_types_default_company    on leave_types;
drop trigger if exists trg_leave_balances_default_company on leave_balances;
drop trigger if exists trg_leave_requests_default_company on leave_requests;
create trigger trg_leave_types_default_company    before insert on leave_types
  for each row execute function _default_company_id();
create trigger trg_leave_balances_default_company before insert on leave_balances
  for each row execute function _default_company_id();
create trigger trg_leave_requests_default_company before insert on leave_requests
  for each row execute function _default_company_id();

-- Approving a leave request deducts from balance.
create or replace function _on_leave_decision() returns trigger
language plpgsql as $$
declare bal_id uuid; fy date;
begin
  if new.status = 'approved' and (old.status is distinct from new.status) then
    fy := make_date(extract(year from new.start_date)::int -
            case when extract(month from new.start_date) < 4 then 1 else 0 end, 4, 1);

    insert into leave_balances (company_id, employee_id, leave_type_id, fy_start, opening, accrued, used)
    values (new.company_id, new.employee_id, new.leave_type_id, fy, 0, 0, 0)
    on conflict (employee_id, leave_type_id, fy_start) do nothing;

    update leave_balances
       set used = used + new.days
     where employee_id = new.employee_id
       and leave_type_id = new.leave_type_id
       and fy_start = fy;

    new.approved_at := now();
  end if;
  return new;
end $$;

drop trigger if exists trg_leave_decision on leave_requests;
create trigger trg_leave_decision before update of status on leave_requests
for each row execute function _on_leave_decision();

-- ---------- REPLACE BLANKET RLS WITH COMPANY-SCOPED RLS --------------
do $$
declare t text;
begin
  for t in select unnest(array['vacancies','candidates','interviews','employees',
                                'attendance','payroll','activity_logs',
                                'leave_types','leave_balances','leave_requests'])
  loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists "auth_all"     on %I', t);
    execute format('drop policy if exists "company_scope" on %I', t);
    execute format(
      'create policy "company_scope" on %I
         for all
         using      (company_id = current_company_id())
         with check (company_id = current_company_id())', t);
  end loop;
end $$;

-- Users table: each row visible only to the company it belongs to;
-- only admins can insert/update/delete other users.
alter table users enable row level security;
drop policy if exists "users_read"  on users;
drop policy if exists "users_write" on users;
create policy "users_read" on users
  for select using (company_id = current_company_id());
create policy "users_write" on users
  for all
  using      (company_id = current_company_id() and has_role('admin'))
  with check (company_id = current_company_id() and has_role('admin'));

-- Companies: a user can read its own company.
alter table companies enable row level security;
drop policy if exists "company_self" on companies;
create policy "company_self" on companies
  for select using (id = current_company_id());

-- ---------- HRMS RPCs ------------------------------------------------
-- One-shot dashboard payload — single round-trip, RLS-safe.
create or replace function rpc_dashboard()
returns jsonb
language plpgsql stable security definer
as $$
declare
  result jsonb;
begin
  with funnel as (select stage::text, count(*)::int as c from candidates group by stage),
       aging as (
         with active as (
           select c.id,
             coalesce(
               (select (h.value->>'at')::timestamptz
                  from jsonb_array_elements(c.history) h
                 order by (h.value->>'at')::timestamptz desc limit 1),
               c.created_at) as last_change
             from candidates c
            where c.stage not in ('hired','rejected')
         )
         select case
           when extract(epoch from (now()-last_change))/86400 <= 3  then '<=3'
           when extract(epoch from (now()-last_change))/86400 <= 7  then '4-7'
           when extract(epoch from (now()-last_change))/86400 <= 14 then '8-14'
           when extract(epoch from (now()-last_change))/86400 <= 30 then '15-30'
           else '>30' end as bucket,
           count(*)::int as c
         from active group by 1
       ),
       hires as (
         select count(*) filter (where stage = 'hired')::int as total,
                count(*) filter (where stage = 'hired'
                                  and date_trunc('month', updated_at) = date_trunc('month', now()))::int as this_month,
                avg(extract(epoch from (updated_at - created_at))/86400) filter (where stage = 'hired') as avg_tth_days
           from candidates
       )
  select jsonb_build_object(
    'totals', jsonb_build_object(
      'employees',         (select count(*) from employees where status = 'active'),
      'active_candidates', (select count(*) from candidates where stage not in ('hired','rejected')),
      'open_vacancies',    (select count(*) from vacancies where status = 'open'),
      'hired_this_month',  (select this_month from hires),
      'avg_time_to_hire',  coalesce((select round(avg_tth_days::numeric, 1) from hires), 0)
    ),
    'funnel', coalesce((select jsonb_object_agg(stage, c) from funnel), '{}'::jsonb),
    'aging',  coalesce((select jsonb_object_agg(bucket, c) from aging), '{}'::jsonb)
  ) into result;
  return result;
end $$;
