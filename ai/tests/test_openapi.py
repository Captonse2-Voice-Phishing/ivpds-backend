def test_openapi_document_describes_the_api(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "IVPDS AI Service"
    assert set(document["paths"]) == {"/health", "/v1/info", "/v1/indicators", "/v1/transcriptions"}


def test_openapi_marks_v1_routes_as_api_key_protected_and_health_as_open(client):
    document = client.get("/openapi.json").json()

    schemes = document["components"]["securitySchemes"]
    assert [s for s in schemes.values() if s["type"] == "apiKey" and s["name"] == "X-API-Key" and s["in"] == "header"]
    assert document["paths"]["/v1/info"]["get"]["security"]
    assert "security" not in document["paths"]["/health"]["get"]


def test_openapi_uses_camel_case_field_names(client):
    document = client.get("/openapi.json").json()

    assert set(document["components"]["schemas"]["PipelineComponents"]["properties"]) == {
        "audioProcessing",
        "speechToText",
        "ruleEngine",
        "nlpModel",
        "riskEngine",
    }


def test_swagger_ui_is_served(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text
