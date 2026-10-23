"""Adapter for the Airgen ERP (Twenty CRM REST API, https://erp.airgen.ai/rest).

Conventions confirmed by the Airgen Operator in Phase 1 (verify against /rest/open-api/core):
  * objects are camelCase: crmOpportunity -> REST path crmOpportunities, fields camelCase (arcOpportunityId ...)
  * list   GET   {base}/{plural}?limit=60&<cursor>=<endCursor>   -> {"data":{plural:[...]},"pageInfo":{endCursor,hasNextPage},"totalCount"}
  * create POST  {base}/batch/{plural}  (array body, plain INSERT - no upsert)  |  update PATCH {base}/{plural}/{id}
  * fingerprint GET {base}/{plural}/groupBy?group_by=[{"guid":true}]&aggregate=["countNotEmptyId","maxUpdatedAt"]
  * unknown client columns live in the RAW_JSON field `dynamicFields`
  * Twenty's `id` (UUID) != our `guid`: upsert = list existing -> insert new, PATCH changed (idempotent)
Everything uncertain is isolated in this file; tests run it against a fake Twenty server.
"""
from __future__ import annotations
import hashlib, json, re, threading, time
from datetime import datetime
import httpx
from .. import config
from .base import ERPClient, Row

PAGE = 60
CURSOR_PARAM = "startingAfter"      # Twenty versions differ (startingAfter | starting_after); flip here if the ERP rejects it
SYSTEM_FIELDS = {"id", "createdAt", "updatedAt", "deletedAt", "createdBy", "position", "name", "searchVector"}
PLURAL = {  # our object -> REST collection
    "opportunities": "crmOpportunities", "goals": "crmGoals", "accounts": "crmAccounts", "contacts": "crmContacts",
    "leads": "crmLeads", "appointments": "crmAppointments", "activity_types": "crmActivityTypes",
    "opportunity_snapshots": "crmOpportunitySnapshots", "agent_action": "crmAgentActions",
}


def camel(s: str) -> str:
    p = s.split("_")
    return p[0] + "".join(x.capitalize() for x in p[1:])


