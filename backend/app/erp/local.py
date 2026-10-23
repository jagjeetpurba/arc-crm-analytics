"""SQLite-backed ERP stand-in. Same relational shape as the Airgen ERP objects."""
from __future__ import annotations
import hashlib, json, sqlite3, threading
from datetime import datetime, timezone
from pathlib import Path
from .base import ERPClient, Row

SQL_TYPE = {"str": "TEXT", "date": "TEXT", "float": "REAL", "int": "INTEGER"}


def row_hash(row: Row) -> str:
    return hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


class LocalERP(ERPClient):
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.schema: dict = {}
        with self.lock:
            self.db.execute("CREATE TABLE IF NOT EXISTS field_registry(object TEXT, name TEXT, type TEXT, first_seen TEXT, PRIMARY KEY(object,name))")
            self.db.execute("CREATE TABLE IF NOT EXISTS sync_log(ts TEXT, source TEXT, object TEXT, inserted INT, updated INT, unchanged INT)")

    # -- schema -------------------------------------------------------
    def ensure_schema(self, schema: dict) -> None:
        self.schema = schema
        with self.lock:
            for name, o in schema["objects"].items():
                cols = ", ".join(f'"{c}" {SQL_TYPE[d["type"]]}' for c, d in o["columns"].items() if c != o["key"])
                cols = (", " + cols) if cols else ""
                self.db.execute(f'CREATE TABLE IF NOT EXISTS "{name}"("{o["key"]}" TEXT PRIMARY KEY{cols}, extra TEXT DEFAULT \'{{}}\', row_hash TEXT, loaded_at TEXT)')
            self.db.commit()

    def _declared(self, obj):
        return list(self.schema["objects"][obj]["columns"])

    # -- reads --------------------------------------------------------
    def fetch(self, obj: str) -> list[Row]:
        with self.lock:
            rows = self.db.execute(f'SELECT * FROM "{obj}"').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            extra = json.loads(d.pop("extra") or "{}")
            d.pop("row_hash", None); d.pop("loaded_at", None)
            d.update(extra)
            out.append(d)
        return out

    # -- writes -------------------------------------------------------
    def upsert(self, obj: str, rows: list[Row], source: str = "") -> dict:
        decl = self._declared(obj)
        key = self.schema["objects"][obj]["key"]
        st = {"inserted": 0, "updated": 0, "unchanged": 0}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.lock:
            existing = {r[0]: r[1] for r in self.db.execute(f'SELECT "{key}", row_hash FROM "{obj}"')}
            for row in rows:
                k = row.get(key)
                if not k:
                    continue
                known = {c: row.get(c) for c in decl}
                extra = {c: v for c, v in row.items() if c not in decl and v not in (None, "")}
                h = row_hash({**known, "extra": extra})
                if k in existing and existing[k] == h:
                    st["unchanged"] += 1
                    continue
                cols = decl + ["extra", "row_hash", "loaded_at"]
                vals = [known[c] for c in decl] + [json.dumps(extra, default=str), h, now]
                q = f'INSERT OR REPLACE INTO "{obj}"({",".join(chr(34)+c+chr(34) for c in cols)}) VALUES({",".join("?"*len(cols))})'
                self.db.execute(q, vals)
                st["updated" if k in existing else "inserted"] += 1
                for c, v in extra.items():
                    t = "float" if isinstance(v, (int, float)) else "str"
                    self.db.execute("INSERT OR IGNORE INTO field_registry VALUES(?,?,?,?)", (obj, c, t, now))
            self.db.execute("INSERT INTO sync_log VALUES(?,?,?,?,?,?)", (now, source, obj, st["inserted"], st["updated"], st["unchanged"]))
            self.db.commit()
        return st

    def append(self, obj: str, rows: list[Row]) -> int:
        n = 0
        for r in rows:
            n += self.upsert(obj, [r], source="append")["inserted"]
        return n

    # -- change detection ---------------------------------------------
    def change_token(self) -> dict[str, dict]:
        out = {}
        with self.lock:
            for name in self.schema.get("objects", {}):
                key = self.schema["objects"][name]["key"]
                rows = self.db.execute(f'SELECT "{key}", row_hash FROM "{name}" ORDER BY "{key}"').fetchall()
                h = hashlib.sha1("".join(f"{a}{b}" for a, b in rows).encode()).hexdigest()[:16]
                out[name] = {"count": len(rows), "checksum": h}
        return out

    def dynamic_fields(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT object, name, type FROM field_registry")]
