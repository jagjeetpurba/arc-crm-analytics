"""ERP contract. The analytics backend only ever talks to this interface, so the
Airgen ERP and the local dev store are interchangeable."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

Row = dict[str, Any]


class ERPClient(ABC):
    @abstractmethod
    def ensure_schema(self, schema: dict) -> None: ...

    @abstractmethod
    def fetch(self, obj: str) -> list[Row]:
        """All rows of an object. Declared columns + dynamic `extra` fields, flattened."""

    @abstractmethod
    def upsert(self, obj: str, rows: list[Row], source: str = "") -> dict:
        """Idempotent by key. Returns {inserted, updated, unchanged}."""

    @abstractmethod
    def change_token(self) -> dict[str, dict]:
        """{object: {count, checksum}} — cheap fingerprint used by the healing agent / watcher."""

    @abstractmethod
    def dynamic_fields(self) -> list[dict]:
        """Fields discovered outside the declared schema: [{object, name, type}]."""

    @abstractmethod
    def append(self, obj: str, rows: list[Row]) -> int:
        """Append-only insert (snapshots, audit)."""
