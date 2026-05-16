// Vanilla resource hook: wraps an async fetcher in a tiny observable
// with { data, loading, error } and re-fetch on demand. No framework needed.
//
//   const r = useResource(getDashboardData);
//   r.subscribe(state => render(state));
//   r.load();
//   r.reload();

export function useResource(fetcher) {
  const state = { data: null, loading: false, error: null };
  const subs = new Set();

  const emit = () => subs.forEach(fn => { try { fn({ ...state }); } catch (e) { console.error(e); } });

  async function load(...args) {
    state.loading = true; state.error = null; emit();
    try {
      state.data = await fetcher(...args);
    } catch (err) {
      state.error = err;
    } finally {
      state.loading = false; emit();
    }
    return state.data;
  }

  return {
    get state() { return { ...state }; },
    subscribe(fn) { subs.add(fn); fn({ ...state }); return () => subs.delete(fn); },
    load,
    reload: load,
  };
}
