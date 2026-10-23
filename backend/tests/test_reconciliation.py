"""BRD §12.1 reconciliation: figures must equal the reference values in BRD Appendix B."""
import pytest
from app.state import get_state


def kpi(c, w, **f):
    return c.get(f"/api/widget/{w}", params=f).json()["payload"]


def item(payload, kid):
    return next(i for i in payload["items"] if i["id"] == kid)


def test_counts_by_status():
    e = get_state().engine
    n = lambda k: e.run({"kpi": k}, {})["value"]
    assert n("won_count") == 273 and n("lost_count") == 49 and n("open_count") == 179


def test_q3_target_matches_brd():
    e = get_state().engine
    assert e.run({"kpi": "quarterly_gp_target"}, {"period": "2026-Q3"})["value"] == 10_436_648


def test_q3_close_6869748_81_deals():
    r = get_state().engine.run({"kpi": "achieved_gp"}, {"period": "2026-Q3"})
    assert round(r["value"]) == 6_869_748 and r["scope"]["record_count"] == 81


def test_q3_by_month():
    rows = get_state().engine.run({"kpi": "achieved_gp", "group_by": "actual_close:month"}, {"period": "2026-Q3"})["rows"]
    m = {r["key"]: round(r["value"]) for r in rows}
    assert m == {"2026-07": 2_180_077, "2026-08": 692_236, "2026-09": 3_997_435}


def test_achieved_gp_won_only_all_dates():
    assert round(get_state().engine.run({"kpi": "achieved_gp"}, {})["value"]) == 14_425_155


def test_every_figure_has_scope(client):
    p = kpi(client, "exec_kpis", period="2026-Q3")
    for i in p["items"]:
        s = i["scope"]
        assert s["as_of"] and "record_count" in s and "governing_date" in s


def test_period_mismatch_withholds_percentage(client):
    p = kpi(client, "exec_kpis", period="all")
    assert p["comparison_flag"] and "vs_target" not in item(p, "achieved_gp")


def test_unsupported_filter_is_reported_not_faked(client):
    p = kpi(client, "exec_kpis", period="2026-Q3", vertical="Government")
    assert "vertical" in item(p, "quarterly_gp_target")["scope"]["filters_ignored"]


def test_idempotent_reload():
    from app.ingest.loader import load_workbook_into_erp
    from tests.conftest import WORKBOOK
    s = get_state()
    load_workbook_into_erp(WORKBOOK, s.erp, s.schema)      # first pass may legitimately change rows
    before = s.erp.change_token()
    rep = load_workbook_into_erp(WORKBOOK, s.erp, s.schema)
    assert all(r["inserted"] == 0 and r["updated"] == 0 for r in rep.values())
    assert s.erp.change_token() == before
