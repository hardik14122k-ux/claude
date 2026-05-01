// Employees CRUD. Onboarding from candidate → employee is handled by the
// _candidate_to_employee trigger; this module covers everything else.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { validateEmployee } from '../lib/validators.js';

const TABLE = 'employees';

export async function listEmployees({ status = 'active', q } = {}) {
  let query = sb.from(TABLE).select('*').order('date_of_joining', { ascending: false });
  if (status) query = query.eq('status', status);
  if (q) {
    const safe = q.replace(/[%,]/g, ' ');
    query = query.or(`full_name.ilike.%${safe}%,email.ilike.%${safe}%,employee_code.ilike.%${safe}%`);
  }
  return rowToObj(await unwrap(query, 'Failed to load employees'));
}

export async function getEmployee(id) {
  return rowToObj(await unwrap(
    sb.from(TABLE).select('*').eq('id', id).single(),
    'Employee not found'));
}

// Direct create (used when adding employees outside the recruitment flow).
export async function createEmployee(input) {
  validateEmployee(input);
  // Auto-allocate employee_code if not provided.
  if (!input.employeeCode) {
    const { data: codes } = await sb.from(TABLE)
      .select('employee_code')
      .order('employee_code', { ascending: false })
      .limit(1);
    const last = codes?.[0]?.employee_code || 'EMP0000';
    const next = parseInt(String(last).replace(/\D/g, '') || '0', 10) + 1;
    input.employeeCode = 'EMP' + String(next).padStart(4, '0');
  }
  const row = objToRow({
    candidateId: input.candidateId || null,
    employeeCode: input.employeeCode,
    fullName: input.fullName,
    email: input.email || null,
    phone: input.phone || null,
    department: input.department || 'General',
    designation: input.designation || null,
    dateOfJoining: input.dateOfJoining || new Date().toISOString().slice(0, 10),
    status: input.status || 'active',
    managerId: input.managerId || null,
    ctcAnnual: input.ctcAnnual ?? null,
    basicMonthly: input.basicMonthly ?? null,
    hraMonthly: input.hraMonthly ?? null,
    allowancesMonthly: input.allowancesMonthly ?? null,
    pfApplicable: input.pfApplicable !== false,
    esiApplicable: !!input.esiApplicable,
    bankAccount: input.bankAccount || null,
    ifsc: input.ifsc || null,
    pan: input.pan || null,
    uan: input.uan || null,
  });
  const data = await unwrap(sb.from(TABLE).insert(row).select().single(), 'Failed to create employee');
  return rowToObj(data);
}

export async function updateEmployee(id, patch) {
  const data = await unwrap(
    sb.from(TABLE).update(objToRow(patch)).eq('id', id).select().single(),
    'Failed to update employee');
  return rowToObj(data);
}

// Set salary breakup. Auto-derives a sensible default from CTC if components missing.
export async function setSalary(id, { ctcAnnual, basicMonthly, hraMonthly, allowancesMonthly }) {
  const ctc = Number(ctcAnnual) || 0;
  const monthly = ctc / 12;
  const basic = basicMonthly ?? Math.round(monthly * 0.40);
  const hra   = hraMonthly   ?? Math.round(basic * 0.40);
  const allow = allowancesMonthly ?? Math.round(monthly - basic - hra);
  return updateEmployee(id, { ctcAnnual: ctc, basicMonthly: basic, hraMonthly: hra, allowancesMonthly: allow });
}
