Paste everything below the line into the Airgen Operator chat and attach ARC_CRM_Analytics_v15_Vendor_Single_Reference_WinLoss.xlsx.

---

CHANGE OF SCOPE for now. The attached workbook is the ONLY source of truth. Load it once into the 9 crm* ERP tables you already created, and make every agent operate on that ERP data only. Do NOT build or connect any live/incremental ARC or Dynamics 365 integration yet (that is a later phase): no Dynamics connector, no scheduled pulls, no email-triggered ingestion.

## Step 1 — One-time load of the workbook into the ERP (arc-ingest, run it as a manual, human-approved job)
Use code execution in the sandbox (openpyxl, read_only, data_only=True). Read ONLY these 7 sheets and ignore the other ~70 sheets (they are synthetic samples, specs and documentation). In each sheet the header row is the first row whose first cell equals the value in the "header starts with" column (rows above it are titles). Skip fully empty rows.

| Sheet | Header starts with | ERP object | Key |
|---|---|---|---|
| PILOT Opportunities | Opportunity GUID | crmOpportunity | guid |
| PILOT Goals | Goal GUID | crmGoal | guid |
| PILOT Accounts | Account GUID | crmAccount | guid |
| PILOT Contacts | Contact GUID | crmContact | guid |
| PILOT Leads | Lead GUID | crmLead | guid |
| PILOT Appointments | Appointment GUID | crmAppointment | guid |
| PILOT Type Mapping | ARC Type (exact) | crmActivityType | arcType |

Header → field mapping (exact header text on the left):
- **Opportunities:** Opportunity GUID→guid; ARC Opportunity ID→arcOpportunityId; Account (display only)→accountDisplay; Client Manager (display)→clientManager; CRM Owner (display)→crmOwner; Created On→createdOn; Estimated Close→estimatedClose; Actual Close→actualClose; Status Reason→statusReason; Opportunity Stage→stage; Forecast Category→forecastCategory; Probability (%)→probability; Est. GP (AED)→estGp; Actual GP (AED)→actualGp; Est. Revenue (AED)→estRevenue; Actual Revenue (AED)→actualRevenue; Account Vertical (from opp export)→vertical; Lead Business ID (pilot only)→leadBusinessId.
- **Goals:** Goal GUID→guid; Goal Name→goalName; Goal Owner (display)→goalOwner; Goal Metric→goalMetric; Fiscal Period→fiscalPeriod; Fiscal Year→fiscalYear; Goal Start→goalStart; Goal End→goalEnd; Target AED (parsed)→targetAed; Goal Actual AED (parsed)→goalActualAed; Goal In-Progress AED→inProgressAed; CRM % Achieved (as displayed)→crmPctAchieved.
- **Accounts:** Account GUID→guid; Account Name→name (use the field you created for it); Assigned Client Manager (display)→assignedClientManager; CRM Owner (display)→crmOwner; Business Vertical→businessVertical; ARC Business Vertical→arcBusinessVertical; Account Type→accountType; Exported Account Status→accountStatus; Created On→createdOn.
- **Contacts:** Contact GUID→guid; Company Name (display only)→companyName; Created On→createdOn; Modified On→modifiedOn; Status→status; Account GUID→accountGuid (mostly blank — leave blank, never match by company name).
- **Leads:** Lead GUID→guid; ARC Lead ID→arcLeadId; Company (display only)→company; Lead Owner (display)→leadOwner; Lead Source→leadSource; Primary LOB (lead only)→primaryLob; Lead Sales Stage→salesStage; Lead Rating→rating; Customer Budget (AED)→budgetAed; Created On→createdOn; Modified On→modifiedOn.
- **Appointments:** Appointment GUID→guid; CRM Owner (display)→crmOwner; ARC Type→arcType (also set the relation to crmActivityType by arcType); Start Time→startTime; End Time→endTime; Actual Duration (min)→durationMin; Status→status; Regarding (display only)→regarding; Related Account (display only)→relatedAccount.
- **Type Mapping:** ARC Type (exact)→arcType; Proposed Productivity Group→productivityGroup; Approval Status→approvalStatus.

Do NOT load the workbook's derived/formula columns (Analytical Status, Eligible Forecast GP, Weighted Forecast GP, Observed Won GP, Observed Won Revenue, Overdue?, Q3 Observed Won GP, Row QA, Relationship QA, CM differs from Owner, Owner vs CM, Goal Population, Goal QA, Completed Hours, Proposed Productivity Group on appointments, Guidance, Exported Opportunity Business-ID Matches, "(Do Not Modify)…" columns). The backend recomputes these. Any OTHER unmapped header → store in `dynamicFields` (JSON).

Cleaning rules: trim whitespace on all text (one vertical value has a trailing space); numbers → numeric (strip currency text/commas; blank stays null, never 0); dates → ISO UTC (date-only values at 00:00:00Z); keep blanks as null; never default a blank probability; never merge or match records by company name. Keep `guid` (CRM GUID) as the key; arcOpportunityId is NOT unique (3 collisions are expected — keep all rows).

Idempotent write (Twenty batch is insert-only): GET existing records (limit 60, paged) → POST /rest/batch/<plural> only for new keys (chunks of 60) → PATCH only rows whose values differ. Re-running the same file must insert 0 and update 0.

## Step 2 — Verify and show me the results (do not skip)
1. Row counts in the ERP: crmOpportunities 563, crmGoals 28, crmAccounts 62, crmContacts 62, crmLeads 55, crmAppointments 71, crmActivityTypes 12.
2. Opportunities by statusReason: WON 273, In Progress 179, LOST 49, On Hold 29, CANCELLED 27, DISQUALIFIED 6.
3. Reconciliation (compute from the ERP rows, show the numbers): sum(targetAed) where goalMetric = "Actual GP" and goalStart in 2026-07-01..2026-09-30 = 10,436,648; sum(actualGp) where statusReason = WON and actualClose in 2026-07-01..2026-09-30 = 6,869,748 across 81 deals; sum(actualGp) where WON, all dates = 14,425,155.
4. Re-run the load → must report 0 inserted, 0 updated.
5. Write one row to crmAgentAction (kind=`initial-load`, per-object counts, source file name, the three reconciliation figures).
If any number differs, STOP and tell me which one and why; do not "fix" figures by adjusting data.

## Step 3 — Agents, scoped to this static dataset
Create/keep the 4 agents as specified earlier (arc-ingest, arc-healing, arc-assistant, arc-spec-curator) with these changes:
- **arc-ingest:** manual trigger only (I attach a workbook, you show the dry-run, I approve). Remove the email/webhook/scheduled triggers. It can only write the 7 workbook objects.
- **arc-healing:** unchanged — it watches the ERP vs the dashboard (re-sync when someone edits the ERP). It never pulls from any CRM.
- **arc-assistant:** answers ONLY from the ERP data loaded from this workbook, via the backend ({ARC_API}/api/widget, /api/drill, /api/exceptions, /api/records/{object}) or the ERP read tool. Every answer states "Source: ARC pilot workbook (as of 2026-09-22)". If a question needs data that is not in the workbook (loss reasons, history before snapshots, other quarters' targets, live CRM data), say it is not available — never infer or invent. It must not browse the web or any live CRM. Writes remain whitelisted, confirm-first, and logged to crmAgentAction.
- **arc-spec-curator:** unchanged.
- State clearly in each agent's instructions: "This is a pilot extract used as the source of truth for now; never present it as final client performance."

Don't invent credentials or endpoints. When done, list what you created/changed and what I still must supply (ARC_API, API keys as masked env vars).
