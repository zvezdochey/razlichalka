from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import create_app


def make_client():
    app = create_app()

    @app.get("/api/_conflict")
    def _conflict():
        raise ApiError("conflict", "нельзя удалить встроенную процедуру")

    @app.get("/api/_boom")
    def _boom():
        raise RuntimeError("секретная трассировка")

    @app.get("/api/_need/{n}")
    def _need(n: int):
        return {"n": n}

    return TestClient(app, raise_server_exceptions=False)


def test_health():
    r = make_client().get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_route_is_not_found():
    r = make_client().get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_api_error_conflict():
    r = make_client().get("/api/_conflict")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "conflict", "message": "нельзя удалить встроенную процедуру"}}


def test_unexpected_error_is_internal_without_trace():
    r = make_client().get("/api/_boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"
    assert "секретная" not in r.text


def test_validation_error_is_400_with_field():
    r = make_client().get("/api/_need/abc")
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "bad_file"
    assert "n" in err["message"]
