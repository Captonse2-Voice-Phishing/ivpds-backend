import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.errors import ApiError
from app.main import create_app


class _Payload(BaseModel):
    name: str = Field(min_length=1)
    age: int = Field(ge=1)


@pytest.fixture
def client():
    """The real app plus probe routes that exist only in this test, to trigger each kind of error."""
    app = create_app()

    @app.post("/probe/validate")
    def validate(payload: _Payload) -> _Payload:
        return payload

    @app.get("/probe/api-error")
    def api_error() -> None:
        raise ApiError(409, "PROBE_CONFLICT", "Probe conflict.")

    @app.get("/probe/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def assert_error_shape(response, status, code, path):
    body = response.json()
    assert response.status_code == status
    assert body["status"] == status
    assert body["code"] == code
    assert body["path"] == path
    assert body["requestId"] == response.headers["X-Request-Id"]
    assert "timestamp" in body and "message" in body
    return body


def test_valid_request_passes_through(client):
    response = client.post("/probe/validate", json={"name": "An", "age": 30})

    assert response.status_code == 200
    assert response.json() == {"name": "An", "age": 30}


def test_invalid_body_returns_field_errors(client):
    response = client.post("/probe/validate", json={"name": "", "age": 0})

    body = assert_error_shape(response, 422, "VALIDATION_FAILED", "/probe/validate")
    assert sorted(e["field"] for e in body["fieldErrors"]) == ["age", "name"]
    assert all(e["message"] for e in body["fieldErrors"])


def test_malformed_json_is_a_validation_error(client):
    response = client.post(
        "/probe/validate", content="{not json", headers={"Content-Type": "application/json"}
    )

    assert_error_shape(response, 422, "VALIDATION_FAILED", "/probe/validate")


def test_api_error_keeps_its_status_code_and_message(client):
    response = client.get("/probe/api-error")

    body = assert_error_shape(response, 409, "PROBE_CONFLICT", "/probe/api-error")
    assert body["message"] == "Probe conflict."
    assert "fieldErrors" not in body


def test_unexpected_exception_returns_500_without_leaking_details(client):
    response = client.get("/probe/boom")

    body = assert_error_shape(response, 500, "INTERNAL_ERROR", "/probe/boom")
    assert body["message"] == "An unexpected error occurred."
    assert "secret internal detail" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_request_id_from_the_caller_reaches_the_error_body_even_on_500(client):
    response = client.get("/probe/boom", headers={"X-Request-Id": "trace-me-1"})

    assert response.headers["X-Request-Id"] == "trace-me-1"
    assert response.json()["requestId"] == "trace-me-1"


def test_unknown_route_returns_404(client):
    response = client.get("/no-such-route")

    assert_error_shape(response, 404, "NOT_FOUND", "/no-such-route")


def test_wrong_method_returns_405(client):
    response = client.post("/health")

    assert_error_shape(response, 405, "METHOD_NOT_ALLOWED", "/health")
