// Attendance: mark, list, summarize.
// `working_hours` is computed by the DB as a STORED generated column.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { validateAttendance } from '../lib/validators.js';

const TABLE = 'attendance';

const FULL_DAY_HOURS = 8;
const HALF_DAY_HOURS = 4;
const MANUAL_STATUSES = new Set(['leave', 'holiday', 'weekend']);

// Auto-derive Present/Half-day/Absent from check_in/check_out.
// Manual statuses (leave/holiday/weekend) win over the derivation.
export function deriveStatus({ status, checkIn, checkOut }) {
  if (status && MANUAL_STATUSES.has(status)) return status;
  if (!checkIn) return 'absent';
  if (!checkOut) return 'present'; // checked in but not yet out
  const hrs = (new Date(checkOut) - new Date(checkIn)) / 3_600_000;
  if (hrs >= FULL_DAY_HOURS) return 'present';
  if (hrs >= HALF_DAY_HOURS) return 'half_day';
  return 'half_day';
}

export async function markAttendance({ employeeId, date, status, checkIn = null, checkOut = null, notes = null }) {
  const finalStatus = deriveStatus({ status, checkIn, checkOut });
  const payload = objToRow({
    employeeId,
    attendanceDate: date,
    status: finalStatus,
    checkIn: checkIn || null,
    checkOut: checkOut || null,
    notes,
  });
  validateAttendance(payload);
  const data = await unwrap(
    sb.from(TABLE).upsert(payload, { onConflict: 'employee_id,attendance_date' }).select().single(),
    'Failed to mark attendance');
  return rowToObj(data);
}

export async function checkIn(employeeId, at = new Date().toISOString()) {
  const date = at.slice(0, 10);
  return markAttendance({ employeeId, date, status: 'present', checkIn: at });
}

export async function checkOut(employeeId, at = new Date().toISOString()) {
  const date = at.slice(0, 10);
  // Update only check_out so check_in is preserved.
  const existing = await unwrap(
    sb.from(TABLE).select('*').eq('employee_id', employeeId).eq('attendance_date', date).maybeSingle(),
    'Failed to read attendance');
  if (!existing) return markAttendance({ employeeId, date, status: 'present', checkOut: at });
  const data = await unwrap(
    sb.from(TABLE).update({ check_out: at }).eq('id', existing.id).select().single(),
    'Failed to check out');
  return rowToObj(data);
}

export async function getAttendanceByEmployee(employeeId, { from, to } = {}) {
  let q = sb.from(TABLE).select('*').eq('employee_id', employeeId).order('attendance_date', { ascending: false });
  if (from) q = q.gte('attendance_date', from);
  if (to)   q = q.lte('attendance_date', to);
  return rowToObj(await unwrap(q, 'Failed to load attendance'));
}

// Roll up counts per status for an employee in a given month.
export async function monthlySummary(employeeId, year, month) {
  const start = `${year}-${String(month).padStart(2,'0')}-01`;
  const next  = new Date(year, month, 1).toISOString().slice(0, 10);
  const rows = await getAttendanceByEmployee(employeeId, { from: start, to: next });
  const counts = { present: 0, absent: 0, leave: 0, half_day: 0, holiday: 0, weekend: 0 };
  let workingHours = 0;
  rows.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; workingHours += Number(r.workingHours) || 0; });
  return { counts, workingHours, lopDays: counts.absent + counts.leave * 0 };
}
