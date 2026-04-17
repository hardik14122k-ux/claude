import { h } from '../ui.js';
import { getState, STAGES, stageLabel, averageTATByStage, agingBuckets, daysBetween } from '../store.js';
import { relTime } from '../ui.js';

export function Dashboard() {
  const s = getState();
  const active = s.candidates.filter(c => c.stage !== 'hired' && c.stage !== 'rejected');
  const hired = s.candidates.filter(c => c.stage === 'hired');
  const openVacancies = s.vacancies.filter(v => v.status === 'Open' || !v.status);
  const pendingOffers = s.candidates.filter(c => c.stage === 'offer');
  const tat = averageTATByStage();
  const avgTimeToHire = avgTimeToHireDays(hired);
  const hiredThisMonth = hired.filter(c => sameMonth(c.updatedAt, new Date())).length;

  const funnelCounts = Object.fromEntries(STAGES.map(s => [s.id, 0]));
  s.candidates.forEach(c => { funnelCounts[c.stage] = (funnelCounts[c.stage] || 0) + 1; });
  const funnelMax = Math.max(1, ...Object.values(funnelCounts));

  const aging = agingBuckets();

  return h('div', {}, [
    h('div', { class: 'grid cards' }, [
      kpi('Open Vacancies', openVacancies.length, `${sum(openVacancies, v => v.openings || 1)} openings total`),
      kpi('Active Candidates', active.length, `${s.candidates.length} total`),
      kpi('Offers Pending', pendingOffers.length, 'Awaiting response'),
      kpi('Hired · this month', hiredThisMonth, `${hired.length} all-time`),
      kpi('Avg. Time-to-Hire', avgTimeToHire ? `${avgTimeToHire}d` : '—', 'From sourced → hired'),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [
          h('h2', {}, ['Hiring Funnel']),
          h('span', { class: 'muted' }, [`${s.candidates.length} candidates tracked`])
        ]),
        h('div', { class: 'funnel' }, STAGES.filter(s => s.id !== 'rejected').map(stage => {
          const count = funnelCounts[stage.id] || 0;
          const pct = Math.round((count / funnelMax) * 100);
          return h('div', { class: 'funnel-row' }, [
            h('div', {}, [stage.label]),
            h('div', { class: 'funnel-bar' }, [h('div', { class: 'funnel-fill', style: { width: pct + '%' } })]),
            h('div', { style: { textAlign: 'right', fontVariantNumeric: 'tabular-nums' } }, [String(count)])
          ]);
        }))
      ]),

      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['TAT Aging — active pipeline'])]),
        h('div', { class: 'aging' }, [
          agingTile('≤ 3d', aging['<=3'], 'green'),
          agingTile('4–7d', aging['4-7'], 'green'),
          agingTile('8–14d', aging['8-14'], 'amber'),
          agingTile('15–30d', aging['15-30'], 'amber'),
          agingTile('> 30d', aging['>30'], 'red'),
        ]),
        h('div', { class: 'sep' }),
        h('div', {}, [h('h2', { style: { fontSize: '13px', margin: '4px 0 10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.08em' } }, ['Avg. days in stage'])]),
        h('div', {}, STAGES.filter(x => x.sla > 0).map(st =>
          h('div', { class: 'row-flex', style: { padding: '6px 0', borderBottom: '1px solid var(--border)' } }, [
            h('div', { style: { width: '120px' } }, [st.label]),
            h('div', { class: 'spacer' }),
            h('span', { class: `chip ${tat[st.id] > st.sla ? 'warn' : 'ok'}` }, [
              `${tat[st.id] || 0}d`, h('span', { class: 'muted', style: { marginLeft: '6px' } }, [`SLA ${st.sla}d`])
            ])
          ])
        ))
      ]),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Open Vacancies'])]),
        openVacancies.length
          ? h('table', { class: 'table' }, [
              h('thead', {}, [h('tr', {}, [h('th', {}, ['Role']), h('th', {}, ['Dept']), h('th', {}, ['Hiring Mgr']), h('th', {}, ['Openings']), h('th', {}, ['Priority']), h('th', {}, ['Age'])])]),
              h('tbody', {}, openVacancies.slice(0, 8).map(v => h('tr', {}, [
                h('td', {}, [h('div', { style: { fontWeight: 600 } }, [v.title]), h('div', { class: 'muted', style: { fontSize: '11px' } }, [v.location])]),
                h('td', {}, [v.department]),
                h('td', {}, [v.hiringManager || '—']),
                h('td', {}, [String(v.openings || 1)]),
                h('td', {}, [h('span', { class: `chip ${priorityChip(v.priority)}` }, [v.priority || 'Medium'])]),
                h('td', {}, [`${daysBetween(v.createdAt)}d`])
              ])))
            ])
          : h('div', { class: 'empty' }, ['No open vacancies — create one to get started.'])
      ]),

      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Recent activity'])]),
        s.activity.length
          ? h('div', {}, s.activity.slice(0, 10).map(a => h('div', { class: 'row-flex', style: { padding: '6px 0', borderBottom: '1px solid var(--border)' } }, [
              h('span', { class: `dot ${dotForActivity(a.type)}` }),
              h('div', { style: { flex: 1 } }, [a.message]),
              h('span', { class: 'muted', style: { fontSize: '11px' } }, [relTime(a.ts)])
            ])))
          : h('div', { class: 'empty' }, ['No activity yet.'])
      ])
    ])
  ]);
}

function kpi(label, value, sub) {
  return h('div', { class: 'card kpi' }, [
    h('div', { class: 'kpi-label' }, [label]),
    h('div', { class: 'kpi-value' }, [String(value)]),
    h('div', { class: 'kpi-sub' }, [sub])
  ]);
}

function agingTile(label, n, tone) {
  return h('div', { class: `bucket ${tone}` }, [
    h('div', { class: 'num' }, [String(n)]),
    h('div', { class: 'lbl' }, [label])
  ]);
}

function priorityChip(p) {
  if (p === 'High') return 'bad';
  if (p === 'Low') return 'ok';
  return 'warn';
}

function dotForActivity(type) {
  if (!type) return '';
  if (type.startsWith('vacancy')) return 'ok';
  if (type.startsWith('interview')) return 'warn';
  if (type.includes('rejected')) return 'bad';
  return 'ok';
}

function sum(arr, f) { return arr.reduce((a, x) => a + (f(x) || 0), 0); }

function sameMonth(iso, d) {
  if (!iso) return false;
  const a = new Date(iso);
  return a.getMonth() === d.getMonth() && a.getFullYear() === d.getFullYear();
}

function avgTimeToHireDays(hired) {
  if (!hired.length) return 0;
  const totals = hired.map(c => {
    const first = c.history?.[0]?.at || c.createdAt;
    const last = c.history?.[c.history.length - 1]?.at || c.updatedAt;
    return (new Date(last) - new Date(first)) / 86400000;
  });
  return Math.round(totals.reduce((a, x) => a + x, 0) / totals.length);
}
