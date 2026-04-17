import { h } from '../ui.js';
import { getState, STAGES, averageTATByStage, daysBetween } from '../store.js';

export function Reports() {
  const s = getState();
  const tat = averageTATByStage();
  const bySource = groupCount(s.candidates, c => c.source || 'Unknown');
  const byStage = groupCount(s.candidates, c => c.stage);
  const byVacancy = s.vacancies.map(v => ({
    v,
    total: s.candidates.filter(c => c.vacancyId === v.id).length,
    active: s.candidates.filter(c => c.vacancyId === v.id && c.stage !== 'hired' && c.stage !== 'rejected').length,
    hired: s.candidates.filter(c => c.vacancyId === v.id && c.stage === 'hired').length,
    age: daysBetween(v.createdAt),
  }));

  const rejects = s.candidates.filter(c => c.stage === 'rejected');
  const hired = s.candidates.filter(c => c.stage === 'hired');
  const conversionScreenToOffer = pct(
    s.candidates.filter(c => ['offer','hired'].includes(c.stage)).length,
    s.candidates.filter(c => c.history?.some(h => h.stage === 'screening')).length
  );

  return h('div', {}, [
    h('div', { class: 'section-title' }, [h('h2', {}, ['Reports'])]),

    h('div', { class: 'grid cards' }, [
      kpi('Total candidates', s.candidates.length),
      kpi('Hired', hired.length),
      kpi('Rejected', rejects.length),
      kpi('Screen → Offer', `${conversionScreenToOffer}%`),
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Average days in stage'])]),
        barList(STAGES.filter(s => s.sla > 0).map(st => ({
          label: st.label,
          value: tat[st.id] || 0,
          sla: st.sla,
        })))
      ]),
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Source breakdown'])]),
        barList(bySource.map(([label, value]) => ({ label, value })))
      ])
    ]),

    h('div', { class: 'two-col', style: { marginTop: '16px' } }, [
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Stage distribution'])]),
        barList(STAGES.map(st => ({ label: st.label, value: byStage.find(x => x[0] === st.id)?.[1] || 0 })))
      ]),
      h('div', { class: 'card' }, [
        h('div', { class: 'section-title' }, [h('h2', {}, ['Per-role snapshot'])]),
        byVacancy.length
          ? h('table', { class: 'table' }, [
              h('thead', {}, [h('tr', {}, [h('th', {}, ['Role']), h('th', {}, ['Total']), h('th', {}, ['Active']), h('th', {}, ['Hired']), h('th', {}, ['Age'])])]),
              h('tbody', {}, byVacancy.map(r => h('tr', {}, [
                h('td', {}, [r.v.title]),
                h('td', {}, [String(r.total)]),
                h('td', {}, [String(r.active)]),
                h('td', {}, [String(r.hired)]),
                h('td', {}, [`${r.age}d`])
              ])))
            ])
          : h('div', { class: 'empty' }, ['No vacancies yet.'])
      ])
    ])
  ]);
}

function barList(rows) {
  const max = Math.max(1, ...rows.map(r => r.value));
  return h('div', {}, rows.map(r => h('div', { class: 'funnel-row', style: { margin: '6px 0' } }, [
    h('div', {}, [r.label]),
    h('div', { class: 'funnel-bar' }, [h('div', { class: 'funnel-fill', style: { width: Math.round((r.value / max) * 100) + '%' } })]),
    h('div', { style: { textAlign: 'right', fontVariantNumeric: 'tabular-nums' } }, [
      String(r.value),
      r.sla != null ? h('span', { class: 'muted', style: { fontSize: '11px', marginLeft: '4px' } }, [`/${r.sla}`]) : null
    ])
  ])));
}

function groupCount(arr, fn) {
  const m = new Map();
  arr.forEach(x => { const k = fn(x); m.set(k, (m.get(k) || 0) + 1); });
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

function pct(n, d) { if (!d) return 0; return Math.round((n / d) * 100); }

function kpi(label, value) {
  return h('div', { class: 'card kpi' }, [
    h('div', { class: 'kpi-label' }, [label]),
    h('div', { class: 'kpi-value' }, [String(value)])
  ]);
}
