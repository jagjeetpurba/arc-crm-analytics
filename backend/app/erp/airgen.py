"""Adapter for the Airgen ERP.

NOTE: the exact REST surface of your Airgen ERP is not known to this scaffold. The
endpoint paths below are placeholders — confirm them in the Airgen console (or give the
Airgen agent the task 'expose analytics objects over REST') and adjust the 4 TODO lines.
Contract the ERP must offer per object:
  GET   {base}/objects/{obj}/records?limit&offset   -> {"records":[{...}], "total":N}
  PUT   {base}/objects/{obj}/records/{key}          -> upsert one record
  POST  {base}/objects/{obj}/records:batchUpsert    -> {"inserted":n,"updated":n,"unchanged":n}
  GET   {base}/objects/{obj}/fingerprint            -> {"count":N,"checksum":"..."}
"""
from __future__ import annotations
import httpx
from .. import config
from .base import ERPClient, Row


class AirgenERP(ERPClient):
    def __init__(self):
        self.http = httpx.Client(base_url=config.AIRGEN_BASE_URL,
                                 headers={"Authorization": f"Bearer {config.AIRGEN_API_KEY}"}, timeout=30)
        self.schema: dict = {}

    def ensure_schema(self, schema: dict) -> None:
        self.schema = schema   # objects are created in Airgen by the ingest agent, not by this service

    def fetch(self, obj: str) -> list[Row]:
        out, off = [], 0
        while True:
            r = self.http.get(f"/objects/{obj}/records", params={"limit": 1000, "offset": off})   # TODO confirm path
            r.raise_for_status()
            body = r.json()
            out += body["records"]
            off += len(body["records"])
            if not body["records"] or off >= body.get("total", off):
                return out

    def upsert(self, obj: str, rows: list[Row], source: str = "") -> dict:
        r = self.http.post(f"/objects/{obj}/records:batchUpsert", json={"records": rows, "source": source})  # TODO
        r.raise_for_status()
        return r.json()

    def change_token(self) -> dict[str, dict]:
        out = {}
        for obj in self.schema.get("objects", {}):
            r = self.http.get(f"/objects/{obj}/fingerprint")                                         # TODO
            if r.status_code == 200:
                out[obj] = r.json()
        return out

    def dynamic_fields(self) -> list[dict]:
        r = self.http.get("/fields", params={"dynamic": "true"})                                     # TODO
        return r.json().get("fields", []) if r.status_code == 200 else []

    def append(self, obj: str, rows: list[Row]) -> int:
        return self.upsert(obj, rows, "append").get("inserted", 0)
