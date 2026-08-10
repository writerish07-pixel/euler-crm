export const inr = (n, opts = {}) => {
  const v = Number(n || 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: opts.decimals ?? 0,
    minimumFractionDigits: opts.decimals ?? 0,
  }).format(v);
};

export const num = (n) => new Intl.NumberFormat("en-IN").format(Number(n || 0));

export const compactInr = (n) => {
  const v = Number(n || 0);
  if (Math.abs(v) >= 10000000) return `₹${(v / 10000000).toFixed(2)} Cr`;
  if (Math.abs(v) >= 100000) return `₹${(v / 100000).toFixed(2)} L`;
  if (Math.abs(v) >= 1000) return `₹${(v / 1000).toFixed(1)}K`;
  return inr(v);
};

export const fmtDate = (d) => {
  if (!d) return "—";
  const s = String(d).split("T")[0];
  const dt = new Date(s);
  if (isNaN(dt)) return s;
  return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

/** Local calendar date as YYYY-MM-DD for `<input type="date">` defaults. */
export const todayISO = () => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};
