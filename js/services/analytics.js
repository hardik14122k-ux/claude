// Analytics — funnel counts, TAT, aging, time-to-hire.
// Heavy aggregations live as Postgres functions (rpc_*); the client just calls them.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj } from '../lib/mapper.js';

export const STAGES = [
  { id: 'sourced',   label: 'Sourced',   sla: 3  },
  { id: 'screening', label: 'Screening', sla: 5  },
  { id: 'interview', label: 'Interview', sla: 10 },
  { id: 'offer',     label: 'Offer',     sla: 7  },
  { id: 'hired',     label: 'Hired',     sla: 0  },
  { id: 'rejected',  label: 'Rejected',  sla: 0  },
];

export function stageLabel(id) {
  return STAGES.find(s => s.id === id)?.label || id;
}

export async function funnelCounts() {
  const rows = await unwrap(sb.rpc('rpc_funnel_counts'), 'Funnel query failed');
  const out = Object.fromEntries(STAGES.map(s => [s.id, 0]));
  rows.forEach(r => { out[r.stage] = Number(r.count) || 0; });
  return out;
}

export async function avgTatByStage() {
  const rows = await unwrap(sb.rpc('rpc_avg_tat_by_stage'), 'TAT query failed');
  const out = Object.fromEntries(STAGES.map(s => [s.id, 0]));
  rows.forEach(r => { out[r.stage] = Number(r.avg_days) || 0; });
  return out;
}

export async function agingBuckets() {
  const rows = await unwrap(sb.rpc('rpc_aging_buckets'), 'Aging query failed');
  const out = { '<=3': 0, '4-7': 0, '8-14': 0, '15-30': 0, '>30': 0 };
  rows.forEach(r => { out[r.bucket] = Number(r.count) || 0; });
  return out;
}

// Average days from first stage entry to `hired`.
export async function avgTimeToHireDays() {
  const rows = rowToObj(await unwrap(
    sb.from('candidates').select('history,created_at,updated_at').eq('stage', 'hired'),
    'Failed to compute time-to-hire'));
  if (!rows.length) return 0;
  const days = rows.map(c => {
    const h = c.history || [];
    const first = new Date(h[0]?.at || c.createdAt).getTime();
    const last  = new Date(h[h.length - 1]?.at || c.updatedAt).getTime();
    return (last - first) / 86400000;
  });
  return Math.round(days.reduce((a, x) => a + x, 0) / days.length);
}

// Snapshot for the dashboard: one round-trip-friendly bundle.
export async function dashboardSnapshot() {
  const [funnel, tat, aging, tth, vacancies, candidatesAll, activity] = await Promise.all([
    funnelCounts(),
    avgTatByStage(),
    agingBuckets(),
    avgTimeToHireDays(),
    rowToObj(await unwrap(sb.from('vacancies').select('*').eq('status', 'open').order('created_at', { ascending: false }), 'Vacancies failed')),
    rowToObj(await unwrap(sb.from('candidates').select('id,stage,updated_at'), 'Candidates failed')),
    rowToObj(await unwrap(sb.from('activity_logs').select('*').order('created_at', { ascending: false }).limit(10), 'Activity failed')),
  ]);
  return { funnel, tat, aging, timeToHireDays: tth, vacancies, candidatesAll, activity };
}
