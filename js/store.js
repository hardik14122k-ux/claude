// Reactive persistent store for the recruitment tracker.
// State is saved to localStorage and subscribers are notified on any change.

const KEY = 'talenttrack.v1';

export const STAGES = [
  { id: 'sourced',    label: 'Sourced',     sla: 3  },
  { id: 'screening',  label: 'Screening',   sla: 5  },
  { id: 'interview',  label: 'Interview',   sla: 10 },
  { id: 'offer',      label: 'Offer',       sla: 7  },
  { id: 'hired',      label: 'Hired',       sla: 0  },
  { id: 'rejected',   label: 'Rejected',    sla: 0  },
];

const DEFAULT_STATE = {
  vacancies: [],
  candidates: [],
  interviews: [],
  activity: [],
  settings: {
    company: 'Acme Corp',
    stages: STAGES.map(s => s.id),
  },
};

let state = load();
const listeners = new Set();

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return structuredClone(DEFAULT_STATE);
    const parsed = JSON.parse(raw);
    return { ...structuredClone(DEFAULT_STATE), ...parsed };
  } catch {
    return structuredClone(DEFAULT_STATE);
  }
}

function persist() {
  localStorage.setItem(KEY, JSON.stringify(state));
}

export function getState() { return state; }

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  persist();
  listeners.forEach(fn => { try { fn(state); } catch (e) { console.error(e); } });
}

export function uid(prefix = 'id') {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36).slice(-3)}`;
}

export function nowISO() { return new Date().toISOString(); }

export function logActivity(type, message, meta = {}) {
  state.activity.unshift({ id: uid('act'), type, message, meta, ts: nowISO() });
  state.activity = state.activity.slice(0, 200);
}

// -------- Vacancies --------
export function createVacancy(data) {
  const v = {
    id: uid('vac'),
    title: data.title || 'Untitled role',
    department: data.department || 'General',
    location: data.location || 'Remote',
    hiringManager: data.hiringManager || '',
    openings: Number(data.openings) || 1,
    priority: data.priority || 'Medium',
    status: data.status || 'Open',
    targetClose: data.targetClose || '',
    description: data.description || '',
    skills: data.skills || [],
    createdAt: nowISO(),
  };
  state.vacancies.unshift(v);
  logActivity('vacancy.created', `Vacancy "${v.title}" opened`);
  emit();
  return v;
}

export function updateVacancy(id, patch) {
  const v = state.vacancies.find(x => x.id === id);
  if (!v) return;
  Object.assign(v, patch);
  emit();
}

export function deleteVacancy(id) {
  state.vacancies = state.vacancies.filter(x => x.id !== id);
  state.candidates = state.candidates.map(c => c.vacancyId === id ? { ...c, vacancyId: null } : c);
  emit();
}

// -------- Candidates --------
export function createCandidate(data) {
  const c = {
    id: uid('cand'),
    name: data.name || 'Unnamed Candidate',
    email: data.email || '',
    phone: data.phone || '',
    location: data.location || '',
    headline: data.headline || '',
    skills: data.skills || [],
    experienceYears: data.experienceYears ?? null,
    education: data.education || [],
    experience: data.experience || [],
    source: data.source || 'CV Upload',
    vacancyId: data.vacancyId || null,
    stage: data.stage || 'sourced',
    rating: data.rating || 0,
    rawCv: data.rawCv || '',
    fileName: data.fileName || '',
    history: [{ stage: data.stage || 'sourced', at: nowISO() }],
    createdAt: nowISO(),
    updatedAt: nowISO(),
  };
  state.candidates.unshift(c);
  logActivity('candidate.created', `Candidate "${c.name}" added`, { candidateId: c.id });
  emit();
  return c;
}

export function updateCandidate(id, patch) {
  const c = state.candidates.find(x => x.id === id);
  if (!c) return;
  Object.assign(c, patch, { updatedAt: nowISO() });
  emit();
}

export function moveCandidate(id, toStage) {
  const c = state.candidates.find(x => x.id === id);
  if (!c || c.stage === toStage) return;
  c.history.push({ stage: toStage, at: nowISO(), from: c.stage });
  c.stage = toStage;
  c.updatedAt = nowISO();
  logActivity('candidate.moved', `${c.name} → ${toStage}`, { candidateId: c.id });
  emit();
}

export function deleteCandidate(id) {
  state.candidates = state.candidates.filter(x => x.id !== id);
  state.interviews = state.interviews.filter(x => x.candidateId !== id);
  emit();
}

// -------- Interviews --------
export function scheduleInterview(data) {
  const i = {
    id: uid('int'),
    candidateId: data.candidateId,
    interviewer: data.interviewer || '',
    type: data.type || 'Technical',
    date: data.date || nowISO(),
    status: data.status || 'Scheduled',
    feedback: data.feedback || '',
    rating: data.rating || 0,
    createdAt: nowISO(),
  };
  state.interviews.unshift(i);
  const c = state.candidates.find(x => x.id === i.candidateId);
  logActivity('interview.scheduled', `Interview scheduled${c ? ` with ${c.name}` : ''}`);
  emit();
  return i;
}

export function updateInterview(id, patch) {
  const i = state.interviews.find(x => x.id === id);
  if (!i) return;
  Object.assign(i, patch);
  emit();
}

export function deleteInterview(id) {
  state.interviews = state.interviews.filter(x => x.id !== id);
  emit();
}

// -------- Bulk helpers --------
export function resetAll() {
  state = structuredClone(DEFAULT_STATE);
  emit();
}

export function replaceState(next) {
  state = { ...structuredClone(DEFAULT_STATE), ...next };
  emit();
}

// -------- Derived helpers --------
export function daysBetween(a, b = new Date()) {
  const ms = new Date(b).getTime() - new Date(a).getTime();
  return Math.max(0, Math.floor(ms / 86400000));
}

export function stageLabel(id) {
  return STAGES.find(s => s.id === id)?.label || id;
}

export function averageTATByStage() {
  // Average days spent in each non-terminal stage based on history transitions.
  const buckets = {};
  STAGES.forEach(s => (buckets[s.id] = { total: 0, count: 0 }));
  state.candidates.forEach(c => {
    const h = c.history || [];
    for (let i = 0; i < h.length; i++) {
      const cur = h[i];
      const next = h[i + 1];
      const end = next ? new Date(next.at) : new Date();
      const days = (end - new Date(cur.at)) / 86400000;
      if (buckets[cur.stage]) {
        buckets[cur.stage].total += days;
        buckets[cur.stage].count += 1;
      }
    }
  });
  return Object.fromEntries(
    Object.entries(buckets).map(([k, v]) => [k, v.count ? +(v.total / v.count).toFixed(1) : 0])
  );
}

export function agingBuckets() {
  // Number of active candidates grouped by days since last stage change.
  const active = state.candidates.filter(c => c.stage !== 'hired' && c.stage !== 'rejected');
  const result = { '<=3': 0, '4-7': 0, '8-14': 0, '15-30': 0, '>30': 0 };
  active.forEach(c => {
    const lastChange = c.history?.[c.history.length - 1]?.at || c.createdAt;
    const d = daysBetween(lastChange);
    if (d <= 3) result['<=3']++;
    else if (d <= 7) result['4-7']++;
    else if (d <= 14) result['8-14']++;
    else if (d <= 30) result['15-30']++;
    else result['>30']++;
  });
  return result;
}
