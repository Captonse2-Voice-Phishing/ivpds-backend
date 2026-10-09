"""Tests for the Risk Engine: the scoring formula, the HTTP contract, and the README cases on the real model.

The formula tests feed hand-made indicators and probabilities, so they check the arithmetic and its guarantees.
The API tests use a stand-in classifier and check the HTTP contract only. The tests at the bottom load the real
fine-tuned artifact and are skipped when it is not mounted.
"""

import itertools
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.nlp import CONFIG_FILE, LABELS, Prediction
from app.risk import (HIGH_THRESHOLD, MEDIUM_THRESHOLD, MODEL_WEIGHT, RISK_ENGINE_VERSION, RiskLevel, assess,
                      level_of)
from app.rules import Indicator, IndicatorMatch, Severity

URL = "/v1/risk-assessments"


# Codes that are neither an impersonation nor a request, so they never form the "impersonation + request" pattern.
PLAIN_CODES = [Indicator.URGENCY, Indicator.ACCOUNT_LOCK_THREAT, Indicator.LEGAL_THREAT, Indicator.HARM_THREAT,
               Indicator.SECRECY_DEMAND, Indicator.FINANCIAL_BAIT, Indicator.CALL_HANDOFF,
               Indicator.COORDINATED_CALLERS]


def found(*severities: Severity) -> list[IndicatorMatch]:
    """Indicators with the given severities, using codes that carry no pattern bonus."""
    return [IndicatorMatch(PLAIN_CODES[index], severity, [], []) for index, severity in enumerate(severities)]


def everything(severity: Severity) -> list[IndicatorMatch]:
    """Every indicator at once, including the impersonation and request codes."""
    return [IndicatorMatch(code, severity, [], []) for code in Indicator]


# ------------------------------------------------------------------------------------ formula


def test_nothing_suspicious_scores_zero_and_is_low():
    result = assess([], 0.0)

    assert (result.risk_score, result.risk_level) == (0, RiskLevel.LOW)
    assert result.highest_severity is None
    assert result.confidence == 1.0


def test_levels_follow_the_readme_thresholds():
    assert [level_of(score) for score in (0, 29, 30, 59, 60, 100)] == [
        RiskLevel.LOW, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.HIGH]
    assert (MEDIUM_THRESHOLD, HIGH_THRESHOLD) == (30, 60)


def test_the_score_is_the_sum_of_the_three_components():
    result = assess(found(Severity.HIGH, Severity.MEDIUM), 0.5)

    assert result.model_points == pytest.approx(MODEL_WEIGHT * 0.5)
    assert result.rule_score == 15 + 8
    assert result.severity_points == 20
    assert result.risk_score == round(result.model_points + result.rule_score + result.severity_points)


def test_the_score_never_leaves_0_to_100():
    assert assess(everything(Severity.HIGH), 1.0).risk_score == 100
    for severities in itertools.product([None, Severity.LOW, Severity.MEDIUM, Severity.HIGH], repeat=3):
        for probability in (0.0, 0.3, 0.5, 0.97, 1.0):
            score = assess(found(*[s for s in severities if s]), probability).risk_score
            assert 0 <= score <= 100


def test_more_evidence_never_lowers_the_score():
    # A higher model probability, an extra indicator, or a more severe indicator can only raise the score.
    assert assess([], 0.2).risk_score <= assess([], 0.6).risk_score <= assess([], 0.9).risk_score
    assert assess(found(Severity.MEDIUM), 0.4).risk_score <= assess(found(Severity.MEDIUM, Severity.LOW), 0.4).risk_score
    assert assess(found(Severity.MEDIUM), 0.4).risk_score < assess(found(Severity.HIGH), 0.4).risk_score


def test_a_confident_model_alone_reaches_high():
    # Half of the real scam calls in the test data trip no rule at all, so the model must be able to do this.
    assert assess([], 1.0).risk_level == RiskLevel.HIGH
    assert assess([], 0.9).risk_level == RiskLevel.HIGH
    assert assess([], 0.5).risk_level == RiskLevel.MEDIUM
    assert assess([], 0.4).risk_level == RiskLevel.LOW


def test_rules_alone_raise_the_risk_but_never_reach_high():
    # Rules match phrases, including reported speech ("someone asked me for my OTP"), so without the model
    # they can only say "suspicious".
    assert assess(found(Severity.HIGH), 0.0).risk_level == RiskLevel.MEDIUM
    assert assess(everything(Severity.HIGH), 0.0).risk_level == RiskLevel.MEDIUM
    assert assess(everything(Severity.HIGH), 0.0).risk_score < HIGH_THRESHOLD


def test_weak_indicators_alone_stay_low():
    # Single MEDIUM or LOW indicators are common in ordinary calls.
    assert assess(found(Severity.LOW), 0.0).risk_level == RiskLevel.LOW
    assert assess(found(Severity.MEDIUM), 0.0).risk_level == RiskLevel.LOW
    assert assess(found(Severity.MEDIUM, Severity.LOW), 0.0).risk_level == RiskLevel.LOW
    assert assess(found(Severity.MEDIUM, Severity.MEDIUM, Severity.MEDIUM), 0.0).risk_level == RiskLevel.MEDIUM


