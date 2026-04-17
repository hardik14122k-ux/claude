// Router + global event wiring.

import { subscribe, resetAll } from './store.js';
import { seedDemoData } from './seed.js';
import { toast } from './ui.js';

import { Dashboard } from './views/dashboard.js';
import { Vacancies, openVacancyForm } from './views/vacancies.js';
import { Candidates, openUploadDialog, openCandidate } from './views/candidates.js';
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

document.getElementById('quick-upload').addEventListener('click', () => openUploadDialog(() => {
  if (currentRoute === 'candidates' || currentRoute === 'pipeline' || currentRoute === 'dashboard') render();
}));

document.getElementById('quick-vacancy').addEventListener('click', () => openVacancyForm());

document.getElementById('seed-btn').addEventListener('click', () => {
  const added = seedDemoData();
  if (added) { toast('Demo data loaded', 'ok'); render(); }
  else toast('Already have data — reset first', 'bad');
});

document.getElementById('reset-btn').addEventListener('click', () => {
  if (confirm('Reset ALL data? This cannot be undone.')) { resetAll(); toast('Reset', 'ok'); render(); }
});

// Global search: jumps to candidates view with filter, or opens a candidate directly on Enter.
const search = document.getElementById('globalSearch');
search.addEventListener('keydown', e => {
  if (e.key === 'Enter' && search.value.trim()) {
    navigate('candidates');
    // Populate the in-view search using a microtask — simple approach:
    setTimeout(() => {
      const inViewSearch = viewEl.querySelector('input[placeholder^="Search by name"]');
      if (inViewSearch) {
        inViewSearch.value = search.value;
        inViewSearch.dispatchEvent(new Event('input'));
      }
    }, 10);
  }
});

// Reactive re-render on any state change (cheap for this scale).
subscribe(() => render());

// Initial route from hash.
navigate((location.hash || '#dashboard').slice(1));

// Nudge the user to load demo data on first run.
if (!localStorage.getItem('talenttrack.v1')) {
  setTimeout(() => toast('Tip: click "Load demo data" in the sidebar to explore.', ''), 400);
}
