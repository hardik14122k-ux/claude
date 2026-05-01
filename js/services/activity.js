// Activity log reader. Writes happen automatically via DB triggers.

import { sb } from '../lib/supabase.js';
import { unwrap } from '../lib/errors.js';
import { rowToObj } from '../lib/mapper.js';

export async function listActivity({ limit = 50 } = {}) {
  return rowToObj(await unwrap(
    sb.from('activity_logs').select('*').order('created_at', { ascending: false }).limit(limit),
    'Failed to load activity'));
}

// Manual log helper (for client-side events that don't hit a trigger).
export async function logActivity({ type, message, meta = {}, entityType = null, entityId = null }) {
  await unwrap(sb.from('activity_logs').insert({
    type, message, meta, entity_type: entityType, entity_id: entityId,
  }), 'Failed to log activity');
}
