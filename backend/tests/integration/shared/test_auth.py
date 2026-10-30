"""Real login: password check, lockout, sessions, guards, and the 4 addresses."""

import pytest
from fastapi.testclient import TestClient

import charie.shared.auth as auth
from charie.shared.auth import LoginLimiter
from tests.conftest import log_in


@pytest.fixture(autouse=True)
def _fresh_security(monkeypatch):
    auth.limiter.tries.clear()
    monkeypatch.setattr(auth, "now", lambda: 1_700_000_000.0)
    yield
    auth.limiter.tries.clear()


def _move_clock(monkeypatch, seconds):
    monkeypatch.setattr(auth, "now", lambda: 1_700_000_000.0 + seconds)


def test_right_password_signs_in(chat_client):
    log_in(chat_client)
    response = chat_client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["logged_in"] is True


def test_wrong_password_is_refused(chat_client):
    response = chat_client.post("/api/login", json={"password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"] == "wrong_password"


def test_five_wrong_tries_block_for_five_minutes(chat_client, monkeypatch):
    for _ in range(5):
        assert chat_client.post("/api/login", json={"password": "nope"}).status_code == 401
    blocked = chat_client.post("/api/login", json={"password": "test-password"})
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "too_many_tries"
    _move_clock(monkeypatch, 5 * 60 + 1)
    log_in(chat_client)


def test_other_address_not_blocked():
    limiter = LoginLimiter()
    for _ in range(5):
        limiter.record("one")
    assert limiter.blocked("one")
    assert not limiter.blocked("two")


def _api_routes(app):
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path.startswith("/api/"):
            yield path, methods


def test_every_api_address_needs_login(chat_client, learner_client):
    from charie.chat.app import build_app as chat_app
    from charie.learner.app import build_app as learner_app

    for client, build in ((chat_client, chat_app), (learner_client, learner_app)):
        for path, methods in _api_routes(build()):
            if path in ("/api/login", "/api/health"):
                continue
            method = "GET" if "GET" in methods else sorted(methods)[0]
            if path == "/api/settings":
                body: dict = {"theme": "sage"}
            elif path == "/api/password":
                body = {"current": "test-password", "new": "new-password-ok"}
            else:
                body = {}
            response = client.request(method, path, json=body if method != "GET" else None)
            assert response.status_code == 401, (path, method)
            assert response.json()["error"] == "login_needed"


def test_login_and_health_are_public(chat_client):
    assert chat_client.get("/api/health").status_code == 200
    response = chat_client.post("/api/login", json={"password": "nope"})
    assert response.json()["error"] == "wrong_password"


def test_expired_session_needs_login(chat_client, monkeypatch):
    log_in(chat_client)
    assert chat_client.get("/api/me").status_code == 200
    _move_clock(monkeypatch, 7 * 24 * 60 * 60 + 1)
    assert chat_client.get("/api/me").status_code == 401


def test_password_change(chat_client):
    log_in(chat_client)
    response = chat_client.post(
        "/api/password", json={"current": "test-password", "new": "new-password-ok"}
    )
    assert response.status_code == 200
    from charie.shared.db import session_scope

    with session_scope() as session:
        from charie.shared.settings import get_setting

        assert get_setting(session, "password_hash").startswith("$argon2id$")
    assert chat_client.get("/api/me").status_code == 200
    from charie.chat.app import build_app

    fresh = TestClient(
        build_app(), base_url="http://testserver", headers={"Origin": "http://testserver"}
    )
    assert fresh.post("/api/login", json={"password": "test-password"}).status_code == 401
    assert fresh.post("/api/login", json={"password": "new-password-ok"}).status_code == 200


def test_password_change_needs_current(chat_client):
    log_in(chat_client)
    response = chat_client.post(
        "/api/password", json={"current": "wrong", "new": "new-password-ok"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "wrong_password"


def test_new_password_too_short(chat_client):
    log_in(chat_client)
    response = chat_client.post("/api/password", json={"current": "test-password", "new": "short"})
    assert response.status_code == 400
    assert response.json()["error"] == "password_too_short"


def test_foreign_origin_is_refused(chat_client):
    log_in(chat_client)
    response = chat_client.post("/api/logout", headers={"Origin": "http://evil.test"}, json={})
    assert response.status_code == 403
    assert response.json()["error"] == "bad_origin"


def test_missing_origin_is_refused(chat_client):
    log_in(chat_client)
    response = chat_client.post("/api/logout", headers={"Origin": ""}, json={})
    assert response.status_code == 403


def test_non_json_change_is_refused(chat_client):
    log_in(chat_client)
    response = chat_client.post(
        "/api/logout", content=b"not json", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 415
    assert response.json()["error"] == "json_only"


def test_logout_ends_session(chat_client):
    log_in(chat_client)
    assert chat_client.post("/api/logout").status_code == 200
    assert chat_client.get("/api/me").status_code == 401


def test_me_shows_setup_done_theme_and_app_addresses(chat_client, monkeypatch):
    log_in(chat_client)
    me = chat_client.get("/api/me").json()
    assert me["setup_done"] is False
    assert me["theme"] == "sage"
    assert me["chat_url"] == "http://localhost:5173"
    assert me["learner_url"] == "http://localhost:5174"
    assert chat_client.patch("/api/settings", json={"theme": "mist"}).status_code == 200
    assert chat_client.get("/api/me").json()["theme"] == "mist"
    monkeypatch.setenv("CHARIE_CHAT_URL", "http://chat.example")
    monkeypatch.setenv("CHARIE_LEARNER_URL", "http://learner.example")
    from charie.shared.config import get_settings

    get_settings.cache_clear()
    me = chat_client.get("/api/me").json()
    assert me["chat_url"] == "http://chat.example"
    assert me["learner_url"] == "http://learner.example"


def test_no_password_set_message(chat_client, monkeypatch):
    auth.limiter.tries.clear()
    from charie.shared.config import Settings

    monkeypatch.setattr("charie.shared.auth.get_settings", lambda: Settings(charie_password=None))
    response = chat_client.post("/api/login", json={"password": "anything"})
    assert response.status_code == 503
    assert response.json()["error"] == "no_password"
