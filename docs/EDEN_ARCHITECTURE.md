# EDEN — System Architecture (Initial Draft v0.1)

> **EDEN** — *"Your one-stop garden for everything HR."*
> A multi-party HR-services SaaS: a consultancy operates it, client companies
> consume it, and external referral partners feed talent acquisition into it.
>
> Status: **DRAFT FOR REVIEW.** Decision points are flagged `⟦DECISION⟧`.
> Nothing here is implemented yet — this is the blueprint we converge on
> *before* writing code.

---

## 0. Why the current prototype is not enough

The working prototype proves the HR domain logic (recruitment → employee →
attendance → leave → payroll → compliance). But it assumes **one
organisation, one tenant, flat roles**. EDEN's real problem is not HR
features — it is **who is allowed to see and do what, across a 3-sided
network of parties**. That is an *authorization and tenancy* problem first,
and an HR problem second. This document is mostly about that.

---

## 1. The five principal types (precise definitions)

| # | Principal | Belongs to | Data they touch | Trust tier |
|---|-----------|-----------|-----------------|-----------|
| 1 | **Consultancy Owner** | The consultancy that *operates* EDEN | Everything, across all clients (master) | Platform |
| 2 | **Consultancy Member** | The consultancy | The client(s) assigned to them, scoped by HR function **and** clearance level | Platform-delegated |
| 3 | **Client Owner** | A client company | Everything within *their own* company | Tenant-admin |
| 4 | **Client Member (HR/Manager/Employee)** | A client company | Their own company, scoped by HR function, clearance, and record-scope (all / dept / team / self) | Tenant-scoped |
| 5 | **Recruitment Partner** | External partner firm/individual | **Only TA (recruitment) data** of the client(s) *they referred*, time-boxed, no comp/PII export | External-limited |

Two more we must model even though you didn't list them — real systems
always need them:

| # | Principal | Why it is mandatory |
|---|-----------|--------------------|
| 6 | **Auditor / Compliance (read-only)** | Statutory audits, internal SoD review — read everything, change nothing |
| 7 | **System / Service account** | Scheduled payroll runs, integrations, webhooks — non-human, narrowly scoped |

---

## 2. How real systems solve this (research baseline)

I looked at how Workday, Rippling, Darwinbox, Keka, Deel, and Gusto model
this. The consistent patterns:

1. **Tenancy is a graph, not a flag.** Nobody uses a single `company_id`.
   They model Platform → Org → Legal Entity → Location → Department → Team →
   Worker as a hierarchy, and grant access at *any node*, inheriting down.
2. **RBAC alone is never enough.** Every serious system uses **Scoped RBAC +
   ABAC overlays**: a role says *what actions*, a *scoped assignment* says
   *on which slice of the org*, and *attribute policies* mask sensitive
   fields. Workday calls these "security groups + domains"; Rippling calls
   them "permission sets + groups"; the shape is identical.
3. **Data sensitivity is tiered.** Salary, bank, Aadhaar/PAN, health,
   disciplinary, and litigation data sit behind a **clearance ceiling**
   independent of the functional role. An HR ops person can edit attendance
   (functional) yet be blind to CTC (clearance).
4. **Defense in depth for isolation.** Authorization is enforced at *three*
   layers: API policy engine, database row-level security, and field
   masking in serialization. A bug in one layer must not leak tenants.
5. **Consultancy/agency model = "managed tenants."** Deel/Rippling EOR and
   PEOs solve exactly your case: an operator's staff act *on behalf of*
   client tenants through **delegated, audited, time-boxed grants**, with
   **break-glass** and **impersonation logging**.
6. **Maker–checker & Segregation of Duties** are first-class (payroll
   especially): the person who runs payroll cannot be the one who approves
   and releases it.

EDEN's model below is the synthesis of these patterns, narrowed to your
5-party reality and the Indian statutory context.

---

## 3. Tenancy graph (the backbone)

```
EDEN Platform
 └─ Consultancy            (operator org; ⟦DECISION⟧ one, or many = white-label?)
     ├─ Consultancy Users  (owners, members)
     ├─ Partners           (external; linked to clients via Referrals)
     └─ Client Company          ◀── the primary TENANT boundary
         ├─ Legal Entity        (PF/ESI/PT/TAN registration boundary)
         │   └─ Location / Establishment   (Shops & Estab / factory)
         │       └─ Department
         │           └─ Team
         │               └─ Employee  (the data subject)
         ├─ Client Users
         └─ Referral  ◀── Partner that introduced this client (for TA scope)
```

