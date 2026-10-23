Paste everything below the line into the Airgen **Operator** chat ("Create a new agent").

---

I need you to build the backend for an "ARC CRM Management Analytics" solution inside Airgen: ERP objects first, then 4 agents. The dashboard (React + FastAPI) is hosted separately in my Git repo and only reads from the ERP; do NOT build any UI. Work in the order below and report after each phase. Ask me before anything destructive.

## Context
ARC (client) sends a CRM export workbook (.xlsx, from Dynamics 365). Goal: store it in the ERP relationally, let a backend compute KPIs from it, and keep the dashboard in sync when the ERP changes. Agents only move, validate, heal, explain and propose. They never compute KPIs and never render screens. Currency is AED.

## PHASE 1 — ERP objects (create all; allow extra/dynamic fields on the first seven)
Key for every object is the CRM GUID (text). Types: text / decimal / datetime. Trim whitespace on text on write.

1. **opportunities** (key guid): arc_opportunity_id (text, NOT unique — do not add a unique constraint), account_display, client_manager, crm_owner, created_on (datetime), estimated_close (datetime), actual_close (datetime), status_reason, stage, forecast_category, probability (decimal), est_gp (decimal; this is gross profit, not revenue), actual_gp (decimal), est_revenue (decimal), actual_revenue (decimal, supporting only), vertical, lead_business_id.
2. **goals** (key guid): goal_name, goal_owner, goal_metric, fiscal_period, fiscal_year, goal_start, goal_end, target_aed, goal_actual_aed, in_progress_aed, crm_pct_achieved.
3. **accounts** (key guid): name, assigned_client_manager, crm_owner, business_vertical, arc_business_vertical, account_type, account_status, created_on.
4. **contacts** (key guid): company_name, created_on, modified_on, status, account_guid (mostly blank; never match by company name).
5. **leads** (key guid): arc_lead_id, company, lead_owner, lead_source, primary_lob, sales_stage, rating, budget_aed, created_on, modified_on.
6. **appointments** (key guid): crm_owner, arc_type, start_time, end_time, duration_min, status, regarding, related_account.
7. **activity_types** (key arc_type): productivity_group, approval_status.
8. **opportunity_snapshots** (key snapshot_key; INSERT-ONLY): snapshot_date, opportunity_guid, client_manager, stage, forecast_category, probability, est_gp, estimated_close.
9. **agent_action** (key action_id; INSERT-ONLY audit log): ts, agent, kind, target_object, target_key, before_json, after_json, outcome, prompt.

Relationships (many→one): appointments.arc_type→activity_types.arc_type; contacts.account_guid→accounts.guid; opportunity_snapshots.opportunity_guid→opportunities.guid.

Rules to enforce: attribution is by `client_manager`, never `crm_owner`; no deletes by agents; actual_gp / actual_revenue are never hand-edited; unknown incoming columns must be STORED as dynamic fields, not rejected.

Also provide: (a) a read-only API key scoped to these objects, (b) a write key scoped to objects 1–7 for the ingest agent only, (c) for every object a cheap change fingerprint (row count + checksum or max modified time). When done, **tell me exactly: the REST base URL, auth header format, and the endpoints for list-records (with paging), batch-upsert, and fingerprint** — I need them to wire my backend.

## PHASE 2 — Agents (all sandboxed, per-agent scoped credentials, guardrails ON: PII redaction, prompt-injection protection, budget cap, stop-on-breach). Start each as a Co-pilot (I approve), except where stated.

### Agent 1: arc-ingest
- Trigger: inbound email with an .xlsx attachment, or webhook/manual upload. Tools: file tools, code execution, ERP write (write key), messaging.
- Workbook layout: sheets named "PILOT Opportunities", "PILOT Goals", "PILOT Accounts", "PILOT Contacts", "PILOT Leads", "PILOT Appointments", "PILOT Type Mapping". Headers sit on row 4 (rows above are titles). Ignore workbook formula/derived columns (Analytical Status, Eligible Forecast GP, Weighted Forecast GP, Observed Won GP, Overdue?, Row QA, CM differs from Owner, etc.): the backend recomputes them.
- Header → field mapping for opportunities: Opportunity GUID→guid, ARC Opportunity ID→arc_opportunity_id, Account (display only)→account_display, Client Manager (display)→client_manager, CRM Owner (display)→crm_owner, Created On→created_on, Estimated Close→estimated_close, Actual Close→actual_close, Status Reason→status_reason, Opportunity Stage→stage, Forecast Category→forecast_category, Probability (%)→probability, Est. GP (AED)→est_gp, Actual GP (AED)→actual_gp, Est. Revenue (AED)→est_revenue, Actual Revenue (AED)→actual_revenue, Account Vertical (from opp export)→vertical, Lead Business ID (pilot only)→lead_business_id. Map the other sheets the same way by matching header text to the field names above (e.g. "Target AED (parsed)"→target_aed, "Goal Owner (display)"→goal_owner).
- Steps: (1) dry-run and report rows per object, new columns, missing headers; (2) STOP and message me if mapped headers are missing, a sheet is empty, or any object's row count drops >20% vs the ERP; (3) new columns are fine → store as dynamic fields and list them in the report; (4) upsert by GUID — idempotent, a second run of the same file must change 0 rows; (5) log a row in agent_action; (6) reply with a 5-line report (rows per object inserted/updated/unchanged, new fields, warnings).
- Never merge records by company name, never compute KPIs, never print personal data.

