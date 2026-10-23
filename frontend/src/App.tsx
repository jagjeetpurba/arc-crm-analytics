import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Radio } from "lucide-react";
import { getJSON } from "./api";
import { useUrlState } from "./useUrlState";
import { Widget } from "./widgets";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const ALL = "__all__";   // Radix Select cannot hold an empty-string value

function Filter({ label, value, onChange, options, isNew }: any) {
  return (
    <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
      <span className="flex items-center gap-1.5">{label}{isNew && <Badge variant="secondary" className="px-1.5 py-0 text-[9px]">new</Badge>}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 min-w-[160px] bg-card text-[13px] normal-case tracking-normal text-foreground"><SelectValue /></SelectTrigger>
        <SelectContent>{options.map((o: any) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
      </Select>
    </label>
  );
}

export default function App() {
  const [url, setUrl] = useUrlState();
  const [dataVersion, setDataVersion] = useState(0);
  const [live, setLive] = useState<"connecting" | "live" | "offline">("connecting");
  const [toast, setToast] = useState<string | null>(null);

  const spec = useQuery({ queryKey: ["spec", dataVersion], queryFn: () => getJSON("/api/spec"), placeholderData: (p) => p });

  // Live sync: the backend pushes a version bump whenever the ERP changed (healing agent / watcher / webhook / ingest)
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

  if (spec.isLoading || !s) return <div className="p-16 text-center text-muted-foreground">Loading dashboard spec…</div>;
  if (spec.isError) return <div className="p-16 text-center text-destructive">Cannot reach the analytics API.</div>;

  const pages: any[] = s.pages;
  const page = pages.find((p) => p.id === url.page) ?? pages[0];
  const dyn = Object.entries<any>(s.filters.dynamic);
  const opts = (arr: string[]) => [{ value: ALL, label: "All" }, ...arr.map((o) => ({ value: o, label: o }))];

  return (
    <div className="mx-auto max-w-[1280px] overflow-x-hidden px-5 pb-16">
      <header className="flex items-center justify-between pb-2 pt-4">
        <div className="flex items-center gap-2.5 text-lg font-bold"><span className="size-2.5 rounded-full bg-brand" />{s.title}</div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground" title={`data v${dataVersion}`}>
          <Radio className={cn("size-3.5", live === "live" ? "text-green-600" : live === "offline" ? "text-destructive" : "text-muted-foreground")} />
          {live === "live" ? "Live" : live === "offline" ? "Reconnecting…" : "Connecting"} · as of {s.as_of}
        </div>
      </header>

      <div className="flex flex-wrap gap-3 py-2.5" role="search">
        <Filter label="Period" value={filters.period} onChange={(v: string) => setUrl({ period: v })} options={s.filters.period.options} />
        <Filter label="Client manager" value={url.client_manager ?? ALL} onChange={(v: string) => setUrl({ client_manager: v === ALL ? null : v })} options={opts(s.filters.client_manager.options)} />
        <Filter label="Vertical" value={url.vertical ?? ALL} onChange={(v: string) => setUrl({ vertical: v === ALL ? null : v })} options={opts(s.filters.vertical.options)} />
        {dyn.map(([k, d]) => (
          <Filter key={k} isNew label={d.label} value={url[k] ?? ALL} onChange={(v: string) => setUrl({ [k]: v === ALL ? null : v })} options={opts(d.options)} />
        ))}
      </div>

      <Tabs value={page.id} onValueChange={(v) => setUrl({ page: v })}>
        <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-b bg-transparent p-0">
          {pages.map((p) => (
            <TabsTrigger key={p.id} value={p.id}
              className="rounded-none border-0 border-b-2 border-transparent px-3.5 py-2.5 text-muted-foreground shadow-none data-[state=active]:border-0 data-[state=active]:border-b-2 data-[state=active]:border-brand data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none">
              {p.title}
              {p.auto && <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-[9px] uppercase">{p.tag === "NEW OBJECT" ? "new" : "auto"}</Badge>}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <main>
        <div className="flex flex-col gap-0.5 pb-1 pt-4"><b>{page.question}</b>{page.note && <span className="text-xs text-muted-foreground">{page.note}</span>}</div>
        <div className="mt-2.5 grid grid-cols-12 gap-3.5">
          {page.widgets.map((w: any) => (
            <section key={w.id} className={cn("min-w-0 col-span-12",
              w.width === 6 && "md:col-span-6", w.width === 5 && "md:col-span-5", w.width === 7 && "md:col-span-7")}>
              <Widget w={w} filters={filters} dataVersion={dataVersion} spec={s} />
            </section>
          ))}
        </div>
      </main>
      {toast && (
        <button type="button" role="status" onClick={() => setToast(null)}
          className="fixed bottom-5 right-5 rounded-lg bg-primary px-3.5 py-2.5 text-sm text-primary-foreground shadow-lg">{toast}</button>
      )}
    </div>
  );
}