**Rules**

- The **tenant key on every domain row is `client_company_id`** (plus
  `legal_entity_id` where statutory boundaries matter — payroll, PF, TDS).
- A grant made at any node **inherits downward** (grant at Legal Entity ⇒
  covers all its Locations/Depts) unless an explicit deny narrows it.
- Consultancy and Partner principals **do not own** a `client_company_id`;
  they reach clients through **assignment** (consultancy) or **referral**
  (partner) join tables that RLS reads.

---

## 4. The authorization model (core of EDEN)

Access is a **function of nine dimensions**. A request is allowed only if
*every* dimension permits it.

| # | Dimension | Example | Where enforced |
|---|-----------|---------|----------------|
| 1 | **Identity** | authenticated user `u_123` | Auth service (OIDC) |
| 2 | **Role** | `PAYROLL_PROCESSOR` → set of action permissions | PDP (policy engine) |
| 3 | **Tenant scope** | this grant applies to `client=Acme`, `entity=Acme-South` | PDP + DB RLS |
| 4 | **Module/function mask** | grant limited to `{recruitment, attendance}` | PDP + DB RLS |
| 5 | **Clearance ceiling** | ceiling `L3` → may see comp but not Aadhaar (`L4`) | PDP + field masking |
| 6 | **Record scope** | `all / legal_entity / department / team / self / referred` | DB RLS |
| 7 | **Action** | `read / create / update / delete / approve / export / impersonate` | PDP |
| 8 | **Temporal window** | partner access valid `2026-01-01 → 2026-06-30` | PDP + RLS |
| 9 | **Environment** | MFA required for `export`; IP allowlist; break-glass | API gateway + PDP |

**Decision rule:** *deny overrides allow*. Explicit deny entries beat any
grant. Default is **deny**.

### 4.1 Object model (RBAC + ABAC)

```
PERMISSION   (code, resource, action, min_clearance, is_sensitive)
ROLE         (code, name, tier[platform|consultancy|client|partner], is_system)
ROLE_PERMISSION (role → permission)

PRINCIPAL    (user / partner-user / service)
ROLE_ASSIGNMENT  ◀── the heart of the model
   principal_id
   role_id
   scope_type   {platform, consultancy, client, legal_entity, location, department, team, self, referred}
   scope_id     (nullable for 'self' / 'referred')
   module_mask  (set: recruitment, core_hr, time, leave, payroll, performance, compliance, documents, billing)  -- NULL = all in role
   clearance_ceiling   (L0..L4)
   record_scope  {all, legal_entity, department, team, self, referred}
   valid_from, valid_to
   conditions    (jsonb: ip_allowlist, mfa_required, justification_required, sod_group)
   granted_by, granted_at, status

CLEARANCE_LEVEL  (L0..L4 definitions)
DATA_CLASSIFICATION (resource/field → min_clearance, pii_category)
FIELD_MASK_POLICY  (resource, field, mask_below_clearance, mask_style[hash|partial|redact])
DELEGATION   (from_principal, to_principal, role_assignment_id, valid_from/to, reason)
SOD_RULE     (mutually exclusive permission pairs, e.g. payroll.run ⊕ payroll.approve)
ACCESS_REVIEW (periodic recertification campaigns)
BREAK_GLASS_SESSION (principal, target_scope, reason, approved_by, expires_at)
ACCESS_LOG / AUDIT_LOG  (immutable, hash-chained)
```

### 4.2 Clearance tiers (data sensitivity, independent of role)

| Tier | Name | Examples | Typical holders |
|------|------|----------|-----------------|
| **L0** | Operational | Org chart, job titles, location, headcount | Everyone incl. partners |
| **L1** | Internal HR | Contact info, attendance, leave balances, candidate pipeline stage | HR ops, managers, partners (TA only) |
| **L2** | Sensitive HR | Performance ratings, PIPs, disciplinary, grievance, documents | HR generalists, dept heads |
| **L3** | Confidential Comp | CTC, payslips, bank account, tax, increments | Payroll, HR head, client owner |
| **L4** | Regulated PII | Aadhaar, PAN, biometric, health, background-check, litigation | Named custodians only; always audited |

