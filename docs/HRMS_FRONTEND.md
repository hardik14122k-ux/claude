# TalentTrack HRMS — Frontend Architecture

The JS SPA is now a thin Supabase client. All state, validation,
and business rules live in the database; the frontend renders and dispatches.

## Folder layout

```
.
├── index.html                # entry; loads pdf.js + supabase-js + js/app.js
├── styles.css
├── js/
│   ├── config.js             # reads window.SUPABASE_URL / window.SUPABASE_ANON
│   ├── app.js                # router + global wiring
│   ├── store.js              # async cache + pub/sub (no localStorage)
│   ├── seed.js               # demo data via Supabase
│   ├── cv-parser.js          # PDF → structured candidate (unchanged)
│   ├── ui.js                 # h(), modal, toast, fmt helpers
│   ├── lib/
│   │   ├── supabase.js       # single client instance
│   │   ├── errors.js         # HrmsError + unwrap()
│   │   ├── validators.js     # input validation
│   │   └── mapper.js         # snake_case ↔ camelCase
│   ├── services/             # one module per domain
│   │   ├── vacancies.js
│   │   ├── candidates.js
│   │   ├── interviews.js
│   │   ├── activity.js
│   │   ├── employees.js
│   │   ├── attendance.js
│   │   ├── payroll.js
│   │   └── analytics.js      # funnel / TAT / aging / time-to-hire
│   └── views/
│       ├── dashboard.js      # async, with skeleton state (reference impl)
│       └── ...               # the rest still work — switch them off store.js
└── supabase/
    └── schema.sql            # full schema, triggers, RLS, RPCs
```

## How requests flow

```
View ──► Service ──► Supabase (PostgREST/RPC) ──► Postgres
                                  │
                                  └─► Triggers run:
                                      • update history
                                      • create employee on hire
                                      • write activity_logs
```

## Setup (one-time)

1. Create a project at https://supabase.com.
2. In the SQL editor, paste & run `supabase/schema.sql`.
3. Copy the project URL and `anon` public key from
   *Settings → API*.
4. Edit `index.html`:
   ```html
   window.SUPABASE_URL  = 'https://YOUR-PROJECT.supabase.co';
   window.SUPABASE_ANON = 'eyJhbGciOi…';
   ```
5. Serve the SPA over any static host (Netlify, Vercel, S3, `python3 -m http.server`, etc.).
6. Click **Load demo data** in the sidebar. Triggers will populate
   `activity_logs` and create one `employees` row for the
   candidate seeded as `hired`.

## Service-layer API (most-used)

```js
// Vacancies
import { listVacancies, createVacancy, updateVacancy, deleteVacancy } from './services/vacancies.js';

// Candidates
import { listCandidates, createCandidate, moveCandidate, deleteCandidate } from './services/candidates.js';
// moveCandidate(id, 'hired') → DB trigger creates an employees row automatically.

// Interviews
import { listInterviews, scheduleInterview, updateInterview } from './services/interviews.js';

// Employees
import { listEmployees, createEmployee, setSalary } from './services/employees.js';

// Attendance
import { markAttendance, checkIn, checkOut, getAttendanceByEmployee, monthlySummary } from './services/attendance.js';

// Payroll
import { generatePayroll, generateMonthlyPayroll, listPayrollByPeriod, calculatePayslip } from './services/payroll.js';

// Analytics (used by Dashboard)
import { dashboardSnapshot, funnelCounts, avgTatByStage, agingBuckets } from './services/analytics.js';
```

## Example calls

```js
// Add a vacancy
await createVacancy({ title: 'Backend Engineer', skills: ['Python','AWS'], priority: 'high' });

// Move a candidate to "hired" — triggers automatic employee creation
await moveCandidate(candidateId, 'hired');

// Mark attendance
await markAttendance({ employeeId, date: '2026-05-01', status: 'present', checkIn: new Date().toISOString() });

// Generate this month's payroll for everyone active
await generateMonthlyPayroll({ month: 5, year: 2026, workingDays: 22 });
```

## Migrating other views

The old views (`vacancies.js`, `candidates.js`, `pipeline.js`,
`interviews.js`, `reports.js`, `settings.js`) still read from
`store.js` — but `store.getState()` now returns the in-memory
cache. Each view should:

1. Call `await store.refresh('candidates')` (or whichever channel) on mount.
2. Show a skeleton/loading state in the meantime (see `dashboard.js`).
3. Subscribe to the channel and re-render on changes:
   ```js
   subscribe('candidates', () => render());
   ```
4. Replace any direct mutations with the corresponding service calls.

## Production hardening checklist

- Replace the catch-all `auth_all` RLS policy with per-org / per-role rules.
- Set up Supabase Auth (email/password or OAuth) and add a sign-in screen.
- Enable Supabase Storage for raw CV files instead of storing PDFs in `raw_cv`.
- Add a Postgres function to bulk-recompute analytics nightly if data grows beyond 100k candidates.
- Wrap `generateMonthlyPayroll` in a server-side Edge Function so calculation
  runs on the server even if the user closes the tab.
- Configure point-in-time recovery in Supabase project settings.
