import { h } from '../ui.js';

export function SkeletonLine({ width = '100%', big = false } = {}) {
  return h('div', { class: 'sk-line' + (big ? ' big' : ''), style: { width } });
}

export function SkeletonCard({ lines = 3 } = {}) {
  return h('div', { class: 'card kpi skeleton' }, [
    SkeletonLine({ width: '60%' }),
    SkeletonLine({ width: '40%', big: true }),
    ...Array.from({ length: lines - 2 }, () => SkeletonLine({ width: '80%' })),
  ]);
}

export function SkeletonGrid({ count = 5 } = {}) {
  return h('div', { class: 'grid cards' },
    Array.from({ length: count }, () => SkeletonCard()));
}