**Self-exception:** a principal may always see **L3 data about
themselves** (own payslip). **L4-about-self** is partially masked even to
the subject (e.g. Aadhaar shown as `XXXX-XXXX-1234`) and access is logged.

### 4.3 Effective-access resolution (request-time algorithm)

```
1. Authenticate → principal.
2. Resolve ACTIVE CONTEXT: which client_company (+ entity) the request targets
   (from JWT `act` claim / tenant switcher; partners/consultancy must pick one).
3. Collect ROLE_ASSIGNMENTS for principal where:
     scope covers active context (graph ancestor match OR referred-set match)
     AND now ∈ [valid_from, valid_to]
     AND status = active
4. effective_permissions = ⋃ role.permissions, then ∩ each assignment.module_mask
5. clearance = max(assignment.clearance_ceiling) among applicable assignments
6. record_scope = most permissive among applicable assignments
7. Apply SOD_RULES (reject if conflicting perms both active without checker)
8. Apply explicit DENY entries (override)
9. For each field in response: visible iff field.min_clearance ≤ clearance
     (apply FIELD_MASK_POLICY otherwise); self-subject overrides per 4.2
10. Enforce environment conditions (MFA/IP/break-glass)
11. Log decision (allow & deny) to ACCESS_LOG (hash-chained)
```

### 4.4 The five principals as concrete grants

| Principal | role (example) | scope_type | module_mask | clearance | record_scope | temporal |
|-----------|----------------|-----------|-------------|-----------|--------------|----------|
| **Consultancy Owner** | `CONSULTANCY_OWNER` | `consultancy` | all | L4 | all | none |
| **Consultancy Member — single function** | `CLIENT_OPS` | `client` (per assigned client) | `{payroll}` | L3 | all (within client) | contract window |
| **Consultancy Member — all functions** | `CLIENT_GENERALIST` | `client` | all | L3 (L4 only if custodian) | all | contract window |
| **Consultancy Member — select functions** | custom | `client` | `{recruitment, attendance}` | L1 | all | contract window |
| **Client Owner** | `CLIENT_OWNER` | `client` (own) | all | L4 | all | none |
| **Client HR (scoped)** | `CLIENT_HR` | `legal_entity` / `department` | `{core_hr, leave, attendance}` | L2 | legal_entity/dept | none |
| **Client Manager** | `MANAGER_SELF_TEAM` | `team` | `{attendance, leave, performance}` | L1 | team | none |
| **Client Employee (ESS)** | `EMPLOYEE_SELF` | `self` | `{core_hr, leave, attendance, payroll(self)}` | L1 (+ own L3) | self | none |
| **Recruitment Partner** | `PARTNER_TA_VIEWER` | `referred` | `{recruitment}` (read + limited) | L1 (no comp; PII masked; **no export**) | referred clients only | referral window |
| **Auditor** | `AUDITOR_RO` | `consultancy`/`client` | all (read) | L4 (read, masked logging) | all | campaign window |

> **Partner specifics** (you flagged this as important): a partner sees, for
> *clients they referred only*: vacancy list, pipeline stage counts,
> candidate names + status (no resumes, no contact PII, no salary, **no
> export/download**), and **their own commission/billing** line. Access
> auto-expires at the end of the referral window or on client off-boarding.
> Everything they see is logged and visible to the Consultancy Owner.

---

## 5. Multi-tenancy & isolation strategy

⟦DECISION⟧ **Default = Pooled Postgres + Row-Level Security**, with a
**promotion path to dedicated schema/DB** for enterprise clients that
demand physical isolation or specific data residency.

**Why pooled-RLS as default:** cheapest per tenant, supports the
consultancy's cross-client workflows, matches the prototype's Supabase
direction. **Why a silo option:** some enterprise clients (and certain
data-residency contracts) will require it; build the abstraction now so
promotion is config, not a rewrite.

**Defense in depth (all three, always):**

