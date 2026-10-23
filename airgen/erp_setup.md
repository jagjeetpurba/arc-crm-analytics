# Airgen ERP setup

Source of truth: `spec/erp_schema.yaml` (generated JSON: `make erp-objects` → `airgen/erp_objects.json`).

**Objects** – opportunities, goals, accounts, contacts, leads, appointments, activity_types (ingested from the client workbook),
plus system objects `opportunity_snapshots` (append-only) and `agent_action` (audit).

**Rules the ERP must enforce** (BRD §9.2 / §9.3)
- Key is the CRM **GUID**; `arc_opportunity_id` is **not** unique (DQ-01) – do not set a unique constraint on it.
- `client_manager` is the attribution field; `crm_owner` is informational only (FR-06).
- `est_gp` is **gross profit**, not revenue; `actual_revenue` is supporting info only.
- Money in AED, `decimal`; dates stored as ISO datetime; four independent date roles (created / estimated close / actual close / goal period).
- Trim categorical values on write (`vertical` had a trailing-space variant – DQ-04).
- Allow **dynamic fields** on the ingestion objects: unknown client columns must be stored (not rejected) – the backend profiler turns them into filters/widgets.
- `opportunity_snapshots` and `agent_action`: insert-only (no update/delete permission for anyone but the platform).
- Relationships: see `relations:` in the schema file.

**Change detection** – the backend needs, per object, a cheap fingerprint `{count, checksum}` (e.g. count + max(modified_on) + hash of keys/versions).
If the ERP can emit a webhook on write, point it at the Healing Agent trigger; otherwise the 5-minute schedule is enough.
