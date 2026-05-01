// Dashboard — fetches its data from Supabase via the analytics service.
// Renders skeletons immediately and swaps in real content when ready.

import { h, relTime } from '../ui.js';
import { STAGES, stageLabel, dashboardSnapshot } from '../services/analytics.js';
import { daysBetween } from '../store.js';

export function Dashboard() {
  const root = h('div', { class: 'view-dashboard' });
  root.appendChild(skeletonGrid());
  load(root);
  return root;
}

async function load(root) {
  try {
    const snap = await dashboardSnapshot();
    root.innerHTML = '';
    root.appendChild(renderDashboard(snap));
  } catch (err) {
    root.innerHTML = '';
    root.appendChild(h('div', { class: 'empty' }, [
      'Could not load dashboard: ' + err.message,
      h('br'),
      h('span', { class: 'muted small' }, ['Check Supabase config in index.html.']),
    ]));
  }
}

function renderDashboard(snap) {
  const { funnel, tat, aging, timeToHireDays, vacancies, candidatesAll, activity } = snap;

  const active = candidatesAll.filter(c => c.stage !== 'hired' && c.stage !== 'rejected');
  const hired  = candidatesAll.filter(c => c.stage === 'hired');
  const pendingOffers = candidatesAll.filter(c => c.stage === 'offer');
  const hiredThisMonth = hired.filter(c => sameMonth(c.updatedAt, new Date())).length;
  const funnelMax = Math.max(1, ...Object.values(funnel));

  return h('div', {}, [
    h('div', { class: 'grid cards' }, [
      kpi('Open Vacancies',     vacancies.length, `${sum(vacancies, v => v.openings || 1)} openings total`),
      kpi('Active Candidates',  active.length,    `${candidatesAll.length} total`),
      kpi('Offers Pending',     pendingOffers.length, 'Awaiting response'),
      kpi('Hired · this month', hiredThisMonth,   `${hired.length} all-time`),
      kpi('Avg. Time-to-Hire',  timeToHireDays ? `${timeToHireDays}d` : '—', 'From sourced → hired'),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [
          h('h2', {}, ['Hiring Funnel']),
          h('span', { class: 'muted' }, [`${candidatesAll.length} candidates tracked`]),
        ]),
        h('div', { class: 'funnel' }, STAGES.filter(s => s.id !== 'rejected').map(stage => {
          const count = funnel[stage.id] || 0;
          const pct = Math.round((count / funnelMax) * 100);
          return h('div', { class: 'funnel-row' }, [
            h('div', {}, [stage.label]),
            h('div', { class: 'funnel-bar' }, [h('div', { class: 'funnel-fill', style: { width: pct + '%' } })]),
            h('div', { style: { textAlign: 'right', fontVariantNumeric: 'tabular-nums' } }, [String(count)]),
          ]);
        })),
      ]),

      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['TAT Aging — active pipeline'])]),
        h('div', { class: 'aging' }, [
          agingTile('≤ 3d',    aging['<=3'],   'green'),
          agingTile('4–7d',    aging['4-7'],   'green'),
          agingTile('8–14d',   aging['8-14'],  'amber'),
          agingTile('15–30d',  aging['15-30'], 'amber'),
          agingTile('> 30d',   aging['>30'],   'red'),
        ]),
        h('div', { class: 'sep' }),
        h('div', {}, [h('h2', { class: 'sublabel' }, ['Avg. days in stage'])]),
        h('div', {}, STAGES.filter(x => x.sla > 0).map(st => {
          const v = tat[st.id] || 0;
          return h('div', { class: 'row-flex', style: { padding: '6px 0', borderBottom: '1px solid var(--border)' } }, [
            h('div', { style: { width: '120px' } }, [st.label]),
            h('div', { class: 'spacer' }),
            h('span', { class: `chip ${v > st.sla ? 'warn' : 'ok'}` }, [
              `${v}d`, h('span', { class: 'muted', style: { marginLeft: '6px' } }, [`SLA ${st.sla}d`]),
            ]),
          ]);
        })),
      ]),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Open Vacancies'])]),
        vacancies.length
          ? h('table', { class: 'table' }, [
              h('thead', {}, [h('tr', {}, [h('th', {}, ['Role']), h('th', {}, ['Dept']), h('th', {}, ['Hiring Mgr']), h('th', {}, ['Openings']), h('th', {}, ['Priority']), h('th', {}, ['Age'])])]),
              h('tbody', {}, vacancies.slice(0, 8).map(v => h('tr', {}, [
                h('td', {}, [h('div', { style: { fontWeight: 600 } }, [v.title]), h('div', { class: 'muted', style: { fontSize: '11px' } }, [v.location])]),
                h('td', {}, [v.department]),
                h('td', {}, [v.hiringManager || '—']),
                h('td', {}, [String(v.openings || 1)]),
                h('td', {}, [h('span', { class: `chip ${priorityChip(v.priority)}` }, [titleCase(v.priority || 'medium')])]),
                h('td', {}, [`${daysBetween(v.createdAt)}d`]),
              ]))),
            ])
          : h('div', { class: 'empty' }, ['No open vacancies — create one to get started.']),
      ]),

      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Recent activity'])]),
        activity.length
          ? h('div', {}, activity.slice(0, 10).map(a => h('div', { class: 'row-flex', style: { padding: '6px 0', borderBottom: '1px solid var(--border)' } }, [
              h('span', { class: `dot ${dotForActivity(a.type)}` }),
              h('div', { style: { flex: 1 } }, [a.message]),
              h('span', { class: 'muted', style: { fontSize: '11px' } }, [relTime(a.createdAt)]),
            ])))
          : h('div', { class: 'empty' }, ['No activity yet.']),
      ]),
    ]),
  ]);
}

function kpi(label, value, sub) {
  return h('div', { class: 'card kpi' }, [
    h('div', { class: 'kpi-label' }, [label]),
    h('div', { class: 'kpi-value' }, [String(value)]),
    h('div', { class: 'kpi-sub' }, [sub]),
  ]);
}

function agingTile(label, n, tone) {
  return h('div', { class: `bucket ${tone}` }, [
    h('div', { class: 'num' }, [String(n)]),
    h('div', { class: 'lbl' }, [label]),
  ]);
}

function skeletonGrid() {
  const card = () => h('div', { class: 'card kpi skeleton' }, [
    h('div', { class: 'sk-line', style: { width: '60%' } }),
    h('div', { class: 'sk-line big', style: { width: '40%', marginTop: '10px' } }),
    h('div', { class: 'sk-line', style: { width: '80%', marginTop: '8px' } }),
  ]);
  return h('div', { class: 'grid cards' }, [card(), card(), card(), card(), card()]);
}

function priorityChip(p) {
  const v = (p || '').toLowerCase();
  if (v === 'high') return 'bad';
  if (v === 'low')  return 'ok';
  return 'warn';
}
function dotForActivity(type) {
  if (!type) return '';
  if (type.startsWith('vacancy'))   return 'ok';
  if (type.startsWith('interview')) return 'warn';
  if (type.includes('rejected'))    return 'bad';
  return 'ok';
}
function sum(arr, f) { return arr.reduce((a, x) => a + (f(x) || 0), 0); }
function sameMonth(iso, d) {
  if (!iso) return false;
  const a = new Date(iso);
  return a.getMonth() === d.getMonth() && a.getFullYear() === d.getFullYear();
}
function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
