import { h } from '../ui.js';

export function EmptyState({ title, hint = '', action } = {}) {
  return h('div', { class: 'empty' }, [
    h('div', { style: { fontWeight: 600, marginBottom: '4px' } }, [title]),
    hint ? h('div', { class: 'muted small' }, [hint]) : null,
    action ? h('div', { style: { marginTop: '12px' } }, [action]) : null,
  ]);
}

export function ErrorState({ message, onRetry }) {
  return h('div', { class: 'empty' }, [
    h('div', { style: { fontWeight: 600, color: '#ff8b8b', marginBottom: '4px' } }, ['Something went wrong']),
    h('div', { class: 'muted small' }, [message || 'Unexpected error']),
    onRetry ? h('button', { class: 'btn sm', style: { marginTop: '12px' }, onclick: onRetry }, ['Retry']) : null,
  ]);
}
