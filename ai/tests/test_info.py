def test_info_requires_an_api_key(client):
    response = client.get("/v1/info")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["status"] == 401
    assert body["path"] == "/v1/info"
    assert body["requestId"] == response.headers["X-Request-Id"]
    assert "timestamp" in body


def test_info_rejects_a_wrong_api_key(client):
    for wrong in ["wrong-key", "", "test-api-key-0123456788", "TEST-API-KEY-0123456789"]:
        response = client.get("/v1/info", headers={"X-API-Key": wrong})

        assert response.status_code == 401, wrong
        assert response.json()["code"] == "UNAUTHORIZED"


def test_info_reports_the_real_state_of_each_component(client, auth):
    # This client does not run the startup that loads the model, so speech-to-text is not usable.
    response = client.get("/v1/info", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ivpds-ai"
    assert body["version"] == "0.1.0"
    assert body["components"] == {
        "audioProcessing": "READY",
        "speechToText": "UNAVAILABLE",
        "ruleEngine": "READY",
        # Implemented, but this client has no fine-tuned artifact to load.
        "nlpModel": "UNAVAILABLE",
        # Not built yet, and the service must say so.
        "riskEngine": "NOT_IMPLEMENTED",
    }
    assert body["nlpModel"] is None


def test_api_key_is_not_accepted_as_a_query_parameter(client):
    response = client.get("/v1/info", params={"X-API-Key": "test-api-key-0123456789"})

    assert response.status_code == 401
