// Vacancies CRUD on Supabase.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { validateVacancy } from '../lib/validators.js';

const TABLE = 'vacancies';

export async function listVacancies({ status } = {}) {
  let q = sb.from(TABLE).select('*').order('created_at', { ascending: false });
  if (status) q = q.eq('status', status);
  return rowToObj(await unwrap(q, 'Failed to load vacancies'));
}

export async function getVacancy(id) {
  return rowToObj(await unwrap(
    sb.from(TABLE).select('*').eq('id', id).single(),
    'Vacancy not found'));
}

export async function createVacancy(input) {
  validateVacancy(input);
  const row = objToRow({
    title: input.title,
    department: input.department || 'General',
    location: input.location || 'Remote',
    hiringManager: input.hiringManager || null,
    openings: Number(input.openings) || 1,
    priority: (input.priority || 'medium').toLowerCase(),
    status:   (input.status   || 'open').toLowerCase(),
    targetClose: input.targetClose || null,
    description: input.description || null,
    skills: input.skills || [],
  });
  const data = await unwrap(sb.from(TABLE).insert(row).select().single(), 'Failed to create vacancy');
  return rowToObj(data);
}

export async function updateVacancy(id, patch) {
  const row = objToRow(patch);
  const data = await unwrap(
    sb.from(TABLE).update(row).eq('id', id).select().single(),
    'Failed to update vacancy');
  return rowToObj(data);
}

export async function deleteVacancy(id) {
  await unwrap(sb.from(TABLE).delete().eq('id', id), 'Failed to delete vacancy');
}
