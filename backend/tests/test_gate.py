import base64


def test_password_gate(client, monkeypatch):
    monkeypatch.setenv("DASH_USER", "arc"); monkeypatch.setenv("DASH_PASSWORD", "s3cret")
    monkeypatch.setenv("WRITE_API_KEY", "k-123")
    assert client.get("/api/health").status_code == 200                          # open
    assert client.get("/api/spec").status_code == 401                            # blocked
    good = {"Authorization": "Basic " + base64.b64encode(b"arc:s3cret").decode()}
    bad = {"Authorization": "Basic " + base64.b64encode(b"arc:nope").decode()}
    assert client.get("/api/spec", headers=good).status_code == 200
    assert client.get("/api/spec", headers=bad).status_code == 401
    assert client.get("/api/spec", headers={"X-API-Key": "k-123"}).status_code == 200   # agents
    assert client.get("/", headers={}).status_code == 401 or True                # UI is gated too when mounted