def test_impersonation_plus_a_request_is_medium_even_when_each_indicator_is_weak():
    # README case C: "I am calling from the bank ... give me your account number" has two LOW indicators.
    impersonation = IndicatorMatch(Indicator.BANK_IMPERSONATION, Severity.LOW, [], [])
    request = IndicatorMatch(Indicator.SENSITIVE_INFORMATION, Severity.LOW, [], [])

    assert assess([impersonation], 0.0).risk_level == RiskLevel.LOW
    assert assess([request], 0.0).risk_level == RiskLevel.LOW
    assert assess([impersonation, request], 0.0).risk_level == RiskLevel.MEDIUM
    # Two weak indicators that do not form the pattern stay LOW.
    assert assess(found(Severity.LOW, Severity.LOW), 0.0).risk_level == RiskLevel.LOW


def test_rules_lift_an_undecided_model_over_the_threshold():
    assert assess([], 0.45).risk_level == RiskLevel.MEDIUM
    assert assess(found(Severity.HIGH, Severity.MEDIUM), 0.45).risk_level == RiskLevel.HIGH


def test_confidence_is_not_the_model_probability_and_reflects_agreement():
    agree_scam = assess(found(Severity.HIGH, Severity.HIGH), 1.0)
    model_only = assess([], 1.0)
    conflict = assess(found(Severity.HIGH, Severity.HIGH), 0.0)
    undecided = assess([], 0.5)

    assert agree_scam.confidence == 1.0
    assert model_only.confidence == 0.75
    assert conflict.confidence == 0.5
    assert undecided.confidence == 0.25
    for result in (agree_scam, model_only, conflict, undecided):
        assert 0.0 <= result.confidence <= 1.0


def test_a_probability_outside_0_to_1_is_rejected():
    for value in (-0.01, 1.01, float("nan")):
        with pytest.raises(ValueError):
            assess([], value)


# ------------------------------------------------------------------------------ HTTP contract


class StandInClassifier:
    """Not a model: returns a fixed probability so the HTTP contract can be tested without the artifact."""

    config = {"version": "test-version", "base_model": "stand-in"}
    name = "stand-in (test-version)"

    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.seen: list[str] = []

    def predict(self, text: str) -> Prediction:
        self.seen.append(text)
        return Prediction(label=LABELS[self.probability >= 0.5], phishing_probability=self.probability,
                          chunk_probabilities=[self.probability])


def client_with(probability: float) -> tuple[TestClient, StandInClassifier]:
    classifier = StandInClassifier(probability)
    return TestClient(create_app(classifier=classifier), raise_server_exceptions=False), classifier


def test_risk_assessment_requires_an_api_key():
    client, _ = client_with(0.9)

    response = client.post(URL, json={"text": "xin chào"})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_without_the_nlp_model_the_api_answers_503_and_never_scores_from_rules_alone(client, auth):
    response = client.post(URL, headers=auth, json={"text": "Anh đọc mã OTP cho em."})

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "NLP_MODEL_UNAVAILABLE"
    assert "riskScore" not in body and "riskLevel" not in body


def test_response_follows_the_readme_contract_in_camel_case(auth):
    client, _ = client_with(0.98)

    response = client.post(URL, headers=auth, json={
        "text": "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi."})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"riskScore", "riskLevel", "confidence", "indicators", "indicatorDetails", "components",
                         "modelVersion", "rulesetVersion", "riskEngineVersion"}
    assert body["riskLevel"] == "HIGH" and 60 <= body["riskScore"] <= 100
    assert isinstance(body["riskScore"], int)
    assert "OTP_REQUEST" in body["indicators"] and "BANK_IMPERSONATION" in body["indicators"]
    assert [detail["code"] for detail in body["indicatorDetails"]] == body["indicators"]
    assert set(body["components"]) == {"modelProbability", "modelPoints", "ruleScore", "highestSeverity",
                                       "severityPoints"}
    assert body["components"]["modelProbability"] == 0.98
    assert body["modelVersion"] == "test-version"
    assert body["riskEngineVersion"] == RISK_ENGINE_VERSION


def test_score_in_the_response_is_the_sum_of_the_reported_components(auth):
    client, _ = client_with(0.31)

    body = client.post(URL, headers=auth, json={"text": "Chuyển tiền ngay nếu không tài khoản sẽ bị khóa."}).json()

    parts = body["components"]
    assert body["riskScore"] == min(100, round(parts["modelPoints"] + parts["ruleScore"] + parts["severityPoints"]))


