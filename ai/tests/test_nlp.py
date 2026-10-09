"""Tests for the NLP model layer: text preparation, chunking, aggregation, the API, and the real artifact.

The API tests use a stand-in classifier to check the HTTP contract only; they say nothing about model quality.
The tests at the bottom load the real fine-tuned artifact and are skipped when it is not mounted
(run them with ``-v <repo>/ai/models:/opt/models/nlp:ro -e AI_NLP_MODEL_DIR=/opt/models/nlp/<name>``).
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.nlp import CONFIG_FILE, LABELS, Prediction, aggregate, normalize_for_model, token_windows

URL = "/v1/classifications"


# ------------------------------------------------------------------------------- preprocessing


def test_text_is_normalised_to_what_a_whisper_transcript_looks_like():
    assert normalize_for_model("  Anh ĐỌC mã OTP,\ncho em!  ") == "anh đọc mã otp cho em"
    assert normalize_for_model("khoá SIM...") == "khoá sim"
    assert normalize_for_model("?!., \n") == ""


def test_short_token_lists_stay_in_one_window():
    assert token_windows([1, 2, 3], window=5, stride=2) == [[1, 2, 3]]
    assert token_windows([], window=5, stride=2) == [[]]


def test_long_token_lists_are_cut_into_overlapping_windows_that_cover_everything():
    tokens = list(range(10))

    windows = token_windows(tokens, window=4, stride=2)

    assert windows == [[0, 1, 2, 3], [2, 3, 4, 5], [4, 5, 6, 7], [6, 7, 8, 9]]
    assert all(len(window) <= 4 for window in windows)
    assert sorted({token for window in windows for token in window}) == tokens


def test_the_last_window_is_not_followed_by_a_redundant_one():
    assert token_windows(list(range(6)), window=4, stride=2) == [[0, 1, 2, 3], [2, 3, 4, 5]]
    assert token_windows(list(range(7)), window=4, stride=2)[-1] == [4, 5, 6]


def test_chunk_probabilities_are_combined_by_the_configured_method():
    scores = [0.1, 0.9, 0.5]

    assert aggregate(scores, "mean") == pytest.approx(0.5)
    assert aggregate(scores, "max") == 0.9
    assert aggregate(scores, "top2") == pytest.approx(0.7)
    assert aggregate([0.4], "top2") == 0.4
    with pytest.raises(ValueError):
        aggregate(scores, "median")


# ----------------------------------------------------------------------------- HTTP contract


class StandInClassifier:
    """Not a model: returns fixed numbers so the HTTP contract can be tested without the artifact."""

    config = {"version": "test-version", "base_model": "stand-in"}
    name = "stand-in (test-version)"

    def predict(self, text: str) -> Prediction:
        return Prediction(label=LABELS[1], phishing_probability=0.8765432, chunk_probabilities=[0.7, 0.9])


@pytest.fixture
def client_with_classifier():
    return TestClient(create_app(classifier=StandInClassifier()), raise_server_exceptions=False)


def test_classification_requires_an_api_key(client_with_classifier):
    response = client_with_classifier.post(URL, json={"text": "xin chào"})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_without_an_artifact_the_api_answers_503_and_never_invents_a_result(client, auth):
    response = client.post(URL, headers=auth, json={"text": "Anh đọc mã OTP cho em."})

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "NLP_MODEL_UNAVAILABLE"
    assert "label" not in body and "phishingProbability" not in body


def test_classification_response_is_camel_case_and_has_no_risk_fields(client_with_classifier, auth):
    response = client_with_classifier.post(URL, headers=auth, json={"text": "Anh đọc mã OTP cho em."})

    assert response.status_code == 200
    assert response.json() == {
        "label": "PHISHING", "phishingProbability": 0.876543, "chunkCount": 2, "chunkProbabilities": [0.7, 0.9],
        "modelVersion": "test-version",
    }


def test_invalid_classification_bodies_are_validation_errors(client_with_classifier, auth):
    for body in [{}, {"text": None}, {"text": 5}, {"text": "x" * 100_001}]:
        response = client_with_classifier.post(URL, headers=auth, json=body)

        assert response.status_code == 422, str(body)[:40]
        assert response.json()["code"] == "VALIDATION_FAILED"


def test_info_reports_whether_the_nlp_model_is_loaded(client, client_with_classifier, auth):
    without = client.get("/v1/info", headers=auth).json()
    with_model = client_with_classifier.get("/v1/info", headers=auth).json()

    assert without["components"]["nlpModel"] == "UNAVAILABLE" and without["nlpModel"] is None
    assert with_model["components"]["nlpModel"] == "READY"
    assert with_model["nlpModel"] == "stand-in (test-version)"


# ------------------------------------------------------------------------ the real artifact

ARTIFACT = Path(os.environ.get("AI_NLP_MODEL_DIR", "/opt/models/nlp"))
needs_artifact = pytest.mark.skipif(not (ARTIFACT / CONFIG_FILE).is_file(), reason="no fine-tuned artifact mounted")


@pytest.fixture(scope="module")
def real_classifier():
    from app.nlp import TextClassifier

    return TextClassifier(ARTIFACT)


@needs_artifact
def test_real_artifact_returns_probabilities_in_range_and_a_consistent_label(real_classifier):
    prediction = real_classifier.predict("Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi.")

    assert 0.0 <= prediction.phishing_probability <= 1.0
    assert len(prediction.chunk_probabilities) == 1
    threshold = real_classifier.config["threshold"]
    assert prediction.label == ("PHISHING" if prediction.phishing_probability >= threshold else "NORMAL")


@needs_artifact
def test_real_artifact_is_deterministic_and_ignores_case_and_punctuation(real_classifier):
    first = real_classifier.predict("Anh chuyển tiền vào tài khoản an toàn ngay, nếu không sẽ bị bắt!")
    second = real_classifier.predict("anh chuyển tiền vào tài khoản an toàn ngay nếu không sẽ bị bắt")

    assert first.phishing_probability == pytest.approx(second.phishing_probability, abs=1e-6)


@needs_artifact
def test_real_artifact_handles_empty_and_very_long_text(real_classifier):
    assert real_classifier.predict("   ").phishing_probability == 0.0
    long_text = "alo em chào anh hôm nay anh có khỏe không em gọi để hỏi thăm sức khỏe của anh " * 400

    prediction = real_classifier.predict(long_text)

    assert len(prediction.chunk_probabilities) > 5
    assert all(0.0 <= value <= 1.0 for value in prediction.chunk_probabilities)


@needs_artifact
def test_real_artifact_is_served_by_the_api(auth):
    with TestClient(create_app(classifier=None)) as client:  # runs startup, which loads the artifact
        info = client.get("/v1/info", headers=auth).json()
        response = client.post(URL, headers=auth, json={"text": "Anh đọc mã OTP cho em để em hủy giao dịch."})

    assert info["components"]["nlpModel"] == "READY"
    assert response.status_code == 200
    body = response.json()
    assert body["label"] in LABELS and 0.0 <= body["phishingProbability"] <= 1.0
    assert body["chunkCount"] == len(body["chunkProbabilities"]) == 1
