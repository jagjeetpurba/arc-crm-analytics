"""Process-wide state: specs, ERP handle, cached governed data, model. `refresh()` is the
single place data is (re)loaded — called by the watcher, by /api/sync/heal (healing agent) and after ingestion."""
from __future__ import annotations
import hashlib, json, threading, time
from datetime import date, datetime, timezone
import yaml
from . import config
from .analytics import predict, specgen
from .analytics.common import d, norm
from .analytics.engine import Engine
from .analytics.tables import test_manager
from .erp import get_erp


def _yaml(name):
    return yaml.safe_load((config.SPEC_DIR / name).read_text())


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.erp = get_erp()
        self.version = 0
        self.token: dict = {}
        self.data: dict = {}
        self.events: list[dict] = []
        self.spec_mtimes: dict = {}
        self.last_sync_at = None
        self.reload_specs()
        self.erp.ensure_schema(self.schema)
        self.refresh(force=True, reason="startup")

    # ---- specs (hot reload) ----
    def reload_specs(self) -> bool:
        m = {n: (config.SPEC_DIR / n).stat().st_mtime for n in ("erp_schema.yaml", "kpis.yaml", "dashboard.yaml", "rules.yaml")}
        if m == self.spec_mtimes:
            return False
        self.schema, self.kpis, self.dash, self.rules = _yaml("erp_schema.yaml"), _yaml("kpis.yaml"), _yaml("dashboard.yaml"), _yaml("rules.yaml")
        self.spec_mtimes = m
        if hasattr(self.erp, "ensure_schema") and self.version:
            self.erp.ensure_schema(self.schema)
        return True

    # ---- the sync / heal core ----
    def _fingerprint(self, max_age=10.0) -> dict:
        """ERP fingerprint, cached for a few seconds so status polls don't burn the ERP rate limit."""
        now = time.monotonic()
        if getattr(self, "_fp", None) is None or now - self._fp_at > max_age:
            self._fp, self._fp_at = self.erp.change_token(), now
        return self._fp

    def drift(self, fresh: dict | None = None) -> list[str]:
        fresh = fresh if fresh is not None else self._fingerprint(0)   # status checks must reflect the ERP right now
        return [o for o in set(fresh) | set(self.token) if fresh.get(o) != self.token.get(o)]

    def refresh(self, force=False, reason="") -> dict:
        with self.lock:
            spec_changed = self.reload_specs()
            self._fp = None                                   # always compare against a fresh fingerprint here
            fresh = self._fingerprint(0)
            changed = self.drift(fresh)
            if not (force or changed or spec_changed):
                return {"changed": [], "version": self.version, "spec_changed": False}
            self.token = fresh
            # re-read only what changed (first load / forced = everything) to stay inside the ERP rate limit
            todo = list(self.schema["objects"]) if (force or not self.data) else [o for o in changed if o in self.schema["objects"]]
            for o in todo:
                self.data[o] = self.erp.fetch(o)
            self.data = {o: self.data.get(o, []) for o in self.schema["objects"]}
            dates = [d(r.get(f)) for r in self.data.get("opportunities", []) for f in ("created_on", "actual_close")]
            dates = [x for x in dates if x]
            self.as_of = date.fromisoformat(config.AS_OF) if config.AS_OF else (max(dates) if dates else date.today())
            self.engine = Engine(self.data, self.schema, self.kpis, self.as_of)
            self.model = predict.train(self.data, self.as_of)
            self.generated = specgen.generate(self.data, self.schema, self.dash, self.kpis)
            self.spec_hash = hashlib.sha1(json.dumps([self.dash, self.generated], sort_keys=True, default=str).encode()).hexdigest()[:10]
            self.version += 1
            self.last_sync_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            ev = {"version": self.version, "at": self.last_sync_at, "changed": changed, "reason": reason, "spec_changed": spec_changed,
                  "spec_hash": self.spec_hash, "counts": {o: len(r) for o, r in self.data.items() if r}}
            self.events = (self.events + [ev])[-50:]
            return ev

    # ---- filter options (DQ-04/05/07) ----
    def options(self) -> dict:
        opps, goals = self.data.get("opportunities", []), self.data.get("goals", [])
        cms = sorted({norm(r["client_manager"]) for r in opps if r.get("client_manager")} | {norm(g["goal_owner"]) for g in goals if g.get("goal_owner")})
        cms = [c for c in cms if not test_manager(c, self.rules)]
        verts = sorted({norm(r["vertical"]) for r in opps if r.get("vertical")} |
                       {norm(a["business_vertical"]) for a in self.data.get("accounts", []) if a.get("business_vertical")})
        qs = set()
        for r in opps:
            for f in ("created_on", "actual_close", "estimated_close"):
                x = d(r.get(f))
                if x: qs.add(f"{x.year}-Q{(x.month - 1) // 3 + 1}")
        gq = set()
        for g in goals:
            x = d(g.get("goal_start"))
            if x: gq.add(f"{x.year}-Q{(x.month - 1) // 3 + 1}")
        periods = [{"value": "all", "label": "All dates"}] + [{"value": q, "label": q.replace("-", " ")} for q in sorted(qs)]
        default = sorted(gq)[-1] if gq else "all"
        dyn = {}
        for f in self.generated["filters"]:
            vals = sorted({norm(r.get(f["name"])) for r in self.data.get(f["source"], []) if r.get(f["name"]) not in (None, "")})
            dyn[f["name"]] = {"label": f["label"], "options": vals, "source": f["source"]}
        return {"period": {"options": periods, "default": default},
                "client_manager": {"label": "Client manager", "options": cms},
                "vertical": {"label": "Vertical", "options": verts}, "dynamic": dyn}

    def all_pages(self):
        return self.dash["pages"] + self.generated["pages"]

    def find_widget(self, wid):
        for p in self.all_pages():
            for w in p["widgets"]:
                if w["id"] == wid:
                    return w
        return None


_state: State | None = None


def get_state() -> State:
    global _state
    if _state is None:
        _state = State()
    return _state


def start_watcher():
    """Fallback poller: even without the Airgen healing agent the screen follows the ERP."""
    if config.WATCH_INTERVAL_S <= 0:
        return
    def loop():
        while True:
            time.sleep(config.WATCH_INTERVAL_S)
            try:
                get_state().refresh(reason="watcher")
            except Exception as e:  # keep the poller alive
                print("watcher error:", e)
    threading.Thread(target=loop, daemon=True, name="erp-watcher").start()
