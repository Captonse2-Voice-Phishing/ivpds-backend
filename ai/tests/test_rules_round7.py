"""Tests for the rules added in ruleset 2026.10.6.

Each new rule has sentences it must catch and ordinary sentences with the same words that it must leave alone.
The gaps these rules close were found with the short-clip test set and the large accuracy test: short scam
requests that no rule recognised, so the Risk Engine's short-clip guard held them at MEDIUM.
"""

import pytest

from app.risk import RiskLevel, assess
from app.rules import RULESET_VERSION, Indicator, RuleEngine, Severity

ENGINE = RuleEngine()


def found(text: str) -> dict[str, Severity]:
    return {match.code.value: match.severity for match in ENGINE.analyze(text)}


def rule_ids(text: str) -> set[str]:
    return {rule_id for match in ENGINE.analyze(text) for rule_id in match.rule_ids}


def test_the_ruleset_version_was_bumped():
    assert RULESET_VERSION == "2026.10.6"


# --------------------------------------------------------------------------------- codes without the word OTP


@pytest.mark.parametrize("text", [
    "Hệ thống vừa gửi cho anh một mã gồm sáu chữ số, anh đọc lại cho em để em xác nhận chủ tài khoản.",
    "Có một mã sáu số gửi về máy chị, chị đọc cho em nhé.",
    "Bên em vừa gửi về điện thoại bác một mã, bác đọc cho cháu.",
    "mã vừa gửi về máy anh đọc lại giúp em",
])
def test_reading_back_a_code_that_was_just_sent_is_an_otp_request(text):
    assert found(text).get("OTP_REQUEST") == Severity.HIGH


@pytest.mark.parametrize("text", [
    "Anh đọc mã đơn hàng cho em để em tìm kiện hàng ạ.",
    "Mã giảm giá em gửi cho chị trong tin nhắn rồi, chị nhập khi thanh toán nhé.",
    "Em vừa gửi hợp đồng qua thư, anh đọc giúp em xem có sai gì không.",
    "Mã số thuế của công ty anh đọc cho em ghi hóa đơn.",
    "Ngân hàng dặn không đọc mã gửi về máy cho bất kỳ ai.",
    "Hôm qua có người bảo tôi đọc mã vừa gửi về máy cho họ, tôi cúp máy luôn.",
])
def test_other_codes_and_reported_or_refused_requests_are_not_otp_requests(text):
    assert "OTP_REQUEST" not in found(text)


def test_urging_someone_to_read_a_code_is_a_weaker_otp_signal():
    assert found("Chị đọc mã luôn nhé, sắp hết hạn rồi.").get("OTP_REQUEST") == Severity.MEDIUM
    assert "OTP_REQUEST" not in found("Em đọc mã đề rồi mới làm bài nhé.")


# --------------------------------------------------------------------------------------- cards, face, balance


@pytest.mark.parametrize("text", [
    "Chị chụp mặt trước mặt sau thẻ ngân hàng gửi vào số này để bên em hoàn tiền cho chị.",
    "Anh chụp ảnh thẻ ATM gửi qua Zalo cho em.",
    "Chị đừng tắt máy, chị đọc từng số trên thẻ ATM cho em, em nhập vào hệ thống để gỡ phong tỏa.",
])
def test_photographing_or_reading_out_a_bank_card_is_a_strong_signal(text):
    assert found(text).get("SENSITIVE_INFORMATION") == Severity.HIGH


@pytest.mark.parametrize("text", [
    "Tôi chụp ảnh thẻ ngân hàng của tôi để lưu lại cho khỏi quên.",
    "Đừng chụp thẻ ngân hàng gửi cho ai nhé mẹ.",
    "Thẻ ngân hàng của chị đã về chi nhánh, chị mang căn cước ra nhận.",
    "Em đọc số trên thẻ thư viện giúp cô để cô ghi sổ mượn sách.",
])
def test_ordinary_mentions_of_cards_are_not_flagged_by_the_new_card_rules(text):
    assert not rule_ids(text) & {"SI-11", "SI-12"}