### Agent 2: arc-healing  (Ambient — run it every 5 minutes AND on ERP-change webhook if available; cheap fast model)
- Tools: HTTP to my backend only (egress allow-list = backend host), messaging. No ERP write. Env (masked): ARC_API (backend base URL), WRITE_API_KEY. I will give you the values.
- Each run: GET {ARC_API}/api/sync/status. If `drift` is empty → end silently. If drift lists objects → POST {ARC_API}/api/sync/heal (send the env var WRITE_API_KEY in the request header named X-API-Key). Then check status again: drift must be empty and `version` increased by exactly 1; retry once after 30 s. Then GET /api/spec and confirm any newly discovered fields appear under filters.dynamic or in pages with auto=true; report if not. Log with POST {ARC_API}/api/audit {agent, kind:"heal", before, after, outcome}. Two failures in a row or backend unreachable → STOP and alert me; never loop. It must never edit data, specs or KPI definitions.

### Agent 3: arc-assistant  (Assistant in chat + Co-pilot for writes; strongest model, fallback chain on)
- Tools: HTTP read endpoints of my backend, ERP read, ERP write limited to the whitelist below.
- Answering: fetch figures ONLY via GET {ARC_API}/api/widget/{id}, /api/drill/{kpi}, /api/exceptions, /api/explain/{kpi} using the filters the user is looking at (period, client_manager, vertical). Never compute a KPI yourself. Every answer cites KPI id, governing date, period, record count, as-of, and 1–3 example opportunity ids from the response's `scope` block. If `scope.filters_ignored` is non-empty, say which filters did not apply. If something is "not producible" (loss reason, historical movement), say so — never infer. For predictive widgets (pr_*), always state the CV AUC, the p10–p90 band and the top drivers, and call them directional. Estimated GP is a forecast, never achieved GP or revenue.

- Data access (always live, never from memory or an earlier chat turn): (a) KPIs, totals, trends, rankings, exceptions, predictions → backend `GET {ARC_API}/api/widget/{id}`, `/api/drill/{kpi}`, `/api/exceptions`; (b) look-ups of specific records or lists ("show opp 2026-O-00231", "deals of Jalal in Technical Proposal") → `GET {ARC_API}/api/records/{object}?<field>=<value>&q=<text>&limit=` (read-only, returns the live ERP rows plus data_version and as_of), or the ERP read tool if it can filter server-side; (c) if the user asks "is this current?" → `GET /api/sync/status` and report version/drift. If the ERP and the backend disagree (drift non-empty), say so and answer from the ERP record, flagging that the dashboard figure is catching up.
- Writes: propose → show before/after → wait for explicit "confirm" from an authorised user → apply → re-read the record → log in agent_action (actor, prompt, before, after, outcome). Whitelist: opportunities.{estimated_close, probability, stage, forecast_category, client_manager}, leads.{sales_stage, rating}. Never touch actual_gp, actual_revenue, est_gp; never delete.

### Agent 4: arc-spec-curator  (Co-pilot, weekly)
- Tools: HTTP read, GitHub/GitLab branch+PR only (no merge), code execution. Each week list auto-generated dashboard fields from GET /api/spec, and for fields populated >80% propose a KPI in spec/kpis.yaml (one definition, one governing date, explicit exclusions) or a widget in spec/dashboard.yaml as a PR on a `curator/*` branch. Do not merge; ARC Sales Ops owns definitions.

## PHASE 3 — Smoke test (do it and show me results)
1. Upload the attached workbook to arc-ingest; confirm counts: opportunities 563, goals 28, accounts 62, contacts 62, leads 55, appointments 71, activity_types 12, and 273 won / 179 in progress / 49 lost / 29 on hold among opportunities.
2. Re-run the same file → must report 0 inserted, 0 updated.
3. Edit one opportunity's est_gp in the ERP → arc-healing should detect drift and heal within one cycle (use a manual run if the schedule hasn't fired).
4. Summarise: what you created, which credentials/env vars I still must supply (ARC_API, WRITE_API_KEY, ERP keys), and anything you could not do.

Don't invent endpoints or credentials: if a capability (webhook, fingerprint, scoped keys) isn't available in Airgen, say so and propose the closest alternative.
