"""Rule Engine tests: for every indicator there are positive, negative, context, false-positive and
edge cases, plus the six mandatory cases from the project brief (A to F)."""

import json
import time
import unicodedata
from pathlib import Path

import pytest

from app.rules import RULES, Indicator, RuleEngine, Severity, Turn, normalize, parse_turns

engine = RuleEngine()

OTP = Indicator.OTP_REQUEST
MONEY = Indicator.MONEY_TRANSFER
BANK = Indicator.BANK_IMPERSONATION
URGENCY = Indicator.URGENCY
LOCK = Indicator.ACCOUNT_LOCK_THREAT
SENSITIVE = Indicator.SENSITIVE_INFORMATION
AUTHORITY = Indicator.AUTHORITY_IMPERSONATION
LEGAL = Indicator.LEGAL_THREAT
SECRECY = Indicator.SECRECY_DEMAND
REMOTE = Indicator.REMOTE_ACCESS_REQUEST
BAIT = Indicator.FINANCIAL_BAIT
PAYMENT = Indicator.UNUSUAL_PAYMENT
HARM = Indicator.HARM_THREAT
HANDOFF = Indicator.CALL_HANDOFF
COORDINATED = Indicator.COORDINATED_CALLERS


def codes(text: str) -> set[Indicator]:
    return {match.code for match in engine.analyze(text)}


def found(text: str, indicator: Indicator):
    return next((match for match in engine.analyze(text) if match.code == indicator), None)


def as_whisper_would_write(text: str) -> str:
    """Lower case, no punctuation: the form PhoWhisper transcripts actually have."""
    return " ".join("".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).split())


# =============================================================== mandatory cases from the brief

CASE_A = "Tôi mua hàng của bạn."
CASE_B = "Cho tôi số tài khoản để tôi chuyển tiền."
CASE_C = "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Cho tôi số tài khoản."
CASE_D = "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi."
CASE_E = "Chuyển tiền ngay nếu không tài khoản sẽ bị khóa."
CASE_F = "Tôi đăng nhập ngân hàng và nhập OTP của chính tôi."

EXPECTED = {
    CASE_A: set(),
    CASE_B: set(),
    CASE_C: {BANK, SENSITIVE},
    CASE_D: {BANK, OTP},
    CASE_E: {URGENCY, LOCK, MONEY},
    CASE_F: set(),
}


@pytest.mark.parametrize("text", EXPECTED, ids=list("ABCDEF"))
def test_mandatory_case(text):
    assert codes(text) == EXPECTED[text]


@pytest.mark.parametrize("text", EXPECTED, ids=list("ABCDEF"))
def test_mandatory_case_in_the_form_whisper_produces(text):
    assert codes(as_whisper_would_write(text)) == EXPECTED[text]


def test_case_b_ordinary_payment_is_not_flagged_just_because_it_mentions_a_transfer():
    assert found(CASE_B, MONEY) is None
    assert found(CASE_B, SENSITIVE) is None


def test_case_c_raises_more_signals_than_the_ordinary_cases_but_no_high_severity_one():
    matches = engine.analyze(CASE_C)

    assert len(matches) > len(engine.analyze(CASE_A)) and len(matches) > len(engine.analyze(CASE_B))
    assert all(match.severity != Severity.HIGH for match in matches)


def test_case_d_contains_a_high_severity_otp_request():
    assert found(CASE_D, OTP).severity == Severity.HIGH
    assert "đọc mã otp" in found(CASE_D, OTP).evidence[0]


def test_case_f_own_otp_and_merely_mentioning_the_bank_are_not_signals():
    assert found(CASE_F, OTP) is None
    assert found(CASE_F, BANK) is None


# ================================================================================ OTP_REQUEST


@pytest.mark.parametrize("text", [
    "Đọc mã OTP cho tôi.",
    "Anh cung cấp mã xác thực giúp em.",
    "Chị cho em xin mã OTP vừa gửi về điện thoại.",
    "mã otp vừa về máy anh đọc cho em nhé",
    "anh nhập mã otp vào đường link em vừa gửi",
    "anh đọc mã ô tê pê cho em",
    "đọc cho em mã o t p",
    "Anh báo lại mã xác nhận cho bên em ạ.",
])
def test_otp_request_is_detected(text):
    assert OTP in codes(text)


@pytest.mark.parametrize("text", [
    "Tuyệt đối không cung cấp mã OTP cho bất kỳ ai.",
    "Đừng đọc mã OTP cho ai, kể cả nhân viên ngân hàng.",
    "Ngân hàng không bao giờ yêu cầu anh cung cấp mã OTP qua điện thoại.",
    "Tôi vừa nhận được mã OTP.",
    "Tôi sẽ đọc mã OTP cho anh.",
    "Ngân hàng đã gửi mã OTP cho tôi.",
    "Anh đã đọc mã OTP cho ai chưa?",
    "Ứng dụng yêu cầu nhập mã OTP để đăng nhập.",
    "Mã OTP của tôi hết hạn rồi.",
])
def test_otp_mentions_that_are_not_requests_are_ignored(text):
    assert OTP not in codes(text)


def test_otp_request_made_under_a_condition_is_still_a_request():
    # "nếu ... không" is a threat, not a negation.
    assert OTP in codes("Nếu anh không đọc mã OTP thì giao dịch sẽ bị hủy.")


