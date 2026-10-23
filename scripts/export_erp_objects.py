#!/usr/bin/env python
"""Emit spec/erp_schema.yaml as JSON to paste into the Airgen ERP object builder (or hand to the ingest agent)."""
import json, yaml
from pathlib import Path
s = yaml.safe_load((Path(__file__).resolve().parents[1] / "spec" / "erp_schema.yaml").read_text())
TYPE = {"str": "text", "date": "datetime", "float": "decimal", "int": "integer"}
out = {"objects": [], "relations": s.get("relations", [])}
for name, o in s["objects"].items():
    out["objects"].append({"name": name, "label": o["label"], "primary_key": o["key"],
                           "fields": [{"name": c, "type": TYPE[d["type"]], "source_header": d.get("source")} for c, d in o["columns"].items()],
                           "allow_dynamic_fields": True})
print(json.dumps(out, indent=2))
