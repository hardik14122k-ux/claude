// Candidates CRUD + stage transitions.
// History maintenance and employee auto-creation on `hired` are handled by
// DB triggers (_candidate_stage_change and _candidate_to_employee).

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { validateCandidate, validateStageTransition } from '../lib/validators.js';

const TABLE = 'candidates';

export async function listCandidates({ stage, vacancyId, q } = {}) {
  let query = sb.from(TABLE).select('*').order('created_at', { ascending: false });
  if (stage)     query = query.eq('stage', stage);
  if (vacancyId) query = query.eq('vacancy_id', vacancyId);
  if (q) {
    const safe = q.replace(/[%,]/g, ' ');
    query = query.or(`name.ilike.%${safe}%,email.ilike.%${safe}%,headline.ilike.%${safe}%`);
  }
  return rowToObj(await unwrap(query, 'Failed to load candidates'));
}

export async function getCandidate(id) {
  return rowToObj(await unwrap(
    sb.from(TABLE).select('*').eq('id', id).single(),
    'Candidate not found'));
}

export async function createCandidate(input) {
  validateCandidate(input);
  const row = objToRow({
    name: input.name,
    email: input.email || null,
    phone: input.phone || null,
    location: input.location || null,
    headline: input.headline || null,
    skills: input.skills || [],
    experienceYears: input.experienceYears ?? null,
    education: input.education || [],
    experience: input.experience || [],
    source: input.source || 'CV Upload',
    vacancyId: input.vacancyId || null,
    stage: input.stage || 'sourced',
    rating: input.rating || null,
    rawCv: input.rawCv || null,
    fileName: input.fileName || null,
    history: [{ stage: input.stage || 'sourced', at: new Date().toISOString() }],
  });
  const data = await unwrap(sb.from(TABLE).insert(row).select().single(), 'Failed to create candidate');
  return rowToObj(data);
}

export async function updateCandidate(id, patch) {
  const row = objToRow(patch);
  const data = await unwrap(
    sb.from(TABLE).update(row).eq('id', id).select().single(),
    'Failed to update candidate');
  return rowToObj(data);
}

export async function moveCandidate(id, toStage) {
  validateStageTransition(toStage);
  const data = await unwrap(
    sb.from(TABLE).update({ stage: toStage }).eq('id', id).select().single(),
    'Failed to move candidate');
  return rowToObj(data);
}

export async function deleteCandidate(id) {
  await unwrap(sb.from(TABLE).delete().eq('id', id), 'Failed to delete candidate');
}