def test_words_from_two_different_sentences_are_not_joined_into_a_request():
    assert OTP not in codes("Anh đọc báo đi. Mã OTP là gì vậy?")


# ============================================================================= MONEY_TRANSFER


@pytest.mark.parametrize("text", [
    "Anh vui lòng chuyển khoản trước khi nhận hàng.",
    "Chị phải chuyển tiền ngay.",
    "Anh chuyển tiền ngay cho em.",
    "Nếu không chuyển tiền thì hồ sơ sẽ được gửi sang công an.",
    "Yêu cầu anh nộp tiền để xác minh.",
])
def test_demand_to_transfer_money_is_detected(text):
    assert MONEY in codes(text)


@pytest.mark.parametrize("text", [
    "Tôi sẽ chuyển tiền cho anh vào ngày mai.",
    "Để tôi chuyển khoản ngay cho chị.",
    "Tôi cần chuyển tiền gấp cho con tôi.",
    "Đừng chuyển tiền cho người lạ.",
    "Anh đã chuyển tiền chưa?",
    "Tôi không chuyển tiền đâu.",
    "Hôm qua mẹ chuyển tiền học cho con.",
    "Phí chuyển tiền là bao nhiêu?",
])
def test_transfers_that_are_not_demands_on_the_listener_are_ignored(text):
    assert MONEY not in codes(text)


def test_transfer_to_a_so_called_safe_account_is_high_severity():
    match = found("Anh chuyển toàn bộ tiền vào tài khoản an toàn của chúng tôi.", MONEY)

    assert match.severity == Severity.HIGH
    assert "MT-4" in match.rule_ids


def test_plain_transfer_demand_is_medium_severity():
    assert found("Chị phải chuyển tiền ngay.", MONEY).severity == Severity.MEDIUM


# ========================================================================= BANK_IMPERSONATION


@pytest.mark.parametrize("text", [
    "Tôi gọi từ ngân hàng.",
    "Em là nhân viên chăm sóc khách hàng của ngân hàng Vietcombank.",
    "Đây là tổng đài ngân hàng Techcombank.",
    "Em bên ngân hàng ACB ạ.",
    "Chúng tôi gọi cho anh từ bộ phận thẻ của ngân hàng.",
    "Em gọi điện từ BIDV.",
])
def test_claim_to_be_from_a_bank_is_detected(text):
    assert BANK in codes(text)


@pytest.mark.parametrize("text", [
    "Tôi vừa gọi cho ngân hàng để hỏi.",
    "Tôi là khách hàng của ngân hàng.",
    "Anh là nhân viên ngân hàng à?",
    "Tôi không phải là nhân viên ngân hàng.",
    "Tôi ra ngân hàng rút tiền.",
    "Ngân hàng gần nhà tôi đóng cửa rồi.",
    "Tôi đăng nhập ngân hàng.",
])
def test_talking_about_a_bank_is_not_a_claim_to_be_the_bank(text):
    assert BANK not in codes(text)


def test_bank_claim_alone_is_low_severity_because_real_bank_staff_say_it_too():
    assert found("Tôi gọi từ ngân hàng.", BANK).severity == Severity.LOW


# ==================================================================================== URGENCY


@pytest.mark.parametrize("text", [
    "Anh làm theo hướng dẫn ngay.",
    "Chị phải xác nhận trong vòng 5 phút.",
    "Trong vòng hai mươi bốn giờ nếu không xử lý tài khoản sẽ bị khóa.",
    "Nếu không hợp tác anh sẽ bị khởi tố.",
    "Ngay lập tức truy cập đường link này.",
    "Anh cung cấp thông tin gấp.",
])
def test_pressure_on_the_listener_is_detected(text):
    assert URGENCY in codes(text)


@pytest.mark.parametrize("text", [
    "Tôi sẽ gọi lại ngay.",
    "Em chuyển máy ngay ạ.",
    "Giao hàng trong vòng 2 giờ.",
    "Ngay cả tôi cũng không biết.",
    "Tôi sẽ thanh toán ngay.",
    "Nếu không có gì thay đổi thì mai tôi sẽ qua.",
    "Anh đăng nhập ngay khi nhận được thông báo.",
    "Nhà tôi ở ngay cạnh ngân hàng.",
])
def test_everyday_uses_of_urgent_sounding_words_are_ignored(text):
    assert URGENCY not in codes(text)


# ======================================================================== ACCOUNT_LOCK_THREAT


@pytest.mark.parametrize("text", [
    "Tài khoản của anh sẽ bị khóa.",
    "Thẻ của chị đã bị phong toả.",
    "Chúng tôi sẽ khóa tài khoản của anh trong hôm nay.",
    "Sim của anh sẽ bị khoá sau hai giờ.",
    "Tài khoản ngân hàng của anh có thể bị đóng băng.",
])
def test_threat_to_lock_the_listeners_account_is_detected(text):
    assert LOCK in codes(text)


