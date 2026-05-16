// Date helpers — kept tiny and dependency-free.

export const ISO = (d = new Date()) => new Date(d).toISOString();
export const YMD = (d = new Date()) => new Date(d).toISOString().slice(0, 10);

export function daysBetween(a, b = new Date()) {
  return Math.max(0, Math.floor((new Date(b) - new Date(a)) / 86400000));
}

export function sameMonth(a, b = new Date()) {
  if (!a) return false;
  const x = new Date(a), y = new Date(b);
  return x.getMonth() === y.getMonth() && x.getFullYear() === y.getFullYear();
}

// Indian fiscal year (Apr–Mar). Returns the YYYY-04-01 for the FY containing `d`.
export function fiscalYearStart(d = new Date()) {
  const dt = new Date(d);
  const y = dt.getFullYear();
  const fy = dt.getMonth() < 3 ? y - 1 : y;
  return `${fy}-04-01`;
}

export function startOfMonth(d = new Date()) {
  const x = new Date(d); x.setDate(1); x.setHours(0,0,0,0);
  return x;
}

export function endOfMonth(d = new Date()) {
  const x = new Date(d); x.setMonth(x.getMonth() + 1, 0); x.setHours(23,59,59,999);
  return x;
}

export function workingDaysInMonth(year, month) {
  const last = new Date(year, month, 0).getDate();
  let n = 0;
  for (let day = 1; day <= last; day++) {
    const wd = new Date(year, month - 1, day).getDay();
    if (wd !== 0 && wd !== 6) n++;
  }
  return n;
}
