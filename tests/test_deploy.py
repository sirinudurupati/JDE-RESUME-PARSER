import base64

import pytest


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_no_password_means_open_on_localhost(client):
    assert client.get("/").status_code == 200


def test_password_protects_everything_but_health(client, monkeypatch):
    monkeypatch.setenv("TM_PASSWORD", "s3cret")
    assert client.get("/healthz").get_json() == {"status": "ok"}          # health check stays open
    for path in ("/", "/api/jobs", "/api/config", "/static/app.js"):
        r = client.get(path)
        assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"], path
    assert client.get("/api/jobs", headers=basic("hr", "wrong")).status_code == 401
    assert client.get("/api/jobs", headers=basic("other", "s3cret")).status_code == 401
    assert client.get("/api/jobs", headers=basic("hr", "s3cret")).status_code == 200
    assert client.post("/api/jobs/upload").status_code == 401             # uploads need the login too


def test_custom_user(client, monkeypatch):
    monkeypatch.setenv("TM_PASSWORD", "pw")
    monkeypatch.setenv("TM_USER", "recruiter")
    assert client.get("/", headers=basic("recruiter", "pw")).status_code == 200
    assert client.get("/", headers=basic("hr", "pw")).status_code == 401


def test_production_refuses_to_start_without_password(monkeypatch, tmp_path):
    from talentmatch import config
    from talentmatch.web import create_app
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "u")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setenv("TM_ENV", "production")
    monkeypatch.delenv("TM_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="TM_PASSWORD"):
        create_app()
    monkeypatch.setenv("TM_PASSWORD", "x")
    app = create_app()                                                     # fine once a password exists
    r = app.test_client().get("/", headers=basic("hr", "x"))
    assert r.status_code == 200 and "Strict-Transport-Security" in r.headers
