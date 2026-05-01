// Reactive auth state. Subscribe to get notified when the current user changes.

import { currentUser, onAuthChange, loadCurrentUser } from '../lib/auth.js';

let _hydrated = false;

export function useAuth() {
  if (!_hydrated) { _hydrated = true; loadCurrentUser().catch(() => {}); }
  const subs = new Set();
  const off = onAuthChange((u) => subs.forEach(fn => fn(u)));
  return {
    get user() { return currentUser(); },
    subscribe(fn) { subs.add(fn); fn(currentUser()); return () => { subs.delete(fn); off(); }; },
  };
}
