// Tiny DOM helpers used across views.

export function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (v == null || v === false) return;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'dataset') Object.entries(v).forEach(([dk, dv]) => (el.dataset[dk] = dv));
    else el.setAttribute(k, v === true ? '' : v);
  });
  const arr = Array.isArray(children) ? children : [children];
  arr.flat().forEach(c => {
    if (c == null || c === false) return;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  });
  return el;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

export function toast(message, kind = '') {
  const root = document.getElementById('toast-root');
  const el = h('div', { class: `toast ${kind}` }, [message]);
  root.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(10px)'; }, 2400);
  setTimeout(() => el.remove(), 2800);
}

export function openModal({ title, body, actions = [], size = '' }) {
  const root = document.getElementById('modal-root');
  const close = () => { root.innerHTML = ''; };
  const modal = h('div', { class: 'modal-backdrop', onclick: (e) => { if (e.target === e.currentTarget) close(); } }, [
    h('div', { class: `modal ${size}` }, [
      h('div', { class: 'modal-head' }, [
        h('div', {}, [h('strong', {}, [title])]),
        h('button', { class: 'btn sm ghost', onclick: close }, ['Close'])
      ]),
      h('div', { class: 'modal-body' }, [body]),
      actions.length ? h('div', { class: 'modal-foot' }, actions.map(a => h('button', {
        class: `btn ${a.primary ? 'primary' : ''}`,
        onclick: () => a.onClick?.(close)
      }, [a.label]))) : null
    ])
  ]);
  root.appendChild(modal);
  return { close };
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function relTime(iso) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s/60)}m ago`;
  if (s < 86400) return `${Math.floor(s/3600)}h ago`;
  if (s < 86400*7) return `${Math.floor(s/86400)}d ago`;
  return fmtDate(iso);
}

export function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(n => n[0].toUpperCase()).join('') || '?';
}