1. **API policy engine (PDP)** — central allow/deny before any handler runs.
2. **Database RLS** — every domain table has policies keyed off
   session GUCs (`eden.principal`, `eden.active_client`,
   `eden.clearance`, `eden.record_scope`) set per request from the
   *validated* token. Consultancy/partner reach is enforced by RLS joining
   to `consultancy_client_assignment` / `referrals`.
3. **Field masking** — serialization layer redacts fields above the
   caller's clearance even if a query over-selects.

A failure in any one layer must not leak data across tenants. The tenant
key is never taken from the request body — only from the verified token /
session context.

---

## 6. System architecture (services & data)

⟦DECISION⟧ **Start as a modular monolith** (clear module boundaries, one
deployable, one Postgres) and extract services only when scale demands.
Premature microservices would kill velocity at your stage.

```
                ┌────────────────────────────────────────────┐
   Browser /    │  CDN + WAF + API Gateway                    │
   Mobile  ───▶ │  (rate-limit, mTLS S2S, request signing)    │
                └───────────────┬────────────────────────────┘
                                │
        ┌───────────────────────┼────────────────────────────┐
        │                       │                             │
 ┌──────▼──────┐      ┌─────────▼──────────┐        ┌─────────▼─────────┐
 │ Identity    │      │ Authorization PDP  │        │ Domain Modules    │
 │ (OIDC,      │      │ (policy eval,      │        │ Recruitment       │
 │  MFA, SCIM, │◀────▶│  effective-access, │◀──────▶│ Core HR           │
 │  SAML for   │      │  emits RLS GUCs,   │        │ Time & Attendance │
 │  enterprise)│      │  SoD, break-glass) │        │ Leave             │
 └─────────────┘      └────────────────────┘        │ Payroll           │
                                                    │ Compliance        │
 ┌─────────────┐   ┌──────────────┐   ┌───────────┐ │ Documents         │
 │ Postgres    │   │ Object Store │   │ Search    │ │ Billing (clients  │
 │ (RLS,       │   │ (S3-compat,  │   │ (OpenSrch)│ │  + partner comm.) │
 │  encrypted, │   │  per-tenant  │   └───────────┘ │ Notifications     │
 │  PITR)      │   │  prefix, KMS)│                  │ Analytics (sep DW)│
 └─────────────┘   └──────────────┘                  └───────────────────┘
        ▲                                                   │
        │            ┌───────────────────────┐              │
        └────────────│ Event bus (outbox →   │◀─────────────┘
                      │ Kafka/Rabbit):        │
                      │ candidate.hired →     │  immutable
                      │ employee.created, …   │  AUDIT LOG (hash-chained,
                      └───────────────────────┘  append-only / WORM)
```

**Cross-cutting:** KMS/Vault for secrets; envelope + column-level
encryption for L4 fields (Aadhaar/PAN/bank); job scheduler for payroll
runs, leave accrual, compliance reminders, access recertification; a
separate **de-identified** analytics warehouse (never run BI on the live
tenant DB).

**Key automation via events (outbox pattern):** `candidate.hired` →
`employee.created` → `salary_structure.requested`; `leave.approved` →
`balance.debited`; `payroll.locked` → `payslip.published` +
`statutory.filings.prepared`. Same automations as the prototype, but
transactional and auditable.

---

## 7. Database schema (draft DDL — identity, authz, audit, billing)

> HR-domain tables (candidates, vacancies, employees, attendance, leave,
> payroll, …) are reused from the existing prototype schema, **with two
> changes applied uniformly**: every row carries `client_company_id`
> (tenant key) and, where statutory, `legal_entity_id`; and every table
> gets the RLS policy template in §8.

### 7.1 Identity & tenancy

