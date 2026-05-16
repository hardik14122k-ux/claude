// snake_case ↔ camelCase mapping for DB rows ⇆ JS objects.
// Keeps the rest of the JS code idiomatic without leaking DB conventions.

const toCamel = (s) => s.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
const toSnake = (s) => s.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase());

export function rowToObj(row) {
  if (row == null || typeof row !== 'object') return row;
  if (Array.isArray(row)) return row.map(rowToObj);
  const out = {};
  for (const [k, v] of Object.entries(row)) out[toCamel(k)] = v;
  return out;
}

export function objToRow(obj) {
  if (obj == null || typeof obj !== 'object') return obj;
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined) continue;
    out[toSnake(k)] = v;
  }
  return out;
}
