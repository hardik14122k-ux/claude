// Dashboard wired to api.getDashboardData() via useResource hook.
// Renders skeletons while loading, error state with retry on failure.

import { h } from '../ui.js';
import { relTime } from '../utils/format.js';
import { daysBetween } from '../utils/date.js';
import { STAGES } from '../services/analytics.js';
import { getDashboardData } from '../api/dashboard.js';
import { useResource } from '../hooks/useResource.js';
import { KpiCard } from '../components/KpiCard.js';
import { SkeletonGrid } from '../components/Skeleton.js';
import { EmptyState, ErrorState } from '../components/EmptyState.js';

export function Dashboard() {
  const root = h('div', { class: 'view-dashboard' });
  const r = useResource(getDashboardData);

  r.subscribe(({ data, loading, error }) => {
    root.innerHTML = '';
    if (loading)        return root.appendChild(SkeletonGrid({ count: 5 }));
    if (error)          return root.appendChild(ErrorState({ message: error.message, onRetry: () => r.reload() }));
    if (data?.ok)       return root.appendChild(renderDashboard(data));
    root.appendChild(EmptyState({ title: 'No data yet' }));
  });

  r.load();
  return root;
}

function renderDashboard({ totals, funnel, aging, vacancies, activity }) {
  const funnelMax = Math.max(1, ...Object.values(funnel || {}));

  return h('div', {}, [
    h('div', { class: 'grid cards' }, [
      KpiCard({ label: 'Total Employees',    value: totals.employees,         sub: 'Active headcount' }),
      KpiCard({ label: 'Active Candidates',  value: totals.active_candidates, sub: 'In pipeline' }),
      KpiCard({ label: 'Open Vacancies',     value: totals.open_vacancies,    sub: 'Currently hiring' }),
      KpiCard({ label: 'Hired · this month', value: totals.hired_this_month,  sub: 'Net new hires' }),
      KpiCard({ label: 'Avg. Time-to-Hire',  value: totals.avg_time_to_hire ? `${totals.avg_time_to_hire}d` : '—', sub: 'Sourced → hired' }),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [
          h('h2', {}, ['Hiring Funnel']),
          h('span', { class: 'muted' }, [`${sumValues(funnel)} candidates tracked`]),
        ]),
        h('div', { class: 'funnel' }, STAGES.filter(s => s.id !== 'rejected').map(stage => {
          const count = funnel?.[stage.id] || 0;
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
          agingTile('≤ 3d',   aging?.['<=3']   || 0, 'green'),
          agingTile('4–7d',   aging?.['4-7']   || 0, 'green'),
          agingTile('8–14d',  aging?.['8-14']  || 0, 'amber'),
          agingTile('15–30d', aging?.['15-30'] || 0, 'amber'),
          agingTile('> 30d',  aging?.['>30']   || 0, 'red'),
        ]),
      ]),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Open Vacancies'])]),
        vacancies?.length
          ? h('table', { class: 'table' }, [
              h('thead', {}, [h('tr', {}, [h('th', {}, ['Role']), h('th', {}, ['Dept']), h('th', {}, ['Hiring Mgr']), h('th', {}, ['Openings']), h('th', {}, ['Priority']), h('th', {}, ['Age'])])]),
              h('tbody', {}, vacancies.slice(0, 8).map(v => h('tr', {}, [
                h('td', {}, [h('div', { style: { fontWeight: 600 } }, [v.title]), h('div', { class: 'muted', style: { fontSize: '11px' } }, [v.location])]),
                h('td', {}, [v.department]),
                h('td', {}, [v.hiring_manager || v.hiringManager || '—']),
                h('td', {}, [String(v.openings || 1)]),
                h('td', {}, [h('span', { class: `chip ${priorityChip(v.priority)}` }, [titleCase(v.priority || 'medium')])]),
                h('td', {}, [`${daysBetween(v.created_at || v.createdAt)}d`]),
              ]))),
            ])
          : EmptyState({ title: 'No open vacancies', hint: 'Create one to start sourcing.' }),
      ]),

      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Recent activity'])]),
        activity?.length
          ? h('div', {}, activity.slice(0, 10).map(a => h('div', { class: 'row-flex', style: { padding: '6px 0', borderBottom: '1px solid var(--border)' } }, [
              h('span', { class: `dot ${dotForActivity(a.type)}` }),
              h('div', { style: { flex: 1 } }, [a.message]),
              h('span', { class: 'muted', style: { fontSize: '11px' } }, [relTime(a.created_at || a.createdAt)]),
            ])))
          : EmptyState({ title: 'No activity yet' }),
      ]),
    ]),
  ]);
}

function agingTile(label, n, tone) {
  return h('div', { class: `bucket ${tone}` }, [
    h('div', { class: 'num' }, [String(n)]),
    h('div', { class: 'lbl' }, [label]),
  ]);
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
function sumValues(obj) { return Object.values(obj || {}).reduce((a, x) => a + (Number(x) || 0), 0); }
function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
