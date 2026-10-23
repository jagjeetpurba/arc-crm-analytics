import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { getJSON, qs } from "./api";
import { fmt } from "./format";

const ACCENT = "#c2410c";   // NFR-06: one accent, reserved for target/forecast
const INK = "#334155";

export function Widget({ w, filters, dataVersion, spec }: any) {
  const q = useQuery({
    queryKey: ["w", w.id, filters, dataVersion],
    queryFn: () => getJSON(`/api/widget/${w.id}${qs(filters)}`),
    placeholderData: (p) => p,
  });
  const [drill, setDrill] = useState<any>(null);
  if (q.isLoading) return <div className="skeleton">Loading…</div>;
  if (q.isError) return <div className="err">Could not load {w.id}</div>;
  const p = q.data.payload;
  const body = (() => {
    switch (w.type) {
      case "kpi_strip": return <KpiStrip p={p} spec={spec} />;
      case "bar": case "line": return <Bar w={w} p={p} onBar={(key: string) => w.query?.kpi && setDrill({ kpi: w.query.kpi, key, group_by: w.query.group_by })} filters={filters} />;
      case "table": return <Table p={p} />;
      case "exceptions": return <Exceptions filters={filters} dataVersion={dataVersion} />;
      case "predict_forecast": return <PredictForecast p={p} />;
      case "predict_drivers": return <PredictDrivers p={p} />;
      case "predict_deals": return <PredictDeals p={p} />;
      default: return <div className="err">Unknown widget type {w.type}</div>;
    }
  })();
  return (
    <>
      {w.title && <h3>{w.title}{w.auto && <em className="tag">auto</em>}<ScopeBtn scope={p.scope} /></h3>}
      {body}
      {drill && <Drill d={drill} filters={filters} onClose={() => setDrill(null)} />}
    </>
  );
}

function ScopeLine({ scope }: any) {
  if (!scope) return null;
  const ign = Object.keys(scope.filters_ignored ?? {});
  return (
    <div className="scope">
      {scope.period ? `Period ${scope.period}` : "All dates"}{scope.governing_date ? ` on ${scope.governing_date}` : ""} · {scope.record_count ?? "—"} records · as of {scope.as_of}
      {ign.length > 0 && <span className="ign"> · not applied: {ign.join(", ")}</span>}
    </div>
  );
}

function ScopeBtn({ scope }: any) {
  const [open, setOpen] = useState(false);
  if (!scope) return null;
  return (
    <span className="info">
      <button aria-label="Definition, date and exclusions" onClick={() => setOpen(!open)}>i</button>
      {open && (
        <div className="pop" role="dialog">
          {scope.definition && <p><b>Definition</b>{scope.definition}</p>}
          <p><b>Governing date</b>{scope.governing_date ?? "—"}</p>
          <p><b>Exclusions</b>{scope.exclusions ?? "—"}</p>
          <p><b>Records</b>{scope.record_count ?? "—"} · as of {scope.as_of}</p>
          {Object.entries(scope.filters_applied ?? {}).map(([k, v]: any) => <p key={k}><b>Applied</b>{k}: {String(v)}</p>)}
          {Object.entries(scope.filters_ignored ?? {}).map(([k, v]: any) => <p key={k} className="ign"><b>Not applied</b>{k}: {String(v)}</p>)}
        </div>
      )}
    </span>
  );
}

