from __future__ import annotations
import re
from datetime import date, datetime, timedelta


def d(v):
    """ISO string/datetime/date -> date | None"""
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def norm(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else None


def period_range(p: str | None):
    """'2026-Q3' | '2026' | '2026-09' | 'all' -> (start,end) inclusive dates or None"""
    if not p or p == "all":
        return None
    m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
    if m:
        y, q = int(m[1]), int(m[2])
        s = date(y, 3 * q - 2, 1)
        e = date(y + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1)
        return s, e
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m:
        y, mo = int(m[1]), int(m[2])
        return date(y, mo, 1), date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
    m = re.fullmatch(r"(\d{4})", p)
    if m:
        y = int(m[1])
        return date(y, 1, 1), date(y, 12, 31)
    return None


def is_status(r, *names):
    s = (norm(r.get("status_reason")) or "").lower()
    return s in [n.lower() for n in names]


def is_open(r):
    return is_status(r, "in progress")
