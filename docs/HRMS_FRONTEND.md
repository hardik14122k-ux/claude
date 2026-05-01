# TalentTrack HRMS — Frontend Architecture

Frontend talks to Supabase only. State + RBAC + multi-tenant isolation
live in the database. The browser does rendering and dispatch.

## Folder layout

```
.
├── index.html
├── styles.css
├── js/
│   ├── config.js                 # window.SUPABASE_URL / SUPABASE_ANON
│   ├── app.js                    # router + global wiring
│   ├── store.js                  # async cache + pub/sub
│   ├── seed.js                   # demo data via Supabase
│   ├── cv-parser.js              # PDF → candidate
│   ├── ui.js                     # h(), modal, toast
│   ├── lib/                      # primitives
│   │   ├── supabase.js
│   │   ├── auth.js               # signIn/signUp/signOut + currentUser
│   │   ├── errors.js             # HrmsError + unwrap()
│   │   ├── validators.js
│   │   └── mapper.js             # snake ↔ camel
│   ├── services/                 # one module per domain (CRUD)
│   │   ├── vacancies.js
│   │   ├── candidates.js
│   │   ├── interviews.js
│   │   ├── activity.js
│   │   ├── employees.js
│   │   ├── attendance.js         # markAttendance / deriveStatus
│   │   ├── payroll.js            # calculatePayslip / generatePayroll
│   │   ├── analytics.js
│   │   ├── leaves.js             # apply / approve / balances
│   │   └── users.js              # profile + role
│   ├── api/                      # high-level orchestration
│   │   ├── dashboard.js          # getDashboardData
│   │   └── index.js              # barrel export
│   ├── hooks/
│   │   ├── useResource.js        # async resource w/ loading + error
│   │   └── useAuth.js
│   ├── components/
│   │   ├── KpiCard.js
│   │   ├── Skeleton.js
│   │   └── EmptyState.js
│   ├── utils/
│   │   ├── date.js               # YMD, fiscalYearStart, daysBetween
│   │   ├── format.js             # fmtDate, relTime, initials
│   │   └── money.js              # inr, inrPaise
│   └── views/
│       ├── dashboard.js          # reference async view
│       └── ...
└── supabase/
    ├── schema.sql                # base schema, triggers, analytics RPCs
    └── schema_v2.sql             # multi-company, users/roles, leaves, RLS
```

## Multi-company isolation

* Every domain table has `company_id uuid not null` referencing `companies(id)`.
* `users` row links `auth.uid()` to a company + role.
* `current_company_id()` reads the requester's company.
* Each table has RLS policy:
  ```sql
  using      (company_id = current_company_id())
  with check (company_id = current_company_id())
  ```
* On insert, a trigger auto-fills `company_id` so service code stays clean.

## Roles

`admin`, `hr`, `hiring_manager`, `viewer`. Use `requireRole('hr','admin')`
client-side for UX gating; the database enforces the same via RLS + the
`has_role()` helper.

## Setup (one-time)

1. Create a Supabase project.
2. SQL editor → run `supabase/schema.sql` then `supabase/schema_v2.sql`.
3. Settings → API → copy URL and anon key into `index.html`:
   ```js
   window.SUPABASE_URL  = 'https://YOUR-PROJECT.supabase.co';
   window.SUPABASE_ANON = 'eyJhbGciOi…';
   ```
4. Auth → enable Email auth.
5. Create the first user manually:
   ```sql
   -- after the user signs up via Supabase Auth UI:
   insert into users (id, email, full_name, company_id, role)
   values ('<auth.users.id>', 'admin@yourco.com', 'Admin',
           '00000000-0000-0000-0000-000000000001', 'admin');
   ```
6. Serve `index.html` via any static host.

## API surface

