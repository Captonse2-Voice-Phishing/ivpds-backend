URL = "/v1/indicators"


def test_indicators_requires_an_api_key(client):
    response = client.post(URL, json={"text": "Anh đọc mã OTP cho em."})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_indicators_are_returned_with_evidence_in_camel_case(client, auth):
    text = "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi."

    response = client.post(URL, headers=auth, json={"text": text})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"indicators", "rulesetVersion", "speakers", "speakerCount"}
    assert body["rulesetVersion"]
    assert body["speakers"] == [] and body["speakerCount"] == 0
    assert body["indicators"] == [
        {"code": "OTP_REQUEST", "severity": "HIGH", "evidence": ["đọc mã otp"], "ruleIds": ["OTP-1"]},
        {"code": "BANK_IMPERSONATION", "severity": "LOW", "evidence": ["tôi gọi từ ngân hàng"], "ruleIds": ["BI-1"]},
    ]


def test_text_without_signals_returns_an_empty_list_not_an_error(client, auth):
    for text in ["Tôi mua hàng của bạn.", "", "   "]:
        response = client.post(URL, headers=auth, json={"text": text})

        assert response.status_code == 200, text
        assert response.json()["indicators"] == []


def test_the_response_never_contains_a_risk_score_or_level(client, auth):
    # Indicators are evidence only; scoring belongs to the Risk Engine, which does not exist yet.
    body = client.post(URL, headers=auth, json={"text": "Chuyển tiền ngay nếu không tài khoản sẽ bị khóa."}).json()

    assert "riskScore" not in body and "riskLevel" not in body and "confidence" not in body
    assert {i["code"] for i in body["indicators"]} == {"MONEY_TRANSFER", "URGENCY", "ACCOUNT_LOCK_THREAT"}


def test_invalid_bodies_are_validation_errors(client, auth):
    for body in [{"text": 123}, {"text": ["a"]}, {"text": "x" * 100_001}]:
        response = client.post(URL, headers=auth, json=body)

        assert response.status_code == 422, str(body)[:40]
        assert response.json()["code"] == "VALIDATION_FAILED"
        assert response.json()["fieldErrors"][0]["field"] == "text"


TURNS = [
    {"speaker": "Người gọi 1", "text": "Em là nhân viên ngân hàng Vietcombank, em chuyển máy cho đồng chí điều tra viên ạ."},
    {"speaker": "Nạn nhân", "text": "Có chuyện gì vậy?"},
    {"speaker": "Người gọi 2", "text": "Tôi là đại úy Hùng. Chị chuyển toàn bộ tiền vào tài khoản tạm giữ."},
]


def test_conversation_with_three_speakers_is_analysed_per_speaker(client, auth):
    response = client.post(URL, headers=auth, json={"turns": TURNS})

    assert response.status_code == 200
    body = response.json()
    assert body["speakerCount"] == 3
    assert body["speakers"] == [
        {"speaker": "Người gọi 1", "turns": 1, "indicators": ["BANK_IMPERSONATION", "CALL_HANDOFF"]},
        {"speaker": "Nạn nhân", "turns": 1, "indicators": []},
        {"speaker": "Người gọi 2", "turns": 1, "indicators": ["MONEY_TRANSFER", "AUTHORITY_IMPERSONATION"]},
    ]
    coordinated = next(i for i in body["indicators"] if i["code"] == "COORDINATED_CALLERS")
    assert coordinated == {"code": "COORDINATED_CALLERS", "severity": "MEDIUM",
                           "evidence": ["speakers: Người gọi 1, Người gọi 2"], "ruleIds": ["CC-1"]}


def test_text_with_speaker_labels_gives_the_same_result_as_turns(client, auth):
    text = " ".join(f"{t['speaker']}: {t['text']}" for t in TURNS) + " Nạn nhân: Vâng. Người gọi 2: Chị làm đi."
    turns = TURNS + [{"speaker": "Nạn nhân", "text": "Vâng."}, {"speaker": "Người gọi 2", "text": "Chị làm đi."}]

    from_text = client.post(URL, headers=auth, json={"text": text}).json()
    from_turns = client.post(URL, headers=auth, json={"turns": turns}).json()

    assert from_text == from_turns
    assert from_text["speakerCount"] == 3


def test_exactly_one_of_text_and_turns_is_required(client, auth):
    for body in [{}, {"text": None}, {"text": "a", "turns": TURNS}]:
        response = client.post(URL, headers=auth, json=body)

        assert response.status_code == 422, str(body)[:40]
        assert response.json()["code"] == "VALIDATION_FAILED"
        assert response.json()["fieldErrors"][0]["field"] == "body"


def test_invalid_turns_are_validation_errors(client, auth):
    bodies = [
        {"turns": []},
        {"turns": [{"speaker": "", "text": "a"}]},
        {"turns": [{"speaker": "A"}]},
        {"turns": [{"speaker": "A", "text": "x" * 20_001}]},
        {"turns": [{"speaker": "A", "text": "x" * 20_000}] * 6},
    ]
    for body in bodies:
        response = client.post(URL, headers=auth, json=body)

        assert response.status_code == 422, str(body)[:60]
        assert response.json()["code"] == "VALIDATION_FAILED"


def test_text_at_the_length_limit_is_accepted(client, auth):
    response = client.post(URL, headers=auth, json={"text": "a" * 100_000})

    assert response.status_code == 200