@pytest.mark.parametrize("text", [
    "Tài khoản của tôi bị khóa rồi, nhờ anh hỗ trợ.",
    "Tôi muốn khóa thẻ.",
    "Tôi sẽ khóa thẻ ngay.",
    "Tài khoản của anh sẽ không bị khóa đâu.",
    "Anh nhớ khóa cửa cẩn thận.",
    "Tài khoản của anh đang có vấn đề.",
])
def test_locks_that_are_not_threats_to_the_listener_are_ignored(text):
    assert LOCK not in codes(text)


def test_both_spellings_of_the_tone_mark_are_recognised():
    assert codes("tài khoản sẽ bị khoá") == codes("tài khoản sẽ bị khóa") == {LOCK}


# ====================================================================== SENSITIVE_INFORMATION


@pytest.mark.parametrize(("text", "severity"), [
    ("Anh đọc mật khẩu internet banking cho em.", Severity.HIGH),
    ("Cho em xin số thẻ và mã CVV.", Severity.HIGH),
    ("Anh nhập mật khẩu vào đường link này.", Severity.HIGH),
    ("Chị chụp ảnh căn cước công dân gửi qua Zalo.", Severity.MEDIUM),
    ("Anh cung cấp số CMND giúp em.", Severity.MEDIUM),
    ("Cho tôi số tài khoản.", Severity.LOW),
])
def test_request_for_sensitive_information_is_detected_with_graded_severity(text, severity):
    match = found(text, SENSITIVE)

    assert match is not None
    assert match.severity == severity


@pytest.mark.parametrize("text", [
    "Tôi quên mật khẩu rồi.",
    "Không cung cấp mật khẩu cho bất kỳ ai.",
    "Tôi sẽ gửi ảnh căn cước cho anh sau.",
    "Số tài khoản của tôi là 123456789.",
    "Mật khẩu của tôi rất mạnh.",
    "Cho em xin số tài khoản để em chuyển khoản nhé.",
    "Pin điện thoại của tôi sắp hết.",
])
def test_sensitive_words_without_a_request_to_the_listener_are_ignored(text):
    assert SENSITIVE not in codes(text)


def test_the_most_serious_item_requested_sets_the_severity():
    match = found("Cho tôi số tài khoản. Anh đọc luôn mật khẩu cho em.", SENSITIVE)

    assert match.severity == Severity.HIGH
    assert set(match.rule_ids) == {"SI-1", "SI-3"}


# ==================================================================== whole conversations

SCAM_CALL = (
    "alo em chào anh em là nhân viên chăm sóc khách hàng của ngân hàng vietcombank em gọi để thông báo "
    "tài khoản của anh vừa phát sinh giao dịch bất thường nếu không xác minh tài khoản của anh sẽ bị khóa "
    "trong vòng hai giờ để hủy giao dịch anh đọc mã otp vừa gửi về máy cho em ạ"
)

GENUINE_BANK_CALL = (
    "Dạ em chào anh, em gọi từ ngân hàng ABC để thông báo thẻ tín dụng của anh đã được phát hành. "
    "Anh vui lòng ra chi nhánh gần nhất để nhận thẻ. Ngân hàng không bao giờ yêu cầu anh cung cấp "
    "mã OTP hay mật khẩu qua điện thoại. Cảm ơn anh."
)

SHOPPING_CALL = (
    "Alo shop ơi, em muốn mua cái áo màu xanh. Cho em xin số tài khoản để em chuyển khoản nhé. "
    "Dạ em chuyển rồi ạ, shop kiểm tra giúp em. Cảm ơn shop."
)


def test_scam_call_transcript_raises_the_expected_signals():
    assert codes(SCAM_CALL) == {BANK, OTP, LOCK, URGENCY}


def test_genuine_bank_call_only_shows_the_low_severity_bank_claim():
    matches = engine.analyze(GENUINE_BANK_CALL)

    assert [(m.code, m.severity) for m in matches] == [(BANK, Severity.LOW)]


def test_ordinary_shopping_call_raises_nothing():
    assert codes(SHOPPING_CALL) == set()


# ===================================================== everyday speech versus scam scripts
# Written in the form Whisper produces: lower case, no punctuation, no speaker labels.

EVERYDAY_SPEECH = [
    "alo mẹ ơi con chuyển tiền học phí cho em rồi nhé mẹ kiểm tra giúp con",
    "em chào chị shop em đã gửi hàng rồi chị vui lòng kiểm tra và thanh toán khi nhận hàng",
    "anh ơi tài khoản của em hết tiền rồi anh nạp tiền điện thoại giúp em với",
    "tôi muốn hỏi thủ tục mở thẻ tín dụng cần mang theo căn cước công dân không",
    "chị ơi mật khẩu wifi nhà mình là gì thế",
    "bác sĩ dặn phải uống thuốc ngay sau khi ăn",
    "con nhớ khóa cửa và tắt bếp trước khi đi học",
    "tôi cần gặp nhân viên ngân hàng để hỏi về khoản vay",
    "em đọc báo thấy nói dạo này lừa đảo qua điện thoại nhiều lắm họ hay đòi mã otp",
    "công ty yêu cầu nhân viên nộp báo cáo trong vòng hai ngày",
    "anh gửi giúp em số điện thoại của anh hùng",
    "dạ em bên giao hàng nhanh em đang ở dưới nhà anh xuống nhận hàng giúp em ạ",
    "tôi gọi từ bệnh viện để nhắc lịch tái khám ngày mai",
    "hôm qua tôi ra ngân hàng họ bảo thẻ của tôi sắp hết hạn",
    "anh cho em xin địa chỉ để em giao hàng",
    "ngân hàng nhắn tin nói tuyệt đối không chia sẻ mật khẩu và mã otp cho bất kỳ ai",
    "tôi bị khóa tài khoản facebook rồi không đăng nhập được",
    "em cần chuyển khoản tiền nhà cho chủ trọ trước ngày năm",
    "tổng đài xin nghe em có thể hỗ trợ gì cho anh ạ",
    "anh ơi em hỏi chút nếu không trả nợ đúng hạn thì có bị phạt không",
]

