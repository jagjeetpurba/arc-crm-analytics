export const fmt = (v: any, f?: string) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";           // NFR-05: absent shows as —
  if (f === "pct") return (v * 100).toFixed(1) + "%";
  if (f === "int") return Math.round(v).toLocaleString("en-US");
  if (f === "aed") return Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + "M" : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(0) + "K" : Math.round(v).toString();
  if (f === "aed_full") return Math.round(v).toLocaleString("en-US");
  return Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : Number(v).toFixed(1);
};
