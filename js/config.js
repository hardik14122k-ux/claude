// Supabase config — set these via window globals before app.js loads,
// or hard-code them here for static hosting.
//
// In index.html, before the module script:
//   <script>
//     window.SUPABASE_URL  = 'https://xxxxx.supabase.co';
//     window.SUPABASE_ANON = 'eyJhbGciOi...';
//   </script>

export const SUPABASE_URL  = window.SUPABASE_URL  || '';
export const SUPABASE_ANON = window.SUPABASE_ANON || '';

if (!SUPABASE_URL || !SUPABASE_ANON) {
  console.warn('[config] SUPABASE_URL / SUPABASE_ANON not set — set them in index.html');
}