SCAM_SCRIPTS = [
    ("tôi là cán bộ công an anh đang liên quan đến một vụ án rửa tiền yêu cầu anh chuyển toàn bộ tiền vào "
     "tài khoản tạm giữ để xác minh", {MONEY, AUTHORITY, LEGAL}),
    ("em gọi từ trung tâm thẻ ngân hàng thẻ của chị vừa bị trừ năm triệu để hủy giao dịch chị đọc giúp em "
     "mã xác thực vừa gửi về máy", {OTP, BANK}),
    ("chúc mừng anh đã trúng thưởng một xe máy để nhận thưởng anh vui lòng đóng phí hồ sơ ba triệu đồng", {MONEY, BAIT}),
    ("sim của anh sẽ bị khóa sau hai giờ nữa anh bấm vào đường link để cập nhật thông tin ngay",
     {LOCK, URGENCY, REMOTE}),
    ("dạ em bên điện lực nhà mình còn nợ tiền điện nếu không thanh toán ngay sẽ bị cắt điện", {URGENCY, AUTHORITY, LOCK}),
    ("con ơi bố đang cấp cứu chuyển gấp cho bố hai mươi triệu vào số tài khoản này", {MONEY, URGENCY}),
    ("tài khoản của quý khách đã bị khóa do nhập sai mật khẩu vui lòng cung cấp mật khẩu và mã pin để mở khóa",
     {LOCK, SENSITIVE}),
    ("anh chụp ảnh hai mặt căn cước công dân gửi cho em để hoàn tất hồ sơ vay", {SENSITIVE}),
    ("anh cài đặt ứng dụng này rồi đăng nhập ngay để nhận tiền hoàn thuế", {URGENCY, REMOTE}),
    ("chị không được nói với ai về cuộc gọi này chị ra cây atm chuyển tiền ngay cho tôi",
     {MONEY, URGENCY, SECRECY}),
    ("em là nhân viên ngân hàng em cần anh xác nhận số thẻ và ngày hết hạn thẻ", {BANK, SENSITIVE}),
    ("nếu anh không hợp tác chúng tôi sẽ phong tỏa toàn bộ tài khoản của anh", {LOCK, URGENCY}),
]


@pytest.mark.parametrize("text", EVERYDAY_SPEECH)
def test_everyday_speech_raises_no_indicator(text):
    assert codes(text) == set()


@pytest.mark.parametrize(("text", "expected"), SCAM_SCRIPTS)
def test_scam_script_raises_its_indicators(text, expected):
    assert codes(text) == expected


def test_question_about_a_penalty_is_not_an_ultimatum_but_the_statement_is():
    assert URGENCY not in codes("nếu không trả nợ đúng hạn thì có bị phạt không")
    assert URGENCY in codes("nếu không trả nợ đúng hạn thì anh sẽ bị phạt")
    # "không" starting the next idea is not a question mark.
    assert LOCK in codes("tài khoản của anh sẽ bị khóa không thể giao dịch được nữa")


def test_urgent_transfer_with_an_amount_is_a_demand_even_without_the_word_tien():
    match = found("chuyển gấp cho bố hai mươi triệu vào số tài khoản này", MONEY)

    assert match.severity == Severity.HIGH
    assert {"MT-4", "MT-6"} <= set(match.rule_ids)


# ================================================================================ edge cases


@pytest.mark.parametrize("text", ["", "   ", "\n\t", "...", "?!,;", "123 456", "ok"])
def test_empty_or_meaningless_text_gives_no_indicators(text):
    assert engine.analyze(text) == []


def test_letter_case_spacing_and_line_breaks_do_not_matter():
    assert codes("ANH   ĐỌC\nMÃ  OTP\tCHO TÔI") == {OTP}


def test_decomposed_unicode_input_is_handled():
    decomposed = unicodedata.normalize("NFD", "Anh đọc mã OTP cho tôi")

    assert decomposed != "Anh đọc mã OTP cho tôi"
    assert codes(decomposed) == {OTP}


def test_keywords_inside_longer_words_do_not_match():
    # "otp" inside another token, "pin" as a battery, "thẻ" inside nothing lockable.
    assert codes("mã hotpot của nhà hàng, pin máy còn đầy") == set()


def test_indicators_are_reported_once_each_in_a_fixed_order_with_capped_evidence():
    requests = ("Anh đọc mã OTP cho em. Anh cung cấp mã xác thực giúp em. Anh báo mã xác nhận cho em. "
                "Cho em xin mã kích hoạt. Anh gửi mã giao dịch cho em.")
    text = f"Chuyển tiền ngay. {requests} Tôi gọi từ ngân hàng."

    matches = engine.analyze(text)

    assert [m.code for m in matches] == [OTP, MONEY, BANK, URGENCY]
    assert found(text, OTP).evidence == ["đọc mã otp", "cung cấp mã xác thực", "báo mã xác nhận"]


