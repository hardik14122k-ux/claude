// Router + global event wiring (Supabase-backed).

import { subscribe, refreshAll } from './store.js';
import { seedDemoData, resetAllData } from './seed.js';
import { toast } from './ui.js';

import { Dashboard } from './views/dashboard.js';
import { Vacancies, openVacancyForm } from './views/vacancies.js';
import { Candidates, openUploadDialog } from './views/candidates.js';
import { Pipeline } from './views/pipeline.js';
import { Interviews } from './views/interviews.js';
import { Reports } from './views/reports.js';
import { Settings } from './views/settings.js';

const routes = {
  dashboard: Dashboard,
  vacancies: Vacancies,
  candidates: Candidates,
  pipeline: Pipeline,
  interviews: Interviews,
  reports: Reports,
  settings: Settings,
};

let currentRoute = 'dashboard';
const viewEl = document.getElementById('view');

function render() {
  const View = routes[currentRoute] || Dashboard;
  viewEl.innerHTML = '';
  viewEl.appendChild(View());
  document.querySelectorAll('#nav .nav-item').forEach(a => {
    a.classList.toggle('active', a.dataset.route === currentRoute);
  });
  const hash = '#' + currentRoute;
  if (location.hash !== hash) history.replaceState(null, '', hash);
}

function navigate(route) {
  if (!routes[route]) route = 'dashboard';
  currentRoute = route;
  render();
}

document.getElementById('nav').addEventListener('click', e => {
  const a = e.target.closest('.nav-item');
  if (!a) return;
  e.preventDefault();
  navigate(a.dataset.route);
});

window.addEventListener('hashchange', () => navigate((location.hash || '#dashboard').slice(1)));

document.getElementById('quick-upload').addEventListener('click', () => openUploadDialog(() => render()));
document.getElementById('quick-vacancy').addEventListener('click', () => openVacancyForm());

document.getElementById('seed-btn').addEventListener('click', async () => {
  try {
    const added = await seedDemoData();
    if (added) { toast('Demo data loaded', 'ok'); await refreshAll(); render(); }
    else toast('Already have data — reset first', 'bad');
  } catch (err) { toast('Seed failed: ' + err.message, 'bad'); }
});

document.getElementById('reset-btn').addEventListener('click', async () => {
  if (!confirm('Reset ALL data? This cannot be undone.')) return;
  try { await resetAllData(); toast('Reset', 'ok'); await refreshAll(); render(); }
  catch (err) { toast('Reset failed: ' + err.message, 'bad'); }
});

// Global search jumps to candidates view with the term applied.
const search = document.getElementById('globalSearch');
search.addEventListener('keydown', e => {
  if (e.key === 'Enter' && search.value.trim()) {
    navigate('candidates');
    setTimeout(() => {
      const inViewSearch = viewEl.querySelector('input[placeholder^="Search by name"]');
      if (inViewSearch) {
        inViewSearch.value = search.value;
        inViewSearch.dispatchEvent(new Event('input'));
      }
    }, 10);
  }
});

// Re-render on any cache change (cheap at this scale).
subscribe('*', () => render());

// Initial route from hash.
navigate((location.hash || '#dashboard').slice(1));
