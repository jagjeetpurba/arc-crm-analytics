#!/usr/bin/env python
"""Verify ERP host + key and the loaded row counts. Prompts for the key (hidden); never prints it.
Usage: python scripts/check_erp.py https://<host>/rest"""
import getpass, sys, time
import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "https://erp.airgen.ai/rest").rstrip("/")
import os
key = (os.environ.get("ERP_KEY") or getpass.getpass("ERP API key (paste, press Enter; nothing will show): ")).strip()
if len(key) < 40:
    sys.exit(f"Key looks too short ({len(key)} chars) - paste the full token.")
print(f"Key received ({len(key)} chars). Checking {base} ...", flush=True)
H = {"Authorization": "Bearer " + key}
EXPECT = {"crmOpportunities": 563, "crmGoals": 28, "crmAccounts": 62, "crmContacts": 62, "crmLeads": 55,
          "crmAppointments": 71, "crmActivityTypes": 12}
ok = True
for coll, want in EXPECT.items():
    n, cur = 0, None
    while True:
        for _ in range(6):
            print(f"  {coll}: requesting page ...", flush=True)
            time.sleep(0.8)                              # stay under the ERP's 100 requests / 60 s limit
            r = httpx.get(f"{base}/{coll}", headers=H, params={"limit": 60, **({"startingAfter": cur} if cur else {})}, timeout=20)
            if r.status_code != 429:
                break
            print(f"  {coll}: rate limited, waiting 20 s ..."); time.sleep(20)
        if r.status_code != 200:
            print(f"{coll:18} HTTP {r.status_code} {r.text[:120]}"); ok = False; break
        b = r.json()
        n += len((b.get("data") or {}).get(coll, []))
        pi = b.get("pageInfo") or {}
        if not pi.get("hasNextPage"):
            tot = b.get("totalCount")
            flag = "OK " if n == want else "MISMATCH"
            ok &= n == want
            print(f"{coll:18} fetched={n:4} expected={want:4} totalCount={tot} {flag}")
            break
        cur = pi.get("endCursor")
print("ALL GOOD" if ok else "CHECK ABOVE")
