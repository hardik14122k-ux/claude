// Money formatting for the Indian context.
const FMT_INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const FMT_INR_PAISE = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function inr(n)      { return FMT_INR.format(Number(n) || 0); }
export function inrPaise(n) { return FMT_INR_PAISE.format(Number(n) || 0); }
export function round2(n)   { return Math.round((Number(n) || 0) * 100) / 100; }