def test_identical_evidence_is_listed_once():
    match = found("Anh đọc mã OTP cho em. " * 5, OTP)

    assert match.evidence == ["đọc mã otp"]


def test_evidence_quotes_the_matched_words_from_the_normalised_text():
    match = found("Thưa anh, ANH ĐỌC MÃ OTP cho em!", OTP)

    assert match.evidence == ["đọc mã otp"]
    assert match.rule_ids == ["OTP-1"]


def test_long_text_is_analysed_quickly_and_the_signal_at_the_end_is_still_found():
    filler = "hôm nay trời đẹp tôi đi chợ mua rau và cá về nấu cơm cho cả nhà ăn tối. " * 1500
    text = filler + "Anh đọc mã OTP cho em."
    assert len(text) > 100_000

    started = time.perf_counter()
    result = codes(text)

    assert result == {OTP}
    assert time.perf_counter() - started < 2.0


def test_normalize_produces_single_spaced_lower_case_text_with_sentence_breaks():
    # Commas do not break a sentence; a question mark leaves the distinct "||" break.
    assert normalize("  Xin CHÀO,  anh!\nTài khoản... bị KHOÁ? ") == "xin chào anh | tài khoản | bị khóa ||"


README_INDICATORS = {
    "OTP_REQUEST", "MONEY_TRANSFER", "BANK_IMPERSONATION", "URGENCY", "ACCOUNT_LOCK_THREAT", "SENSITIVE_INFORMATION",
}
EXTENSION_INDICATORS = {
    "AUTHORITY_IMPERSONATION", "LEGAL_THREAT", "HARM_THREAT", "SECRECY_DEMAND", "REMOTE_ACCESS_REQUEST", "FINANCIAL_BAIT",
    "UNUSUAL_PAYMENT", "CALL_HANDOFF", "COORDINATED_CALLERS",
}


def test_every_indicator_from_the_readme_has_at_least_one_rule_and_rule_ids_are_unique():
    # COORDINATED_CALLERS has no pattern: it is derived from who said what in a conversation.
    assert {rule.indicator for rule in RULES} == set(Indicator) - {Indicator.COORDINATED_CALLERS}
    assert len({rule.rule_id for rule in RULES}) == len(RULES)
    assert {i.value for i in Indicator} == README_INDICATORS | EXTENSION_INDICATORS
    # The six README indicators come first, in the README's order.
    assert [i.value for i in Indicator][:6] == [
        "OTP_REQUEST", "MONEY_TRANSFER", "BANK_IMPERSONATION", "URGENCY", "ACCOUNT_LOCK_THREAT",
        "SENSITIVE_INFORMATION",
    ]


# ============================================================ indicators beyond the README's six


@pytest.mark.parametrize(("text", "indicator"), [
    ("Tôi là đại úy Nguyễn Văn Nam, công an thành phố Hà Nội.", AUTHORITY),
    ("Tôi gọi từ viện kiểm sát nhân dân tối cao.", AUTHORITY),
    ("Anh đang liên quan đến một đường dây rửa tiền.", LEGAL),
    ("Chúng tôi đã có lệnh bắt tạm giam đối với chị.", LEGAL),
    ("Chị tuyệt đối không được nói với người nhà.", SECRECY),
    ("Việc này phải giữ bí mật điều tra.", SECRECY),
    ("Anh tải ứng dụng dịch vụ công theo hướng dẫn.", REMOTE),
    ("Tôi sẽ kết nối với máy tính của anh từ xa.", REMOTE),
    ("Chúc mừng chị đã trúng thưởng một chiếc xe máy.", BAIT),
    ("Bên em cam kết lợi nhuận mỗi ngày.", BAIT),
    ("Anh ra cửa hàng mua thẻ quà tặng rồi đọc mã cho tôi.", PAYMENT),
    ("Tôi chuyển máy cho đồng chí điều tra viên.", HANDOFF),
])
def test_extension_indicator_is_detected(text, indicator):
    assert indicator in codes(text)


@pytest.mark.parametrize("text", [
    "Anh là công an à?",
    "Tôi không phải là cán bộ công an.",
    "Hôm qua tôi ra công an phường làm căn cước.",
    "Em đọc báo thấy họ dọa có lệnh bắt, mình có bị bắt giữ thật không?",
    "Ngân hàng dặn không tiết lộ mã OTP cho bất kỳ ai.",
    "Đừng cài ứng dụng lạ nhé con.",
    "Tôi đã tải ứng dụng ngân hàng từ lâu rồi.",
    "Em không trúng thưởng gì cả.",
    "Tôi không mua thẻ cào đâu.",
    "Chị chờ chút em chuyển máy cho mẹ.",
    "Đừng lo, mai con về.",
])
def test_everyday_mentions_do_not_raise_extension_indicators(text):
    assert codes(text) & {AUTHORITY, LEGAL, SECRECY, REMOTE, BAIT, PAYMENT, HANDOFF} == set()


