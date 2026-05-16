// Lightweight input validators. Throw HrmsError('validation_error') on failure.

import { HrmsError } from './errors.js';

const STAGES = ['sourced','screening','interview','offer','hired','rejected'];
const VAC_STATUSES   = ['open','on_hold','closed'];
const VAC_PRIORITIES = ['low','medium','high'];
const INT_TYPES   = ['screening','technical','culture','final'];
const INT_STATUS  = ['scheduled','completed','cancelled','no_show'];
const ATT_STATUS  = ['present','absent','leave','half_day','holiday','weekend'];

const fail = (msg, field) => {
  throw new HrmsError(msg, { code: 'validation_error', status: 400, cause: { field } });
};

export const isEmail = (s) => typeof s === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
export const isUuid  = (s) => typeof s === 'string' && /^[0-9a-f-]{36}$/i.test(s);

export function validateVacancy(input) {
  if (!input?.title || typeof input.title !== 'string') fail('Title is required', 'title');
  if (input.openings != null && (Number(input.openings) < 1)) fail('Openings must be ≥ 1', 'openings');
  if (input.priority && !VAC_PRIORITIES.includes(input.priority)) fail('Invalid priority', 'priority');
  if (input.status   && !VAC_STATUSES.includes(input.status))    fail('Invalid status', 'status');
}

export function validateCandidate(input) {
  if (!input?.name || typeof input.name !== 'string') fail('Name is required', 'name');
  if (input.email && !isEmail(input.email)) fail('Invalid email', 'email');
  if (input.stage && !STAGES.includes(input.stage)) fail('Invalid stage', 'stage');
  if (input.rating != null && (input.rating < 0 || input.rating > 5)) fail('Rating must be 0–5', 'rating');
}

export function validateStageTransition(stage) {
  if (!STAGES.includes(stage)) fail(`Invalid stage: ${stage}`, 'stage');
}

export function validateInterview(input) {
  if (!input?.candidate_id || !isUuid(input.candidate_id)) fail('candidate_id required', 'candidate_id');
  if (input.type   && !INT_TYPES.includes(input.type))     fail('Invalid type', 'type');
  if (input.status && !INT_STATUS.includes(input.status))  fail('Invalid status', 'status');
}

export function validateEmployee(input) {
  if (!input?.full_name) fail('full_name required', 'full_name');
  if (input.email && !isEmail(input.email)) fail('Invalid email', 'email');
  if (input.ctc_annual != null && Number(input.ctc_annual) < 0) fail('CTC must be ≥ 0', 'ctc_annual');
}

export function validateAttendance(input) {
  if (!input?.employee_id || !isUuid(input.employee_id)) fail('employee_id required', 'employee_id');
  if (!input?.attendance_date || !/^\d{4}-\d{2}-\d{2}$/.test(input.attendance_date)) fail('attendance_date YYYY-MM-DD required', 'attendance_date');
  if (input.status && !ATT_STATUS.includes(input.status)) fail('Invalid status', 'status');
}

export function validatePayrollPeriod({ month, year }) {
  if (!Number.isInteger(month) || month < 1 || month > 12) fail('month 1–12 required', 'month');
  if (!Number.isInteger(year)  || year  < 2000 || year > 2100) fail('year required', 'year');
}
