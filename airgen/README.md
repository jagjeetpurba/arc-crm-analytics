# Airgen side — agents, ERP, guardrails

Everything that **thinks or acts** lives in Airgen. Everything that **renders or computes governed numbers** lives in this repo.

```
Client .xlsx ──► [Ingest Agent] ──writes──► Airgen ERP (relational objects)
                                              │ read-only
                    [Healing Agent] ◄─watch───┤
                        │ POST /api/sync/heal ▼
                        └────────────► FastAPI backend ──SSE──► React dashboard
                    [Assistant Agent] ──reads /api/widget, /api/drill (cites KPI + rows)
```

Build order in the Airgen console (≈ 30 min):

1. **ERP** – follow `erp_setup.md` (objects come from `spec/erp_schema.yaml`; run `make erp-objects` for JSON).
2. **Credentials** – create two ERP keys: `arc-analytics-ro` (read, analytics objects only → backend `AIRGEN_API_KEY`) and
   `arc-ingest-rw` (write, same objects → Ingest Agent only). Add the backend URL + `WRITE_API_KEY` as masked sandbox env vars on the agents that need them.
3. **Agents** – create each by pasting the prompt in `agents/*.md` (prompt, model, tools, trigger, guardrails are listed at the top of each file).
   Start every agent as a **co-pilot** (human approves), review the diffs for a week, then promote Ingest and Healing to **ambient** – only the trigger changes.
4. **Smoke test** – drop `data/client_export.xlsx` on the Ingest Agent; watch `/api/sync/status`; edit one opportunity in the ERP and confirm the dashboard updates within one healing cycle.

| Agent | Type / trigger | Writes | Scope (least privilege) |
|---|---|---|---|
| `arc-ingest` | Ambient: inbound email / webhook with an .xlsx; co-pilot until trusted | ERP analytics objects (upsert only) | rw on analytics objects, no delete, no access to `agent_action` edits |
| `arc-healing` | Ambient: schedule every 5 min + ERP-change webhook | `agent_action` (audit) via backend | read ERP, call `/api/sync/*`, `/api/audit` |
| `arc-assistant` | Assistant (chat in Slack/Teams/WhatsApp) + Co-pilot for proposed edits | proposals → `agent_action`; applies only after human confirm | read analytics; write whitelist (see prompt); never GP/revenue, never delete |
| `arc-spec-curator` | Co-pilot, weekly | PR on GitHub for `spec/dashboard.yaml` | repo write on a branch only |
