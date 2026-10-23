# ARC CRM Management Analytics

Client workbook → **Airgen ERP** → governed KPIs + predictive indicators → **React dashboard** that follows the ERP live.
Implements the BRD (`ARC-CRM-Analytics-BRD.docx`) Phase 1 screens (Executive, Client Managers, Pipeline, CM360 Win/Loss, Exceptions) plus a Predictive page (BRD Phase 3 preview).

| Where | What |
|---|---|
| **This repo (GitHub)** | `backend/` FastAPI (KPI engine, predictive, sync API) · `frontend/` React + ECharts · `spec/` YAML (ERP schema, KPIs, dashboard, rules) |
| **Airgen** | the agents (`airgen/agents/*.md`: ingest, healing, assistant, spec-curator) and the ERP that holds the data (`airgen/erp_setup.md`) |

See `docs/ARCHITECTURE.md` for the picture and the data flow.

## Run locally (no Airgen needed — SQLite stands in for the ERP)
```bash
cp .env.example .env
make setup
cp ~/Downloads/ARC_CRM_Analytics_v15_Vendor_Single_Reference_WinLoss.xlsx data/client_export.xlsx
make ingest          # idempotent; prints NEW FIELDS if the client added columns
make api             # http://localhost:8000/docs
make ui              # http://localhost:5173
make test            # reconciles to BRD Appendix B (target 10,436,648 · Q3 close 6,869,748 / 81 deals …)
```
Switch to the real ERP: `ERP_MODE=airgen` + `AIRGEN_BASE_URL` + `AIRGEN_API_KEY`, then finish the 4 `TODO` endpoint paths in `backend/app/erp/airgen.py`.

## "Dynamic" — what actually happens when the client sends something new
| Client change | Result | Code change |
|---|---|---|
| New **rows** / edited rows | ERP fingerprint changes → healing agent (or 15 s watcher) calls `/api/sync/heal` → SSE → dashboard refetches | none |
| New **column** on a known sheet | stored as dynamic field, becomes a filter + auto widgets (`auto` tag) and also filters the curated KPIs | none |
| New **object/sheet** | add an entry to `spec/erp_schema.yaml` → auto page appears (`new` tag) | one YAML block |
| New **KPI / page** | add to `spec/kpis.yaml` / `spec/dashboard.yaml` (hot-reloaded) | YAML only |

## Guarantees from the BRD that are enforced in code (and tested)
Scope + as-of on every figure · period/target mismatch withholds the % · unsupported filters reported as "not applied" · attribution by `client_manager` · estimated GP never shown as achieved · blank probability never defaulted · overdue computed from dates · idempotent load · filter state in the URL · drill to records.

## Caveats you should know
- The Airgen ERP REST surface is **not** known to this scaffold — `erp/airgen.py` has placeholder paths. Everything else runs against the local stand-in today.
- The predictive model is trained on 322 closed deals from a *pilot extract*. Two features that leaked the outcome were removed (see `predict.py`); remaining AUC may still be optimistic. Output is labelled directional and shows drivers, per BRD §14.
- Agents are defined as prompts to paste into Airgen; nothing in this repo creates them automatically.
