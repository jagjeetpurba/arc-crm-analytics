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


def get(coll, cur):
    for _ in range(6):
        time.sleep(0.8)                                  # stay under the ERP's 100 requests / 60 s limit
        params = {"limit": 60, **({"starting_after": cur, "startingAfter": cur} if cur else {})}
        r = httpx.get(f"{base}/{coll}", headers=H, params=params, timeout=20)
        if r.status_code != 429:
            return r
        print(f"  {coll}: rate limited, waiting 20 s ...", flush=True); time.sleep(20)
    return r


for coll, want in EXPECT.items():
    n, cur, seen = 0, None, set()
    while True:
        r = get(coll, cur)
        if r.status_code != 200:
            print(f"{coll:18} HTTP {r.status_code} {r.text[:120]}"); ok = False; break
        b = r.json()
        page = (b.get("data") or {}).get(coll, [])
        ids = [x.get("id") for x in page]
        if page and all(i in seen for i in ids):
            print(f"{coll:18} PAGING NOT ADVANCING (same page twice) - cursor parameter ignored"); ok = False; break
        seen.update(ids); n += len(page)
        print(f"  {coll}: page of {len(page)} (running total {n})", flush=True)
        pi, tot = b.get("pageInfo") or {}, b.get("totalCount")
        if not page or not pi.get("hasNextPage") or (tot is not None and n >= tot):
            flag = "OK " if n == want else "MISMATCH"
            ok &= n == want
            print(f"{coll:18} fetched={n:4} expected={want:4} totalCount={tot} {flag}")
            break
        cur = pi.get("endCursor")
print("ALL GOOD" if ok else "CHECK ABOVE")
