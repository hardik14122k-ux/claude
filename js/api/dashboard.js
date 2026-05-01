// Single-call dashboard payload. Falls back to client-side aggregation
// if the rpc_dashboard function isn't deployed yet.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj } from '../lib/mapper.js';
import { dashboardSnapshot } from '../services/analytics.js';

export async function getDashboardData() {
  // Preferred path: single Postgres function call.
  const { data, error } = await sb.rpc('rpc_dashboard');
  if (!error && data) {
    const [recentActivity, openVacancies] = await Promise.all([
      rowToObj(await unwrap(
        sb.from('activity_logs').select('*').order('created_at', { ascending: false }).limit(10),
        'Activity failed')),
      rowToObj(await unwrap(
        sb.from('vacancies').select('*').eq('status', 'open').order('created_at', { ascending: false }).limit(8),
        'Vacancies failed')),
    ]);
    return {
      ok: true,
      totals: data.totals,
      funnel: data.funnel,
      aging:  data.aging,
      vacancies: openVacancies,
      activity:  recentActivity,
    };
  }

  // Fallback: client-side aggregation (slower, more queries).
  const snap = await dashboardSnapshot();
  const active = snap.candidatesAll.filter(c => c.stage !== 'hired' && c.stage !== 'rejected');
  const hired  = snap.candidatesAll.filter(c => c.stage === 'hired');
  const employees = await unwrap(
    sb.from('employees').select('id', { count: 'exact', head: true }).eq('status', 'active'),
    'Employee count failed');
  return {
    ok: true,
    totals: {
      employees: employees?.length ?? 0,
      active_candidates: active.length,
      open_vacancies: snap.vacancies.length,
      hired_this_month: hired.filter(c => sameMonth(c.updatedAt)).length,
      avg_time_to_hire: snap.timeToHireDays,
    },
    funnel: snap.funnel,
    aging:  snap.aging,
    vacancies: snap.vacancies,
    activity:  snap.activity,
  };
}

function sameMonth(iso) {
  if (!iso) return false;
  const a = new Date(iso), b = new Date();
  return a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear();
}
