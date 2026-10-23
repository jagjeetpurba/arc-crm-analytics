import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getJSON } from "./api";
import { useUrlState } from "./useUrlState";
import { Widget } from "./widgets";

export default function App() {
  const qc = useQueryClient();
  const [url, setUrl] = useUrlState();
  const [dataVersion, setDataVersion] = useState(0);
  const [live, setLive] = useState<"connecting" | "live" | "offline">("connecting");
  const [toast, setToast] = useState<string | null>(null);

  const spec = useQuery({ queryKey: ["spec", dataVersion], queryFn: () => getJSON("/api/spec"), placeholderData: (p) => p });

  // Live sync: the backend pushes a version bump whenever the ERP changed (healing agent / watcher / ingest)
  useEffect(() => {
    const es = new EventSource("/api/events");
    es.addEventListener("hello", (e: any) => { setLive("live"); setDataVersion(JSON.parse(e.data).version); });
    es.addEventListener("data_version", (e: any) => {
      const ev = JSON.parse(e.data);
      setDataVersion(ev.version);
      const what = ev.changed?.length ? ev.changed.join(", ") : ev.spec_changed ? "dashboard spec" : "data";
      setToast(`Updated from ERP · ${what} · v${ev.version}`);
      setTimeout(() => setToast(null), 6000);
    });
    es.onerror = () => setLive("offline");
    es.onopen = () => setLive("live");
    return () => es.close();
  }, []);

  const s = spec.data;
  const filters = useMemo(() => {
    if (!s) return {} as Record<string, string>;
    const f: Record<string, string> = { period: url.period ?? s.filters.period.default };
    ["client_manager", "vertical", ...Object.keys(s.filters.dynamic)].forEach((k) => url[k] && (f[k] = url[k]));
    return f;
  }, [s, url]);

  if (spec.isLoading || !s) return <div className="boot">Loading dashboard spec…</div>;
  if (spec.isError) return <div className="boot err">Cannot reach the analytics API.</div>;

  const pages: any[] = s.pages;
  const page = pages.find((p) => p.id === url.page) ?? pages[0];
  const dyn = Object.entries<any>(s.filters.dynamic);

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="dot" />{s.title}</div>
        <div className={`live ${live}`} title={`data v${dataVersion}`}><i />{live === "live" ? "Live" : live === "offline" ? "Reconnecting…" : "Connecting"} · as of {s.as_of}</div>
      </header>

      <div className="filters" role="search">
        <label>Period
          <select value={filters.period} onChange={(e) => setUrl({ period: e.target.value })}>
            {s.filters.period.options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select></label>
        <label>Client manager
          <select value={url.client_manager ?? ""} onChange={(e) => setUrl({ client_manager: e.target.value })}>
            <option value="">All</option>{s.filters.client_manager.options.map((o: string) => <option key={o}>{o}</option>)}
          </select></label>
        <label>Vertical
          <select value={url.vertical ?? ""} onChange={(e) => setUrl({ vertical: e.target.value })}>
            <option value="">All</option>{s.filters.vertical.options.map((o: string) => <option key={o}>{o}</option>)}
          </select></label>
        {dyn.map(([k, d]) => (
          <label key={k} className="dyn">{d.label} <em>new</em>
            <select value={url[k] ?? ""} onChange={(e) => setUrl({ [k]: e.target.value })}>
              <option value="">All</option>{d.options.map((o: string) => <option key={o}>{o}</option>)}
            </select></label>
        ))}
      </div>

      <nav aria-label="Pages">
        {pages.map((p) => (
          <button key={p.id} className={p.id === page.id ? "on" : ""} onClick={() => setUrl({ page: p.id })}>
            {p.title}{p.auto && <em className="tag">{p.tag === "NEW OBJECT" ? "new" : "auto"}</em>}
          </button>
        ))}
      </nav>

      <main>
        <div className="question"><b>{page.question}</b>{page.note && <span>{page.note}</span>}</div>
        <div className="grid">
          {page.widgets.map((w: any) => (
            <section key={w.id} className={`w w${w.width ?? 12}`}>
              <Widget w={w} filters={filters} dataVersion={dataVersion} spec={s} />
            </section>
          ))}
        </div>
      </main>
      {toast && <div className="toast" role="status" onClick={() => setToast(null)}>{toast}</div>}
    </div>
  );
}
