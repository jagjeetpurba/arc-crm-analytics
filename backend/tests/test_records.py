def test_record_lookup(client):
    r = client.get("/api/records/opportunities", params={"arc_opportunity_id": "2026-O-00231"}).json()
    assert r["total"] >= 1 and r["rows"][0]["client_manager"] and r["scope"]["data_version"]
    assert client.get("/api/records/agent_action").status_code == 404
    assert client.get("/api/records/opportunities", params={"q": "alrostamani", "limit": 5}).json()["total"] >= 0


def test_drill_does_not_treat_group_by_as_filter(client):
    r = client.get("/api/drill/achieved_gp", params={"period": "2026-Q3", "group_by": "actual_close:month", "key": "2026-07"}).json()
    assert r["scope"]["filters_ignored"] == {} and r["total"] > 0
    assert all((x["actual_close"] or "").startswith("2026-07") for x in r["rows"])
