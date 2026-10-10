"""Tests for administrator-managed patterns: extra phrase rules sent along with a request.

They cover the rule itself (what it matches and what it must not), how it combines with the built-in rules and
the Risk Engine, and the three places that accept patterns: /v1/indicators, /v1/risk-assessments and live sessions.
"""

import json
import unicodedata

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from helpers import API_KEY, make_settings

from app.main import create_app
from app.risk import RiskLevel, assess
from app.rules import CUSTOM_RULE_SEVERITY, Indicator, RuleEngine, Severity, Turn, custom_rule
from test_live import CALLER, HEADERS, KeywordClassifier, ScriptedTranscriber, read_until, silence, tone
from test_risk import StandInClassifier

ENGINE = RuleEngine()
# A made-up product name, so that no built-in rule matches it.
GIFT = custom_rule("p1", Indicator.FINANCIAL_BAIT, "Gói bảo an, tâm phúc")


def codes(matches) -> list[str]:
    return [match.code.value for match in matches]


# ---------------------------------------------------------------------------------- the rule


def test_a_custom_phrase_is_found_whatever_its_case_and_punctuation():
    found = ENGINE.analyze("Dạ bên em có GÓI BẢO AN tâm phúc ạ.", [GIFT])

    assert codes(found) == ["FINANCIAL_BAIT"]
    assert found[0].severity == CUSTOM_RULE_SEVERITY == Severity.MEDIUM
    assert found[0].rule_ids == ["CUSTOM-p1"]
    assert found[0].evidence == ["gói bảo an tâm phúc"]


def test_without_the_pattern_the_same_text_has_no_indicator():
    assert ENGINE.analyze("Dạ bên em có gói bảo an tâm phúc ạ.") == []


def test_a_custom_phrase_matches_whole_words_only_and_not_across_sentences():
    rule = custom_rule("p2", Indicator.URGENCY, "hạn chót hôm nay")

    # "nhạn" ends with "hạn", but it is another word.
    assert ENGINE.analyze("Con nhạn chót hôm nay bay về.", [rule]) == []
    assert ENGINE.analyze("Đây là hạn chót. Hôm nay em gọi lại.", [rule]) == []
    assert codes(ENGINE.analyze("Đây là hạn chót hôm nay rồi anh.", [rule])) == ["URGENCY"]


def test_a_negated_occurrence_is_not_counted():
    rule = custom_rule("p3", Indicator.REMOTE_ACCESS_REQUEST, "cài ứng dụng hỗ trợ")

    assert ENGINE.analyze("Bố nhớ đừng cài ứng dụng hỗ trợ nào người lạ gửi nhé.", [rule]) == []
    assert codes(ENGINE.analyze("Anh cài ứng dụng hỗ trợ theo link em gửi.", [rule])) == ["REMOTE_ACCESS_REQUEST"]


@pytest.mark.parametrize(("indicator", "phrase"), [
    (Indicator.URGENCY, "gấp"),
    (Indicator.URGENCY, "  ...  "),
    (Indicator.URGENCY, "gấp!!!"),
    (Indicator.COORDINATED_CALLERS, "hai người gọi"),
])
def test_patterns_that_would_match_too_much_or_make_no_sense_are_rejected(indicator, phrase):
    with pytest.raises(ValueError):
        custom_rule("bad", indicator, phrase)


def test_words_are_counted_as_typed_so_whatever_the_backend_accepted_is_accepted_here():
    # The backend counts runs of letters and digits in the phrase as typed. A speech-recognition fix that
    # merges two typed words into one must not turn an accepted pattern into a rejected one.
    merged = custom_rule("p4", Indicator.FINANCIAL_BAIT, "phây búc")
    assert codes(ENGINE.analyze("Em nhắn anh qua facebook rồi đó.", [merged])) == ["FINANCIAL_BAIT"]

    # Tone marks typed as separate characters are part of their word, not word boundaries.
    decomposed = unicodedata.normalize("NFD", "hạn chót")
    assert codes(ENGINE.analyze("Đây là hạn chót rồi anh.", [custom_rule("p5", Indicator.URGENCY, decomposed)])) == [
        "URGENCY"]
    with pytest.raises(ValueError):
        custom_rule("p6", Indicator.URGENCY, unicodedata.normalize("NFD", "chót"))

    # A phrase with a stray "|" counts as two words; it compiles and simply never matches.
    assert ENGINE.analyze("Anh đọc mã otp cho em.", [custom_rule("p7", Indicator.URGENCY, "abc|xyz")])[0].rule_ids != [
        "CUSTOM-p7"]


def test_a_custom_match_joins_the_built_in_rules_without_lowering_their_severity():
    rule = custom_rule("p4", Indicator.OTP_REQUEST, "đọc mã otp")
    text = "Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi."

    built_in = {m.code: m for m in ENGINE.analyze(text)}
    combined = {m.code: m for m in ENGINE.analyze(text, [rule])}

    assert built_in[Indicator.OTP_REQUEST].severity == Severity.HIGH
    assert combined[Indicator.OTP_REQUEST].severity == Severity.HIGH
    assert "CUSTOM-p4" in combined[Indicator.OTP_REQUEST].rule_ids
    assert set(built_in[Indicator.OTP_REQUEST].rule_ids) < set(combined[Indicator.OTP_REQUEST].rule_ids)
    assert set(combined) == set(built_in)


def test_in_a_conversation_the_custom_indicator_belongs_to_whoever_said_the_phrase():
    analysis = ENGINE.analyze_conversation([
        Turn("A", "Bên em có gói bảo an tâm phúc."),
        Turn("B", "Vậy à, tôi cảm ơn."),
    ], [GIFT])

    assert codes(analysis.indicators) == ["FINANCIAL_BAIT"]
    assert {speaker.speaker: [i.value for i in speaker.indicators] for speaker in analysis.speakers} == {
        "A": ["FINANCIAL_BAIT"], "B": []}


