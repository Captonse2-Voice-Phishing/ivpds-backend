import uuid


def test_health_is_up_without_an_api_key(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_every_response_carries_a_generated_request_id(client):
    first = client.get("/health").headers["X-Request-Id"]
    second = client.get("/health").headers["X-Request-Id"]

    assert uuid.UUID(first)
    assert first != second


def test_well_formed_request_id_from_the_caller_is_reused(client):
    response = client.get("/health", headers={"X-Request-Id": "backend-42.a_b"})

    assert response.headers["X-Request-Id"] == "backend-42.a_b"


def test_unsafe_or_overlong_request_id_is_replaced(client):
    for bad in ["bad id <script>", "a" * 65]:
        returned = client.get("/health", headers={"X-Request-Id": bad}).headers["X-Request-Id"]

        assert returned != bad
        assert uuid.UUID(returned)
