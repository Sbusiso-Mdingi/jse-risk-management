export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "n/a" : `${v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 2) =>
  v == null ? "n/a" : `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}`;

export const fmtDate = (iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-ZA", { timeZone: "UTC", ...opts });

export const short = (ticker: string) => ticker.replace(".JO", "");
