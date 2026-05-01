// User profile management. Auth.users is owned by Supabase Auth;
// the `users` row holds profile + role + company link.

import { sb } from '../lib/supabase.js';
import { unwrap, HrmsError } from '../lib/errors.js';
import { rowToObj, objToRow } from '../lib/mapper.js';
import { isEmail } from '../lib/validators.js';

const ROLES = new Set(['admin','hr','hiring_manager','viewer']);

export async function listUsers() {
  return rowToObj(await unwrap(
    sb.from('users').select('*').order('created_at', { ascending: false }),
    'Failed to load users'));
}

export async function getUser(id) {
  return rowToObj(await unwrap(
    sb.from('users').select('*').eq('id', id).single(),
    'User not found'));
}

// Create profile after auth.signUp. Pass the auth user id explicitly.
export async function createUserProfile({ id, email, fullName, companyId, role = 'hr' }) {
  if (!id) throw new HrmsError('auth user id required', { code: 'validation_error', status: 400 });
  if (!isEmail(email)) throw new HrmsError('valid email required', { code: 'validation_error', status: 400 });
  if (!ROLES.has(role)) throw new HrmsError(`Invalid role: ${role}`, { code: 'validation_error', status: 400 });

  const row = objToRow({ id, email, fullName: fullName || null, companyId, role, isActive: true });
  const data = await unwrap(sb.from('users').insert(row).select().single(), 'Failed to create user profile');
  return rowToObj(data);
}

export async function updateUser(id, patch) {
  if (patch.role && !ROLES.has(patch.role)) throw new HrmsError(`Invalid role: ${patch.role}`, { code: 'validation_error', status: 400 });
  const data = await unwrap(
    sb.from('users').update(objToRow(patch)).eq('id', id).select().single(),
    'Failed to update user');
  return rowToObj(data);
}

export async function deactivateUser(id) {
  return updateUser(id, { isActive: false });
}
