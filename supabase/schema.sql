-- =====================================================================
-- TalentTrack HRMS — PostgreSQL schema for Supabase
-- Run once in the Supabase SQL editor. Idempotent: safe to re-run.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------- ENUMS ----------------------------------------------------
do $$ begin
  create type candidate_stage   as enum ('sourced','screening','interview','offer','hired','rejected');
exception when duplicate_object then null; end $$;

do $$ begin
  create type vacancy_status    as enum ('open','on_hold','closed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type vacancy_priority  as enum ('low','medium','high');
exception when duplicate_object then null; end $$;

do $$ begin
  create type interview_status  as enum ('scheduled','completed','cancelled','no_show');
exception when duplicate_object then null; end $$;

do $$ begin
  create type interview_type    as enum ('screening','technical','culture','final');
exception when duplicate_object then null; end $$;

do $$ begin
  create type employee_status   as enum ('active','on_leave','resigned','terminated');
exception when duplicate_object then null; end $$;

do $$ begin
  create type attendance_status as enum ('present','absent','leave','half_day','holiday','weekend');
exception when duplicate_object then null; end $$;

do $$ begin
  create type payroll_status    as enum ('draft','processed','paid');
exception when duplicate_object then null; end $$;

-- ---------- VACANCIES ------------------------------------------------
create table if not exists vacancies (
  id              uuid primary key default gen_random_uuid(),
  title           text not null,
  department      text not null default 'General',
  location        text not null default 'Remote',
  hiring_manager  text,
  openings        int  not null default 1 check (openings >= 1),
  priority        vacancy_priority not null default 'medium',
  status          vacancy_status   not null default 'open',
  target_close    date,
  description     text,
  skills          text[] not null default '{}',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------- CANDIDATES -----------------------------------------------
create table if not exists candidates (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  email             text,
  phone             text,
  location          text,
  headline          text,
  skills            text[] not null default '{}',
  experience_years  numeric(4,1),
  education         jsonb not null default '[]',
  experience        jsonb not null default '[]',
  source            text  not null default 'CV Upload',
  vacancy_id        uuid  references vacancies(id) on delete set null,
  stage             candidate_stage not null default 'sourced',
  rating            int   check (rating between 0 and 5),
  raw_cv            text,
  file_name         text,
  history           jsonb not null default '[]',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- ---------- INTERVIEWS -----------------------------------------------
create table if not exists interviews (
  id            uuid primary key default gen_random_uuid(),
  candidate_id  uuid not null references candidates(id) on delete cascade,
  interviewer   text,
  type          interview_type   not null default 'technical',
  scheduled_at  timestamptz not null default now(),
  status        interview_status not null default 'scheduled',
  feedback      text,
  rating        int check (rating between 0 and 5),
  created_at    timestamptz not null default now()
);

-- ---------- EMPLOYEES ------------------------------------------------
create table if not exists employees (
  id                  uuid primary key default gen_random_uuid(),
  candidate_id        uuid unique references candidates(id) on delete set null,
  employee_code       text unique not null,
  full_name           text not null,
  email               text unique,
  phone               text,
  department          text not null default 'General',
  designation         text,
  date_of_joining     date not null default current_date,
  date_of_leaving     date,
  status              employee_status not null default 'active',
  manager_id          uuid references employees(id) on delete set null,
  ctc_annual          numeric(12,2) check (ctc_annual >= 0),
  basic_monthly       numeric(12,2) check (basic_monthly >= 0),
  hra_monthly         numeric(12,2) check (hra_monthly >= 0),
  allowances_monthly  numeric(12,2) check (allowances_monthly >= 0),
  pf_applicable       bool not null default true,
  esi_applicable      bool not null default false,
  bank_account        text,
  ifsc                text,
  pan                 text,
  uan                 text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------- ATTENDANCE -----------------------------------------------
create table if not exists attendance (
  id              uuid primary key default gen_random_uuid(),
  employee_id     uuid not null references employees(id) on delete cascade,
  attendance_date date not null,
  status          attendance_status not null default 'present',
  check_in        timestamptz,
  check_out       timestamptz,
  working_hours   numeric(4,2) generated always as (
    case when check_in is not null and check_out is not null
      then round((extract(epoch from (check_out - check_in))/3600.0)::numeric, 2)
      else 0 end
  ) stored,
  notes           text,
  created_at      timestamptz not null default now(),
  unique (employee_id, attendance_date)
);

-- ---------- PAYROLL --------------------------------------------------
create table if not exists payroll (
  id                  uuid primary key default gen_random_uuid(),
  employee_id         uuid not null references employees(id) on delete cascade,
  pay_period_month    smallint not null check (pay_period_month between 1 and 12),
  pay_period_year     smallint not null check (pay_period_year between 2000 and 2100),
  working_days        int  not null default 22,
  paid_days           numeric(4,1) not null default 22,
  lop_days            numeric(4,1) not null default 0,
  basic               numeric(12,2) not null default 0,
  hra                 numeric(12,2) not null default 0,
  allowances          numeric(12,2) not null default 0,
  gross_earnings      numeric(12,2) generated always as (basic + hra + allowances) stored,
  pf_employee         numeric(12,2) not null default 0,
  esi_employee        numeric(12,2) not null default 0,
  pt                  numeric(12,2) not null default 0,
  tds                 numeric(12,2) not null default 0,
  lop_deduction       numeric(12,2) not null default 0,
  total_deductions    numeric(12,2) generated always as (pf_employee + esi_employee + pt + tds + lop_deduction) stored,
  net_pay             numeric(12,2) generated always as
                      ((basic + hra + allowances) - (pf_employee + esi_employee + pt + tds + lop_deduction)) stored,
  status              payroll_status not null default 'draft',
  generated_at        timestamptz not null default now(),
  paid_at             timestamptz,
  unique (employee_id, pay_period_month, pay_period_year)
);

-- ---------- ACTIVITY LOG ---------------------------------------------
create table if not exists activity_logs (
  id          uuid primary key default gen_random_uuid(),
  type        text not null,
  message     text not null,
  meta        jsonb not null default '{}',
  entity_type text,
  entity_id   uuid,
  actor       text,
  created_at  timestamptz not null default now()
);

-- ---------- INDEXES --------------------------------------------------
create index if not exists idx_vacancies_status         on vacancies (status);
create index if not exists idx_candidates_stage         on candidates (stage);
create index if not exists idx_candidates_vacancy       on candidates (vacancy_id);
create index if not exists idx_candidates_skills        on candidates using gin (skills);
create index if not exists idx_interviews_candidate     on interviews (candidate_id);
create index if not exists idx_interviews_when          on interviews (scheduled_at);
create index if not exists idx_attendance_emp_date      on attendance (employee_id, attendance_date desc);
create index if not exists idx_payroll_emp_period       on payroll (employee_id, pay_period_year desc, pay_period_month desc);
create index if not exists idx_activity_recent          on activity_logs (created_at desc);

-- ---------- TRIGGERS -------------------------------------------------
create or replace function _set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists trg_vac_upd  on vacancies;
drop trigger if exists trg_cand_upd on candidates;
drop trigger if exists trg_emp_upd  on employees;
create trigger trg_vac_upd  before update on vacancies  for each row execute function _set_updated_at();
create trigger trg_cand_upd before update on candidates for each row execute function _set_updated_at();
create trigger trg_emp_upd  before update on employees  for each row execute function _set_updated_at();

-- Append candidate.history on stage change + log activity
create or replace function _candidate_stage_change() returns trigger
language plpgsql as $$
begin
  if new.stage is distinct from old.stage then
    new.history = coalesce(old.history, '[]'::jsonb)
      || jsonb_build_array(jsonb_build_object(
           'stage', new.stage::text,
           'from',  old.stage::text,
           'at',    now()
         ));
    insert into activity_logs (type, message, entity_type, entity_id, meta)
    values ('candidate.moved',
            format('%s → %s', new.name, new.stage::text),
            'candidate', new.id,
            jsonb_build_object('from', old.stage::text, 'to', new.stage::text));
  end if;
  return new;
end $$;

drop trigger if exists trg_cand_history on candidates;
create trigger trg_cand_history before update of stage on candidates
for each row execute function _candidate_stage_change();

-- Auto-create employee when a candidate is hired
create or replace function _next_employee_code() returns text
language plpgsql as $$
declare n int;
begin
  select coalesce(max(nullif(regexp_replace(employee_code, '\D', '', 'g'), '')::int), 0) + 1
    into n
    from employees
   where employee_code ~ '^EMP\d+$';
  return 'EMP' || lpad(n::text, 4, '0');
end $$;

create or replace function _candidate_to_employee() returns trigger
language plpgsql as $$
declare dept text; role_title text;
begin
  if new.stage = 'hired' and (old.stage is distinct from new.stage) then
    select v.department, v.title into dept, role_title
      from vacancies v where v.id = new.vacancy_id;

    insert into employees (
      candidate_id, employee_code, full_name, email, phone,
      department, designation, date_of_joining, status
    ) values (
      new.id, _next_employee_code(), new.name, new.email, new.phone,
      coalesce(dept, 'General'), role_title, current_date, 'active'
    )
    on conflict (candidate_id) do nothing;

    insert into activity_logs (type, message, entity_type, entity_id, meta)
    values ('employee.onboarded',
            format('Onboarded %s', new.name),
            'candidate', new.id,
            jsonb_build_object('vacancy_id', new.vacancy_id));
  end if;
  return new;
end $$;

drop trigger if exists trg_cand_to_emp on candidates;
create trigger trg_cand_to_emp after update of stage on candidates
for each row execute function _candidate_to_employee();

-- Activity logs on insert
create or replace function _log_create_vac() returns trigger language plpgsql as $$
begin
  insert into activity_logs (type, message, entity_type, entity_id)
  values ('vacancy.created', format('Vacancy "%s" opened', new.title), 'vacancy', new.id);
  return new;
end $$;

create or replace function _log_create_cand() returns trigger language plpgsql as $$
begin
  insert into activity_logs (type, message, entity_type, entity_id)
  values ('candidate.created', format('Candidate "%s" added', new.name), 'candidate', new.id);
  return new;
end $$;

create or replace function _log_create_intv() returns trigger language plpgsql as $$
declare cand_name text;
begin
  select name into cand_name from candidates where id = new.candidate_id;
  insert into activity_logs (type, message, entity_type, entity_id)
  values ('interview.scheduled',
          format('Interview scheduled with %s', coalesce(cand_name,'candidate')),
          'interview', new.id);
  return new;
end $$;

drop trigger if exists trg_log_vac  on vacancies;
drop trigger if exists trg_log_cand on candidates;
drop trigger if exists trg_log_intv on interviews;
create trigger trg_log_vac  after insert on vacancies  for each row execute function _log_create_vac();
create trigger trg_log_cand after insert on candidates for each row execute function _log_create_cand();
create trigger trg_log_intv after insert on interviews for each row execute function _log_create_intv();

-- ---------- ANALYTICS RPCs ------------------------------------------
-- Funnel counts per stage
create or replace function rpc_funnel_counts()
returns table(stage text, count bigint)
language sql stable as $$
  select stage::text, count(*)::bigint from candidates group by stage;
$$;

-- Average TAT per stage from candidates.history
create or replace function rpc_avg_tat_by_stage()
returns table(stage text, avg_days numeric)
language sql stable as $$
  with steps as (
    select c.id,
           (h.value->>'stage')::text as stage,
           (h.value->>'at')::timestamptz as at,
           lead((h.value->>'at')::timestamptz)
             over (partition by c.id order by h.ord) as next_at
      from candidates c,
           jsonb_array_elements(c.history) with ordinality as h(value, ord)
  )
  select stage,
         round(avg(extract(epoch from (coalesce(next_at, now()) - at))/86400)::numeric, 1) as avg_days
    from steps
   group by stage;
$$;

-- Aging buckets for active candidates
create or replace function rpc_aging_buckets()
returns table(bucket text, count bigint)
language sql stable as $$
  with active as (
    select c.id,
      coalesce(
        (select (h.value->>'at')::timestamptz
           from jsonb_array_elements(c.history) h
          order by (h.value->>'at')::timestamptz desc limit 1),
        c.created_at) as last_change
      from candidates c
     where c.stage not in ('hired','rejected')
  ),
  classified as (
    select case
      when extract(epoch from (now()-last_change))/86400 <= 3  then '<=3'
      when extract(epoch from (now()-last_change))/86400 <= 7  then '4-7'
      when extract(epoch from (now()-last_change))/86400 <= 14 then '8-14'
      when extract(epoch from (now()-last_change))/86400 <= 30 then '15-30'
      else '>30' end as bucket
    from active
  )
  select bucket, count(*)::bigint from classified group by bucket;
$$;

-- ---------- ROW-LEVEL SECURITY ---------------------------------------
-- Tighten per-org/per-role for production. Default: any authenticated user has full access.
alter table vacancies      enable row level security;
alter table candidates     enable row level security;
alter table interviews     enable row level security;
alter table employees      enable row level security;
alter table attendance     enable row level security;
alter table payroll        enable row level security;
alter table activity_logs  enable row level security;

do $$
declare t text;
begin
  for t in select unnest(array['vacancies','candidates','interviews','employees','attendance','payroll','activity_logs'])
  loop
    execute format(
      'drop policy if exists "auth_all" on %I; create policy "auth_all" on %I for all using (auth.role() = ''authenticated'') with check (auth.role() = ''authenticated'');',
      t, t);
  end loop;
end $$;