def test_reassurance_before_a_request_does_not_cancel_it():
    # "đừng lo" is not a negation of what follows.
    assert REMOTE in codes("Nhưng đừng lo, chúng tôi có thể sửa nó cho bạn từ xa.")
    assert OTP not in codes("Đừng đọc mã OTP cho ai.")


def test_a_question_from_the_listener_is_not_a_demand_or_a_threat():
    assert MONEY not in codes("Chuyển tiền vào tài khoản nào vậy anh?")
    assert LEGAL not in codes("Tôi có bị bắt giữ không?")
    assert MONEY in codes("Chuyển tiền vào tài khoản này.")


def test_a_request_listing_several_items_separated_by_commas_is_found():
    assert found("Anh cung cấp họ tên, địa chỉ, số thẻ và mã CVV.", SENSITIVE).severity == Severity.HIGH


def test_advance_fee_and_prize_together_are_both_medium():
    matches = {m.code: m.severity for m in engine.analyze(
        "Chị đã trúng thưởng. Để nhận giải chị nộp phí hồ sơ hai triệu.")}

    assert matches[BAIT] == Severity.MEDIUM and matches[MONEY] == Severity.MEDIUM


@pytest.mark.parametrize(("text", "indicator"), [
    ("Hôm nay mày không trả thì tao ghép ảnh mày gửi cho cả công ty.", HARM),
    ("Con mày đang ở trong tay tao.", HARM),
    ("Nếu chị không thanh toán trong chiều nay bên em sẽ cắt nước.", LOCK),
    ("Sim của anh sẽ bị khóa hai chiều.", LOCK),
    ("Em là nhân viên hỗ trợ của ví điện tử.", BANK),
    ("Cháu bị xuất huyết não, cần mổ ngay.", URGENCY),
    ("Anh làm ngay đi.", URGENCY),
    ("Chị không chuyển thì hồ sơ bị hủy.", URGENCY),
    ("Chị nạp thêm mười triệu để mở khóa tài khoản.", MONEY),
    ("Chị bấm vào đường link rồi điền số thẻ và mã OTP.", SENSITIVE),
    ("Trung tá Bình nghe.", AUTHORITY),
    ("Đừng báo công an.", SECRECY),
])
def test_vietnamese_scam_patterns_are_detected(text, indicator):
    assert indicator in codes(text)


@pytest.mark.parametrize("text", [
    "Ngày mai từ tám giờ đến mười một giờ khu phố mình tạm ngừng cấp điện để bảo trì.",
    "Xin đừng làm hại nó.",
    "Nhà tôi mất điện từ sáng.",
    "Em có bị ghi nợ xấu không?",
    "Bác sĩ nói bố phải mổ không?",
    "Con không làm bài tập thì mẹ không cho đi chơi đâu.",
    "Tôi nạp tiền điện thoại để gọi cho mẹ.",
])
def test_everyday_sentences_do_not_match_the_vietnamese_scam_patterns(text):
    assert codes(text) & {HARM, LOCK, LEGAL, MONEY, SECRECY} == set()


def test_a_question_tag_before_a_statement_does_not_negate_the_statement():
    assert URGENCY in codes("Mày chuyển luôn bây giờ được không, tao đang rất gấp.")


def test_the_one_asking_for_an_account_number_after_a_money_request_is_the_payer():
    turns = [
        Turn("Bố", "Hai đứa chuyển vào tài khoản của mẹ."),
        Turn("Con trai", "Dạ, mẹ nhắn lại số tài khoản giúp con."),
    ]
    analysis = engine.analyze_conversation(turns)

    assert {s.speaker: s.indicators for s in analysis.speakers}["Con trai"] == []
    assert SENSITIVE not in {m.code for m in analysis.indicators}
    # Without a money request from someone else, the same question is still a (weak) signal.
    assert SENSITIVE in {m.code for m in engine.analyze_conversation(turns[1:]).indicators}


# ================================================ fewer false alarms, found on public dialogues


def test_infection_alert_followed_by_device_instructions_is_high_severity():
    alert = "Chúng tôi nhận được cảnh báo rằng máy tính của bạn đã bị nhiễm vi-rút."
    instruction = "Tôi cần bạn mở Event Viewer để chúng tôi xem nhật ký."

    assert found(alert, REMOTE).severity == Severity.MEDIUM
    combined = found(f"{alert} {instruction}", REMOTE)
    assert combined.severity == Severity.HIGH and "RA-10" in combined.rule_ids


def test_a_customer_describing_their_own_infected_computer_is_only_a_weak_signal():
    assert found("Tôi nghĩ là máy bị nhiễm vi-rút hay gì đó.", REMOTE).severity == Severity.LOW


def test_gift_card_given_as_a_promotion_is_not_an_unusual_payment():
    assert PAYMENT not in codes("Bạn sẽ nhận được thẻ quà tặng trị giá 100 đô la khi hoàn thành.")
    assert PAYMENT in codes("Anh ra cửa hàng mua thẻ quà tặng rồi đọc mã cho tôi.")
    assert PAYMENT in codes("Chị chuyển tiền để em đổi sang USDT.")


