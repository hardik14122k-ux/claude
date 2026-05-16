// Payroll generation. Indian statutory math kept simple but correct
// for a starter HRMS:
//   - PF (employee): 12% of basic, capped at ₹15,000 ceiling
//   - ESI (employee): 0.75% of gross, only if gross ≤ ₹21,000
//   - PT: state-flat ₹200/month placeholder (override per employee state in production)
//   - TDS: not deducted in monthly run; computed at year-end in a separate module

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj } from '../lib/mapper.js';
import { validatePayrollPeriod } from '../lib/validators.js';
import { getEmployee, listEmployees } from './employees.js';
import { monthlySummary } from './attendance.js';

const TABLE = 'payroll';
const PF_CEILING_BASIC   = 15000;
const ESI_CEILING_GROSS  = 21000;
const PF_RATE            = 0.12;
const ESI_RATE_EMPLOYEE  = 0.0075;
const PT_FLAT_MONTHLY    = 200;

// ---- pure calculation, exported for testing ----
export function calculatePayslip({
  basicMonthly = 0, hraMonthly = 0, allowancesMonthly = 0,
  workingDays = 22, paidDays = 22, lopDays = 0,
  pfApplicable = true, esiApplicable = false,
}) {
  const factor = workingDays > 0 ? Math.max(0, paidDays / workingDays) : 1;
  const basic      = round2(basicMonthly      * factor);
  const hra        = round2(hraMonthly        * factor);
  const allowances = round2(allowancesMonthly * factor);
  const gross      = round2(basic + hra + allowances);

  const pfBase  = Math.min(basic, PF_CEILING_BASIC);
  const pf      = pfApplicable ? round2(pfBase * PF_RATE) : 0;
  const esi     = (esiApplicable && gross <= ESI_CEILING_GROSS) ? round2(gross * ESI_RATE_EMPLOYEE) : 0;
  const pt      = gross > 0 ? PT_FLAT_MONTHLY : 0;
  const tds     = 0;
  const lopDeduction = round2((basicMonthly + hraMonthly + allowancesMonthly) / Math.max(workingDays, 1) * lopDays);

  const totalDeductions = round2(pf + esi + pt + tds + lopDeduction);
  const netPay          = round2(gross - totalDeductions);

  return { basic, hra, allowances, gross, pf, esi, pt, tds, lopDeduction, totalDeductions, netPay };
}

export async function generatePayroll(employeeId, { month, year, workingDays = 22 } = {}) {
  validatePayrollPeriod({ month, year });
  const emp = await getEmployee(employeeId);
  if (emp.status !== 'active') {
    throw new Error(`Employee ${emp.fullName} is not active`);
  }
  const summary = await monthlySummary(employeeId, year, month);
  const lopDays  = summary.counts.absent;
  const paidDays = workingDays - lopDays;

  const slip = calculatePayslip({
    basicMonthly: emp.basicMonthly || 0,
    hraMonthly: emp.hraMonthly || 0,
    allowancesMonthly: emp.allowancesMonthly || 0,
    workingDays, paidDays, lopDays,
    pfApplicable: emp.pfApplicable !== false,
    esiApplicable: !!emp.esiApplicable,
  });

  const row = {
    employee_id: employeeId,
    pay_period_month: month,
    pay_period_year: year,
    working_days: workingDays,
    paid_days: paidDays,
    lop_days: lopDays,
    basic: slip.basic,
    hra: slip.hra,
    allowances: slip.allowances,
    pf_employee: slip.pf,
    esi_employee: slip.esi,
    pt: slip.pt,
    tds: slip.tds,
    lop_deduction: slip.lopDeduction,
    status: 'processed',
  };
  const data = await unwrap(
    sb.from(TABLE).upsert(row, { onConflict: 'employee_id,pay_period_month,pay_period_year' }).select().single(),
    'Failed to generate payroll');
  return rowToObj(data);
}

export async function generateMonthlyPayroll({ month, year, workingDays = 22 } = {}) {
  const employees = await listEmployees({ status: 'active' });
  const results = [];
  for (const emp of employees) {
    try {
      const slip = await generatePayroll(emp.id, { month, year, workingDays });
      results.push({ employeeId: emp.id, ok: true, slip });
    } catch (err) {
      results.push({ employeeId: emp.id, ok: false, error: err.message });
    }
  }
  return results;
}

export async function listPayrollByEmployee(employeeId) {
  return rowToObj(await unwrap(
    sb.from(TABLE).select('*')
      .eq('employee_id', employeeId)
      .order('pay_period_year', { ascending: false })
      .order('pay_period_month', { ascending: false }),
    'Failed to load payroll'));
}

export async function listPayrollByPeriod(year, month) {
  return rowToObj(await unwrap(
    sb.from(TABLE).select('*, employees(full_name, employee_code, department)')
      .eq('pay_period_year', year)
      .eq('pay_period_month', month),
    'Failed to load payroll'));
}

export async function markPaid(payrollId) {
  const data = await unwrap(
    sb.from(TABLE).update({ status: 'paid', paid_at: new Date().toISOString() }).eq('id', payrollId).select().single(),
    'Failed to mark paid');
  return rowToObj(data);
}

function round2(n) { return Math.round((Number(n) || 0) * 100) / 100; }
