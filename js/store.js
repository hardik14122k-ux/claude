// Async cache + pub/sub. Replaces the old localStorage state container.
// Views call `store.refresh('candidates')` to load and broadcast; subscribers
// re-render on the channels they care about.

import * as candidatesSvc from './services/candidates.js';
import * as vacanciesSvc  from './services/vacancies.js';
import * as interviewsSvc from './services/interviews.js';
import * as activitySvc   from './services/activity.js';
import * as employeesSvc  from './services/employees.js';

export { STAGES, stageLabel } from './services/analytics.js';

const cache = {
  vacancies: [],
  candidates: [],
  interviews: [],
  activity: [],
  employees: [],
};
const listeners = new Map(); // channel -> Set<fn>

export function getState() { return cache; }

export function subscribe(channel, fn) {
  // Backward-compat: subscribe(fn) listens to all channels.
  if (typeof channel === 'function') { fn = channel; channel = '*'; }
  if (!listeners.has(channel)) listeners.set(channel, new Set());
  listeners.get(channel).add(fn);
  return () => listeners.get(channel).delete(fn);
}

function emit(channel) {
  const fire = (set) => set?.forEach(fn => { try { fn(cache); } catch (e) { console.error(e); } });
  fire(listeners.get(channel));
  fire(listeners.get('*'));
}

const loaders = {
  vacancies:  () => vacanciesSvc.listVacancies(),
  candidates: () => candidatesSvc.listCandidates(),
  interviews: () => interviewsSvc.listInterviews(),
  activity:   () => activitySvc.listActivity(),
  employees:  () => employeesSvc.listEmployees({ status: null }),
};

export async function refresh(channel) {
  const load = loaders[channel];
  if (!load) throw new Error(`Unknown cache channel: ${channel}`);
  cache[channel] = await load();
  emit(channel);
  return cache[channel];
}

export async function refreshAll() {
  await Promise.all(Object.keys(loaders).map(refresh));
}

// Convenience helpers that mutate via the service layer and then refresh the
// appropriate cache channels. Views can also call services directly and call
// refresh() afterwards — both work.

export async function createVacancy(data)  { await vacanciesSvc.createVacancy(data);  await refresh('vacancies'); await refresh('activity'); }
export async function updateVacancy(id, p) { await vacanciesSvc.updateVacancy(id, p); await refresh('vacancies'); }
export async function deleteVacancy(id)    { await vacanciesSvc.deleteVacancy(id);    await refresh('vacancies'); }

export async function createCandidate(data)  {
  await candidatesSvc.createCandidate(data);
  await Promise.all([refresh('candidates'), refresh('activity')]);
}
export async function updateCandidate(id, p) { await candidatesSvc.updateCandidate(id, p); await refresh('candidates'); }
export async function moveCandidate(id, st)  {
  await candidatesSvc.moveCandidate(id, st);
  await Promise.all([refresh('candidates'), refresh('activity'), refresh('employees')]);
}
export async function deleteCandidate(id)    { await candidatesSvc.deleteCandidate(id); await refresh('candidates'); }

export async function scheduleInterview(data)  {
  await interviewsSvc.scheduleInterview(data);
  await Promise.all([refresh('interviews'), refresh('activity')]);
}
export async function updateInterview(id, p) { await interviewsSvc.updateInterview(id, p); await refresh('interviews'); }
export async function deleteInterview(id)    { await interviewsSvc.deleteInterview(id);    await refresh('interviews'); }

// ---- date helpers kept for view-side convenience ----
export function nowISO() { return new Date().toISOString(); }
export function daysBetween(a, b = new Date()) {
  return Math.max(0, Math.floor((new Date(b) - new Date(a)) / 86400000));
}