def test_being_told_to_film_your_face_is_flagged_but_filming_it_yourself_is_not():
    assert "SI-13" in rule_ids("Anh quay video khuôn mặt nghiêng trái nghiêng phải gửi cho em để mở khóa tài khoản.")
    assert "SI-13" not in rule_ids("Tôi quay video khuôn mặt em bé gửi cho bà xem.")
    assert "SI-13" not in rule_ids("Đừng quay video khuôn mặt gửi cho người lạ.")


@pytest.mark.parametrize("text", [
    "Bác cho cháu biết trong sổ tiết kiệm của bác còn bao nhiêu tiền và gửi ở ngân hàng nào để cháu đối chiếu hồ sơ.",
    "Anh kê khai toàn bộ số dư các tài khoản để cơ quan điều tra xác minh.",
    "Chị cho em biết tài khoản chị có bao nhiêu tiền để em khoanh lại.",
])
def test_probing_how_much_money_the_listener_has_is_a_strong_signal(text):
    assert "SI-14" in rule_ids(text)
    assert found(text)["SENSITIVE_INFORMATION"] == Severity.HIGH


@pytest.mark.parametrize("text", [
    "Em ơi cho chị biết tài khoản của tôi còn bao nhiêu tiền với.",
    "Mẹ ơi tháng này nhà mình còn bao nhiêu tiền chợ?",
    "Ứng dụng báo số dư của tôi không đúng, em kiểm tra giúp.",
    "Ngân hàng không bao giờ yêu cầu khách kê khai số dư qua điện thoại.",
])
def test_asking_about_your_own_money_or_talking_about_money_at_home_is_not_probing(text):
    assert "SI-14" not in rule_ids(text)


# ----------------------------------------------------------------------------------- links, apps, bank login


@pytest.mark.parametrize("text", [
    "Anh bấm đường link em gửi rồi đăng nhập ngân hàng để hủy phí.",
    "Chị cài ứng dụng theo đường link em gửi rồi nhập tài khoản ngân hàng.",
    "Bác bấm vào đường link cháu nhắn rồi đăng nhập ngân hàng để nhận tiền hoàn.",
])
def test_opening_a_sent_link_or_app_and_logging_into_the_bank_is_a_strong_signal(text):
    assert "SI-15" in rule_ids(text)


@pytest.mark.parametrize("text", [
    "Tôi đăng nhập ngân hàng và nhập OTP của chính tôi.",
    "Tôi cài ứng dụng ngân hàng rồi đăng nhập ngân hàng bằng vân tay.",
    "Đừng bấm vào đường link lạ rồi đăng nhập ngân hàng nhé bố.",
])
def test_logging_into_your_own_bank_or_warning_against_links_is_not_flagged(text):
    assert "SI-15" not in rule_ids(text)


def test_asking_to_open_the_banking_app_so_the_caller_can_look_is_flagged():
    assert "RA-12" in rule_ids("Anh mở ứng dụng ngân hàng lên để em kiểm tra máy có bị theo dõi không.")
    assert "RA-12" not in rule_ids("Chị mở ứng dụng ngân hàng lên để xem tiền về chưa nhé.")


# ------------------------------------------------------------------------------------------------ vocabulary


def test_the_caller_calling_themselves_chau_is_recognised_in_requests():
    # Before, "cho cháu" was missing, so the same request from a "cháu" speaker matched nothing.
    assert found("Bác đọc mã OTP cho cháu.").get("OTP_REQUEST") == Severity.HIGH
    assert found("Cô cho cháu xin số thẻ và mã bảo mật.").get("SENSITIVE_INFORMATION") == Severity.HIGH


