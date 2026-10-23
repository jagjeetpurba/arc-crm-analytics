import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { Info } from "lucide-react";
import { getJSON, qs } from "./api";
import { fmt } from "./format";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const ALL = "__all__";

export function Widget({ w, filters, dataVersion, spec }: any) {
  const q = useQuery({
    queryKey: ["w", w.id, filters, dataVersion],
    queryFn: () => getJSON(`/api/widget/${w.id}${qs(filters)}`),
    placeholderData: (p) => p,
  });
  const [drill, setDrill] = useState<any>(null);
  if (q.isLoading) return <Skeleton className="h-40 w-full" />;
  if (q.isError) return <Alert variant="destructive"><AlertDescription>Could not load {w.id}</AlertDescription></Alert>;
  const p = q.data.payload;
  const body = (() => {
    switch (w.type) {
      case "kpi_strip": return <KpiStrip p={p} />;
      case "bar": case "line":
        return <Chart w={w} p={p} onBar={(key: string) => w.query?.kpi && setDrill({ kpi: w.query.kpi, key, group_by: w.query.group_by })} />;
      case "table": return <DataTable p={p} />;
      case "exceptions": return <Exceptions filters={filters} dataVersion={dataVersion} />;
      case "predict_forecast": return <PredictForecast p={p} />;
      case "predict_drivers": return <PredictDrivers p={p} />;
      case "predict_deals": return <PredictDeals p={p} />;
      default: return <Alert variant="destructive"><AlertDescription>Unknown widget type {w.type}</AlertDescription></Alert>;
    }
  })();
  const bare = w.type === "kpi_strip";      // KPI strip draws its own cards
  return (
    <>
      {bare ? body : (
        <Card className="gap-3 py-4">
          {w.title && (
            <CardHeader className="px-4">
              <CardTitle className="flex items-center text-[13px] font-semibold">
                {w.title}{w.auto && <Badge variant="secondary" className="ml-2 px-1.5 py-0 text-[9px] uppercase">auto</Badge>}
                <ScopeBtn scope={p.scope} />
              </CardTitle>
            </CardHeader>
          )}
          <CardContent className="px-4">{body}</CardContent>
        </Card>
      )}
      {drill && <Drill d={drill} filters={filters} onClose={() => setDrill(null)} />}
    </>
  );
}

function ScopeLine({ scope }: any) {
  if (!scope) return null;
  const ign = Object.keys(scope.filters_ignored ?? {});
  return (
    <div className="mt-1.5 text-[11px] text-muted-foreground">
      {scope.period ? `Period ${scope.period}` : "All dates"}{scope.governing_date ? ` on ${scope.governing_date}` : ""} · {scope.record_count ?? "—"} records · as of {scope.as_of}
      {ign.length > 0 && <span className="text-amber-700"> · not applied: {ign.join(", ")}</span>}
    </div>
  );
}

function ScopeBtn({ scope }: any) {
  if (!scope) return null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="ml-1.5 size-5 rounded-full text-muted-foreground" aria-label="Definition, date and exclusions"><Info className="size-3.5" /></Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-1.5 text-xs font-normal normal-case tracking-normal">
        {scope.definition && <Row k="Definition" v={scope.definition} />}
        <Row k="Governing date" v={scope.governing_date ?? "—"} />
        <Row k="Exclusions" v={scope.exclusions ?? "—"} />
        <Row k="Records" v={`${scope.record_count ?? "—"} · as of ${scope.as_of}`} />
        {Object.entries(scope.filters_applied ?? {}).map(([k, v]: any) => <Row key={k} k="Applied" v={`${k}: ${String(v)}`} />)}
        {Object.entries(scope.filters_ignored ?? {}).map(([k, v]: any) => <Row key={k} k="Not applied" v={`${k}: ${String(v)}`} warn />)}
      </PopoverContent>
    </Popover>
  );
}
const Row = ({ k, v, warn }: any) => (
  <p className={cn("m-0", warn && "text-amber-700")}><b className="block text-[10px] uppercase text-muted-foreground">{k}</b>{v}</p>
);

