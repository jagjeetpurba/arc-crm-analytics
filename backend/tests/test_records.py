def test_record_lookup(client):
    r = client.get("/api/records/opportunities", params={"arc_opportunity_id": "2026-O-00231"}).json()
    assert r["total"] >= 1 and r["rows"][0]["client_manager"] and r["scope"]["data_version"]
    assert client.get("/api/records/agent_action").status_code == 404
    assert client.get("/api/records/opportunities", params={"q": "alrostamani", "limit": 5}).json()["total"] >= 0