```sql
create table consultancies (              -- ⟦DECISION⟧ 1 row, or many (white-label)
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'active',
  created_at timestamptz default now()
);

create table client_companies (
  id uuid primary key default gen_random_uuid(),
  consultancy_id uuid not null references consultancies(id),
  legal_name text not null,
  industry text, country text default 'IN',
  data_isolation text not null default 'pooled'   -- pooled | dedicated_schema | dedicated_db
    check (data_isolation in ('pooled','dedicated_schema','dedicated_db')),
  status text not null default 'onboarding',
  referred_by_partner_id uuid,                     -- nullable
  created_at timestamptz default now()
);

create table legal_entities (
  id uuid primary key default gen_random_uuid(),
  client_company_id uuid not null references client_companies(id) on delete cascade,
  name text not null,
  pan text, tan text, pf_code text, esi_code text, pt_state text,
  created_at timestamptz default now()
);

create table locations (
  id uuid primary key default gen_random_uuid(),
  legal_entity_id uuid not null references legal_entities(id) on delete cascade,
  name text not null, state text, shops_estab_no text
);

create table org_units (                  -- departments & teams (self-referential)
  id uuid primary key default gen_random_uuid(),
  client_company_id uuid not null references client_companies(id) on delete cascade,
  parent_id uuid references org_units(id),
  kind text not null check (kind in ('department','team')),
  name text not null
);

create table partners (
  id uuid primary key default gen_random_uuid(),
  consultancy_id uuid not null references consultancies(id),
  name text not null, contact_email text not null,
  commission_pct numeric(5,2) default 0,
  status text not null default 'active'
);

create table referrals (                  -- partner ↔ referred client (TA scope source)
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null references partners(id),
  client_company_id uuid not null references client_companies(id),
  scope text not null default 'recruitment',
  valid_from date not null default current_date,
  valid_to date,                           -- null = open; auto-set on off-board
  status text not null default 'active',
  unique (partner_id, client_company_id)
);

create table principals (                 -- every actor (human or service)
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('user','partner_user','service','auditor')),
  email citext unique,
  full_name text,
  home_party text not null check (home_party in ('consultancy','client','partner','platform')),
  home_party_id uuid,                      -- consultancy_id | client_company_id | partner_id
  status text not null default 'active',
  mfa_enabled boolean default false,
  created_at timestamptz default now()
);

create table identities (                 -- SSO/login methods (OIDC/SAML/SCIM)
  id uuid primary key default gen_random_uuid(),
  principal_id uuid not null references principals(id) on delete cascade,
  provider text not null, subject text not null,
  unique (provider, subject)
);

-- Which consultancy members may act on which clients (consultancy → client bridge)
create table consultancy_client_assignment (
  id uuid primary key default gen_random_uuid(),
  principal_id uuid not null references principals(id),
  client_company_id uuid not null references client_companies(id),
  valid_from date default current_date, valid_to date,
  status text not null default 'active',
  unique (principal_id, client_company_id)
);
```

### 7.2 Authorization

```sql
create table permissions (
  code text primary key,                   -- e.g. 'payroll.payslip:read'
  resource text not null,                   -- 'payroll.payslip'
  action text not null,                     -- read|create|update|delete|approve|export|impersonate
  min_clearance smallint not null default 0,-- 0..4
  is_sensitive boolean not null default false
);

create table roles (
  id uuid primary key default gen_random_uuid(),
  code text unique not null,
  name text not null,
  tier text not null check (tier in ('platform','consultancy','client','partner')),
  is_system boolean not null default true,
  client_company_id uuid references client_companies(id)   -- null for system roles; set for client-custom roles
);

create table role_permissions (
  role_id uuid references roles(id) on delete cascade,
  permission_code text references permissions(code) on delete cascade,
  effect text not null default 'allow' check (effect in ('allow','deny')),
  primary key (role_id, permission_code)
);

create table role_assignments (             -- the heart of the model
  id uuid primary key default gen_random_uuid(),
  principal_id uuid not null references principals(id) on delete cascade,
  role_id uuid not null references roles(id),
  scope_type text not null check (scope_type in
    ('platform','consultancy','client','legal_entity','location','department','team','self','referred')),
  scope_id uuid,                             -- null for self/referred/platform
  module_mask text[],                        -- null = all modules the role allows
  clearance_ceiling smallint not null default 1,
  record_scope text not null default 'all'
    check (record_scope in ('all','legal_entity','department','team','self','referred')),
  valid_from date default current_date,
  valid_to date,
  conditions jsonb not null default '{}',    -- {mfa_required, ip_allowlist, justification_required, sod_group}
  granted_by uuid references principals(id),
  granted_at timestamptz default now(),
  status text not null default 'active'
);
create index on role_assignments (principal_id, status);
create index on role_assignments (scope_type, scope_id);

create table data_classification (
  resource text not null, field text not null,
  min_clearance smallint not null,
  pii_category text,                         -- aadhaar|pan|bank|health|biometric|contact|none
  primary key (resource, field)
);

create table field_mask_policies (
  resource text not null, field text not null,
  mask_below_clearance smallint not null,
  mask_style text not null check (mask_style in ('hash','partial','redact')),
  primary key (resource, field)
);

create table sod_rules (                     -- segregation of duties
  id uuid primary key default gen_random_uuid(),
  perm_a text references permissions(code),
  perm_b text references permissions(code),
  note text
);

create table delegations (
  id uuid primary key default gen_random_uuid(),
  from_principal uuid references principals(id),
  to_principal uuid references principals(id),
  role_assignment_id uuid references role_assignments(id),
  valid_from timestamptz, valid_to timestamptz,
  reason text, created_at timestamptz default now()
);

create table break_glass_sessions (
  id uuid primary key default gen_random_uuid(),
  principal_id uuid references principals(id),
  target_scope_type text, target_scope_id uuid,
  reason text not null,
  approved_by uuid references principals(id),
  started_at timestamptz default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table access_reviews (                -- periodic recertification
  id uuid primary key default gen_random_uuid(),
  campaign text not null,
  role_assignment_id uuid references role_assignments(id),
  reviewer uuid references principals(id),
  decision text check (decision in ('keep','revoke','modify')),
  reviewed_at timestamptz
);
```

