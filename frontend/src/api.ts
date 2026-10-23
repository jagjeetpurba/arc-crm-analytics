export const getJSON = async (url: string) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
};
export const qs = (f: Record<string, string>) => {
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => v && v !== "all" && p.set(k, v));
  const s = p.toString();
  return s ? "?" + s : "";
};
