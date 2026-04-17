import { h, openModal, toast, fmtDate, initials, relTime } from '../ui.js';
import { getState, createCandidate, updateCandidate, deleteCandidate, STAGES, stageLabel, moveCandidate, daysBetween } from '../store.js';
import { extractText, parseCv } from '../cv-parser.js';

export function Candidates() {
  const s = getState();
  let q = '';
  let stageFilter = 'all';
  let vacancyFilter = 'all';
  const container = h('div', {});

  const render = () => {
    const active = document.activeElement;
    const activeId = active?.dataset?.role;
    const selStart = active?.selectionStart, selEnd = active?.selectionEnd;
    container.innerHTML = '';
    const list = s.candidates.filter(c => {
      if (stageFilter !== 'all' && c.stage !== stageFilter) return false;
      if (vacancyFilter !== 'all' && c.vacancyId !== vacancyFilter) return false;
      if (q) {
        const hay = `${c.name} ${c.email} ${c.headline} ${(c.skills||[]).join(' ')}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });

    container.appendChild(h('div', { class: 'section-title' }, [
      h('h2', {}, [`Candidates (${list.length})`]),
      h('div', { class: 'row-flex' }, [
        h('button', { class: 'btn primary', onclick: () => openUploadDialog(render) }, ['+ Upload CV']),
        h('button', { class: 'btn', onclick: () => openCandidateForm() }, ['Add Manually'])
      ])
    ]));

    const searchInput = h('input', { class: 'input', style: { flex: 1 }, placeholder: 'Search by name, skill, email...', value: q, oninput: e => { q = e.target.value; render(); }, dataset: { role: 'cand-search' } });
    container.appendChild(h('div', { class: 'card', style: { marginBottom: '14px' } }, [
      h('div', { class: 'row-flex' }, [
        searchInput,
        selectEl([['all','All stages'], ...STAGES.map(s => [s.id, s.label])], stageFilter, v => { stageFilter = v; render(); }),
        selectEl([['all','All vacancies'], ...s.vacancies.map(v => [v.id, v.title])], vacancyFilter, v => { vacancyFilter = v; render(); }),
      ])
    ]));
    if (activeId === 'cand-search') {
      requestAnimationFrame(() => {
        searchInput.focus();
        if (selStart != null) try { searchInput.setSelectionRange(selStart, selEnd); } catch {}
      });
    }

    if (!list.length) {
      container.appendChild(h('div', { class: 'card empty' }, ['No candidates match — upload a CV or adjust filters.']));
      return;
    }

    container.appendChild(h('div', { class: 'card', style: { padding: 0 } }, [
      h('table', { class: 'table' }, [
        h('thead', {}, [h('tr', {}, [
          h('th', {}, ['Candidate']), h('th', {}, ['Role']), h('th', {}, ['Skills']),
          h('th', {}, ['Stage']), h('th', {}, ['Days in stage']), h('th', {}, ['Added']), h('th', {}, [''])
        ])]),
        h('tbody', {}, list.map(c => h('tr', { onclick: () => openCandidate(c.id) }, [
          h('td', {}, [
            h('div', { class: 'row-flex' }, [
              avatar(c.name),
              h('div', {}, [
                h('div', { style: { fontWeight: 600 } }, [c.name]),
                h('div', { class: 'muted', style: { fontSize: '11px' } }, [`${c.headline || 'No headline'} · ${c.location || '—'}`])
              ])
            ])
          ]),
          h('td', {}, [roleName(c.vacancyId)]),
          h('td', {}, [h('div', { class: 'skill-chips' }, (c.skills || []).slice(0, 4).map(s => h('span', { class: 'chip' }, [s])))]),
          h('td', { onclick: e => e.stopPropagation() }, [stageSelect(c)]),
          h('td', {}, [daysInStage(c) + 'd']),
          h('td', {}, [relTime(c.createdAt)]),
          h('td', { onclick: e => e.stopPropagation() }, [
            h('button', { class: 'btn sm danger-ghost', onclick: () => { if (confirm(`Delete ${c.name}?`)) { deleteCandidate(c.id); toast('Deleted', 'ok'); } } }, ['Delete'])
          ])
        ])))
      ])
    ]));
  };

  render();
  return container;
}

function daysInStage(c) {
  const last = c.history?.[c.history.length - 1]?.at || c.createdAt;
  return daysBetween(last);
}

function roleName(id) {
  if (!id) return '—';
  return getState().vacancies.find(v => v.id === id)?.title || '—';
}

function avatar(name) {
  return h('div', { style: {
    width: '32px', height: '32px', borderRadius: '50%',
    background: 'linear-gradient(135deg,#6d8bff,#8b5cf6)',
    display: 'grid', placeItems: 'center', color: 'white', fontWeight: '700', fontSize: '12px'
  } }, [initials(name)]);
}

function selectEl(options, value, onChange) {
  return h('select', { class: 'input', style: { maxWidth: '200px' }, onchange: e => onChange(e.target.value) },
    options.map(([v, l]) => h('option', { value: v, ...(v === value ? { selected: '' } : {}) }, [l]))
  );
}

function stageSelect(c) {
  return h('select', { class: 'input', style: { maxWidth: '140px' }, onchange: e => moveCandidate(c.id, e.target.value) },
    STAGES.map(s => h('option', { value: s.id, ...(s.id === c.stage ? { selected: '' } : {}) }, [s.label]))
  );
}

// -------- Upload flow --------
export function openUploadDialog(afterParsed) {
  const s = getState();
  let pendingParsed = null;
  let pendingRaw = '';
  let pendingFile = null;

  const dz = h('div', { class: 'dropzone' }, ['Drop a CV here or click to choose (.pdf, .txt, .docx)']);
  const fileInput = h('input', { type: 'file', accept: '.pdf,.txt,.docx,.doc,text/plain,application/pdf', style: { display: 'none' } });
  dz.appendChild(fileInput);
  dz.addEventListener('click', () => fileInput.click());
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', async e => {
    e.preventDefault();
    dz.classList.remove('drag');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', e => { if (e.target.files[0]) handleFile(e.target.files[0]); });

  const preview = h('div', { style: { marginTop: '14px', display: 'none' } });

  const body = h('div', {}, [
    dz,
    h('div', { class: 'muted', style: { fontSize: '12px', marginTop: '8px' } }, [
      'We auto-extract name, email, phone, skills, experience, and education. You can edit before saving.'
    ]),
    preview,
  ]);

  const vacancySelect = h('select', { class: 'input' }, [
    h('option', { value: '' }, ['— No vacancy —']),
    ...s.vacancies.map(v => h('option', { value: v.id }, [v.title]))
  ]);

  const modal = openModal({
    title: 'Upload CV',
    body,
    actions: [
      { label: 'Cancel', onClick: close => close() },
      { label: 'Save Candidate', primary: true, onClick: (close) => {
          if (!pendingParsed) { toast('Upload a CV first', 'bad'); return; }
          const data = collectForm();
          data.vacancyId = vacancySelect.value || null;
          data.rawCv = pendingRaw;
          data.fileName = pendingFile?.name || '';
          createCandidate(data);
          toast('Candidate added', 'ok');
          close();
          afterParsed?.();
        } }
    ]
  });

  let formRefs = null;
  async function handleFile(file) {
    pendingFile = file;
    dz.textContent = `Parsing ${file.name}...`;
    try {
      const text = await extractText(file);
      pendingRaw = text;
      const parsed = parseCv(text, { fileName: file.name });
      pendingParsed = parsed;
      renderPreview(parsed);
      dz.textContent = `Parsed ${file.name} — edit and save.`;
    } catch (err) {
      console.error(err);
      dz.textContent = 'Failed to parse — try a different file.';
      toast('CV parsing failed', 'bad');
    }
  }

  function renderPreview(p) {
    preview.style.display = 'block';
    preview.innerHTML = '';
    const nameI = h('input', { class: 'input', value: p.name || '' });
    const emailI = h('input', { class: 'input', value: p.email || '' });
    const phoneI = h('input', { class: 'input', value: p.phone || '' });
    const locI = h('input', { class: 'input', value: p.location || '' });
    const headI = h('input', { class: 'input', value: p.headline || '' });
    const expI = h('input', { class: 'input', type: 'number', min: '0', value: p.experienceYears ?? '' });
    const skillsI = h('input', { class: 'input', value: (p.skills || []).join(', ') });

    formRefs = { nameI, emailI, phoneI, locI, headI, expI, skillsI };
    preview.appendChild(h('div', { class: 'form-grid' }, [
      wrap('Name', nameI), wrap('Email', emailI),
      wrap('Phone', phoneI), wrap('Location', locI),
      wrap('Headline', headI), wrap('Experience (years)', expI),
      wrap('Skills (comma separated)', skillsI, true),
      wrap('Link to vacancy', vacancySelect, true),
    ]));

    if (p.experience?.length) {
      preview.appendChild(h('div', { class: 'sep' }));
      preview.appendChild(h('label', {}, ['Parsed experience']));
      preview.appendChild(h('div', {}, p.experience.slice(0, 4).map(ex => h('div', { class: 'card', style: { padding: '8px 10px', marginTop: '6px' } }, [
        h('div', { style: { fontWeight: 600 } }, [ex.title]),
        ex.period ? h('div', { class: 'muted', style: { fontSize: '12px' } }, [ex.period]) : null,
        ex.bullets?.length ? h('ul', { style: { margin: '6px 0 0 18px' } }, ex.bullets.slice(0, 3).map(b => h('li', {}, [b]))) : null
      ]))));
    }
  }

  function wrap(label, el, full = false) {
    return h('div', { class: full ? 'full' : '' }, [h('label', {}, [label]), el]);
  }
  function collectForm() {
    if (!formRefs) return {};
    return {
      name: formRefs.nameI.value.trim(),
      email: formRefs.emailI.value.trim(),
      phone: formRefs.phoneI.value.trim(),
      location: formRefs.locI.value.trim(),
      headline: formRefs.headI.value.trim(),
      experienceYears: formRefs.expI.value ? Number(formRefs.expI.value) : null,
      skills: formRefs.skillsI.value.split(',').map(s => s.trim()).filter(Boolean),
      education: pendingParsed?.education || [],
      experience: pendingParsed?.experience || [],
    };
  }

  return modal;
}

// -------- Manual form --------
export function openCandidateForm(existing) {
  const data = { ...(existing || { stage: 'sourced' }) };
  const s = getState();
  const form = h('div', { class: 'form-grid' }, [
    field('Full Name', h('input', { class: 'input', value: data.name || '', oninput: e => data.name = e.target.value })),
    field('Email', h('input', { class: 'input', value: data.email || '', oninput: e => data.email = e.target.value })),
    field('Phone', h('input', { class: 'input', value: data.phone || '', oninput: e => data.phone = e.target.value })),
    field('Location', h('input', { class: 'input', value: data.location || '', oninput: e => data.location = e.target.value })),
    field('Headline', h('input', { class: 'input', value: data.headline || '', oninput: e => data.headline = e.target.value })),
    field('Experience (years)', h('input', { class: 'input', type: 'number', value: data.experienceYears ?? '', oninput: e => data.experienceYears = e.target.value ? Number(e.target.value) : null })),
    field('Source', h('input', { class: 'input', value: data.source || '', oninput: e => data.source = e.target.value, placeholder: 'LinkedIn / Referral / Career site' })),
    field('Vacancy', (() => {
      const sel = h('select', { class: 'input', onchange: e => data.vacancyId = e.target.value || null }, [
        h('option', { value: '' }, ['— None —']),
        ...s.vacancies.map(v => h('option', { value: v.id, ...(v.id === data.vacancyId ? { selected: '' } : {}) }, [v.title]))
      ]);
      return sel;
    })()),
    field('Skills (comma separated)', h('input', { class: 'input', value: (data.skills || []).join(', '), oninput: e => data.skills = e.target.value.split(',').map(s => s.trim()).filter(Boolean) }), true),
  ]);

  openModal({
    title: existing ? `Edit ${existing.name}` : 'Add Candidate',
    body: form,
    actions: [
      { label: 'Cancel', onClick: close => close() },
      { label: existing ? 'Save' : 'Add', primary: true, onClick: (close) => {
          if (!data.name?.trim()) { toast('Name required', 'bad'); return; }
          if (existing) updateCandidate(existing.id, data);
          else createCandidate(data);
          toast('Saved', 'ok');
          close();
        } }
    ]
  });
}

function field(label, input, full = false) {
  return h('div', { class: full ? 'full' : '' }, [h('label', {}, [label]), input]);
}

// -------- Candidate detail --------
export function openCandidate(id) {
  const c = getState().candidates.find(x => x.id === id);
  if (!c) return;
  const vac = c.vacancyId ? getState().vacancies.find(v => v.id === c.vacancyId) : null;
  const stageOrder = ['sourced','screening','interview','offer','hired'];

  openModal({
    title: c.name,
    size: '',
    body: h('div', {}, [
      h('div', { class: 'row-flex', style: { marginBottom: '12px' } }, [
        h('span', { class: 'chip info' }, [vac ? vac.title : 'Unassigned']),
        h('span', { class: 'chip' }, [`Stage: ${stageLabel(c.stage)}`]),
        h('span', { class: 'chip' }, [`Source: ${c.source || '—'}`]),
        c.experienceYears != null ? h('span', { class: 'chip' }, [`${c.experienceYears}y exp`]) : null,
      ]),
      h('div', { class: 'detail' }, [
        h('div', { class: 'block' }, [
          h('h4', {}, ['Contact']),
          h('div', {}, [c.email || '—']),
          h('div', {}, [c.phone || '—']),
          h('div', {}, [c.location || '—'])
        ]),
        h('div', { class: 'block' }, [
          h('h4', {}, ['Skills']),
          h('div', { class: 'skill-chips' }, (c.skills || []).map(s => h('span', { class: 'chip' }, [s])))
        ]),
        h('div', { class: 'block' }, [
          h('h4', {}, ['Experience']),
          c.experience?.length
            ? h('div', {}, c.experience.slice(0, 4).map(ex => h('div', { style: { marginBottom: '8px' } }, [
                h('div', { style: { fontWeight: 600, fontSize: '13px' } }, [ex.title]),
                ex.period ? h('div', { class: 'muted', style: { fontSize: '11px' } }, [ex.period]) : null
              ])))
            : h('div', { class: 'muted' }, ['No experience parsed.'])
        ]),
        h('div', { class: 'block' }, [
          h('h4', {}, ['Education']),
          c.education?.length
            ? h('div', {}, c.education.map(ed => h('div', { style: { marginBottom: '6px' } }, [
                h('div', { style: { fontWeight: 600, fontSize: '13px' } }, [ed.degree || ed.text.slice(0, 60)]),
                ed.year ? h('div', { class: 'muted', style: { fontSize: '11px' } }, [ed.year]) : null
              ])))
            : h('div', { class: 'muted' }, ['No education parsed.'])
        ]),
      ]),
      h('div', { class: 'sep' }),
      h('h4', { style: { color: 'var(--muted)', fontSize: '12px', textTransform: 'uppercase' } }, ['Pipeline']),
      h('div', { class: 'stage-timeline' }, stageOrder.map((st, i) => [
        h('div', { class: `t ${c.history?.some(x => x.stage === st) ? 'done' : ''}` }, [stageLabel(st)]),
        i < stageOrder.length - 1 ? h('span', { class: 'arrow' }, ['→']) : null
      ]).flat()),
      h('div', { class: 'sep' }),
      h('h4', { style: { color: 'var(--muted)', fontSize: '12px', textTransform: 'uppercase' } }, ['History']),
      h('div', {}, (c.history || []).map(h2 => h('div', { class: 'row-flex', style: { padding: '4px 0', borderBottom: '1px solid var(--border)' } }, [
        h('span', { class: 'chip' }, [stageLabel(h2.stage)]),
        h('span', { class: 'muted', style: { fontSize: '12px' } }, [fmtDate(h2.at)])
      ])))
    ]),
    actions: [
      { label: 'Edit', onClick: close => { close(); openCandidateForm(c); } },
      { label: 'Close', primary: true, onClick: close => close() }
    ]
  });
}
