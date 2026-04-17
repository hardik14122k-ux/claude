import { h, initials } from '../ui.js';
import { getState, STAGES, moveCandidate, daysBetween } from '../store.js';
import { openCandidate } from './candidates.js';

export function Pipeline() {
  const s = getState();
  let vacancyId = s.vacancies[0]?.id || 'all';

  const root = h('div', {});
  const render = () => {
    root.innerHTML = '';
    root.appendChild(h('div', { class: 'section-title' }, [
      h('h2', {}, ['Pipeline']),
      h('select', { class: 'input', style: { maxWidth: '260px' }, onchange: e => { vacancyId = e.target.value; render(); } }, [
        h('option', { value: 'all', ...(vacancyId === 'all' ? { selected: '' } : {}) }, ['All Vacancies']),
        ...s.vacancies.map(v => h('option', { value: v.id, ...(v.id === vacancyId ? { selected: '' } : {}) }, [v.title]))
      ])
    ]));

    const filtered = s.candidates.filter(c => vacancyId === 'all' || c.vacancyId === vacancyId);
    const byStage = Object.fromEntries(STAGES.map(st => [st.id, []]));
    filtered.forEach(c => (byStage[c.stage] || (byStage[c.stage] = [])).push(c));

    const board = h('div', { class: 'kanban' }, STAGES.map(stage => {
      const col = h('div', { class: 'column', dataset: { stage: stage.id } }, [
        h('div', { class: 'column-head' }, [
          h('div', { class: 'title' }, [stage.label]),
          h('span', { class: 'count' }, [String((byStage[stage.id] || []).length)])
        ]),
        h('div', { class: 'column-body' }, (byStage[stage.id] || []).map(c => kanbanCard(c)))
      ]);
      col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drag-over'); });
      col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
      col.addEventListener('drop', e => {
        e.preventDefault();
        col.classList.remove('drag-over');
        const id = e.dataTransfer.getData('text/id');
        if (id) { moveCandidate(id, stage.id); }
      });
      return col;
    }));

    root.appendChild(board);

    if (!filtered.length) {
      root.appendChild(h('div', { class: 'card empty', style: { marginTop: '16px' } }, ['No candidates in this pipeline yet.']));
    }
  };

  render();
  return root;
}

function kanbanCard(c) {
  const last = c.history?.[c.history.length - 1]?.at || c.createdAt;
  const d = daysBetween(last);
  const card = h('div', { class: 'kcard', draggable: 'true', onclick: () => openCandidate(c.id) }, [
    h('div', { class: 'row-flex' }, [
      h('div', { style: { width: '28px', height: '28px', borderRadius: '50%', background: 'linear-gradient(135deg,#6d8bff,#8b5cf6)', display: 'grid', placeItems: 'center', fontSize: '11px', fontWeight: 700 } }, [initials(c.name)]),
      h('div', {}, [
        h('div', { class: 'n' }, [c.name]),
        h('div', { class: 'm' }, [c.headline || '—'])
      ])
    ]),
    h('div', { class: 'r' }, (c.skills || []).slice(0, 3).map(s => h('span', { class: 'chip' }, [s]))),
    h('div', { class: 'r' }, [
      h('span', { class: `chip ${d > 14 ? 'bad' : d > 7 ? 'warn' : 'ok'}` }, [`${d}d in stage`])
    ])
  ]);
  card.addEventListener('dragstart', e => {
    e.dataTransfer.setData('text/id', c.id);
    e.dataTransfer.effectAllowed = 'move';
  });
  return card;
}