function KpiStrip({ p }: any) {
  return (
    <div>
      {p.comparison_flag && <div className="flag" role="alert">{p.comparison_flag}</div>}
      <div className="kpis">
        {p.items.map((i: any) => {
          const target = i.id === "quarterly_gp_target" || i.id === "open_forecast_gp" || i.id === "weighted_open_gp";
          return (
            <div key={i.id} className="kpi">
              <div className="lbl">{i.label}<ScopeBtn scope={i.scope} /></div>
              <div className="val" style={{ color: target ? ACCENT : undefined }}>{fmt(i.value, i.format)}</div>
              {i.vs_target != null && <div className="sub">{fmt(i.vs_target, "pct")} of target · gap {fmt(i.gap, "aed")}</div>}
              <ScopeLine scope={i.scope} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Bar({ w, p, onBar, filters }: any) {
  const rows = p.rows ?? [];
  if (!rows.length) return <Empty scope={p.scope} />;
  const fmtKind = p.format ?? "num";
  const horizontal = rows.length > 6 && !(w.query?.group_by ?? "").includes(":month");
  const cats = rows.map((r: any) => r.key), vals = rows.map((r: any) => r.value);
  const opt = {
    animation: false, grid: { left: horizontal ? 150 : 40, right: 24, top: 8, bottom: horizontal ? 8 : 28, containLabel: !horizontal },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, fmtKind === "aed" ? "aed_full" : fmtKind) },
    [horizontal ? "yAxis" : "xAxis"]: { type: "category", data: cats, inverse: horizontal, axisLabel: { color: INK, width: 140, overflow: "truncate" } },
    [horizontal ? "xAxis" : "yAxis"]: { type: "value", axisLabel: { color: INK, formatter: (v: number) => fmt(v, fmtKind) }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    series: [{ type: w.type === "line" ? "line" : "bar", data: vals, itemStyle: { color: fmtKind === "aed" && /forecast|open|expected/i.test(w.title ?? "") ? ACCENT : "#475569" }, barMaxWidth: 28 }],
  };
  return (
    <>
      <ReactECharts option={opt} style={{ height: Math.max(220, horizontal ? rows.length * 26 + 20 : 240) }}
        onEvents={{ click: (e: any) => onBar(e.name) }} />
      <ScopeLine scope={p.scope} />
    </>
  );
}

function Empty({ scope }: any) { return <div className="empty">— no records in this scope<ScopeLine scope={scope} /></div>; }

function Table({ p, maxH = 420 }: any) {
  const cols: [string, string, string][] = p.columns;
  return (
    <>
      <div className="tscroll" style={{ maxHeight: maxH }}>
        <table><thead><tr>{cols.map(([k, l, t]) => <th key={k} className={t !== "text" ? "num" : ""}>{l}</th>)}</tr></thead>
          <tbody>{p.rows.map((r: any, i: number) => (
            <tr key={i} className={r.test_record ? "muted" : ""}>{cols.map(([k, , t]) => <td key={k} className={t !== "text" ? "num" : ""} title={String(r[k] ?? "")}>{t === "text" ? (r[k] ?? "—") : fmt(r[k], t === "aed" ? "aed_full" : t)}</td>)}</tr>
          ))}</tbody></table>
      </div>
      <div className="scope">{p.rows.length} rows{p.note ? ` · ${p.note}` : ""}</div>
    </>
  );
}

function Exceptions({ filters, dataVersion }: any) {
  const [sev, setSev] = useState(""), [rule, setRule] = useState("");
  const q = useQuery({ queryKey: ["exc", filters, sev, rule, dataVersion], queryFn: () => getJSON(`/api/exceptions${qs({ ...filters, severity: sev, rule })}`), placeholderData: (p) => p });
  const d = q.data;
  if (!d) return <div className="skeleton">Loading…</div>;
  return (
    <>
      <div className="chips">
        {["", "Critical", "High", "Monitor"].map((s) => <button key={s} className={sev === s ? "on" : ""} onClick={() => setSev(s)}>{s || "All"} {s && <b>{d.by_severity[s]}</b>}</button>)}
        <select value={rule} onChange={(e) => setRule(e.target.value)} aria-label="Rule"><option value="">All rules</option>{d.rules.map(([id, l]: any) => <option key={id} value={id}>{id} · {l}</option>)}</select>
        <span className="count">{d.filtered_count} shown of {d.total_count} total · as of {d.as_of}</span>
      </div>
      <div className="tscroll" style={{ maxHeight: 460 }}>
        <table><thead><tr><th>Sev.</th><th>Rule</th><th>Record</th><th>Manager</th><th className="num">GP exposure</th><th>Fired by</th><th>Detail</th></tr></thead>
          <tbody>{d.rows.map((r: any, i: number) => (
            <tr key={i}><td><span className={`sev ${r.severity}`}>{r.severity}</span></td><td>{r.rule_id} · {r.rule}</td><td>{r.record}</td><td>{r.client_manager ?? "—"}</td>
              <td className="num">{fmt(r.gp_exposure, "aed_full")}</td><td><code>{r.source_field}</code></td><td>{r.detail}</td></tr>))}</tbody></table>
      </div>
    </>
  );
}

function Unavailable({ p }: any) { return <div className="empty">Not producible: {p.reason}</div>; }

function PredictForecast({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  const f = p.forecast, months = f.months;
  const opt = {
    animation: false, grid: { left: 40, right: 16, top: 28, bottom: 28, containLabel: true }, tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, "aed_full") },
    legend: { top: 0, textStyle: { color: INK } }, xAxis: { type: "category", data: months.map((m: any) => m.month) },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => fmt(v, "aed") }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    series: [
      { name: "Open pipeline (est. GP)", type: "bar", data: months.map((m: any) => m.pipeline_gp), itemStyle: { color: "#cbd5e1" } },
      { name: "CRM probability-weighted", type: "bar", data: months.map((m: any) => m.weighted_crm), itemStyle: { color: "#64748b" } },
      { name: "Model expected GP", type: "bar", data: months.map((m: any) => m.expected_model), itemStyle: { color: ACCENT } },
    ],
  };
  return (
    <>
      <div className="kpis small">
        <div className="kpi"><div className="lbl">Model expected GP</div><div className="val" style={{ color: ACCENT }}>{fmt(f.total_expected_model, "aed")}</div></div>
        <div className="kpi"><div className="lbl">p10 – p90 band</div><div className="val">{fmt(f.p10, "aed")} – {fmt(f.p90, "aed")}</div></div>
        <div className="kpi"><div className="lbl">CRM weighted</div><div className="val">{fmt(f.total_weighted_crm, "aed")}</div></div>
      </div>
      <ReactECharts option={opt} style={{ height: 260 }} />
      <div className="scope">{f.note} · {p.scope.record_count} open deals</div>
    </>
  );
}

function PredictDrivers({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  const m = p.model, max = Math.max(...p.drivers.map((d: any) => Math.abs(d.weight)), 0.01);
  return (
    <>
      <ul className="drivers">{p.drivers.slice(0, 8).map((d: any) => (
        <li key={d.feature}><span>{d.feature}</span>
          <div className="bar"><i className={d.weight > 0 ? "pos" : "neg"} style={{ width: `${(Math.abs(d.weight) / max) * 100}%` }} /></div>
          <small>{d.direction}</small></li>))}</ul>
      <div className="flag soft">Trained on {m.n_closed} closed deals ({m.won} won / {m.lost} lost). Cross-validated AUC {m.cv_auc.toFixed(2)} (0.50 = coin flip) · base win rate {fmt(m.base_rate, "pct")}. {m.caveat}</div>
    </>
  );
}

function PredictDeals({ p }: any) {
  if (!p.available) return <Unavailable p={p} />;
  return (
    <>
      <div className="tscroll" style={{ maxHeight: 460 }}>
        <table><thead><tr><th>Opportunity</th><th>Account</th><th>Manager</th><th>Stage</th><th>Est. close</th><th className="num">Est. GP</th><th className="num">CRM prob.</th><th className="num">Model prob.</th><th className="num">Expected GP</th><th>Top drivers</th></tr></thead>
          <tbody>{p.deals.slice(0, 200).map((d: any) => (
            <tr key={d.guid}><td>{d.record}</td><td title={d.account}>{d.account}</td><td>{d.client_manager}</td><td>{d.stage}</td>
              <td>{d.estimated_close ?? "—"}{d.overdue && <span className="sev High">overdue</span>}</td><td className="num">{fmt(d.est_gp, "aed_full")}</td>
              <td className="num">{d.crm_probability != null ? d.crm_probability + "%" : "—"}</td><td className="num">{d.model_probability.toFixed(0)}%</td>
              <td className="num" style={{ color: ACCENT }}>{fmt(d.expected_gp, "aed_full")}</td><td className="drv">{d.drivers.join(", ")}</td></tr>))}</tbody></table>
      </div>
      <div className="scope">Showing top 200 of {p.deals.length} · as of {p.scope.as_of} · {Object.keys(p.scope.filters_ignored).map((k) => `${k} not applied`).join(", ")}</div>
    </>
  );
}

function Drill({ d, filters, onClose }: any) {
  const q = useQuery({ queryKey: ["drill", d, filters], queryFn: () => getJSON(`/api/drill/${d.kpi}${qs({ ...filters, key: d.key, group_by: d.group_by })}`) });
  const cols = ["arc_opportunity_id", "account_display", "client_manager", "status_reason", "stage", "est_gp", "actual_gp", "estimated_close", "actual_close"];
  return (
    <div className="drawer" role="dialog" aria-label="Records behind this figure">
      <div className="dh"><b>{d.key}</b> · records behind {d.kpi}<button onClick={onClose} aria-label="Close">×</button></div>
      {q.data ? (<>
        <ScopeLine scope={q.data.scope} />
        <div className="tscroll" style={{ maxHeight: "70vh" }}>
          <table><thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
            <tbody>{q.data.rows.map((r: any) => <tr key={r.guid}>{cols.map((c) => <td key={c} className={typeof r[c] === "number" ? "num" : ""}>{typeof r[c] === "number" ? fmt(r[c], "aed_full") : r[c] ?? "—"}</td>)}</tr>)}</tbody></table>
        </div>
        <div className="scope">{q.data.total} records · governing date {q.data.scope.governing_date} · {q.data.scope.exclusions ?? ""}</div>
      </>) : "Loading…"}
    </div>
  );
}
