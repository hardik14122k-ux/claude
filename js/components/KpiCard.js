import { h } from '../ui.js';

export function KpiCard({ label, value, sub = '' }) {
  return h('div', { class: 'card kpi' }, [
    h('div', { class: 'kpi-label' }, [label]),
    h('div', { class: 'kpi-value' }, [String(value ?? '—')]),
    sub ? h('div', { class: 'kpi-sub' }, [sub]) : null,
  ]);
}
