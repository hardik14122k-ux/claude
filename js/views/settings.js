import { h, toast } from '../ui.js';
import { getState, replaceState, resetAll } from '../store.js';

export function Settings() {
  return h('div', {}, [
    h('div', { class: 'section-title' }, [h('h2', {}, ['Settings & Data'])]),

    h('div', { class: 'card' }, [
      h('h3', { style: { margin: '0 0 10px' } }, ['About this app']),
      h('p', { class: 'muted' }, [
        'TalentTrack is a fully client-side recruitment tracker. All data lives in your browser\'s ',
        h('code', {}, ['localStorage']),
        '. CV parsing uses PDF.js + heuristics — no servers, no uploads.'
      ]),
    ]),

    h('div', { class: 'card', style: { marginTop: '16px' } }, [
      h('h3', { style: { margin: '0 0 10px' } }, ['Pipeline stages']),
      h('p', { class: 'muted' }, ['Default stages mirror those used in Greenhouse / Lever / Workable.']),
      h('ul', {}, [
        h('li', {}, ['Sourced — candidate identified']),
        h('li', {}, ['Screening — recruiter call / resume review']),
        h('li', {}, ['Interview — technical / onsite loops']),
        h('li', {}, ['Offer — offer extended']),
        h('li', {}, ['Hired / Rejected — terminal']),
      ])
    ]),

    h('div', { class: 'card', style: { marginTop: '16px' } }, [
      h('h3', { style: { margin: '0 0 10px' } }, ['Data export / import']),
      h('div', { class: 'row-flex' }, [
        h('button', { class: 'btn', onclick: exportJson }, ['Export JSON']),
        h('label', { class: 'btn', style: { cursor: 'pointer' } }, [
          'Import JSON',
          h('input', { type: 'file', accept: '.json', style: { display: 'none' }, onchange: importJson })
        ]),
        h('button', { class: 'btn danger-ghost', onclick: () => {
          if (confirm('Wipe ALL data? This cannot be undone.')) {
            resetAll();
            toast('Reset complete', 'ok');
          }
        } }, ['Reset all data']),
      ])
    ]),
  ]);
}

function exportJson() {
  const blob = new Blob([JSON.stringify(getState(), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `talenttrack-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast('Exported', 'ok');
}

async function importJson(e) {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    replaceState(parsed);
    toast('Imported', 'ok');
  } catch {
    toast('Invalid JSON', 'bad');
  }
}