def test_custom_patterns_alone_cannot_push_a_call_to_high_risk():
    # Even many custom matches, with a model that sees nothing wrong, stay below HIGH.
    rules = [custom_rule(f"m{index}", indicator, "gói bảo an tâm phúc")
             for index, indicator in enumerate(i for i in Indicator if i != Indicator.COORDINATED_CALLERS)]

    found = ENGINE.analyze("Bên em có gói bảo an tâm phúc cho anh.", rules)

    assert len(found) == len(rules)
    assert all(match.severity == Severity.MEDIUM for match in found)
    assert assess(found, 0.0).risk_level == RiskLevel.MEDIUM
    assert assess(ENGINE.analyze("Bên em có gói bảo an tâm phúc cho anh.", [GIFT]), 0.0).risk_level == RiskLevel.LOW


# -------------------------------------------------------------------------------- HTTP APIs

PATTERN = {"id": "7f3c", "indicatorCode": "FINANCIAL_BAIT", "phrase": "gói bảo an tâm phúc"}
TEXT = "Bên em có gói bảo an tâm phúc cho anh."


def test_indicators_api_applies_the_patterns_sent_with_the_request(client, auth):
    plain = client.post("/v1/indicators", headers=auth, json={"text": TEXT}).json()
    custom = client.post("/v1/indicators", headers=auth, json={"text": TEXT, "customPatterns": [PATTERN]}).json()

    assert plain["indicators"] == []
    assert custom["indicators"] == [{"code": "FINANCIAL_BAIT", "severity": "MEDIUM",
                                     "evidence": ["gói bảo an tâm phúc"], "ruleIds": ["CUSTOM-7f3c"]}]
    # Patterns belong to one request: the next request without them is unaffected.
    assert client.post("/v1/indicators", headers=auth, json={"text": TEXT}).json()["indicators"] == []


@pytest.mark.parametrize("pattern", [
    {"id": "x", "indicatorCode": "NOT_A_CODE", "phrase": "gói bảo an tâm phúc"},
    {"id": "x", "indicatorCode": "URGENCY", "phrase": "gấp"},
    {"id": "x", "indicatorCode": "COORDINATED_CALLERS", "phrase": "hai người gọi"},
    {"id": "bad id!", "indicatorCode": "URGENCY", "phrase": "hạn chót hôm nay"},
    {"indicatorCode": "URGENCY", "phrase": "hạn chót hôm nay"},
    {"id": "x", "indicatorCode": "URGENCY", "phrase": "a" * 201},
])
def test_an_unusable_pattern_is_a_validation_error_not_silently_ignored(client, auth, pattern):
    response = client.post("/v1/indicators", headers=auth, json={"text": TEXT, "customPatterns": [pattern]})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_risk_assessment_counts_the_custom_indicator_and_says_which_pattern_matched(auth):
    client = TestClient(create_app(classifier=StandInClassifier(0.0)), raise_server_exceptions=False)

    plain = client.post("/v1/risk-assessments", headers=auth, json={"text": TEXT}).json()
    custom = client.post("/v1/risk-assessments", headers=auth,
                         json={"text": TEXT, "customPatterns": [PATTERN]}).json()

    assert plain["indicators"] == [] and plain["riskScore"] < custom["riskScore"]
    assert custom["indicators"] == ["FINANCIAL_BAIT"]
    assert custom["indicatorDetails"][0]["ruleIds"] == ["CUSTOM-7f3c"]
    assert custom["riskLevel"] == "LOW"
    assert custom["components"]["highestSeverity"] == "MEDIUM"


# ------------------------------------------------------------------------------ live sessions


def live_app(lines):
    return create_app(make_settings(), ScriptedTranscriber(lines), KeywordClassifier())


def test_a_live_session_uses_the_patterns_given_in_its_start_message():
    with TestClient(live_app([TEXT])).websocket_connect("/v1/live-sessions", headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_text(json.dumps({"type": "start", "customPatterns": [PATTERN]}))
        websocket.send_bytes(CALLER + tone(1) + silence(1))
        events = read_until(websocket, "risk")
        websocket.send_text('{"type": "end"}')
        final = read_until(websocket, "final")[-1]

    assert events[-1]["indicators"] == ["FINANCIAL_BAIT"] == events[-1]["newIndicators"]
    assert final["indicators"] == ["FINANCIAL_BAIT"]


def test_a_live_session_without_a_start_message_uses_only_the_built_in_rules():
    with TestClient(live_app([TEXT])).websocket_connect("/v1/live-sessions", headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_bytes(CALLER + tone(1) + silence(1))
        assert read_until(websocket, "risk")[-1]["indicators"] == []


@pytest.mark.parametrize(("messages", "code"), [
    ([json.dumps({"type": "start", "customPatterns": [{"id": "x", "indicatorCode": "NOPE", "phrase": "a b"}]})],
     "INVALID_CUSTOM_PATTERNS"),
    ([json.dumps({"type": "start", "customPatterns": "everything"})], "INVALID_CUSTOM_PATTERNS"),
    ([CALLER + tone(0.2), json.dumps({"type": "start", "customPatterns": [PATTERN]})], "INVALID_MESSAGE"),
])
def test_bad_or_late_start_messages_stop_the_live_session_with_a_reason(messages, code):
    with TestClient(live_app([])).websocket_connect("/v1/live-sessions", headers=HEADERS) as websocket:
        websocket.receive_json()
        for message in messages:
            if isinstance(message, bytes):
                websocket.send_bytes(message)
            else:
                websocket.send_text(message)
        error = websocket.receive_json()
        assert (error["type"], error["code"]) == ("error", code)
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()