function KpiStrip({ p }: any) {
  return (
    <div className="space-y-2.5">
      {p.comparison_flag && <Alert role="alert" className="border-amber-300 bg-amber-50 text-amber-900"><AlertDescription className="text-amber-900">{p.comparison_flag}</AlertDescription></Alert>}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
        {p.items.map((i: any) => {
          const brand = ["quarterly_gp_target", "open_forecast_gp", "weighted_open_gp"].includes(i.id);   // accent reserved for target/forecast
          return (
            <Card key={i.id} className="gap-1 py-3">
              <CardContent className="px-3.5">
                <div className="flex items-center text-[11px] uppercase tracking-wide text-muted-foreground">{i.label}<ScopeBtn scope={i.scope} /></div>
                <div className={cn("my-0.5 text-[26px] font-bold", brand && "text-brand")}>{fmt(i.value, i.format)}</div>
                {i.vs_target != null && <div className="text-xs text-muted-foreground">{fmt(i.vs_target, "pct")} of target · gap {fmt(i.gap, "aed")}</div>}
                <ScopeLine scope={i.scope} />
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Empty({ scope }: any) { return <div className="p-6 text-center text-muted-foreground">— no records in this scope<ScopeLine scope={scope} /></div>; }

function Chart({ w, p, onBar }: any) {
  const rows = (p.rows ?? []).map((r: any) => ({ key: r.key, value: r.value }));
  if (!rows.length) return <Empty scope={p.scope} />;
  const kind = p.format ?? "num";
  const brand = kind === "aed" && /forecast|open|expected/i.test(w.title ?? "");
  const horizontal = rows.length > 6 && !(w.query?.group_by ?? "").includes(":month");
  const config = { value: { label: p.label ?? w.title ?? "Value", color: brand ? "var(--accent-brand)" : "var(--chart-1)" } } satisfies ChartConfig;
  const tick = (v: number) => fmt(v, kind);
  const tip = <ChartTooltipContent formatter={(v: any) => <span className="font-mono font-medium tabular-nums">{fmt(Number(v), kind === "aed" ? "aed_full" : kind)}</span>} />;
  const height = horizontal ? Math.max(220, rows.length * 26 + 30) : 240;
  return (
    <>
      <ChartContainer config={config} className="w-full" style={{ height }}>
        {w.type === "line" ? (
          <LineChart data={rows} margin={{ left: 4, right: 12, top: 8 }}>
            <CartesianGrid vertical={false} /><XAxis dataKey="key" tickLine={false} axisLine={false} /><YAxis tickFormatter={tick} width={56} tickLine={false} axisLine={false} />
            <ChartTooltip content={tip} /><Line dataKey="value" stroke="var(--color-value)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        ) : horizontal ? (
          <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 12 }}>
            <CartesianGrid horizontal={false} />
            <XAxis type="number" tickFormatter={tick} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="key" width={150} tickLine={false} axisLine={false} tickFormatter={(v: string) => (v.length > 22 ? v.slice(0, 21) + "…" : v)} />
            <ChartTooltip cursor={false} content={tip} />
            <Bar dataKey="value" fill="var(--color-value)" radius={3} barSize={16} isAnimationActive={false} cursor="pointer" onClick={(d: any) => onBar(d?.payload?.key ?? d?.key)} />
          </BarChart>
        ) : (
          <BarChart data={rows} margin={{ left: 4, right: 12, top: 8 }}>
            <CartesianGrid vertical={false} /><XAxis dataKey="key" tickLine={false} axisLine={false} />
            <YAxis tickFormatter={tick} width={56} tickLine={false} axisLine={false} />
            <ChartTooltip cursor={false} content={tip} />
            <Bar dataKey="value" fill="var(--color-value)" radius={3} maxBarSize={36} isAnimationActive={false} cursor="pointer" onClick={(d: any) => onBar(d?.payload?.key ?? d?.key)} />
          </BarChart>
        )}
      </ChartContainer>
      <ScopeLine scope={p.scope} />
    </>
  );
}

function DataTable({ p, maxH = 420 }: any) {
  const cols: [string, string, string][] = p.columns;
  return (
    <>
      <div className="overflow-auto rounded-md border" style={{ maxHeight: maxH }}>
        <Table className="text-xs">
          <TableHeader className="sticky top-0 bg-muted"><TableRow>{cols.map(([k, l, t]) => <TableHead key={k} className={cn("whitespace-nowrap", t !== "text" && "text-right")}>{l}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{p.rows.map((r: any, i: number) => (
            <TableRow key={i} className={r.test_record ? "text-muted-foreground/60" : ""}>
              {cols.map(([k, , t]) => <TableCell key={k} className={cn("max-w-[260px] truncate", t !== "text" && "text-right")} title={String(r[k] ?? "")}>{t === "text" ? (r[k] ?? "—") : fmt(r[k], t === "aed" ? "aed_full" : t)}</TableCell>)}
            </TableRow>))}</TableBody>
        </Table>
      </div>
      <div className="mt-1.5 text-[11px] text-muted-foreground">{p.rows.length} rows{p.note ? ` · ${p.note}` : ""}</div>
    </>
  );
}

const SEV: Record<string, string> = { Critical: "bg-red-100 text-red-800", High: "bg-orange-100 text-orange-800", Monitor: "bg-slate-200 text-slate-700" };
const SevBadge = ({ s, children }: any) => <Badge variant="secondary" className={cn("px-1.5 py-0 text-[10px]", SEV[s])}>{children ?? s}</Badge>;

function Exceptions({ filters, dataVersion }: any) {
  const [sev, setSev] = useState(""), [rule, setRule] = useState("");
  const q = useQuery({ queryKey: ["exc", filters, sev, rule, dataVersion], queryFn: () => getJSON(`/api/exceptions${qs({ ...filters, severity: sev, rule })}`), placeholderData: (p) => p });
  const d = q.data;
  if (!d) return <Skeleton className="h-40 w-full" />;
  return (
    <Card className="gap-3 py-4"><CardContent className="px-4">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {["", "Critical", "High", "Monitor"].map((s) => (
          <Button key={s} size="sm" variant={sev === s ? "default" : "outline"} className="h-7 rounded-full px-3 text-xs" onClick={() => setSev(s)}>
            {s || "All"} {s && <b>{d.by_severity[s]}</b>}
          </Button>
        ))}
        <Select value={rule || ALL} onValueChange={(v) => setRule(v === ALL ? "" : v)}>
          <SelectTrigger className="h-7 w-[260px] text-xs" aria-label="Rule"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>All rules</SelectItem>{d.rules.map(([id, l]: any) => <SelectItem key={id} value={id}>{id} · {l}</SelectItem>)}</SelectContent>
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">{d.filtered_count} shown of {d.total_count} total · as of {d.as_of}</span>
      </div>
      <div className="overflow-auto rounded-md border" style={{ maxHeight: 460 }}>
        <Table className="text-xs">
          <TableHeader className="sticky top-0 bg-muted"><TableRow><TableHead>Sev.</TableHead><TableHead>Rule</TableHead><TableHead>Record</TableHead><TableHead>Manager</TableHead><TableHead className="text-right">GP exposure</TableHead><TableHead>Fired by</TableHead><TableHead>Detail</TableHead></TableRow></TableHeader>
          <TableBody>{d.rows.map((r: any, i: number) => (
            <TableRow key={i}><TableCell><SevBadge s={r.severity} /></TableCell><TableCell className="max-w-[260px] truncate">{r.rule_id} · {r.rule}</TableCell><TableCell>{r.record}</TableCell><TableCell>{r.client_manager ?? "—"}</TableCell>
              <TableCell className="text-right">{fmt(r.gp_exposure, "aed_full")}</TableCell><TableCell><code>{r.source_field}</code></TableCell><TableCell className="max-w-[320px] truncate" title={r.detail}>{r.detail}</TableCell></TableRow>))}</TableBody>
        </Table>
      </div>
    </CardContent></Card>
  );
}

const Unavailable = ({ p }: any) => <div className="p-6 text-center text-muted-foreground">Not producible: {p.reason}</div>;

function PredictForecast({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  const f = p.forecast;
  const config = {
    pipeline_gp: { label: "Open pipeline (est. GP)", color: "var(--chart-3)" },
    weighted_crm: { label: "CRM probability-weighted", color: "var(--chart-1)" },
    expected_model: { label: "Model expected GP", color: "var(--accent-brand)" },
  } satisfies ChartConfig;
  return (
    <>
      <div className="mb-2 grid grid-cols-3 gap-2.5">
        <Mini label="Model expected GP" value={fmt(f.total_expected_model, "aed")} brand />
        <Mini label="p10 – p90 band" value={`${fmt(f.p10, "aed")} – ${fmt(f.p90, "aed")}`} />
        <Mini label="CRM weighted" value={fmt(f.total_weighted_crm, "aed")} />
      </div>
      <ChartContainer config={config} className="h-[260px] w-full">
        <BarChart data={f.months} margin={{ left: 4, right: 12, top: 8 }}>
          <CartesianGrid vertical={false} /><XAxis dataKey="month" tickLine={false} axisLine={false} />
          <YAxis tickFormatter={(v: number) => fmt(v, "aed")} width={56} tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent formatter={(v: any, n: any) => <span className="font-mono tabular-nums">{config[n as keyof typeof config]?.label}: {fmt(Number(v), "aed_full")}</span>} />} />
          <Bar dataKey="pipeline_gp" fill="var(--color-pipeline_gp)" radius={2} isAnimationActive={false} />
          <Bar dataKey="weighted_crm" fill="var(--color-weighted_crm)" radius={2} isAnimationActive={false} />
          <Bar dataKey="expected_model" fill="var(--color-expected_model)" radius={2} isAnimationActive={false} />
        </BarChart>
      </ChartContainer>
      <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        {Object.entries(config).map(([k, c]) => <span key={k} className="flex items-center gap-1"><i className="inline-block size-2 rounded-sm" style={{ background: c.color }} />{c.label}</span>)}
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground">{f.note} · {p.scope.record_count} open deals</div>
    </>
  );
}
const Mini = ({ label, value, brand }: any) => (
  <Card className="gap-0 py-2.5"><CardContent className="px-3">
    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
    <div className={cn("text-lg font-bold", brand && "text-brand")}>{value}</div>
  </CardContent></Card>
);

function PredictDrivers({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  const m = p.model, max = Math.max(...p.drivers.map((d: any) => Math.abs(d.weight)), 0.01);
  return (
    <>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">{p.drivers.slice(0, 8).map((d: any) => (
        <li key={d.feature} className="grid grid-cols-[1fr_90px] gap-x-2.5 text-xs">
          <span>{d.feature}</span>
          <div className="h-2 self-center rounded bg-muted"><i className={cn("block h-2 rounded", d.weight > 0 ? "bg-green-600" : "bg-red-600")} style={{ width: `${(Math.abs(d.weight) / max) * 100}%` }} /></div>
          <small className="col-span-2 -mt-0.5 text-[10px] text-muted-foreground">{d.direction}</small>
        </li>))}</ul>
      <Alert className="mt-2.5 bg-muted"><AlertDescription className="text-[11px]">
        Trained on {m.n_closed} closed deals ({m.won} won / {m.lost} lost). Cross-validated AUC {m.cv_auc.toFixed(2)} (0.50 = coin flip) · base win rate {fmt(m.base_rate, "pct")}. {m.caveat}
      </AlertDescription></Alert>
    </>
  );
}

function PredictDeals({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  return (
    <>
      <div className="overflow-auto rounded-md border" style={{ maxHeight: 460 }}>
        <Table className="text-xs">
          <TableHeader className="sticky top-0 bg-muted"><TableRow>
            <TableHead>Opportunity</TableHead><TableHead>Account</TableHead><TableHead>Manager</TableHead><TableHead>Stage</TableHead><TableHead>Est. close</TableHead>
            <TableHead className="text-right">Est. GP</TableHead><TableHead className="text-right">CRM prob.</TableHead><TableHead className="text-right">Model prob.</TableHead><TableHead className="text-right">Expected GP</TableHead><TableHead>Top drivers</TableHead>
          </TableRow></TableHeader>
          <TableBody>{p.deals.slice(0, 200).map((d: any) => (
            <TableRow key={d.guid}>
              <TableCell>{d.record}</TableCell><TableCell className="max-w-[220px] truncate" title={d.account}>{d.account}</TableCell><TableCell>{d.client_manager}</TableCell><TableCell>{d.stage}</TableCell>
              <TableCell>{d.estimated_close ?? "—"}{d.overdue && <SevBadge s="High">overdue</SevBadge>}</TableCell>
              <TableCell className="text-right">{fmt(d.est_gp, "aed_full")}</TableCell>
              <TableCell className="text-right">{d.crm_probability != null ? d.crm_probability + "%" : "—"}</TableCell>
              <TableCell className="text-right">{d.model_probability.toFixed(0)}%</TableCell>
              <TableCell className="text-right text-brand">{fmt(d.expected_gp, "aed_full")}</TableCell>
              <TableCell className="max-w-[260px] truncate text-[11px] text-muted-foreground">{d.drivers.join(", ")}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </div>
      <div className="mt-1.5 text-[11px] text-muted-foreground">Showing top 200 of {p.deals.length} · as of {p.scope.as_of} · {Object.keys(p.scope.filters_ignored).map((k) => `${k} not applied`).join(", ")}</div>
    </>
  );
}

function Drill({ d, filters, onClose }: any) {
  const q = useQuery({ queryKey: ["drill", d, filters], queryFn: () => getJSON(`/api/drill/${d.kpi}${qs({ ...filters, key: d.key, group_by: d.group_by })}`) });
  const cols = ["arc_opportunity_id", "account_display", "client_manager", "status_reason", "stage", "est_gp", "actual_gp", "estimated_close", "actual_close"];
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-2 overflow-auto sm:max-w-3xl">
        <SheetHeader><SheetTitle>{d.key}</SheetTitle><SheetDescription>Records behind {d.kpi}</SheetDescription></SheetHeader>
        <div className="px-4 pb-4">
          {q.data ? (<>
            <ScopeLine scope={q.data.scope} />
            <div className="mt-2 overflow-auto rounded-md border" style={{ maxHeight: "70vh" }}>
              <Table className="text-xs">
                <TableHeader className="sticky top-0 bg-muted"><TableRow>{cols.map((c) => <TableHead key={c} className="whitespace-nowrap">{c.replace(/_/g, " ")}</TableHead>)}</TableRow></TableHeader>
                <TableBody>{q.data.rows.map((r: any) => <TableRow key={r.guid}>{cols.map((c) => <TableCell key={c} className={cn("max-w-[220px] truncate", typeof r[c] === "number" && "text-right")}>{typeof r[c] === "number" ? fmt(r[c], "aed_full") : r[c] ?? "—"}</TableCell>)}</TableRow>)}</TableBody>
              </Table>
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">{q.data.total} records · governing date {q.data.scope.governing_date} · {q.data.scope.exclusions ?? ""}</div>
          </>) : <Skeleton className="h-40 w-full" />}
        </div>
      </SheetContent>
    </Sheet>
  );
}
