import { useCallback, useEffect, useState } from "react";

// FR-23: all filter + page state lives in the URL so a view can be shared/reloaded identically.
export function useUrlState(): [Record<string, string>, (patch: Record<string, string | null>) => void] {
  const read = () => Object.fromEntries(new URLSearchParams(window.location.search));
  const [s, setS] = useState(read);
  useEffect(() => { const h = () => setS(read()); window.addEventListener("popstate", h); return () => window.removeEventListener("popstate", h); }, []);
  const set = useCallback((patch: Record<string, string | null>) => {
    const p = new URLSearchParams(window.location.search);
    Object.entries(patch).forEach(([k, v]) => (v === null || v === "" ? p.delete(k) : p.set(k, v)));
    window.history.pushState({}, "", "?" + p.toString());
    setS(read());
  }, []);
  return [s, set];
}