### 7.3 Audit & compliance

```sql
create table audit_log (                     -- immutable, hash-chained
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  principal_id uuid, acted_as uuid,           -- impersonation: acted_as ≠ principal
  client_company_id uuid, legal_entity_id uuid,
  module text, action text,
  resource text, resource_id uuid,
  decision text check (decision in ('allow','deny')),
  before jsonb, after jsonb,
  ip inet, user_agent text,
  prev_hash bytea, row_hash bytea             -- tamper-evident chain
);

create table consent_records (               -- DPDP Act 2023
  id uuid primary key default gen_random_uuid(),
  data_principal uuid,                        -- the employee/candidate
  client_company_id uuid,
  purpose text not null, granted boolean not null,
  granted_at timestamptz, withdrawn_at timestamptz
);

create table data_retention_policies (
  client_company_id uuid, resource text,
  retain_months int not null,
  legal_hold boolean default false,
  primary key (client_company_id, resource)
);
```

### 7.4 Billing

```sql
create table client_subscriptions (
  id uuid primary key default gen_random_uuid(),
  client_company_id uuid references client_companies(id),
  plan text, seats int, per_seat numeric(10,2),
  billing_cycle text default 'monthly', status text default 'active'
);

create table partner_commissions (
  id uuid primary key default gen_random_uuid(),
  partner_id uuid references partners(id),
  client_company_id uuid references client_companies(id),
  basis text,                                 -- e.g. 'first_year_fee'
  amount numeric(12,2), status text default 'accrued',
  period_month int, period_year int
);
```

---

## 8. RLS policy template (applied to every domain table)

```sql
-- Session GUCs set by the API from the *validated* token, never the body:
--   eden.principal        uuid
--   eden.active_client    uuid
--   eden.clearance        int
--   eden.record_scope     text
--   eden.scope_dept       uuid (nullable)

alter table <domain_table> enable row level security;

create policy tenant_isolation on <domain_table>
  using (
    client_company_id = current_setting('eden.active_client')::uuid
    and (
      -- consultancy member must be assigned to this client
      exists (select 1 from consultancy_client_assignment a
              where a.principal_id = current_setting('eden.principal')::uuid
                and a.client_company_id = <domain_table>.client_company_id
                and a.status='active'
                and current_date between a.valid_from and coalesce(a.valid_to, current_date))
      -- OR a client/native principal whose home company matches
      or exists (select 1 from principals p
              where p.id = current_setting('eden.principal')::uuid
                and p.home_party='client'
                and p.home_party_id = <domain_table>.client_company_id)
      -- OR a partner, restricted to referred clients AND recruitment module
      or exists (select 1 from referrals r
              where r.client_company_id = <domain_table>.client_company_id
                and r.partner_id = (select home_party_id from principals
                                    where id=current_setting('eden.principal')::uuid)
                and r.status='active'
                and '<module>' = 'recruitment')
    )
  )
  with check ( client_company_id = current_setting('eden.active_client')::uuid );

-- Record-scope narrowing (department/team/self) layered as an additional
-- restrictive policy; field masking handled in the serialization layer.
```

