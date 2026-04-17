import { h, openModal, toast, fmtDate } from '../ui.js';
import { getState, createVacancy, updateVacancy, deleteVacancy, daysBetween } from '../store.js';

export function Vacancies() {
  const s = getState();
  return h('div', {}, [
    h('div', { class: 'section-title' }, [
      h('h2', {}, [`Vacancies (${s.vacancies.length})`]),
      h('button', { class: 'btn primary', onclick: () => openVacancyForm() }, ['+ New Vacancy'])
    ]),
    s.vacancies.length
      ? h('div', { class: 'card', style: { padding: 0 } }, [
          h('table', { class: 'table' }, [
            h('thead', {}, [h('tr', {}, [
              h('th', {}, ['Role']), h('th', {}, ['Department']), h('th', {}, ['Location']),
              h('th', {}, ['Hiring Manager']), h('th', {}, ['Openings']), h('th', {}, ['Priority']),
              h('th', {}, ['Status']), h('th', {}, ['Opened']), h('th', {}, ['Target Close']), h('th', {}, [''])
            ])]),
            h('tbody', {}, s.vacancies.map(v => h('tr', {}, [
              h('td', {}, [
                h('div', { style: { fontWeight: 600 } }, [v.title]),
                h('div', { class: 'muted', style: { fontSize: '11px' } }, [pipelineCount(v.id)])
              ]),
              h('td', {}, [v.department]),
              h('td', {}, [v.location]),
              h('td', {}, [v.hiringManager || '—']),
              h('td', {}, [String(v.openings || 1)]),
              h('td', {}, [h('span', { class: `chip ${v.priority === 'High' ? 'bad' : v.priority === 'Low' ? 'ok' : 'warn'}` }, [v.priority || 'Medium'])]),
              h('td', {}, [h('span', { class: `chip ${v.status === 'Closed' ? '' : 'ok'}` }, [v.status || 'Open'])]),
              h('td', {}, [`${fmtDate(v.createdAt)} · ${daysBetween(v.createdAt)}d ago`]),
              h('td', {}, [v.targetClose ? fmtDate(v.targetClose) : '—']),
              h('td', {}, [
                h('div', { class: 'row-flex' }, [
                  h('button', { class: 'btn sm', onclick: () => openVacancyForm(v) }, ['Edit']),
                  h('button', { class: 'btn sm danger-ghost', onclick: () => {
                    if (confirm(`Delete "${v.title}"? Candidates will be unlinked.`)) {
                      deleteVacancy(v.id);
                      toast('Vacancy deleted', 'ok');
                    }
                  } }, ['Delete'])
                ])
              ])
            ])))
          ])
        ])
      : h('div', { class: 'card empty' }, ['No vacancies yet. Click "New Vacancy" or load demo data.'])
  ]);
}

function pipelineCount(vid) {
  const s = getState();
  const n = s.candidates.filter(c => c.vacancyId === vid).length;
  return n ? `${n} candidate${n === 1 ? '' : 's'} in pipeline` : 'No candidates yet';
}

export function openVacancyForm(existing) {
  const data = { ...(existing || { openings: 1, priority: 'Medium', status: 'Open' }) };
  const form = h('div', { class: 'form-grid' }, [
    field('Role / Title', h('input', { class: 'input', value: data.title || '', oninput: e => data.title = e.target.value, placeholder: 'Senior Backend Engineer' })),
    field('Department', h('input', { class: 'input', value: data.department || '', oninput: e => data.department = e.target.value })),
    field('Location', h('input', { class: 'input', value: data.location || '', oninput: e => data.location = e.target.value })),
    field('Hiring Manager', h('input', { class: 'input', value: data.hiringManager || '', oninput: e => data.hiringManager = e.target.value })),
    field('Openings', h('input', { class: 'input', type: 'number', min: '1', value: data.openings || 1, oninput: e => data.openings = Number(e.target.value) })),
    field('Priority', selectEl(['High','Medium','Low'], data.priority || 'Medium', v => data.priority = v)),
    field('Status', selectEl(['Open','On Hold','Closed'], data.status || 'Open', v => data.status = v)),
    field('Target Close', h('input', { class: 'input', type: 'date', value: toDateInput(data.targetClose), oninput: e => data.targetClose = e.target.value ? new Date(e.target.value).toISOString() : '' })),
    field('Skills (comma separated)', h('input', { class: 'input', value: (data.skills || []).join(', '), oninput: e => data.skills = e.target.value.split(',').map(s => s.trim()).filter(Boolean) }), true),
    field('Description', h('textarea', { class: 'input', rows: 4, oninput: e => data.description = e.target.value }, [data.description || '']), true),
  ]);

  openModal({
    title: existing ? `Edit "${existing.title}"` : 'New Vacancy',
    body: form,
    actions: [
      { label: 'Cancel', onClick: close => close() },
      { label: existing ? 'Save' : 'Create', primary: true, onClick: (close) => {
          if (!data.title?.trim()) { toast('Title is required', 'bad'); return; }
          if (existing) { updateVacancy(existing.id, data); toast('Vacancy updated', 'ok'); }
          else { createVacancy(data); toast('Vacancy created', 'ok'); }
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

function toDateInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toISOString().slice(0, 10);
}