@pytest.mark.parametrize(("text", "code"), [
    ("Chị chuyển mười hai triệu vào tài khoản của cán bộ thụ lý.", "MONEY_TRANSFER"),
    ("Bác chuyển toàn bộ tiền sang tài khoản ký quỹ tạm thời.", "MONEY_TRANSFER"),
    ("Cô chuyển tám triệu tiền sắm lễ vào tài khoản của thầy.", "MONEY_TRANSFER"),
])
def test_paying_into_a_named_persons_or_made_up_account_is_a_strong_signal(text, code):
    assert found(text).get(code) == Severity.HIGH


@pytest.mark.parametrize(("text", "code"), [
    ("Việc này kín, chị yên tâm.", "SECRECY_DEMAND"),
    ("Việc này tôi giúp riêng, đừng nói ra.", "SECRECY_DEMAND"),
    ("Không trả thì chúng tôi cho người đến tận nhà.", "HARM_THREAT"),
    ("Em gửi hình chị cho hết danh bạ.", "HARM_THREAT"),
    ("Chiều tôi chuyển lại gấp đôi.", "FINANCIAL_BAIT"),
    ("Chị vào nhóm rồi nạp tiền theo hướng dẫn để bé lên hạng.", "FINANCIAL_BAIT"),
    ("Anh chuyển ngay kẻo hết suất.", "URGENCY"),
])
def test_new_phrases_of_existing_indicators(text, code):
    assert code in found(text)


@pytest.mark.parametrize("text", [
    "Thông tin của anh được giữ kín theo quy định.",
    "Shipper giao hàng đến tận nhà cho chị nhé.",
    "Hợp đồng của mình có phí bảo hiểm mỗi năm, anh xem lại giúp em.",
    "Lớp mình chốt danh sách đi dã ngoại vào thứ sáu.",
])
def test_the_new_phrases_do_not_fire_on_everyday_sentences(text):
    codes = found(text)
    assert "SECRECY_DEMAND" not in codes and "MONEY_TRANSFER" not in codes


# ------------------------------------------------------------------------- effect on the short-clip guard


@pytest.mark.parametrize("text", [
    "Hệ thống vừa gửi cho anh một mã gồm sáu chữ số, anh đọc lại cho em để em xác nhận chủ tài khoản.",
    "Chị chụp mặt trước mặt sau thẻ ngân hàng gửi vào số này để bên em hoàn tiền cho chị.",
    "Chị đừng tắt máy, chị đọc từng số trên thẻ ATM cho em, em nhập vào hệ thống để gỡ phong tỏa.",
])
def test_a_short_scam_the_rules_now_recognise_is_no_longer_held_at_medium(text):
    # With the model sure it is a scam, the guard used to cap these short clips at MEDIUM for lack of rule support.
    result = assess(ENGINE.analyze(text), 1.0, words=len(text.split()))
    assert result.risk_level == RiskLevel.HIGH and not result.short_text_capped


def test_the_savings_question_is_caught_even_when_the_model_sees_nothing():
    text = "Bác cho cháu biết trong sổ tiết kiệm của bác còn bao nhiêu tiền và gửi ở ngân hàng nào để cháu đối chiếu hồ sơ."
    assert assess(ENGINE.analyze(text), 0.07, words=len(text.split())).risk_level != RiskLevel.LOW


@pytest.mark.parametrize("text", [
    "Dạ em chào anh, em gọi từ khách sạn Hoa Mai ạ. Anh đặt phòng ngày hai mươi tháng này, anh vui lòng chuyển khoản "
    "đặt cọc năm trăm nghìn để bên em giữ phòng cho anh nhé.",
    "Chào chị, em bên cửa hàng điện máy. Cái tủ lạnh chị hỏi hôm qua còn đúng một cái, chị đặt cọc trước ba trăm "
    "nghìn thì em giữ hàng cho chị đến cuối tuần.",
])
def test_ordinary_deposit_requests_are_still_held_at_medium_when_the_model_is_wrong(text):
    result = assess(ENGINE.analyze(text), 1.0, words=len(text.split()))
    assert result.risk_level == RiskLevel.MEDIUM


def test_indicator_enum_is_unchanged():
    assert len(list(Indicator)) == 15