---

## 9. Segregation-of-duties & maker–checker (payroll-critical)

| Conflict (cannot be same person on same client) |
|--------------------------------------------------|
| `payroll.run` ⊕ `payroll.approve` |
| `payroll.approve` ⊕ `payroll.release` (bank) |
| `employee.create` ⊕ `employee.compensation:update` (ghost-employee fraud) |
| `vacancy.approve` ⊕ `candidate.hire` |
| `role.grant` ⊕ `access_review.decide` |

Enforced both by `sod_rules` at grant time and at action time in the PDP.

---

## 10. Compliance & data protection (India-first)

- **DPDP Act 2023:** consent capture, purpose limitation, data-principal
  rights (access/correction/erasure), breach notification, data-fiduciary
  obligations → `consent_records`, erasure workflow vs `legal_hold`.
- **Statutory payroll:** EPF, ESI, PT (state), TDS/24Q, LWF, gratuity,
  bonus — scoped at **legal entity** (the registration boundary).
- **Audit retention:** payroll/tax artefacts ≥ 8 years; audit log
  append-only, hash-chained, exportable for statutory audit.
- **Encryption:** TLS in transit; AES-256 at rest; column-level envelope
  encryption for L4 (Aadhaar/PAN/bank/biometric/health).
- **Access governance:** quarterly access recertification campaigns;
  break-glass requires reason + approver + auto-expiry + post-hoc review;
  all impersonation (consultancy → client support) logged with `acted_as`.

---

## 11. Gap analysis vs current prototype

| Area | Prototype today | EDEN target | Effort |
|------|-----------------|-------------|--------|
| Tenancy | single `company_id` flag | Platform→Client→Entity→Dept graph | High |
| AuthZ | flat roles, blanket RLS | Scoped RBAC + ABAC + clearance + masking | High |
| Parties | 1 org | Consultancy + Clients + Partners + Auditor | High |
| Isolation | one DB | Pooled-RLS default + silo promotion path | Medium |
| Audit | activity log | Immutable hash-chained audit + access log | Medium |
| Compliance | rule engine | + DPDP consent, retention, legal hold | Medium |
| Billing | none | Client subscriptions + partner commissions | Medium |
| Architecture | Flask monolith / JS+Supabase | Modular monolith + PDP + event bus | High |
| HR domain logic | **solid, reusable** | reuse with tenancy keys added | Low |

The HR domain logic you already validated is keep-able. The rebuild is
concentrated in **tenancy + authorization + audit** — exactly where it
should be.

---

## 12. Proposed build phases (after we agree the design)

1. **P0 – Identity & tenancy core:** principals, tenancy graph, OIDC/MFA,
   tenant switcher, RLS skeleton. No HR features yet.
2. **P1 – Authorization engine:** permissions, roles, scoped assignments,
   PDP, clearance + field masking, audit log. Ship with one module
   (recruitment) end-to-end behind the new authz.
3. **P2 – Migrate HR domain** (employee, attendance, leave, payroll,
   compliance) onto tenancy keys + PDP. Reuse validated logic.
4. **P3 – Partner portal** (referred-clients TA view, commissions).
5. **P4 – Governance:** SoD, access reviews, break-glass, DPDP consent &
   retention, billing.
6. **P5 – Scale:** silo-promotion for enterprise clients, analytics DW,
   service extraction where justified.

---

## 13. Open decisions (need your input before P0)

1. **One consultancy or white-label many?** Does EDEN serve only *your*
   consultancy, or will other consultancies run on it as a white-label
   platform? This sets the top of the tenancy graph.
2. **Default isolation:** pooled-RLS (recommended) with silo *promotion*
   for enterprise — agree?
3. **Build approach:** evolve the current Flask/Supabase prototype, or
   greenfield on this architecture reusing only the HR-domain logic?
4. **Partner depth:** read-only TA *visibility + commissions* only
   (recommended), or do partners actively *manage* candidates (submit,
   move stages) for referred clients?
