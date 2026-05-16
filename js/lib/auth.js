// Thin wrapper around Supabase auth for sign-in/up/out + current-user fetch.
// The `users` table row tied to auth.uid() supplies company_id and role.

import { sb } from './supabase.js';
import { unwrap, HrmsError } from './errors.js';
import { rowToObj } from './mapper.js';

let _currentUser = null;
const subs = new Set();

export function onAuthChange(fn) { subs.add(fn); return () => subs.delete(fn); }
function emit() { subs.forEach(fn => { try { fn(_currentUser); } catch (e) { console.error(e); } }); }

export async function signIn(email, password) {
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw new HrmsError(error.message, { code: 'auth_failed', status: 401, cause: error });
  await loadCurrentUser();
  return data.user;
}

export async function signUp({ email, password, fullName, companyId, role = 'hr' }) {
  const { data, error } = await sb.auth.signUp({
    email, password,
    options: { data: { full_name: fullName, company_id: companyId, role } },
  });
  if (error) throw new HrmsError(error.message, { code: 'auth_failed', status: 400, cause: error });
  return data.user;
}

export async function signOut() {
  await sb.auth.signOut();
  _currentUser = null;
  emit();
}

export async function loadCurrentUser() {
  const { data: { user } } = await sb.auth.getUser();
  if (!user) { _currentUser = null; emit(); return null; }

  const profile = await unwrap(
    sb.from('users').select('*').eq('id', user.id).maybeSingle(),
    'Failed to load user profile');

  _currentUser = profile
    ? { ...rowToObj(profile), authId: user.id }
    : { authId: user.id, email: user.email, role: 'viewer', companyId: null };
  emit();
  return _currentUser;
}

export function currentUser() { return _currentUser; }

export function requireRole(...roles) {
  const u = _currentUser;
  if (!u) throw new HrmsError('Not signed in', { code: 'auth_required', status: 401 });
  if (u.role === 'admin') return;
  if (!roles.includes(u.role)) {
    throw new HrmsError(`Requires role: ${roles.join(' or ')}`, { code: 'forbidden', status: 403 });
  }
}

// Listen to Supabase auth state changes.
sb.auth.onAuthStateChange(() => loadCurrentUser());