def test_insurance_premium_is_not_an_advance_fee():
    assert MONEY not in codes("Chị có thể thanh toán phí bảo hiểm hằng tháng hoặc hằng năm.")
    assert MONEY in codes("Chị thanh toán phí hồ sơ ba triệu để nhận giải.")


def test_confidentiality_assurance_is_not_a_secrecy_demand():
    assert SECRECY not in codes("Thông tin của anh sẽ được giữ bí mật tuyệt đối.")
    assert SECRECY in codes("Chị phải giữ bí mật, không nói với người nhà.")


def test_speaker_reporting_a_threat_made_to_themselves_is_not_threatening_the_listener():
    assert LEGAL not in codes("Họ nói nếu không trả thì tôi sẽ bị bắt.")
    assert LEGAL in codes("Nếu không trả thì anh sẽ bị bắt.")


def test_of_yours_after_addressing_the_listener_is_the_listeners_item():
    # "của mình" refers to the listener when the sentence addresses them.
    assert SENSITIVE in codes("Cô vui lòng xác nhận số thẻ tín dụng của mình.")
    assert SENSITIVE not in codes("Tôi vừa xác nhận số thẻ của mình trên ứng dụng.")


def test_unsolicited_refund_offer_is_bait_but_a_shop_returning_a_payment_is_not():
    assert BAIT in codes("Chúng tôi muốn hoàn lại tiền cho bạn vì hệ thống tính phí hai lần.")
    assert BAIT in codes("Bạn đủ điều kiện được hoàn lại 427 đô la.")
    assert BAIT not in codes("Cái váy hết size nên tiền chị đã chuyển em hoàn lại nhé.")
    assert BAIT not in codes("Thuê bao của anh đủ điều kiện đăng ký gói cước chín mươi nghìn một tháng.")


def test_a_national_id_number_is_medium_not_high():
    assert found("Anh cung cấp số an sinh xã hội giúp tôi.", SENSITIVE).severity == Severity.MEDIUM


def test_sending_a_link_alone_is_a_weak_signal():
    assert found("Em gửi link xác nhận qua email cho anh nhé.", REMOTE).severity == Severity.LOW
    assert found("Chị bấm vào đường link em vừa nhắn.", REMOTE).severity == Severity.MEDIUM


# ============================================================== conversations with speakers

THREE_PARTY_SCAM = [
    Turn("Người gọi 1", "Dạ em chào chị, em là nhân viên ngân hàng Vietcombank. Thẻ của chị phát sinh giao dịch lạ."),
    Turn("Nạn nhân", "Tôi có giao dịch gì đâu?"),
    Turn("Người gọi 1", "Việc này liên quan đến pháp luật, em chuyển máy cho đồng chí điều tra viên ạ."),
    Turn("Người gọi 2", "Tôi là đại úy Hùng, cơ quan điều tra. Chị đang liên quan đến một đường dây rửa tiền."),
    Turn("Nạn nhân", "Tôi không biết gì cả. Tôi phải chuyển tiền vào tài khoản nào?"),
    Turn("Người gọi 2", "Chị chuyển toàn bộ tiền vào tài khoản tạm giữ. Chị không được nói với ai."),
]


def test_three_party_scam_is_attributed_to_the_right_speakers():
    analysis = engine.analyze_conversation(THREE_PARTY_SCAM)
    by_speaker = {s.speaker: set(s.indicators) for s in analysis.speakers}

    assert [s.speaker for s in analysis.speakers] == ["Người gọi 1", "Nạn nhân", "Người gọi 2"]
    assert [s.turns for s in analysis.speakers] == [2, 2, 2]
    assert by_speaker["Người gọi 1"] == {BANK, HANDOFF}
    assert by_speaker["Người gọi 2"] == {MONEY, AUTHORITY, LEGAL, SECRECY}
    assert by_speaker["Nạn nhân"] == set()


def test_two_callers_pressing_the_same_person_raise_coordinated_callers():
    match = next(m for m in engine.analyze_conversation(THREE_PARTY_SCAM).indicators if m.code == COORDINATED)

    assert match.severity == Severity.MEDIUM
    assert match.rule_ids == ["CC-1"]
    assert match.evidence == ["speakers: Người gọi 1, Người gọi 2"]


def test_a_single_caller_does_not_raise_coordinated_callers():
    turns = [turn for turn in THREE_PARTY_SCAM if turn.speaker != "Người gọi 1"]

    assert COORDINATED not in {m.code for m in engine.analyze_conversation(turns).indicators}


def test_genuine_three_party_call_with_a_handoff_is_not_coordinated():
    turns = [
        Turn("Lễ tân", "Phòng khám xin nghe ạ."),
        Turn("Khách", "Tôi muốn hỏi kết quả xét nghiệm."),
        Turn("Lễ tân", "Dạ em chuyển máy cho bác sĩ ạ."),
        Turn("Bác sĩ", "Chào chị, kết quả của chị bình thường, tuần sau chị tái khám nhé."),
    ]
    analysis = engine.analyze_conversation(turns)

    assert {m.code for m in analysis.indicators} == {HANDOFF}
    assert all(m.severity == Severity.LOW for m in analysis.indicators)


def test_words_of_different_speakers_are_not_joined_into_one_request():
    turns = [Turn("A", "Anh đọc"), Turn("B", "mã OTP là gì vậy")]

    assert engine.analyze_conversation(turns).indicators == []


