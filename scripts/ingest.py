#!/usr/bin/env python
"""Load a client workbook into the ERP (idempotent). Usage: python scripts/ingest.py data/client_export.xlsx"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.state import get_state
from app.ingest.loader import load_workbook_into_erp

args = [a for a in sys.argv[1:] if not a.startswith("--")]
dry = "--dry-run" in sys.argv
path = Path(args[0] if args else "data/client_export.xlsx")
s = get_state()
rep = load_workbook_into_erp(path, s.erp, s.schema, dry_run=dry)
for obj, r in rep.items():
    extra = f"  NEW FIELDS: {r['dynamic_headers']}" if r["dynamic_headers"] else ""
    miss = f"  MISSING: {r['missing_headers']}" if r["missing_headers"] else ""
    print(f"{obj:14} rows={r['rows']:4} +{r['inserted']} ~{r['updated']} ={r['unchanged']}{extra}{miss}")
print("DRY RUN - nothing written" if dry else "sync: " + str(s.refresh(reason="cli-ingest")))
