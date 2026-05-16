// Normalize Supabase / network errors into a single shape the UI can use.

export class HrmsError extends Error {
  constructor(message, { code = 'unknown', cause = null, status = 500 } = {}) {
    super(message);
    this.name   = 'HrmsError';
    this.code   = code;
    this.status = status;
    this.cause  = cause;
  }
}

export function fromSupabase(err, fallback = 'Unexpected database error') {
  if (!err) return null;
  // PostgREST error shape: { message, details, hint, code }
  return new HrmsError(err.message || fallback, {
    code: err.code || 'pg_error',
    status: err.status || 500,
    cause: err,
  });
}

// Wraps a Supabase call: throws HrmsError on { error }, returns data otherwise.
export async function unwrap(promise, fallback = 'Operation failed') {
  const { data, error } = await promise;
  if (error) throw fromSupabase(error, fallback);
  return data;
}