```js
import {
  // dashboard
  getDashboardData,
  // recruitment
  createCandidate, moveCandidate, listCandidates,
  createVacancy,   listVacancies,
  scheduleInterview,
  // HR core
  getEmployees, createEmployee, setSalary,
  markAttendance, checkIn, checkOut, monthlySummary,
  generatePayroll, generateMonthlyPayroll, calculatePayslip,
  // leaves
  applyLeave, decideRequest, listLeaveRequests, listLeaveTypes, getLeaveBalances,
  // users
  listUsers, createUserProfile, updateUser, deactivateUser,
  // auth
  signIn, signUp, signOut, currentUser, requireRole,
} from './api/index.js';
```

## Example calls

```js
// Sign in (sets company + role for the rest of the session via RLS)
await signIn('admin@yourco.com', 'secret');

// Dashboard
const dash = await getDashboardData();
// → { totals, funnel, aging, vacancies, activity }

// Recruitment → HR handoff (DB trigger creates the employee)
await moveCandidate(candidateId, 'hired');

// Attendance with auto-status derivation
await markAttendance({
  employeeId,
  date: '2026-05-01',
  checkIn:  '2026-05-01T09:15:00Z',
  checkOut: '2026-05-01T18:30:00Z',
}); // → status: 'present' (worked ≥ 8h)

// Apply for leave
await applyLeave({
  employeeId, leaveTypeId,
  startDate: '2026-05-15', endDate: '2026-05-16',
  reason: 'Personal',
});

// Approve (DB trigger deducts from balance)
await decideRequest(requestId, { approve: true, approverId: currentUser().id });

// Generate this month's payroll for everyone active
await generateMonthlyPayroll({ month: 5, year: 2026, workingDays: 22 });
```

## useResource pattern

```js
import { useResource } from './hooks/useResource.js';
import { listLeaveRequests } from './api/index.js';

const r = useResource(listLeaveRequests);
r.subscribe(({ data, loading, error }) => {
  if (loading) return root.replaceChildren(SkeletonGrid());
  if (error)   return root.replaceChildren(ErrorState({ message: error.message, onRetry: r.reload }));
  root.replaceChildren(renderList(data));
});
r.load({ status: 'pending' });
```

## Payroll math (Indian)

Implemented in `services/payroll.js` → `calculatePayslip()`:

| Component | Formula |
|---|---|
| Basic       | `basicMonthly × (paidDays / workingDays)` |
| HRA         | `hraMonthly × (paidDays / workingDays)` |
| Allowances  | `allowancesMonthly × (paidDays / workingDays)` |
| Gross       | sum of above |
| **PF (employee)** | `min(basic, 15000) × 12%` if `pf_applicable` |
| **ESI (employee)** | `gross × 0.75%` if `esi_applicable` AND `gross ≤ 21000` |
| PT          | flat ₹200 if gross > 0 (state-aware override per emp in production) |
| LOP deduction | `(monthlyGross / workingDays) × lopDays` |
| **Net Pay** | `gross − (PF + ESI + PT + TDS + LOP)` |

`generatePayroll(employeeId, { month, year, workingDays })` reads
attendance for the month, derives `paidDays = workingDays - absent`,
and writes a row in `payroll` (status `processed`). The DB stores
`gross_earnings`, `total_deductions`, and `net_pay` as generated columns.

## Attendance status

`deriveStatus({ status, checkIn, checkOut })`:

* manual `leave` / `holiday` / `weekend` → respected
* no `check_in` → **absent**
* `check_in` only → **present** (still on the clock)
* hours ≥ 8 → **present**
* hours ≥ 4 → **half_day**
* otherwise → **half_day** (any clocked-in time counts as half day)

## Production hardening checklist

* Replace the seed admin in step 5 with a proper sign-up flow.
* Tighten RLS for `payroll` (only `hr`/`admin` should see other employees).
* Move `generateMonthlyPayroll` into a Supabase Edge Function so a
  closed tab doesn't abort it.
* Configure Storage buckets for raw CV PDFs instead of `raw_cv` text.
* Enable point-in-time recovery in project settings.
* Set up a `pg_cron` job for monthly leave accrual.
