// Interviews CRUD.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { validateInterview } from '../lib/validators.js';

const TABLE = 'interviews';

export async function listInterviews({ candidateId, status, from, to } = {}) {
  let q = sb.from(TABLE).select('*').order('scheduled_at', { ascending: false });
  if (candidateId) q = q.eq('candidate_id', candidateId);
  if (status)      q = q.eq('status', status);
  if (from)        q = q.gte('scheduled_at', from);
  if (to)          q = q.lte('scheduled_at', to);
  return rowToObj(await unwrap(q, 'Failed to load interviews'));
}

export async function scheduleInterview(input) {
  const payload = objToRow({
    candidateId: input.candidateId,
    interviewer: input.interviewer || null,
    type: (input.type || 'technical').toLowerCase(),
    scheduledAt: input.scheduledAt || input.date || new Date().toISOString(),
    status: (input.status || 'scheduled').toLowerCase(),
    feedback: input.feedback || null,
    rating: input.rating || null,
  });
  validateInterview(payload);
  const data = await unwrap(sb.from(TABLE).insert(payload).select().single(), 'Failed to schedule interview');
  return rowToObj(data);
}

export async function updateInterview(id, patch) {
  const data = await unwrap(
    sb.from(TABLE).update(objToRow(patch)).eq('id', id).select().single(),
    'Failed to update interview');
  return rowToObj(data);
}

export async function deleteInterview(id) {
  await unwrap(sb.from(TABLE).delete().eq('id', id), 'Failed to delete interview');
}
