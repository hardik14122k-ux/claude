import { h, openModal, toast, fmtDateTime } from '../ui.js';
import { getState, scheduleInterview, updateInterview, deleteInterview, moveCandidate } from '../store.js';

export function Interviews() {
  const s = getState();
  const sorted = [...s.interviews].sort((a, b) => new Date(a.date) - new Date(b.date));
  const upcoming = sorted.filter(i => new Date(i.date) >= new Date() && i.status !== 'Completed' && i.status !== 'Cancelled');
  const past = sorted.filter(i => !upcoming.includes(i));

  return h('div', {}, [
    h('div', { class: 'section-title' }, [
      h('h2', {}, [`Interviews (${s.interviews.length})`]),
      h('button', { class: 'btn primary', onclick: () => openInterviewForm() }, ['+ Schedule Interview'])
    ]),
    block('Upcoming', upcoming),
    h('div', { style: { height: '16px' } }),
    block('Past / Completed', past)
  ]);
}

function block(title, list) {
  return h('div', { class: 'card' }, [
    h('div', { class: 'section-title' }, [h('h2', {}, [title]), h('span', { class: 'muted' }, [`${list.length}`])]),
    list.length
      ? h('table', { class: 'table' }, [
          h('thead', {}, [h('tr', {}, [
            h('th', {}, ['When']), h('th', {}, ['Candidate']), h('th', {}, ['Role']),
            h('th', {}, ['Type']), h('th', {}, ['Interviewer']), h('th', {}, ['Status']), h('th', {}, ['Rating']), h('th', {}, [''])
          ])]),
          h('tbody', {}, list.map(i => {
            const s = getState();
            const c = s.candidates.find(x => x.id === i.candidateId);
            const v = c?.vacancyId ? s.vacancies.find(x => x.id === c.vacancyId) : null;
            return h('tr', {}, [
              h('td', {}, [fmtDateTime(i.date)]),
              h('td', {}, [c?.name || '—']),
              h('td', {}, [v?.title || '—']),
              h('td', {}, [i.type]),
              h('td', {}, [i.interviewer || '—']),
              h('td', {}, [h('span', { class: `chip ${i.status === 'Completed' ? 'ok' : i.status === 'Cancelled' ? 'bad' : 'info'}` }, [i.status])]),
              h('td', {}, [i.rating ? '★'.repeat(i.rating) + '☆'.repeat(5 - i.rating) : '—']),
              h('td', {}, [
                h('div', { class: 'row-flex' }, [
                  h('button', { class: 'btn sm', onclick: () => openInterviewForm(i) }, ['Edit']),
                  h('button', { class: 'btn sm danger-ghost', onclick: () => { if (confirm('Delete interview?')) { deleteInterview(i.id); toast('Deleted', 'ok'); } } }, ['Delete'])
                ])
              ])
            ]);
          }))
        ])
      : h('div', { class: 'empty' }, ['Nothing here yet.'])
  ]);
}

export function openInterviewForm(existing) {
  const data = { ...(existing || { status: 'Scheduled', type: 'Technical', rating: 0 }) };
  const s = getState();
  const candSelect = h('select', { class: 'input', onchange: e => data.candidateId = e.target.value }, [
    h('option', { value: '' }, ['— Select candidate —']),
    ...s.candidates.map(c => h('option', { value: c.id, ...(c.id === data.candidateId ? { selected: '' } : {}) }, [c.name]))
  ]);

  const body = h('div', { class: 'form-grid' }, [
    field('Candidate', candSelect, true),
    field('Date & time', h('input', { class: 'input', type: 'datetime-local', value: toDT(data.date), oninput: e => data.date = e.target.value ? new Date(e.target.value).toISOString() : '' })),
    field('Type', selectEl(['Screening','Technical','Culture','System Design','Final','Reference'], data.type, v => data.type = v)),
    field('Interviewer', h('input', { class: 'input', value: data.interviewer || '', oninput: e => data.interviewer = e.target.value })),
    field('Status', selectEl(['Scheduled','Completed','Cancelled','No-show'], data.status, v => data.status = v)),
    field('Rating (0-5)', h('input', { class: 'input', type: 'number', min: '0', max: '5', value: data.rating || 0, oninput: e => data.rating = Number(e.target.value) })),
    field('Feedback', h('textarea', { class: 'input', rows: 4, oninput: e => data.feedback = e.target.value }, [data.feedback || '']), true),
  ]);

  openModal({
    title: existing ? 'Edit Interview' : 'Schedule Interview',
    body,
    actions: [
      { label: 'Cancel', onClick: close => close() },
      { label: existing ? 'Save' : 'Schedule', primary: true, onClick: (close) => {
          if (!data.candidateId) { toast('Pick a candidate', 'bad'); return; }
          if (!data.date) { toast('Pick a date', 'bad'); return; }
          if (existing) updateInterview(existing.id, data);
          else {
            scheduleInterview(data);
            // Auto-advance candidate to interview stage if still in screening
            const c = getState().candidates.find(x => x.id === data.candidateId);
            if (c && (c.stage === 'sourced' || c.stage === 'screening')) moveCandidate(c.id, 'interview');
          }
          toast('Saved', 'ok');
          close();
        } }
    ]
  });
}

function field(label, input, full = false) {
  return h('div', { class: full ? 'full' : '' }, [h('label', {}, [label]), input]);
}
function selectEl(options, value, onChange) {
  return h('select', { class: 'input', onchange: e => onChange(e.target.value) },
    options.map(o => h('option', { value: o, ...(o === value ? { selected: '' } : {}) }, [o]))
  );
}
function toDT(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