def snake(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _to_iso(v):
    if not v:
        return None
    s = str(v)
    return s + "T00:00:00.000Z" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else (s if s.endswith("Z") or "+" in s[10:] else s + ".000Z")


def _from_iso(v):
    """Back to the loader's convention: date-only at midnight, else seconds-precision ISO, no tz."""
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return v
    return dt.date().isoformat() if dt.hour == dt.minute == dt.second == 0 else dt.isoformat(timespec="seconds")


class AirgenERP(ERPClient):
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.base = (config.AIRGEN_BASE_URL or "https://erp.airgen.ai/rest").rstrip("/")
        self.http = httpx.Client(headers={"Authorization": f"Bearer {config.AIRGEN_API_KEY}"}, timeout=30, transport=transport)
        self.schema: dict = {}
        self._ids: dict[str, dict[str, str]] = {}
        self._gate = threading.Lock()
        self._last = 0.0

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        """All ERP calls go through here: spaced to AIRGEN_MAX_RPM and retried on 429 (honours Retry-After)."""
        for attempt in range(6):
            if config.AIRGEN_MAX_RPM > 0:
                with self._gate:
                    wait = self._last + 60.0 / config.AIRGEN_MAX_RPM - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                    self._last = time.monotonic()
            r = self.http.request(method, url, **kw)
            if r.status_code != 429:
                return r
            ra = r.headers.get("retry-after")
            time.sleep(min(float(ra) if ra and ra.replace(".", "").isdigit() else 12.0 * (attempt + 1), 65.0) if config.AIRGEN_MAX_RPM > 0 else 0)
        return r

    def ensure_schema(self, schema: dict) -> None:
        self.schema = schema   # objects/fields are created in Airgen by the Operator, not by this service

    # -- (de)serialisation ---------------------------------------------
    def _auth(self, obj) -> dict:
        """Log/snapshot objects are written with the separate append-only key; everything else uses the read-only key."""
        if obj in ("agent_action", "opportunity_snapshots") and config.AIRGEN_APPEND_KEY:
            return {"Authorization": f"Bearer {config.AIRGEN_APPEND_KEY}"}
        return {}

    def _types(self, obj):
        return {c: d["type"] for c, d in self.schema["objects"][obj]["columns"].items()}

    def _from_erp(self, obj, rec) -> Row:
        types, out = self._types(obj), {}
        for k, v in rec.items():
            if k in SYSTEM_FIELDS or k == "dynamicFields":
                continue
            s = snake(k)
            if s in types:
                out[s] = _from_iso(v) if types[s] == "date" else v
        dyn = rec.get("dynamicFields") or {}
        if isinstance(dyn, str):
            dyn = json.loads(dyn or "{}")
        out.update(dyn)
        for c in types:
            out.setdefault(c, None)
        return out

    def _to_erp(self, obj, row: Row) -> dict:
        types = self._types(obj)
        body, dyn = {}, {}
        for k, v in row.items():
            if k in types:
                body[camel(k)] = _to_iso(v) if types[k] == "date" else v
            elif v not in (None, ""):
                dyn[k] = v
        if dyn:
            body["dynamicFields"] = dyn
        return body

    # -- reads ----------------------------------------------------------
    def _list_raw(self, obj) -> list[dict]:
        plural, out, cursor = PLURAL[obj], [], None
        while True:
            params = {"limit": PAGE, **({CURSOR_PARAM: cursor} if cursor else {})}
            r = self._req("GET", f"{self.base}/{plural}", params=params, headers=self._auth(obj))
            r.raise_for_status()
            body = r.json()
            out += (body.get("data") or {}).get(plural, [])
            pi = body.get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                return out
            cursor = pi.get("endCursor")

    def fetch(self, obj: str) -> list[Row]:
        raw = self._list_raw(obj)
        key = self.schema["objects"][obj]["key"]
        self._ids[obj] = {r.get(camel(key)): r["id"] for r in raw if r.get(camel(key))}
        return [self._from_erp(obj, r) for r in raw]

    # -- writes ---------------------------------------------------------
    def upsert(self, obj: str, rows: list[Row], source: str = "") -> dict:
        plural, key = PLURAL[obj], self.schema["objects"][obj]["key"]
        raw = self._list_raw(obj)
        existing = {r[camel(key)]: r for r in raw if r.get(camel(key))}
        self._ids[obj] = {k: r["id"] for k, r in existing.items()}
        st = {"inserted": 0, "updated": 0, "unchanged": 0}
        new, changed = [], []
        for row in rows:
            k = row.get(key)
            if not k:
                continue
            body = self._to_erp(obj, row)
            cur = existing.get(k)
            if cur is None:
                new.append(body)
                continue
            cur_norm = self._from_erp(obj, cur)
            mine_norm = self._from_erp(obj, {**body, "dynamicFields": body.get("dynamicFields", {})})
            drop_none = lambda d: {a: b for a, b in d.items() if b not in (None, "")}
            if drop_none(cur_norm) == drop_none(mine_norm):
                st["unchanged"] += 1
            else:
                changed.append((cur["id"], body))
        for i in range(0, len(new), PAGE):
            r = self._req("POST", f"{self.base}/batch/{plural}", json=new[i:i + PAGE], headers=self._auth(obj))
            r.raise_for_status()
            st["inserted"] += len(new[i:i + PAGE])
        for rid, body in changed:
            r = self._req("PATCH", f"{self.base}/{plural}/{rid}", json=body, headers=self._auth(obj))
            r.raise_for_status()
            st["updated"] += 1
        return st

    def append(self, obj: str, rows: list[Row]) -> int:
        return self.upsert(obj, rows, "append")["inserted"]   # insert-only objects: existing keys are left untouched by design

    # -- change detection -------------------------------------------------
    def _find(self, node, name):
        if isinstance(node, dict):
            for k, v in node.items():
                if name.lower() in k.lower() and isinstance(v, (int, float, str)):
                    return v
                f = self._find(v, name)
                if f is not None:
                    return f
        elif isinstance(node, list):
            for x in node:
                f = self._find(x, name)
                if f is not None:
                    return f
        return None

    def change_token(self) -> dict[str, dict]:
        """count + max(updatedAt) from groupBy (cheap). Falls back to hashing rows if the response can't be parsed.
        NOTE: count+max(updatedAt) misses a delete followed by an insert in the same instant; acceptable for drift detection."""
        out = {}
        for obj, o in self.schema.get("objects", {}).items():
            plural, key = PLURAL.get(obj), o["key"]
            if not plural:
                continue
            try:
                r = self._req("GET", f"{self.base}/{plural}/groupBy", params={"group_by": json.dumps([{camel(key): True}]),
                                                                            "aggregate": json.dumps(["countNotEmptyId", "maxUpdatedAt"])})
                r.raise_for_status()
                body = r.json()
                cnt, mx = self._find(body, "countNotEmptyId"), self._find(body, "maxUpdatedAt")
                if cnt is None and mx is None:
                    raise ValueError("unparseable groupBy")
                out[obj] = {"count": int(cnt or 0), "checksum": str(mx)}
            except Exception:
                rows = sorted(self._list_raw(obj), key=lambda x: str(x.get("id")))
                out[obj] = {"count": len(rows), "checksum": hashlib.sha1(json.dumps([[x.get("id"), x.get("updatedAt")] for x in rows]).encode()).hexdigest()[:16]}
        return out

    def dynamic_fields(self) -> list[dict]:
        seen = {}
        for obj in self.schema.get("objects", {}):
            if obj not in PLURAL:
                continue
            for r in self._list_raw(obj):
                for k in (r.get("dynamicFields") or {}):
                    seen[(obj, k)] = {"object": obj, "name": k, "type": "str"}
        return list(seen.values())
