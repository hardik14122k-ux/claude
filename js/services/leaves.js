// Leave management: types, balances, requests.
// company_id is set by DB trigger; RLS enforces tenant isolation.
// Approving a request automatically deducts from leave_balances (DB trigger).

import { sb } from '../lib/supabase.js';
import { unwrap, HrmsError } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { fiscalYearStart } from '../utils/date.js';

// ---------- Leave Types ----------
export async function listLeaveTypes() {
  return rowToObj(await unwrap(
    sb.from('leave_types').select('*').order('code'),
    'Failed to load leave types'));
}

export async function upsertLeaveType(input) {
  if (!input?.code || !input?.name) throw new HrmsError('code + name required', { code: 'validation_error', status: 400 });
  const row = objToRow({
    code: input.code,
    name: input.name,
    annualQuota: Number(input.annualQuota) || 0,
    isPaid: input.isPaid !== false,
    carryForward: !!input.carryForward,
  });
  const data = await unwrap(
    sb.from('leave_types').upsert(row, { onConflict: 'company_id,code' }).select().single(),
    'Failed to save leave type');
  return rowToObj(data);
}

// ---------- Balances ----------
export async function getBalances(employeeId, fyStart = fiscalYearStart()) {
  return rowToObj(await unwrap(
    sb.from('leave_balances').select('*, leave_types(code, name)')
      .eq('employee_id', employeeId)
      .eq('fy_start', fyStart),
    'Failed to load balances'));
}

export async function adjustBalance({ employeeId, leaveTypeId, fyStart, opening = 0, accrued = 0, encashed = 0 }) {
  const row = objToRow({
    employeeId, leaveTypeId,
    fyStart: fyStart || fiscalYearStart(),
    opening, accrued, encashed,
  });
  const data = await unwrap(
    sb.from('leave_balances').upsert(row, { onConflict: 'employee_id,leave_type_id,fy_start' }).select().single(),
    'Failed to update balance');
  return rowToObj(data);
}

// ---------- Requests ----------
export async function applyLeave({ employeeId, leaveTypeId, startDate, endDate, reason }) {
  if (!employeeId || !leaveTypeId) throw new HrmsError('employee_id + leave_type_id required', { code: 'validation_error', status: 400 });
  if (!startDate || !endDate) throw new HrmsError('start_date + end_date required', { code: 'validation_error', status: 400 });
  const days = workingDaysBetween(startDate, endDate);
  if (days <= 0) throw new HrmsError('Leave must span ≥ 1 working day', { code: 'validation_error', status: 400 });

  const row = objToRow({
    employeeId, leaveTypeId,
    startDate, endDate, days,
    reason: reason || null,
    status: 'pending',
  });
  const data = await unwrap(
    sb.from('leave_requests').insert(row).select().single(),
    'Failed to apply for leave');
  return rowToObj(data);
}

export async function listRequests({ employeeId, status } = {}) {
  let q = sb.from('leave_requests')
    .select('*, employees(full_name, employee_code), leave_types(code, name)')
    .order('created_at', { ascending: false });
  if (employeeId) q = q.eq('employee_id', employeeId);
  if (status)     q = q.eq('status', status);
  return rowToObj(await unwrap(q, 'Failed to load leave requests'));
}

export async function decideRequest(requestId, { approve, approverId }) {
  const row = { status: approve ? 'approved' : 'rejected', approver_id: approverId || null };
  const data = await unwrap(
    sb.from('leave_requests').update(row).eq('id', requestId).select().single(),
    'Failed to decide leave request');
  return rowToObj(data);
}

export async function cancelRequest(requestId) {
  const data = await unwrap(
    sb.from('leave_requests').update({ status: 'cancelled' }).eq('id', requestId).select().single(),
    'Failed to cancel request');
  return rowToObj(data);
}

// ---------- helpers ----------
function workingDaysBetween(start, end) {
  let n = 0;
  for (let d = new Date(start); d <= new Date(end); d.setDate(d.getDate() + 1)) {
    const wd = d.getDay();
    if (wd !== 0 && wd !== 6) n++;
  }
  return n;
}
