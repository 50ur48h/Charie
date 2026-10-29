from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from charie.shared.errors import ApiError, install_error_handlers
from charie.shared.web import create_app


@pytest.fixture()
def screens(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<p>app</p>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("code", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(screens: Path) -> TestClient:
    return TestClient(create_app("chat", static_dir=screens))


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"ok": True}


def test_unknown_api_address_is_json_404(client: TestClient):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "message": "That address doesn't exist."}


def test_api_error_shape():
    from fastapi import FastAPI

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/api/boom")
    async def boom() -> None:
        raise ApiError(409, "x", "y")

    assert TestClient(app).get("/api/boom").json() == {"error": "x", "message": "y"}


def test_crash_is_plain_500():
    from fastapi import FastAPI

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError("stack traces stay in the log")

    response = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {
        "error": "server_error",
        "message": "Something went wrong on our side. Please try again.",
    }


def test_bad_request_names_fields():
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI()
    install_error_handlers(app)

    class Body(BaseModel):
        name: str
        age: int

    @app.post("/api/thing")
    async def thing(body: Body) -> None:
        raise AssertionError("unreachable")

    response = TestClient(app).post("/api/thing", json={"name": 1})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert "age" in response.json()["message"]


def test_page_address_gets_index_html(client: TestClient):
    response = client.get("/settings")
    assert response.status_code == 200
    assert "<p>app</p>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_asset_is_served_with_long_cache(client: TestClient):
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_no_files_outside_static_dir(client: TestClient):
    response = client.get("/../pyproject.toml")
    assert "<p>app</p>" in response.text


def test_screens_not_built_message(tmp_path: Path):
    app = create_app("chat", static_dir=tmp_path / "missing")
    response = TestClient(app).get("/settings")
    assert response.status_code == 404
    assert response.json() == {
        "error": "screens_not_built",
        "message": "The screens aren't built yet. Run npm run build in frontend/.",
    }
