// Single Supabase client instance shared by every service.
// Uses the official UMD bundle loaded in index.html as `window.supabase`.

import { SUPABASE_URL, SUPABASE_ANON } from '../config.js';

if (!window.supabase || !window.supabase.createClient) {
  throw new Error('Supabase JS SDK not loaded — add the CDN script to index.html');
}

export const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON, {
  auth: { persistSession: true, autoRefreshToken: true },
});