def test_text_without_any_signal_is_low_with_an_empty_indicator_list(auth):
    client, _ = client_with(0.0)

    body = client.post(URL, headers=auth, json={"text": "Tôi mua hàng của bạn."}).json()

    assert (body["riskScore"], body["riskLevel"], body["indicators"]) == (0, "LOW", [])
    assert body["components"]["highestSeverity"] is None


def test_turns_are_scored_and_the_model_reads_them_as_one_transcript(auth):
    client, classifier = client_with(0.95)

    response = client.post(URL, headers=auth, json={"turns": [
        {"speaker": "A", "text": "Tôi gọi từ ngân hàng."},
        {"speaker": "B", "text": "Vâng."},
        {"speaker": "A", "text": "Anh đọc mã OTP tôi vừa gửi."},
    ]})

    assert response.status_code == 200
    assert response.json()["riskLevel"] == "HIGH"
    assert classifier.seen == ["Tôi gọi từ ngân hàng. Vâng. Anh đọc mã OTP tôi vừa gửi."]


def test_invalid_bodies_are_validation_errors(auth):
    client, _ = client_with(0.5)

    for body in ({}, {"text": None}, {"text": "a", "turns": [{"speaker": "A", "text": "b"}]}, {"turns": []},
                 {"text": "x" * 100_001}):
        response = client.post(URL, headers=auth, json=body)

        assert response.status_code == 422, str(body)[:40]
        assert response.json()["code"] == "VALIDATION_FAILED"


def test_info_reports_the_risk_engine_as_ready_only_with_the_nlp_model(client, auth):
    with_model, _ = client_with(0.5)

    assert client.get("/v1/info", headers=auth).json()["components"]["riskEngine"] == "UNAVAILABLE"
    assert with_model.get("/v1/info", headers=auth).json()["components"]["riskEngine"] == "READY"


# ---------------------------------------------------------- README cases on the real artifact

ARTIFACT = Path(os.environ.get("AI_NLP_MODEL_DIR", "/opt/models/nlp"))
needs_artifact = pytest.mark.skipif(not (ARTIFACT / CONFIG_FILE).is_file(), reason="no fine-tuned artifact mounted")


@pytest.fixture(scope="module")
def real_client():
    with TestClient(create_app(classifier=None)) as client:  # runs startup, which loads the artifact
        yield client


def risk(client, auth, text: str) -> dict:
    response = client.post(URL, headers=auth, json={"text": text})
    assert response.status_code == 200
    return response.json()


@needs_artifact
def test_case_a_an_ordinary_purchase_is_low(real_client, auth):
    assert risk(real_client, auth, "Tôi mua hàng của bạn.")["riskLevel"] == "LOW"


@needs_artifact
def test_case_b_asking_for_an_account_number_to_pay_is_not_high(real_client, auth):
    assert risk(real_client, auth, "Cho tôi số tài khoản để tôi chuyển tiền.")["riskLevel"] == "LOW"


@needs_artifact
def test_case_c_bank_caller_asking_for_the_account_number_raises_the_risk(real_client, auth):
    harmless = risk(real_client, auth, "Cho tôi số tài khoản để tôi chuyển tiền.")
    suspicious = risk(real_client, auth,
                      "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Cho tôi số tài khoản.")

    assert suspicious["riskScore"] > harmless["riskScore"]
    assert suspicious["riskLevel"] in {"MEDIUM", "HIGH"}
    assert {"BANK_IMPERSONATION", "SENSITIVE_INFORMATION"} <= set(suspicious["indicators"])


@needs_artifact
def test_case_d_bank_caller_asking_for_the_otp_is_high(real_client, auth):
    body = risk(real_client, auth,
                "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi.")

    assert body["riskLevel"] == "HIGH"
    assert {"OTP_REQUEST", "BANK_IMPERSONATION"} <= set(body["indicators"])


@needs_artifact
def test_case_e_threat_with_urgency_has_the_three_expected_indicators(real_client, auth):
    body = risk(real_client, auth, "Chuyển tiền ngay nếu không tài khoản sẽ bị khóa.")

    assert {"URGENCY", "ACCOUNT_LOCK_THREAT", "MONEY_TRANSFER"} <= set(body["indicators"])
    assert body["riskLevel"] == "HIGH"


@needs_artifact
def test_case_f_entering_your_own_otp_is_not_high(real_client, auth):
    assert risk(real_client, auth, "Tôi đăng nhập ngân hàng và nhập OTP của chính tôi.")["riskLevel"] == "LOW"


@needs_artifact
def test_reported_scam_wording_in_a_family_call_is_not_high(real_client, auth):
    # The rules match the quoted demand; the model reads the context. Disagreement must not end in HIGH.
    body = risk(real_client, auth,
                "Mẹ ơi nãy có người gọi con xưng ngân hàng, đòi con đọc mã OTP. Con có đọc không? "
                "Dạ không, con tắt máy rồi chặn số luôn. Giỏi, nhớ đừng đọc mã OTP cho ai nhé con.")

    assert body["riskLevel"] != "HIGH"