def test_the_victims_question_is_not_counted_against_the_caller():
    turns = [
        Turn("A", "Chào anh, em gọi để xác nhận lịch giao hàng ngày mai."),
        Turn("B", "Có cần tôi đọc mã OTP cho em không?"),
        Turn("A", "Dạ không cần đâu ạ."),
    ]
    analysis = engine.analyze_conversation(turns)

    assert {s.speaker: s.indicators for s in analysis.speakers}["A"] == []


def test_labelled_text_is_split_into_turns_including_a_speaker_who_talks_once():
    text = ("A: Em chào anh. B: Chào em. A: Em chuyển máy cho quản lý ạ. C: Tôi là quản lý đây. "
            "B: Vâng. A: Dạ anh nghe giúp em.")
    turns = parse_turns(text)

    assert [t.speaker for t in turns] == ["A", "B", "A", "C", "B", "A"]
    assert turns[3].text == "Tôi là quản lý đây."


@pytest.mark.parametrize("text", [
    "Lưu ý: tài khoản của anh sẽ bị khóa.",
    "anh đọc mã otp cho em",
    "Giờ hẹn: 10:30. Địa chỉ: 12 Lê Lợi.",
    "",
])
def test_text_without_repeated_speaker_labels_is_not_split(text):
    assert parse_turns(text) is None


def test_analyze_treats_labelled_text_as_a_conversation():
    text = " ".join(f"{turn.speaker}: {turn.text}" for turn in THREE_PARTY_SCAM)
    analysis = engine.analyze_text(text)

    assert len(analysis.speakers) == 3
    assert COORDINATED in {m.code for m in analysis.indicators}
    assert engine.analyze_text("anh đọc mã otp cho em").speakers == []


# ============================================== regression over the labelled conversation set


MIN_SCAMS_FLAGGED = 97  # of 98, measured with ruleset 2026.10.4
MAX_NORMAL_FLAGGED = 1  # of 52


def _conversations():
    path = Path(__file__).parent / "data" / "conversations_vi.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _suspicious(matches) -> bool:
    """Provisional reading until the Risk Engine exists: any HIGH, or two indicators with one above LOW."""
    high = any(m.severity == Severity.HIGH for m in matches)
    strong = any(m.severity != Severity.LOW for m in matches)
    return high or (strong and len(matches) >= 2)


def test_conversation_set_has_the_documented_shape():
    rows = _conversations()

    assert len(rows) == 150
    assert sum(r["label"] for r in rows) == 98
    assert sum(len({s for s, _ in r["turns"]}) >= 3 for r in rows) == 68
    assert sum(r["split"] == "holdout" for r in rows) == 50


def test_rule_engine_keeps_its_measured_level_on_the_conversation_set():
    # Floors set from the measured result (see the Rule Engine report); a drop means a regression.
    rows = _conversations()
    flagged = {r["id"]: _suspicious(engine.analyze_conversation([Turn(s, t) for s, t in r["turns"]]).indicators)
               for r in rows}
    scams = [r["id"] for r in rows if r["label"] == 1]
    normal = [r["id"] for r in rows if r["label"] == 0]

    assert sum(flagged[i] for i in scams) >= MIN_SCAMS_FLAGGED
    assert sum(flagged[i] for i in normal) <= MAX_NORMAL_FLAGGED


# ============================================== patterns taken from real call recordings (ASR text)


def test_common_speech_recognition_mistakes_are_normalised():
    assert "trúng thưởng" in normalize("chương trình bốc thăm trụ thưởng")
    assert normalize("gửi một đường linh và một mã cốt") == "gửi một đường link và một mã code"


@pytest.mark.parametrize(("text", "indicator"), [
    ("công ty bảo hiểm xin chào quý khách có một bảo hiểm chưa nhận đây là lần thông báo cuối cùng", BAIT),
    ("vui lòng bấm phím sáu để được nhân viên hỗ trợ", HANDOFF),
    ("số máy này của anh đang nằm trong chương trình bốc thăm trụ thưởng của bên em", BAIT),
    ("mình chỉ vui lòng thanh toán cái thuế nhập khẩu là năm phẩy năm phần trăm", MONEY),
    ("cổng game bên em có tài xỉu bắn cá game bài và xổ số anh ạ", BAIT),
    ("chúng tôi sẽ khóa toàn bộ lại nhá", LOCK),
    ("tôi gọi cho anh bên công an điều tra thành phố hà nội", AUTHORITY),
    ("khi bắt đầu lưu âm không được có người thứ ba xuất hiện", SECRECY),
    ("số điện thoại đó lập facebook đăng những thông tin chống phá nhà nước", LEGAL),
])
def test_patterns_from_real_scam_recordings_are_detected(text, indicator):
    assert indicator in codes(text)


@pytest.mark.parametrize("text", [
    "tổng đài xin nghe vui lòng bấm phím một để nghe hướng dẫn",
    "hôm qua tôi lên công an phường làm lại căn cước",
    "em có bưu phẩm gửi cho anh chiều nay em giao nhé",
    "con chơi game xong thì đi ngủ sớm nhé",
])
def test_everyday_sentences_near_those_patterns_stay_clean(text):
    assert codes(text) == set()
