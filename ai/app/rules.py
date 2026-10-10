"""Rule Engine: tìm các dấu hiệu lừa đảo rõ ràng trong transcript tiếng Việt.

Mỗi luật không chỉ tìm từ khóa mà xét cả ngữ cảnh quanh nó: ai là người làm hành động, câu có bị
phủ định không, đang kể lại việc đã xảy ra hay đang yêu cầu. Nhờ vậy "Anh đọc mã OTP tôi vừa gửi"
được coi là dấu hiệu, còn "Tôi nhập OTP của chính tôi" hay "Tuyệt đối không cung cấp OTP cho ai" thì không.

Transcript từ Whisper thường là chữ thường, gần như không có dấu câu và không phân biệt người nói,
nên các luật làm việc trên văn bản đã chuẩn hóa và chỉ ghép các từ nằm gần nhau (cách nhau vài từ).

Giới hạn cần biết: đại từ tiếng Việt như "anh", "chị", "em" vừa có thể chỉ người nói vừa có thể chỉ
người nghe, nên chỉ các đại từ chắc chắn là ngôi thứ nhất ("tôi", "mình", "tớ"...) mới được dùng để
loại trừ. Rule Engine chỉ báo dấu hiệu; việc kết luận mức rủi ro thuộc về Risk Engine.
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

RULESET_VERSION = "2026.10.5"


class Indicator(StrEnum):
    """Các dấu hiệu lừa đảo.

    Sáu dấu hiệu đầu là danh sách trong README. Các dấu hiệu sau được bổ sung khi đo trên hội thoại
    lừa đảo thực tế: sáu dấu hiệu gốc xoay quanh ngân hàng và OTP nên bỏ sót gần hết các kiểu giả danh
    công an, cài ứng dụng điều khiển từ xa, trúng thưởng, đầu tư, tuyển cộng tác viên.
    """

    OTP_REQUEST = "OTP_REQUEST"
    MONEY_TRANSFER = "MONEY_TRANSFER"
    BANK_IMPERSONATION = "BANK_IMPERSONATION"
    URGENCY = "URGENCY"
    ACCOUNT_LOCK_THREAT = "ACCOUNT_LOCK_THREAT"
    SENSITIVE_INFORMATION = "SENSITIVE_INFORMATION"

    # --- Bổ sung ngoài danh sách của README ---
    # Tự xưng là công an, viện kiểm sát, tòa án, thuế, bảo hiểm xã hội...
    AUTHORITY_IMPERSONATION = "AUTHORITY_IMPERSONATION"
    # Dọa bắt, khởi tố, phong tỏa tài sản, hoặc nói người nghe liên quan đến vụ án.
    LEGAL_THREAT = "LEGAL_THREAT"
    # Dọa làm hại hoặc bêu xấu: bắt giữ người thân, ghép ảnh, gọi cho cả danh bạ (đòi nợ, tống tiền).
    HARM_THREAT = "HARM_THREAT"
    # Bắt giữ bí mật, không cho nói với người nhà, không cho tắt máy.
    SECRECY_DEMAND = "SECRECY_DEMAND"
    # Đòi cài ứng dụng, bấm đường link hoặc cho điều khiển thiết bị từ xa.
    REMOTE_ACCESS_REQUEST = "REMOTE_ACCESS_REQUEST"
    # Mồi nhử tài chính: trúng thưởng, cam kết lợi nhuận, hoa hồng cao.
    FINANCIAL_BAIT = "FINANCIAL_BAIT"
    # Đòi trả bằng thẻ cào, thẻ quà tặng, tiền điện tử.
    UNUSUAL_PAYMENT = "UNUSUAL_PAYMENT"
    # Chuyển máy cho "cán bộ", "trưởng phòng", "bác sĩ"...: nhiều người cùng phối hợp trong một cuộc gọi.
    CALL_HANDOFF = "CALL_HANDOFF"
    # Từ hai người nói trở lên cùng gây áp lực lên một người (chỉ xác định được khi biết ai nói câu nào).
    COORDINATED_CALLERS = "COORDINATED_CALLERS"


class Severity(StrEnum):
    """Mức nghiêm trọng của một dấu hiệu khi đứng riêng; Risk Engine dùng giá trị này để tính điểm."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


@dataclass(frozen=True)
class IndicatorMatch:
    """Một dấu hiệu tìm thấy, kèm bằng chứng để giải thích được vì sao nó được báo."""

    code: Indicator
    severity: Severity
    # Các đoạn văn bản (đã chuẩn hóa) khớp với luật.
    evidence: list[str]
    # Mã các luật đã khớp, để truy lại luật nào sinh ra dấu hiệu.
    rule_ids: list[str]


# ----------------------------------------------------------------------------- chuẩn hóa văn bản

# Tiếng Việt có hai cách đặt dấu thanh cho vần oa, oe, uy ("khoá"/"khóa"). Đưa về một cách.
_TONE_VARIANTS = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}
_TONE_VARIANT_RX = re.compile("(" + "|".join(_TONE_VARIANTS) + r")(?!\w)")
# Chỉ dấu kết câu mới ngắt. Dấu phẩy không ngắt, vì lời yêu cầu thường là một chuỗi liệt kê
# ("tên, địa chỉ và số thẻ tín dụng") và transcript của Whisper vốn không có dấu phẩy.
# Lỗi nghe nhầm lặp lại của PhoWhisper trên ghi âm cuộc gọi thật, đưa về cách viết đúng trước khi so luật.
# Chỉ thêm những lỗi đã thấy trong transcript thật thuộc tập train.
_ASR_FIXES = {
    "trụ thưởng": "trúng thưởng", "mã cốt": "mã code", "đường linh": "đường link", "phây búc": "facebook",
    "thuê búc": "facebook",
}
_ASR_FIX_RX = re.compile(r"(?<!\S)(?:" + "|".join(_ASR_FIXES) + r")(?!\S)")
_CLAUSE_BREAK = re.compile(r"[.!?…]+")
_NOT_WORD = re.compile(r"[^\w|]+")


def normalize(text: str) -> str:
    """Chuẩn hóa văn bản để so khớp: chữ thường, Unicode dựng sẵn, một kiểu đặt dấu thanh.

    Dấu câu được đổi thành ký hiệu ngắt ``|`` đứng riêng như một từ, để một luật không ghép các từ
    thuộc hai câu khác nhau. Các từ cách nhau đúng một khoảng trắng.
    """
    lowered = unicodedata.normalize("NFC", text).lower()
    # Câu hỏi được ngắt bằng "||" để các luật biết một câu là câu hỏi; các dấu kết câu khác bằng "|".
    with_breaks = _CLAUSE_BREAK.sub(lambda m: " || " if "?" in m.group(0) else " | ", lowered)
    words_only = _NOT_WORD.sub(" ", with_breaks)
    unified = _TONE_VARIANT_RX.sub(lambda m: _TONE_VARIANTS[m.group(1)], words_only)
    unified = _ASR_FIX_RX.sub(lambda m: _ASR_FIXES[m.group(0)], unified)
    return " ".join(unified.split())


# ------------------------------------------------------------------------------ dựng biểu thức


def _alt(*phrases: str) -> str:
    """Nhóm "một trong các cụm từ"; cụm dài đứng trước để được ưu tiên khớp."""
    return "(?:" + "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + ")"


def _gap(max_words: int) -> str:
    """Tối đa ``max_words`` từ chen giữa, không vượt qua ký hiệu ngắt câu."""
    return rf"(?:[^\s|]+ ){{0,{max_words}}}?"


def _compile(pattern: str) -> re.Pattern[str]:
    """Biên dịch biểu thức, chỉ khớp trọn từ (không khớp một phần của từ khác)."""
    return re.compile(rf"(?<!\S)(?:{pattern})(?!\S)")


# ------------------------------------------------------------------------------- xét ngữ cảnh

# Các từ chắc chắn chỉ người nói. "em", "anh", "chị" không nằm ở đây vì cũng dùng để gọi người nghe.
_FIRST_PERSON = {"tôi", "tui", "tớ", "tao", "mình"}
# Các từ có thể đứng giữa chủ ngữ và động từ: "tôi [sẽ] chuyển", "tôi [cần] đọc".
_ADVERBS = {"đã", "sẽ", "vừa", "mới", "đang", "cũng", "xin", "muốn", "cần", "phải", "định", "có", "thể", "nên"}
_PAST_MARKERS = {"đã", "vừa", "mới"}
_HARD_NEGATORS = {"đừng", "chớ", "cấm", "chẳng", "chưa"}
_REASSURANCE = {"lo", "ngại", "sợ", "sao", "vấn"}
_QUESTION_TAG_HEADS = {"được", "phải", "đúng"}
_OWN = re.compile(r"của (?:chính )?(?:tôi|mình|tui|tớ)(?!\S)")
_OWN_STRICT = re.compile(r"của (?:chính )?(?:tôi|tui|tớ)(?!\S)")
_ADDRESSED = re.compile(r"(?<!\S)(?:vui lòng|anh|chị|bạn|ông|bà|cô|chú|bác|quý khách)(?!\S)")
_QUESTION_AFTER = re.compile(r"^(?:[^\s|]+ ){0,2}?(?:à|hả|phải không|đúng không|chứ)(?!\S)")


def _anchor(match: re.Match[str]) -> int:
    """Vị trí của động từ chính trong đoạn khớp (nhóm ``verb``), mặc định là đầu đoạn khớp."""
    return match.start("verb") if "verb" in match.re.groupindex else match.start()


def _words_before(text: str, position: int) -> list[str]:
    """Các từ đứng trước ``position`` trong cùng một câu."""
    return text[:position].rsplit("|", 1)[-1].split()


def _text_after(text: str, position: int) -> str:
    """Phần còn lại của câu sau ``position``."""
    return text[position:].split("|", 1)[0].strip()


def _negated(text: str, match: re.Match[str]) -> bool:
    """Hành động bị phủ định hoặc là lời khuyên đừng làm ("không cung cấp OTP cho ai").

    "Nếu không ..." là lời đe dọa có điều kiện chứ không phải phủ định, nên không bị loại.
    """
    # Sáu từ là đủ để bắt "không bao giờ yêu cầu anh cung cấp ..." mà chưa với sang ý khác của câu.
    recent = _words_before(text, _anchor(match))[-6:]
    if "nếu" in recent:
        return False
    for index, word in enumerate(recent):
        if word != "không" and word not in _HARD_NEGATORS:
            continue
        # "đừng lo", "không sao" là lời trấn an, không phủ định hành động đứng sau.
        if index + 1 < len(recent) and recent[index + 1] in _REASSURANCE:
            continue
        # "được không", "phải không" là đuôi câu hỏi của ý đứng trước, không phủ định ý đứng sau.
        if word == "không" and index > 0 and recent[index - 1] in _QUESTION_TAG_HEADS:
            continue
        return True
    return False


def _speaker_is_actor(text: str, match: re.Match[str]) -> bool:
    """Người nói tự làm hành động ("tôi sẽ chuyển tiền"), không phải yêu cầu người nghe."""
    before = _words_before(text, _anchor(match))
    skipped = 0
    while before and before[-1] in _ADVERBS and skipped < 3:
        before.pop()
        skipped += 1
    return bool(before) and before[-1] in _FIRST_PERSON


def _reported_past(text: str, match: re.Match[str]) -> bool:
    """Đang kể hoặc hỏi về việc đã xảy ra ("anh đã chuyển tiền chưa"), không phải yêu cầu."""
    before = _words_before(text, _anchor(match))
    return bool(before) and before[-1] in _PAST_MARKERS


def _own_item(text: str, match: re.Match[str]) -> bool:
    """Thứ được nhắc tới là của chính người nói ("OTP của chính tôi", "tài khoản của tôi")."""
    # "Cô vui lòng xác nhận số thẻ của mình": khi câu gọi tên người nghe thì "mình" là người nghe.
    addressed = bool(_ADDRESSED.search(" ".join(_words_before(text, _anchor(match))[-5:])))
    own = _OWN_STRICT if addressed else _OWN
    if own.search(match.group(0)):
        return True
    # "của tôi" có thể đứng sau vài từ: "bốn chữ số cuối của số an sinh xã hội hoặc ngày sinh của tôi".
    following = " ".join(_text_after(text, match.end()).split()[:12])
    return bool(own.search(following))


def _negation_inside(text: str, match: re.Match[str]) -> bool:
    """Trong đoạn khớp có phủ định ("tài khoản sẽ không bị khóa")."""
    return " không " in f" {match.group(0)} "


def _asked_as_question(text: str, match: re.Match[str]) -> bool:
    """Người nói đang hỏi lại ("anh là nhân viên ngân hàng à"), không phải tự xưng."""
    return bool(_QUESTION_AFTER.match(_text_after(text, match.end()) + " "))


_QUESTION_WORDS = {"không", "chưa", "à", "hả", "nhỉ"}
_AFTER_QUESTION_WORD = {"ạ", "anh", "chị", "em", "vậy", "thế", "nhỉ", "hả", "ta"}


def _is_question(text: str, match: re.Match[str]) -> bool:
    """Người nói đang hỏi ("... thì có bị phạt không", "tài khoản bị khóa à"), không phải đe dọa.

    Từ để hỏi phải đứng cuối câu hoặc ngay trước một từ đệm, để "sẽ bị khóa không thể giao dịch"
    không bị coi nhầm là câu hỏi.
    """
    after = _text_after(text, match.end()).split()
    if not after or after[0] not in _QUESTION_WORDS:
        return False
    return len(after) == 1 or after[1] in _AFTER_QUESTION_WORD


_PAYER_INTENT = re.compile(
    r"^(?:[^\s|]+ ){0,2}?để (?:[^\s|]+ ){0,2}?(?:chuyển|gửi|trả|thanh toán|bắn|ck)(?!\S)"
)


def _asker_wants_to_pay(text: str, match: re.Match[str]) -> bool:
    """Người hỏi số tài khoản là để tự mình chuyển tiền tới ("cho tôi số tài khoản để tôi chuyển tiền").

    Cũng tính khi ngay trước đó chính người nói vừa nhắc tới việc trả tiền ("anh chuyển năm triệu,
    em gửi lại số tài khoản nhé").
    """
    if _PAYER_INTENT.match(_text_after(text, match.end()) + " "):
        return True
    return bool(_PAYING_JUST_BEFORE.search(text[max(0, match.start() - 60):match.start()]))


_PAYING_JUST_BEFORE = re.compile(r"(?<!\S)(?:chuyển|trả|thanh toán)(?!\S)")


def _clause_is_question(text: str, match: re.Match[str]) -> bool:
    """Câu chứa đoạn khớp kết thúc bằng dấu hỏi (chỉ biết được khi văn bản có dấu câu)."""
    end = text.find("|", match.end())
    return end != -1 and text.startswith("||", end)


_OFFER_SUBJECTS = _FIRST_PERSON | {
    "em", "anh", "chị", "con", "cháu", "mẹ", "bố", "ba", "má", "cô", "chú", "bác", "ông", "bà",
}


def _speaker_offers(text: str, match: re.Match[str]) -> bool:
    """Người nói đề nghị tự làm ("để chị chuyển cho em"), không phải yêu cầu người nghe."""
    before = _words_before(text, _anchor(match))
    return len(before) >= 2 and before[-2] == "để" and before[-1] in _OFFER_SUBJECTS


_NOT_URGENCY_AFTER = re.compile(r"^(?:cả|khi|từ|tại|cạnh|ngắn|thẳng|sau khi)(?!\S)")


def _ngay_is_not_urgency(text: str, match: re.Match[str]) -> bool:
    """Chữ "ngay" trong "ngay cả", "ngay khi", "ngay thẳng" không mang nghĩa hối thúc."""
    return match.group(0).endswith("ngay") and bool(_NOT_URGENCY_AFTER.match(_text_after(text, match.end()) + " "))


Exclusion = Callable[[str, re.Match[str]], bool]


@dataclass(frozen=True)
class Rule:
    """Một luật: mẫu cần khớp và các ngữ cảnh khiến lần khớp đó không được tính."""

    rule_id: str
    indicator: Indicator
    severity: Severity
    pattern: re.Pattern[str]
    exclusions: tuple[Exclusion, ...] = ()


# ----------------------------------------------------------------------------------- từ vựng

# Whisper có thể viết "OTP" thành chữ rời hoặc phiên âm.
_OTP = _alt(
    "mã otp", "otp", "mã o t p", "o t p", "ô tê pê", "o tê pê", "mã ô tê pê", "mã o tê pê",
    "mã xác thực", "mã xác nhận", "mã xác minh", "mã bảo mật", "mã kích hoạt", "mã giao dịch",
)
_GIVE_TO_ME = (
    "cho tôi xin", "cho em xin", "cho tôi biết", "cho em biết", "cho tôi", "cho em", "cho anh", "cho chị",
    "cho mình", "cho bên em", "cho chúng tôi",
)
# Các động từ yêu cầu người nghe đưa thông tin ra.
_ASK_TO_SHARE = _alt(
    "đọc", "cung cấp", "gửi lại", "gửi", "báo lại", "báo", "nói", "nhắn", "chụp ảnh", "chụp hình", "chụp",
    "xác nhận lại", "khai báo", "xin", *_GIVE_TO_ME,
)
# "xác nhận số thẻ" là đòi thông tin, nhưng "xác nhận mã OTP" còn là thao tác bình thường trên ứng dụng,
# nên "xác nhận" chỉ dùng cho nhóm thông tin nhạy cảm, không dùng cho OTP.
_ASK_TO_SHARE_OR_CONFIRM = _alt(
    "đọc", "cung cấp", "gửi lại", "gửi", "báo lại", "báo", "nói", "nhắn", "chụp ảnh", "chụp hình", "chụp",
    "xác nhận lại", "xác nhận", "khai báo", "xin", *_GIVE_TO_ME,
)
_SHARE_VERBS = _alt("đọc", "gửi lại", "gửi", "báo lại", "báo", "nói", "nhắn", "cung cấp")
_TO_ME = _alt("cho tôi", "cho em", "cho anh", "cho chị", "cho mình", "cho bên em", "cho chúng tôi", "giúp tôi", "giúp em")
_ENTER = _alt("nhập", "điền", "gõ")
_INTO_LINK = _alt("link", "đường link", "đường dẫn", "trang web", "website", "web", "trang này", "đường link này")

_CREDENTIALS = _alt(
    "mật khẩu", "password", "mã pin", "số pin", "pin thẻ", "mã cvv", "cvv", "cvc", "số thẻ", "mã thẻ",
    "thông tin thẻ", "tên đăng nhập", "thông tin đăng nhập", "tài khoản đăng nhập", "ngày hết hạn thẻ",
    "số thẻ tín dụng", "thông tin thẻ tín dụng", "thông tin thẻ ngân hàng", "thông tin ngân hàng",
    "thông tin tài khoản ngân hàng", "ba số mặt sau", "ba số ở mặt sau", "mười sáu số", "16 số",
    "mã bảo mật thẻ", "chi tiết thẻ",
)
# Nơi người nghe đăng nhập bằng mật khẩu ngân hàng. "đăng nhập ngân hàng" trần không tính (Case F).
_BANKING_LOGIN = _alt(
    "tài khoản ngân hàng", "ứng dụng ngân hàng", "app ngân hàng", "internet banking", "mobile banking",
    "ngân hàng trực tuyến", "ngân hàng điện tử", "ví điện tử",
)
_NEED_FROM_YOU = _alt(
    "tôi cần", "em cần", "chúng tôi cần", "bên em cần", "chỉ cần", "tôi sẽ cần", "chúng tôi sẽ cần",
    "cần anh", "cần chị", "cần bạn", "cần ông", "cần bà", "yêu cầu anh", "yêu cầu chị", "yêu cầu bạn",
)
# Các khoản phí phải đóng trước để "nhận" một thứ gì đó: dấu hiệu của lừa đảo ứng trước.
_ADVANCE_FEE = _alt(
    "phí xử lý", "phí hồ sơ", "phí vận chuyển", "phí thông quan", "phí giải ngân",
    "phí kích hoạt", "phí xác minh", "phí hành chính", "phí dịch vụ", "phí bảo lãnh", "phí lưu kho",
    "khoản phí", "một khoản phí", "tiền thuế", "thuế thu nhập", "phí nhận thưởng", "phí nhận giải",
    "phí trước bạ", "thuế trúng thưởng", "tiền phạt", "tiền bảo lãnh",
    "tạm ứng viện phí", "tạm ứng", "tiền máu", "phí mở khóa", "phí bảo hiểm khoản vay",
    "thuế nhập khẩu", "cước phí", "khoản cước phí", "phí thuế",
)
# Mục đích vô lý của một khoản nộp thêm: "nạp thêm mười triệu để mở khóa", "chuyển trước để giữ chỗ".
_UNLOCK_PURPOSE = _alt(
    "mở khóa", "kích hoạt", "xác minh", "giữ chỗ", "giữ suất", "giữ giải", "chứng minh", "thông quan", "giải ngân",
    "làm hồ sơ", "nhận giải", "nhận thưởng", "nhận quà", "rút được", "mở lệnh", "mở", "hủy lệnh",
)
# Chi tiết thẻ: bảo người nghe "nhập" các thứ này vào đâu đó theo hướng dẫn qua điện thoại là đủ đáng ngờ.
_CARD_DETAILS = _alt(
    "số thẻ", "thông tin thẻ", "số thẻ tín dụng", "thông tin thẻ ngân hàng", "thông tin thẻ tín dụng",
    "ba số mặt sau", "ba số ở mặt sau", "mã cvv", "cvv", "cvc",
)
# Người nghe, khi được gọi bằng đại từ. Các từ này cũng có thể chỉ người nói, nên chỉ dùng kèm dấu hiệu khác.
_LISTENER = _alt(
    "anh", "chị", "bạn", "ông", "bà", "bác", "cô", "chú", "em", "cháu", "con", "mẹ", "bố", "mày", "quý khách",
)
# Mã được nhắc lại bằng từ chung chung, sau khi đã nói tới mã gửi về máy: "anh đọc mã đó cho em".
_UNNAMED_CODE = _alt(
    "mã đó", "mã này", "mã ấy", "mã vừa", "mã gồm", "mã sáu", "mã kết nối", "mã trên màn hình",
    "dãy số đó", "dãy số này", "dãy số", "dãy sáu chữ số", "sáu chữ số",
)
_IDENTITY_DOCUMENTS = _alt(
    "căn cước công dân", "số căn cước", "ảnh căn cước", "căn cước", "cccd", "chứng minh nhân dân",
    "chứng minh thư", "số chứng minh", "cmnd", "hộ chiếu",
    # Số định danh do nhà nước cấp ở nước khác: cùng loại với số căn cước, không phải mật khẩu.
    "số an sinh xã hội", "mã số an sinh xã hội",
)
# Cả cách nói chung chung "thông tin tài khoản": chưa rõ là đòi bí mật, nên cùng mức với số tài khoản.
_ACCOUNT_NUMBER = _alt(
    "số tài khoản", "stk", "thông tin tài khoản", "chi tiết tài khoản", "thông tin chi tiết về tài khoản",
)

_TRANSFER = _alt(
    "chuyển tiền", "chuyển khoản", "chuyển số tiền", "chuyển toàn bộ", "chuyển hết", "nộp tiền", "đóng tiền",
    "nạp tiền", "gửi tiền", "đóng phí", "nộp phí", "thanh toán phí", "đặt cọc", "chuyển cọc", "nộp thuế",
    "đóng thuế",
)
_DEMAND = _alt("hãy", "vui lòng", "phải", "cần phải", "yêu cầu", "đề nghị", "buộc phải", "bắt buộc")
_MOVE_MONEY = _alt("chuyển", "nộp", "nạp", "gửi", "đóng")
_PAY = _alt(
    "chuyển khoản", "chuyển tiền", "chuyển cọc", "đặt cọc", "chuyển", "nạp", "đóng", "nộp", "thanh toán",
)
_SUSPICIOUS_DESTINATION = _alt(
    "tài khoản an toàn", "tài khoản tạm giữ", "tài khoản tạm thời", "tài khoản bảo mật", "tài khoản của cơ quan",
    "tài khoản của chúng tôi", "tài khoản bên em", "tài khoản này", "tài khoản sau", "số tài khoản này",
    "số tài khoản sau", "tài khoản thẩm tra", "tài khoản của viện kiểm sát", "tài khoản cá nhân",
    "tài khoản của bác sĩ", "tài khoản của khoa", "tài khoản sàn",
)
# Làm ngay, trả trước: các từ biến một câu nhắc tới tiền thành lời đòi tiền.
_PAY_NOW = (
    rf"(?:{_alt('luôn', 'trong hôm nay', 'bây giờ', 'ngay bây giờ', 'tối thiểu', 'liền')}"
    r"|trước(?= (?:mới|rồi|đi|nhé|để|thì|là)(?!\S)))"
)

_BANK = _alt(
    "ngân hàng", "vietcombank", "vcb", "techcombank", "bidv", "vietinbank", "agribank", "mb bank", "mbbank",
    "acb", "sacombank", "vpbank", "tpbank", "hdbank", "vib", "shb", "ocb", "msb", "eximbank", "seabank",
    "lpbank", "nam a bank", "bac a bank",
    # Ví điện tử và công ty tài chính giữ tiền của người dùng như ngân hàng.
    "ví điện tử", "momo", "zalopay", "vnpay", "viettel money", "shopeepay", "công ty tài chính", "ngân hàng số",
)
_SELF = _alt("tôi", "em", "mình", "chúng tôi", "bên em", "bên tôi", "bên mình", "đây", "anh", "chị", "cháu")
_CALL = _alt("gọi điện", "gọi đến", "gọi tới", "gọi", "liên hệ", "liên lạc", "thông báo")
_STAFF_ROLE = _alt(
    "nhân viên", "giao dịch viên", "chuyên viên", "cán bộ", "tổng đài viên", "tổng đài", "bộ phận", "phòng",
    "trung tâm", "quản lý", "giám đốc", "tư vấn viên", "đại diện",
)

# Chỉ gồm những việc kẻ lừa đảo hay đòi nạn nhân làm. Các động từ quá chung ("gửi", "chuyển", "gọi lại")
# không nằm ở đây, để câu thường ngày như "em chuyển máy ngay ạ" không bị coi là hối thúc.
_ACTION = _alt(
    "chuyển tiền", "chuyển khoản", "nộp tiền", "đóng tiền", "nạp tiền", "gửi tiền", "nộp phí", "đóng phí",
    "làm theo", "thực hiện", "cung cấp", "đọc", "xác nhận", "xác minh", "cập nhật", "cài đặt", "truy cập",
    "hành động",
    "bấm vào", "nhấn vào", "đăng nhập", "thanh toán",
)
_MONEY_WORD = _alt("triệu", "nghìn", "ngàn", "trăm", "tỷ", "đồng", "tiền")
_URGENT = _alt(
    "ngay lập tức", "ngay bây giờ", "ngay", "gấp", "liền", "lập tức", "khẩn cấp", "khẩn trương",
    "càng sớm càng tốt", "nhanh lên",
)
_URGENT_LEAD = _alt("ngay lập tức", "lập tức", "khẩn trương", "gấp rút", "nhanh chóng", "khẩn cấp")
_NUMBER = (
    r"(?:\d+|"
    + _alt("một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười", "mươi", "mốt", "lăm", "tư",
           "vài", "mấy", "nửa")
    + ")"
)
_DEADLINE = (
    rf"(?:trong(?: vòng)? {_NUMBER}(?: {_NUMBER}){{0,3}} {_alt('phút', 'giờ', 'tiếng', 'giây')}(?: {_alt('nữa', 'tới')})?"
    rf"|{_alt('trước', 'đến', 'sau', 'quá')} {_NUMBER}(?: {_NUMBER}){{0,2}} {_alt('giờ', 'phút')})"
)
# Khan hiếm giả tạo và dồn ép thời gian: "chỉ còn hai suất cuối", "làm nhanh kẻo hết", "không kịp đâu".
_SCARCITY = _alt(
    "suất cuối", "ngày cuối", "lượt cuối", "cơ hội cuối", "phiên cuối", "hết trong hôm nay", "chỉ còn hôm nay",
    "hết hạn hôm nay", "kẻo hết", "sắp đóng lệnh", "là đóng lệnh", "quá hạn", "mất suất", "giữ suất",
    "không kịp đâu", "không còn thời gian", "từng phút", "nhận cọc bạn khác",
    "nhận cọc người khác", "đang rất gấp", "đang gấp lắm", "gấp lắm", "cần gấp",
    "lần thông báo cuối cùng", "thông báo cuối cùng", "lần cuối cùng",
)
# "kẻo mất tiền", "kẻo hệ thống khóa mất", "không là mất suất": hậu quả nếu chậm trễ.
_OR_ELSE = (
    rf"(?:{_alt('kẻo', 'không là', 'chậm là', 'không thì')} {_gap(4)}"
    rf"{_alt('mất', 'hủy', 'khóa', 'hết', 'trễ', 'lỡ', 'cắt', 'phạt', 'trừ', 'rút hết', 'đừng trách')})"
)
# Việc mà kẻ lừa đảo ép làm; dùng cho tối hậu thư "không ... thì ...".
_COMPLY = _alt(
    "chuyển", "nộp", "đóng", "nạp", "thanh toán", "trả", "trả thay", "hợp tác", "xử lý", "cập nhật", "nâng cấp",
    "liên kết", "làm", "đọc", "cung cấp",
)
# Cái cớ cấp cứu, dùng để người nghe không kịp kiểm tra lại.
_EMERGENCY = _alt(
    "mổ gấp", "mổ ngay", "cần mổ", "phải mổ", "đang cấp cứu", "nguy kịch", "xuất huyết não",
    "chấn thương sọ não",
)
# Dọa cắt dịch vụ thiết yếu nếu không trả tiền hoặc không làm theo.
_SERVICE_CUT = _alt(
    "cắt điện", "cắt nước", "ngừng cấp điện", "ngừng cấp nước", "cắt liên lạc", "khóa hai chiều",
    "khóa một chiều", "mất điện",
)
_HARM = _alt(
    "ghép ảnh", "đăng ảnh", "bêu xấu",
    "gửi cho cả công ty", "trong tay tao", "trong tay bọn tao", "trong tay chúng tao", "trong tay tôi",
    "không gặp lại", "đừng trách", "xử nó",
    "tung clip", "tung ảnh", "muốn nó an toàn", "gọi cho gia đình mày", "gửi cho gia đình mày",
)
_BAD_OUTCOME = (
    rf"(?:sẽ bị|bị {_alt('khóa', 'phạt', 'truy tố', 'bắt', 'khởi tố', 'cắt', 'hủy', 'mất', 'phong tỏa', 'đình chỉ', 'đóng băng', 'tạm ngưng')}"
    rf"|sẽ {_alt('khóa', 'mất', 'phạt', 'hủy', 'cắt', 'phong tỏa', 'đóng băng')})"
)

_LOCKABLE = _alt(
    "tài khoản", "thẻ tín dụng", "thẻ atm", "thẻ", "sim", "số điện thoại", "thuê bao", "ví điện tử", "dịch vụ",
    # Quyền lợi do nhà nước chi trả cũng bị đem ra dọa "đình chỉ", "cắt".
    "quyền lợi", "phúc lợi", "lương hưu", "trợ cấp", "số an sinh xã hội", "toàn bộ", "số này", "số thuê bao",
)
_LOCK = _alt(
    "khóa vĩnh viễn", "tạm khóa", "khóa", "phong tỏa", "đóng băng", "đình chỉ", "tạm ngưng", "tạm dừng",
    "vô hiệu hóa", "hủy", "cắt", "ngừng hoạt động",
)
_WILL_BE = _alt("sẽ bị", "đã bị", "đang bị", "có thể bị", "bị", "sẽ")
_WILL_DO = _alt("chúng tôi sẽ", "bên em sẽ", "buộc phải", "tiến hành", "sẽ", "phải")

# --- Từ vựng cho các dấu hiệu bổ sung ---
_AUTHORITY = _alt(
    "công an", "cảnh sát", "viện kiểm sát", "tòa án", "cơ quan điều tra", "bộ công an", "cục cảnh sát",
    "chi cục thuế", "cục thuế", "tổng cục thuế", "cơ quan thuế", "sở thuế", "hải quan", "bảo hiểm xã hội",
    "an sinh xã hội", "thanh tra", "ủy ban phường", "ủy ban", "an ninh mạng",
    # Đơn vị cung cấp dịch vụ thiết yếu cũng hay bị giả danh để dọa cắt dịch vụ.
    "công ty điện lực", "điện lực", "công ty cấp nước", "bưu điện", "viettel", "vinaphone", "mobifone",
    "nhà mạng", "bộ thông tin truyền thông", "bộ thông tin", "cục viễn thông", "trung tâm viễn thông",
    "công an điều tra",
)
# Cấp bậc và chức danh tố tụng: chỉ cần tự xưng như vậy qua điện thoại là đã đáng chú ý.
_OFFICER_TITLE = _alt(
    "đại úy", "thượng úy", "trung úy", "thiếu úy", "thiếu tá", "trung tá", "thượng tá", "đại tá",
    "điều tra viên", "kiểm sát viên", "thẩm phán", "thanh tra viên", "cán bộ điều tra",
)
_OFFICIAL = _alt("cán bộ", "nhân viên", "chuyên viên", "đại diện", "thanh tra")
_LEGAL_ACTION = _alt(
    "lệnh bắt giữ", "lệnh bắt", "bắt tạm giam", "bắt giam", "bắt giữ", "tạm giam", "truy tố", "khởi tố",
    "truy nã", "xét xử vắng mặt", "phong tỏa toàn bộ tài sản", "phong tỏa tài sản", "lệnh phong tỏa",
    "bị tình nghi", "đồng phạm", "hành động pháp lý", "giấy triệu tập",
)
_CRIME = _alt("vụ án", "đường dây", "rửa tiền", "ma túy", "lừa đảo", "hàng cấm", "tội phạm")
_TELL = _alt("nói", "kể", "tiết lộ", "báo", "cho", "gọi", "hỏi")
_OTHER_PEOPLE = _alt(
    "với ai", "cho ai", "ai biết", "bất kỳ ai", "người nhà", "gia đình", "con cháu", "người khác", "với bố",
    "với mẹ", "với chồng", "với vợ", "với con", "mẹ", "bố", "chồng", "vợ", "chồng con", "công an",
)
_SECRET_WORDS = re.compile(r"otp|o t p|mật khẩu|mã |thông tin thẻ|số thẻ|số tài khoản")
_REMOTE_CONTROL = _alt(
    "truy cập từ xa", "điều khiển từ xa", "hỗ trợ từ xa", "kết nối từ xa", "teamviewer", "team viewer",
    "anydesk", "any desk", "ultraviewer", "ultra viewer", "quyền truy cập vào máy tính", "quyền điều khiển",
)
_INSTALL = _alt("cài đặt", "cài", "tải xuống", "tải về", "tải", "download")
_SOFTWARE = _alt("ứng dụng", "phần mềm", "app", "chương trình", "bản")
_OPEN = _alt("bấm vào", "nhấn vào", "nhấp vào", "click vào", "truy cập vào", "truy cập", "bấm", "nhấn", "nhấp")
_LINK = _alt("đường link", "link", "đường dẫn", "liên kết")
# Cơ quan mà kẻ lừa đảo hay xưng tên trong lời nói đứt quãng: chỉ cần "bên công an điều tra", "là bộ thông tin".
_NAMED_AGENCY = _alt(
    "công an điều tra", "cơ quan điều tra", "cơ quan cảnh sát điều tra", "viện kiểm sát", "bộ công an",
    "bộ thông tin truyền thông", "bộ thông tin", "cục viễn thông", "trung tâm viễn thông",
)
# Dụ vào cổng cờ bạc trực tuyến.
_GAMBLING = _alt("cổng game", "tài xỉu", "bắn cá", "game bài", "nổ hũ", "cá cược", "nhà cái")
_PRIZE = _alt(
    "trúng thưởng", "trúng giải", "đã trúng", "giải nhất", "giải đặc biệt", "nhận thưởng", "nhận giải",
    "phần thưởng là", "được hoàn thuế", "khoản trợ cấp", "đủ điều kiện nhận",
    "đủ điều kiện để nhận", "khoản tiền hoàn lại", "khoản hoàn tiền", "miễn phí trị giá", "được chọn để nhận",
    "đã được chọn", "người may mắn", "khách hàng may mắn", "may mắn trúng", "được chọn nhận", "kiện quà",
    "thùng quà", "hoàn tiền gấp đôi", "bồi thường thêm", "đền bù thêm", "lãi mỗi ngày", "bảo toàn vốn",
    "lãi gấp đôi", "lãi gấp ba", "bốc thăm trúng thưởng", "bốc thăm", "quay số", "quà tri ân", "tri ân",
    "danh sách nhận quà", "chọn ngẫu nhiên", "số ngẫu nhiên", "phần thưởng duy nhất", "gửi tặng",
)
_GUARANTEE = _alt(
    "cam kết lợi nhuận", "cam kết trúng", "cam kết thu hồi", "không rủi ro", "bao lỗ", "hoàn lại gấp đôi",
    "siêu lợi nhuận", "tỷ lệ thắng", "cam kết không rủi ro", "lỗ tôi chịu", "lỗ bên em đền",
    "cam kết bảo toàn vốn",
)
_RETURN = _alt("lợi nhuận", "lãi", "hoa hồng", "lãi suất")
_ODD_CARD = _alt(
    "thẻ quà tặng", "thẻ cào", "mã thẻ cào", "thẻ nạp", "thẻ trả trước", "gift card", "google play", "itunes",
)
_ODD_CRYPTO = _alt("bitcoin", "tiền điện tử", "tiền ảo", "usdt", "western union", "moneygram")
_HAND_OVER = _alt("chuyển máy", "nối máy", "đưa máy", "chuyển cuộc gọi", "kết nối")
_COLLEAGUE = _alt(
    "cán bộ", "đồng chí", "điều tra viên", "kiểm sát viên", "trưởng phòng", "kế toán", "kỹ thuật viên", "bác sĩ",
    "chuyên viên", "bộ phận", "cơ quan công an", "công an", "quản lý", "cấp trên", "giám sát viên",
    "người giám sát", "thanh tra",
)


def _about_secrets(text: str, match: re.Match[str]) -> bool:
    """Câu "không tiết lộ mã OTP cho bất kỳ ai" là lời khuyên an toàn, không phải bắt giữ bí mật."""
    return bool(_SECRET_WORDS.search(match.group(0)))


_SPEAKER_HARMED = re.compile(r"(?<!\S)(?:tôi|tui|tớ|mình) (?:sẽ |có thể |cũng )?bị(?!\S)")


def _speaker_is_the_one_harmed(text: str, match: re.Match[str]) -> bool:
    """Người nói kể hậu quả xảy đến với chính mình ("nếu không tôi sẽ bị bắt"), không phải dọa người nghe."""
    start = max(0, match.start() - 12)
    return bool(_SPEAKER_HARMED.search(text[start:match.end()]))


def _kept_confidential(text: str, match: re.Match[str]) -> bool:
    """ "Thông tin của anh được giữ bí mật" là cam kết bảo mật, không phải bắt người nghe giấu người nhà."""
    recent = _words_before(text, match.start())[-4:]
    return "được" in recent or "thông" in recent or "sẽ" in recent


_REQUEST_CONTEXT: tuple[Exclusion, ...] = (_negated, _speaker_is_actor, _reported_past, _own_item)
_DEMAND_CONTEXT: tuple[Exclusion, ...] = (_negated, _speaker_is_actor, _reported_past, _speaker_offers, _is_question)


# ------------------------------------------------------------------------------------ các luật

RULES: tuple[Rule, ...] = (
    # --- OTP_REQUEST: yêu cầu người nghe đọc hoặc gửi mã OTP ---
    Rule("OTP-1", Indicator.OTP_REQUEST, Severity.HIGH,
         _compile(rf"(?P<verb>{_ASK_TO_SHARE}) {_gap(4)}{_OTP}"), _REQUEST_CONTEXT),
    Rule("OTP-2", Indicator.OTP_REQUEST, Severity.HIGH,
         _compile(rf"{_OTP} {_gap(6)}(?P<verb>{_SHARE_VERBS}) {_gap(2)}{_TO_ME}"), _REQUEST_CONTEXT),
    Rule("OTP-3", Indicator.OTP_REQUEST, Severity.HIGH,
         _compile(rf"(?P<verb>{_ENTER}) {_gap(3)}{_OTP} {_gap(6)}{_alt('vào', 'lên', 'trên')} {_gap(3)}{_INTO_LINK}"),
         _REQUEST_CONTEXT),
    # Mã được gọi bằng từ chung chung ("mã đó", "dãy số đó"), nên mức thấp hơn khi nói rõ là OTP.
    Rule("OTP-4", Indicator.OTP_REQUEST, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_SHARE_VERBS}) {_gap(3)}{_UNNAMED_CODE}"), _REQUEST_CONTEXT),

    # --- MONEY_TRANSFER: đòi người nghe chuyển tiền ---
    Rule("MT-1", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"{_DEMAND} {_gap(4)}(?P<verb>{_TRANSFER})"), _DEMAND_CONTEXT),
    # Mệnh lệnh đứng đầu câu: "Chuyển tiền ngay ...".
    Rule("MT-2", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         re.compile(rf"(?:^|(?<=\| ))(?P<verb>{_TRANSFER})(?!\S)"), (_clause_is_question,)),
    Rule("MT-3", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_TRANSFER}) {_gap(4)}{_alt('ngay lập tức', 'ngay bây giờ', 'ngay', 'gấp', 'liền', 'lập tức', 'trong vòng', 'trước khi')}"),
         (_negated, _speaker_is_actor, _reported_past, _ngay_is_not_urgency)),
    Rule("MT-4", Indicator.MONEY_TRANSFER, Severity.HIGH,
         _compile(rf"(?P<verb>{_MOVE_MONEY}) {_gap(8)}{_alt('vào', 'sang', 'đến', 'tới', 'qua')} {_gap(2)}{_SUSPICIOUS_DESTINATION}"),
         (_negated, _speaker_is_actor, _reported_past)),
    Rule("MT-5", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"nếu {_gap(2)}không {_gap(1)}(?P<verb>{_TRANSFER})"), ()),
    # "Chuyển gấp cho bố hai mươi triệu": động từ, từ hối thúc, rồi một số tiền.
    Rule("MT-6", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_MOVE_MONEY}) {_alt('gấp', 'ngay', 'liền', 'khẩn cấp')} {_gap(6)}{_MONEY_WORD}"),
         _DEMAND_CONTEXT),
    # "Anh chuyển khoản trong hôm nay", "chị chuyển cọc luôn bây giờ": gọi người nghe rồi bảo trả ngay.
    Rule("MT-7", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"{_LISTENER} {_gap(1)}(?P<verb>{_PAY}) {_gap(4)}{_PAY_NOW}"), _DEMAND_CONTEXT),
    # Bảo chuyển tiền vào một tài khoản. Đứng riêng thì chưa nói lên điều gì (đóng quỹ lớp cũng vậy).
    Rule("MT-8", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_MOVE_MONEY}) {_gap(8)}{_alt('vào', 'sang', 'qua', 'tới', 'đến')} {_gap(1)}{_alt('số tài khoản', 'tài khoản')}"),
         (*_DEMAND_CONTEXT, _clause_is_question)),
    Rule("MT-9", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_alt('nạp', 'chuyển', 'đóng', 'nộp', 'đặt cọc', 'chuyển cọc')}) {_alt('tối thiểu', 'luôn', 'gấp')}"),
         _DEMAND_CONTEXT),
    # "Anh chuyển trước năm triệu": gọi người nghe, bảo chuyển, kèm một số tiền cụ thể.
    Rule("MT-10", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"{_LISTENER} {_gap(2)}(?P<verb>{_alt('chuyển', 'nạp', 'đóng', 'nộp')}) {_gap(4)}{_NUMBER}(?: {_NUMBER}){{0,3}} "
                  rf"{_alt('triệu', 'nghìn', 'ngàn', 'trăm', 'tỷ', 'đô', 'đô la')}"),
         (*_DEMAND_CONTEXT, _clause_is_question)),
    # Phí ứng trước: phải đóng một khoản phí thì mới nhận được tiền, quà, khoản vay.
    Rule("MT-11", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_alt('đóng', 'nộp', 'thanh toán', 'trả', 'chuyển', 'chi trả')}) {_gap(4)}{_ADVANCE_FEE}"),
         (*_DEMAND_CONTEXT, _clause_is_question)),
    # Nộp thêm tiền để "mở khóa", "kích hoạt", "giữ chỗ": khoản nộp có mục đích vô lý.
    Rule("MT-12", Indicator.MONEY_TRANSFER, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_alt('chuyển', 'nạp', 'nộp', 'đóng', 'đặt cọc', 'thanh toán')}) {_gap(8)}để {_gap(3)}{_UNLOCK_PURPOSE}"),
         (*_DEMAND_CONTEXT, _clause_is_question)),

    # --- BANK_IMPERSONATION: người nói tự xưng là người của ngân hàng ---
    Rule("BI-1", Indicator.BANK_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} {_gap(3)}(?P<verb>{_CALL}) {_gap(3)}từ {_gap(4)}{_BANK}"), (_negated, _asked_as_question)),
    Rule("BI-2", Indicator.BANK_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} (?P<verb>{_alt('là', 'làm', 'đang là', 'hiện là')}) {_gap(2)}{_STAFF_ROLE} {_gap(5)}{_BANK}"),
         (_negated, _asked_as_question)),
    Rule("BI-3", Indicator.BANK_IMPERSONATION, Severity.LOW,
         _compile(rf"{_alt('đây là', 'bên em là', 'bên tôi là', 'chúng tôi là')} {_gap(3)}{_BANK}"),
         (_asked_as_question,)),
    Rule("BI-4", Indicator.BANK_IMPERSONATION, Severity.LOW,
         _compile(rf"{_alt('tôi', 'em', 'mình', 'chúng tôi')} {_alt('bên', 'ở bên', 'thuộc', 'đến từ')} {_gap(2)}{_BANK}"),
         (_asked_as_question,)),

    # --- URGENCY: hối thúc người nghe làm ngay ---
    Rule("U-1", Indicator.URGENCY, Severity.LOW,
         _compile(rf"(?P<verb>{_ACTION}) {_gap(3)}{_URGENT}"),
         (_negated, _speaker_is_actor, _reported_past, _ngay_is_not_urgency)),
    Rule("U-2", Indicator.URGENCY, Severity.LOW,
         _compile(rf"{_URGENT_LEAD} {_gap(2)}(?P<verb>{_ACTION})"), (_speaker_is_actor,)),
    # Thời hạn chỉ tính khi đi kèm một yêu cầu hoặc hậu quả; "giao hàng trong vòng 2 giờ" không tính.
    Rule("U-3", Indicator.URGENCY, Severity.LOW,
         _compile(rf"(?P<verb>{_alt('phải', 'cần', 'yêu cầu')}|{_ACTION}) {_gap(8)}{_DEADLINE}"),
         (_negated, _speaker_is_actor)),
    Rule("U-4", Indicator.URGENCY, Severity.LOW,
         _compile(rf"{_DEADLINE} {_gap(8)}(?:nếu không|{_BAD_OUTCOME}|phải)"), ()),
    # Tối hậu thư: "nếu không ... sẽ bị ...", "nếu anh không ... chúng tôi sẽ phong tỏa ...".
    Rule("U-5", Indicator.URGENCY, Severity.LOW,
         _compile(rf"nếu {_gap(2)}không {_gap(14)}{_BAD_OUTCOME}"), (_is_question, _speaker_is_the_one_harmed)),
    Rule("U-6", Indicator.URGENCY, Severity.LOW,
         _compile(rf"(?P<verb>{_MOVE_MONEY}) {_alt('gấp', 'ngay', 'liền', 'khẩn cấp')} {_gap(6)}{_MONEY_WORD}"),
         (_negated, _speaker_is_actor, _reported_past)),
    Rule("U-7", Indicator.URGENCY, Severity.LOW, _compile(_SCARCITY), (_negated,)),
    Rule("U-8", Indicator.URGENCY, Severity.LOW, _compile(_OR_ELSE), ()),
    # "Anh làm ngay đi", "em chuyển luôn đi", "chị đọc nhanh giúp em".
    Rule("U-9", Indicator.URGENCY, Severity.LOW,
         _compile(rf"{_LISTENER} (?P<verb>{_COMPLY}) {_alt('ngay', 'luôn', 'liền', 'nhanh', 'gấp', 'sớm')} "
                  rf"{_alt('đi', 'nhé', 'nha', 'giúp', 'kẻo', 'không', 'trong')}"),
         (_negated, _speaker_offers, _clause_is_question)),
    # Tối hậu thư không có chữ "nếu": "chị không thanh toán trước mười bảy giờ thì ...", "không chuyển thì ...".
    Rule("U-10", Indicator.URGENCY, Severity.LOW,
         _compile(rf"(?:{_LISTENER} |(?<=\| )|^)không (?P<verb>{_COMPLY}) {_gap(8)}{_alt('thì', 'là')}"),
         (_clause_is_question,)),
    Rule("U-11", Indicator.URGENCY, Severity.LOW, _compile(_EMERGENCY), (_negated, _clause_is_question)),
    # "Chúng ta cần phải hành động ngay lập tức": người gọi kéo cả hai vào một việc phải làm ngay.
    Rule("U-12", Indicator.URGENCY, Severity.LOW,
         _compile(rf"{_alt('chúng ta', 'chúng tôi', 'bạn', 'anh', 'chị', 'ông', 'bà')} {_alt('cần phải', 'cần', 'phải')} "
                  rf"{_gap(5)}{_alt('ngay lập tức', 'ngay bây giờ', 'trước khi quá muộn', 'càng sớm càng tốt')}"),
         (_negated, _clause_is_question)),

    # --- ACCOUNT_LOCK_THREAT: dọa khóa tài khoản, thẻ, SIM ---
    Rule("AL-1", Indicator.ACCOUNT_LOCK_THREAT, Severity.MEDIUM,
         _compile(rf"{_LOCKABLE} {_gap(7)}{_WILL_BE} {_gap(1)}{_LOCK}"),
         (_own_item, _negation_inside, _is_question)),
    Rule("AL-2", Indicator.ACCOUNT_LOCK_THREAT, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_WILL_DO}) {_gap(2)}{_LOCK} {_gap(2)}{_LOCKABLE}"),
         (_negated, _speaker_is_actor, _own_item)),
    # Dọa cắt điện, nước, số điện thoại nếu không trả tiền hoặc không làm theo. Thông báo lịch cắt điện
    # để bảo trì không có vế điều kiện nên không khớp.
    Rule("AL-3", Indicator.ACCOUNT_LOCK_THREAT, Severity.MEDIUM,
         _compile(rf"{_alt('không', 'chưa')} {_gap(2)}(?P<verb>{_COMPLY}) {_gap(10)}{_SERVICE_CUT}"),
         (_clause_is_question,)),
    Rule("AL-4", Indicator.ACCOUNT_LOCK_THREAT, Severity.MEDIUM,
         _compile(rf"{_alt('sẽ bị', 'sẽ')} {_alt('khóa hai chiều', 'khóa một chiều', 'cắt liên lạc')}"),
         (_clause_is_question,)),

    # --- SENSITIVE_INFORMATION: đòi thông tin bí mật hoặc giấy tờ cá nhân ---
    Rule("SI-1", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"(?P<verb>{_ASK_TO_SHARE_OR_CONFIRM}) {_gap(4)}{_CREDENTIALS}"), _REQUEST_CONTEXT),
    Rule("SI-2", Indicator.SENSITIVE_INFORMATION, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_ASK_TO_SHARE_OR_CONFIRM}) {_gap(5)}{_IDENTITY_DOCUMENTS}"), _REQUEST_CONTEXT),
    # Số tài khoản không phải bí mật, nên chỉ là dấu hiệu yếu và không tính khi người hỏi muốn tự chuyển tiền tới.
    Rule("SI-3", Indicator.SENSITIVE_INFORMATION, Severity.LOW,
         _compile(rf"(?P<verb>{_ASK_TO_SHARE_OR_CONFIRM}) {_gap(3)}{_ACCOUNT_NUMBER}"),
         (*_REQUEST_CONTEXT, _asker_wants_to_pay)),
    Rule("SI-4", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"(?P<verb>{_ENTER}) {_gap(3)}{_CREDENTIALS} {_gap(6)}{_alt('vào', 'lên', 'trên')} {_gap(3)}{_INTO_LINK}"),
         _REQUEST_CONTEXT),
    Rule("SI-5", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"{_LISTENER} {_gap(1)}(?P<verb>{_ENTER}) {_gap(3)}{_CARD_DETAILS}"), (_negated, _reported_past)),
    # Bảo người nghe đăng nhập ngân hàng theo hướng dẫn qua điện thoại.
    Rule("SI-6", Indicator.SENSITIVE_INFORMATION, Severity.MEDIUM,
         _compile(rf"(?P<verb>đăng nhập) {_gap(3)}{_BANKING_LOGIN}"),
         (*_REQUEST_CONTEXT, _clause_is_question)),
    # Đòi bằng cụm danh từ: "tôi cần số thẻ và mã bảo mật của anh".
    Rule("SI-7", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"(?P<verb>{_NEED_FROM_YOU}) {_gap(8)}{_CREDENTIALS}"), (_negated, _own_item)),
    # "Chị bấm vào rồi điền số thẻ và mã OTP": mở đường link được gửi rồi nhập thông tin bí mật.
    Rule("SI-8", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"(?P<verb>{_OPEN}) {_gap(8)}{_ENTER} {_gap(6)}(?:{_CREDENTIALS}|{_OTP})"),
         (_negated, _speaker_is_actor, _reported_past)),
    # Nhập mật khẩu ngân hàng theo lời người gọi, vào bất cứ đâu.
    Rule("SI-9", Indicator.SENSITIVE_INFORMATION, Severity.HIGH,
         _compile(rf"(?P<verb>{_ENTER}) {_gap(2)}mật khẩu {_gap(2)}{_alt('ngân hàng', 'ứng dụng ngân hàng', 'tài khoản')}"),
         (_negated, _speaker_is_actor, _reported_past, _clause_is_question)),
    # "Chúng tôi cần xác minh một số thông tin": mở đầu của việc moi thông tin; nhân viên thật cũng nói nên mức thấp.
    Rule("SI-10", Indicator.SENSITIVE_INFORMATION, Severity.LOW,
         _compile(rf"(?P<verb>{_alt('xác minh', 'xác nhận', 'cung cấp', 'cho tôi biết', 'cho chúng tôi biết')}) {_gap(3)}"
                  rf"{_alt('một số thông tin', 'một vài thông tin', 'thông tin cá nhân', 'thông tin chi tiết')}"),
         (_negated, _clause_is_question)),

    # --- AUTHORITY_IMPERSONATION: tự xưng là công an, kiểm sát, tòa án, thuế, bảo hiểm xã hội ---
    Rule("AU-1", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} (?P<verb>{_alt('là', 'tên là')}) {_gap(1)}{_OFFICER_TITLE}"), (_negated, _asked_as_question)),
    Rule("AU-2", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} (?P<verb>{_alt('là', 'làm', 'tên là')}) {_gap(4)}{_OFFICIAL} {_gap(4)}{_AUTHORITY}"),
         (_negated, _asked_as_question)),
    Rule("AU-3", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} {_gap(3)}(?P<verb>{_CALL}) {_gap(3)}từ {_gap(4)}{_AUTHORITY}"),
         (_negated, _asked_as_question)),
    Rule("AU-4", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_alt('đây là', 'bên em là', 'chúng tôi là')} {_gap(4)}{_AUTHORITY}"), (_asked_as_question,)),
    Rule("AU-5", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} (?P<verb>{_alt('là', 'tên là')}) {_gap(4)}{_alt('từ', 'của', 'thuộc', 'bên')} {_gap(4)}{_AUTHORITY}"),
         (_negated, _asked_as_question)),
    # "Trung tá Bình nghe", "Bưu điện thành phố xin thông báo".
    Rule("AU-6", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_OFFICER_TITLE} {_gap(6)}{_alt('nghe', 'đây', 'nghe đây')}"), (_asked_as_question,)),
    Rule("AU-7", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_AUTHORITY} {_gap(3)}{_alt('xin thông báo', 'thông báo', 'đây', 'nghe')}"), (_asked_as_question,)),
    # Lời nói thật thường không đủ câu: "tôi gọi cho anh bên công an điều tra", "là bộ thông tin anh biết không".
    Rule("AU-9", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_alt('bên', 'là', 'từ', 'của')} {_NAMED_AGENCY}"), (_negated, _asked_as_question)),
    Rule("AU-8", Indicator.AUTHORITY_IMPERSONATION, Severity.LOW,
         _compile(rf"{_SELF} {_alt('ở', 'bên', 'ở bên', 'thuộc')} {_gap(3)}{_AUTHORITY}"), (_negated, _asked_as_question)),

    # --- LEGAL_THREAT: dọa bắt, khởi tố, phong tỏa, hoặc gán người nghe vào một vụ án ---
    Rule("LT-1", Indicator.LEGAL_THREAT, Severity.MEDIUM, _compile(_LEGAL_ACTION), (_negated, _clause_is_question)),
    Rule("LT-2", Indicator.LEGAL_THREAT, Severity.MEDIUM,
         _compile(rf"{_alt('liên quan đến', 'liên quan tới', 'dính líu đến', 'dính líu tới')} {_gap(6)}{_CRIME}"),
         (_negated,)),
    Rule("LT-3", Indicator.LEGAL_THREAT, Severity.MEDIUM,
         _compile(rf"{_alt('sẽ bị', 'sẽ dính', 'có thể bị')} {_gap(2)}{_alt('bắt', 'nợ xấu', 'khởi tố', 'truy tố', 'phạt tù', 'kiện')}"),
         (_is_question, _speaker_is_the_one_harmed)),
    Rule("LT-4", Indicator.LEGAL_THREAT, Severity.MEDIUM,
         _compile(rf"số an sinh xã hội {_gap(5)}{_alt('bị đình chỉ', 'đình chỉ', 'bị treo', 'bị khóa', 'bị xâm phạm', 'bị đánh cắp', 'bị sử dụng')}"),
         ()),
    # Gán cho người nghe tội "đăng tin chống phá": cái cớ quen thuộc của kiểu giả nhà mạng rồi chuyển sang công an.
    Rule("LT-6", Indicator.LEGAL_THREAT, Severity.MEDIUM,
         _compile(_alt("chống phá nhà nước", "chống phá đảng", "chống phá", "lập cho anh một hồ sơ",
                       "lập cho chị một hồ sơ", "có hiệu lực trên pháp lý", "có hiệu lực pháp lý")),
         (_negated, _clause_is_question)),
    Rule("LT-5", Indicator.LEGAL_THREAT, Severity.MEDIUM,
         _compile(_alt("bị ghi nợ xấu", "ghi nợ xấu", "kiện anh ra tòa", "kiện chị ra tòa", "kiện ra tòa",
                       "xử phạt hành chính", "chuyển công an", "chuyển sang công an", "chuyển hồ sơ sang")),
         (_negated, _clause_is_question)),

    # --- HARM_THREAT: dọa làm hại, bêu xấu, giữ người ---
    Rule("HT-1", Indicator.HARM_THREAT, Severity.MEDIUM, _compile(_HARM), (_negated, _clause_is_question)),

    # --- SECRECY_DEMAND: cô lập người nghe khỏi những người có thể can ngăn ---
    Rule("SD-1", Indicator.SECRECY_DEMAND, Severity.MEDIUM,
         _compile(rf"{_alt('không được', 'đừng', 'tuyệt đối không', 'không nên', 'cấm')} {_gap(2)}{_TELL} {_gap(3)}{_OTHER_PEOPLE}"),
         (_about_secrets,)),
    Rule("SD-2", Indicator.SECRECY_DEMAND, Severity.MEDIUM,
         _compile(_alt("giữ bí mật", "bí mật điều tra", "giữ kín", "không để người khác nghe", "ra chỗ vắng",
                       "chỗ vắng người", "không được nói là", "đừng nói là", "đừng gọi ai", "đừng báo ai",
                       "đừng nói ai", "đừng kể ai")), (_kept_confidential,)),
    # "Ghi âm lời khai": bắt người nghe ở một mình, không có người thứ ba, giữ yên tĩnh suốt cuộc gọi.
    Rule("SD-4", Indicator.SECRECY_DEMAND, Severity.MEDIUM,
         _compile(_alt("người thứ ba", "không gian yên tĩnh", "giữ yên tĩnh", "bên cạnh không có")), ()),
    # Giữ máy liên tục cũng xảy ra khi hỗ trợ thật, nên chỉ là dấu hiệu yếu.
    Rule("SD-3", Indicator.SECRECY_DEMAND, Severity.LOW,
         _compile(rf"{_alt('không được', 'đừng')} {_alt('tắt máy', 'cúp máy', 'ngắt máy', 'gác máy')}"), ()),

    # --- REMOTE_ACCESS_REQUEST: chiếm quyền điều khiển thiết bị của người nghe ---
    Rule("RA-1", Indicator.REMOTE_ACCESS_REQUEST, Severity.HIGH, _compile(_REMOTE_CONTROL), (_negated,)),
    Rule("RA-2", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_INSTALL}) {_gap(3)}{_SOFTWARE}"), (_negated, _speaker_is_actor, _reported_past)),
    Rule("RA-3", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_OPEN}) {_gap(3)}{_LINK}"), (_negated, _speaker_is_actor, _reported_past)),
    # Gửi đường link trong lúc đang gọi. Doanh nghiệp thật cũng gửi link, nên đứng riêng chỉ là dấu hiệu yếu;
    # không loại trừ ngôi thứ nhất vì chính kẻ gọi là người gửi.
    Rule("RA-4", Indicator.REMOTE_ACCESS_REQUEST, Severity.LOW,
         _compile(rf"{_alt('gửi', 'nhắn')} {_gap(3)}{_LINK}"), (_negated,)),
    Rule("RA-5", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(_alt("cho phép tất cả các quyền", "cấp tất cả các quyền", "cấp quyền", "mã kết nối",
                       "chia sẻ màn hình")), (_negated,)),
    Rule("RA-6", Indicator.REMOTE_ACCESS_REQUEST, Severity.HIGH,
         _compile(rf"(?P<verb>{_alt('truy cập', 'kết nối', 'điều khiển', 'sửa', 'xóa', 'khắc phục', 'kiểm tra', 'xử lý')}) "
                  rf"{_gap(6)}từ xa"), (_negated,)),
    # Cái cớ "máy bị nhiễm vi-rút" của kiểu giả danh hỗ trợ kỹ thuật; đứng riêng chỉ là dấu hiệu yếu.
    Rule("RA-7", Indicator.REMOTE_ACCESS_REQUEST, Severity.LOW,
         _compile(rf"{_alt('máy tính', 'thiết bị', 'điện thoại', 'máy')} {_gap(5)}{_alt('bị nhiễm', 'nhiễm', 'dính', 'bị dính', 'có')} "
                  rf"{_gap(2)}{_alt('vi rút', 'virus', 'mã độc', 'phần mềm độc hại')}"), (_negated, _clause_is_question)),
    # Người gọi tự báo "chúng tôi nhận được cảnh báo máy của anh nhiễm vi-rút": không ai gọi báo như vậy
    # ngoài kẻ giả danh hỗ trợ kỹ thuật. Khác với khách hàng tự nói "máy tôi bị nhiễm vi-rút" (RA-7).
    Rule("RA-8", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(rf"{_alt('chúng tôi', 'bên em', 'bên tôi', 'hệ thống của chúng tôi', 'hệ thống bên em')} {_gap(4)}"
                  rf"{_alt('nhận được', 'phát hiện', 'nhận thấy', 'ghi nhận', 'theo dõi')} {_gap(12)}"
                  rf"{_alt('vi rút', 'virus', 'mã độc', 'phần mềm độc hại', 'nhiễm', 'bị xâm nhập', 'bị tấn công')}"),
         (_negated,)),
    # Nói thẳng "máy tính của anh đã bị nhiễm": người gọi khẳng định về thiết bị của người nghe.
    Rule("RA-11", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(rf"{_alt('máy tính', 'thiết bị', 'điện thoại', 'máy', 'tài khoản')} của {_LISTENER} {_gap(3)}"
                  rf"{_alt('bị nhiễm', 'nhiễm', 'bị xâm nhập', 'bị tấn công', 'bị hack', 'bị chiếm quyền')}"),
         (_negated, _clause_is_question)),
    # Bảo người nghe mở một trang web hay công cụ hệ thống theo hướng dẫn qua điện thoại.
    Rule("RA-9", Indicator.REMOTE_ACCESS_REQUEST, Severity.MEDIUM,
         _compile(rf"{_alt('cần', 'muốn', 'yêu cầu', 'vui lòng', 'hãy')} {_gap(6)}"
                  rf"(?P<verb>{_alt('truy cập', 'vào', 'mở', 'tải xuống', 'tải', 'cài đặt', 'cài')}) {_gap(4)}"
                  rf"{_alt('trang web', 'website', 'event viewer', 'trình xem sự kiện', 'url', 'trình duyệt', 'phần mềm', 'chương trình', 'công cụ')}"),
         (_negated, _speaker_is_actor, _clause_is_question)),

    # --- FINANCIAL_BAIT: lời hứa quá tốt để là thật ---
    Rule("FB-1", Indicator.FINANCIAL_BAIT, Severity.MEDIUM, _compile(_PRIZE), (_negated, _clause_is_question)),
    Rule("FB-2", Indicator.FINANCIAL_BAIT, Severity.MEDIUM, _compile(_GUARANTEE), (_negated,)),
    Rule("FB-3", Indicator.FINANCIAL_BAIT, Severity.LOW, _compile(rf"{_RETURN} {_gap(6)}phần trăm"), (_negated,)),
    # Biệt ngữ của lừa đảo "làm nhiệm vụ": đơn ảo, ứng tiền rồi nhận lại gốc kèm hoa hồng.
    Rule("FB-4", Indicator.FINANCIAL_BAIT, Severity.MEDIUM,
         _compile(_alt("đơn hàng ảo", "đơn ảo", "hoàn lại tiền gốc", "trả gốc và hoa hồng", "gốc và hoa hồng",
                       "nhận nhiệm vụ", "làm nhiệm vụ", "nhiệm vụ tiếp theo")), (_negated,)),
    # Tự gọi tới báo "được hoàn lại 500 đô la", "đủ điều kiện được hoàn tiền". Chủ shop nói "em hoàn lại
    # tiền chị đã chuyển" không khớp vì không nêu một khoản tiền từ trên trời rơi xuống.
    Rule("FB-5", Indicator.FINANCIAL_BAIT, Severity.MEDIUM,
         _compile(rf"{_alt('đủ điều kiện được', 'đủ điều kiện nhận', 'đủ điều kiện để nhận', 'được nhận', 'sẽ hoàn', 'muốn hoàn', 'được hoàn', 'hoàn lại cho', 'hoàn trả cho')} "
                  rf"{_gap(10)}{_NUMBER}(?: {_NUMBER}){{0,3}} {_alt('đô la', 'đô', 'triệu', 'nghìn', 'ngàn', 'trăm nghìn')}"),
         (_negated, _clause_is_question)),

    # Tự gọi tới đòi trả lại tiền mà không nêu số: "chúng tôi muốn hoàn lại tiền cho bạn", "chúng tôi nợ bạn".
    Rule("FB-6", Indicator.FINANCIAL_BAIT, Severity.MEDIUM,
         _compile(rf"{_alt('chúng tôi', 'bên em', 'bên tôi', 'công ty')} {_gap(3)}"
                  rf"(?:{_alt('muốn', 'sẽ', 'sẵn sàng')} {_alt('hoàn lại', 'hoàn trả', 'hoàn')} {_gap(3)}{_alt('tiền', 'khoản', 'toàn bộ')}"
                  rf"|nợ {_alt('bạn', 'anh', 'chị', 'ông', 'bà', 'quý khách')})"),
         (_negated, _clause_is_question)),
    # "Quý khách có một bảo hiểm chưa nhận": mồi của cuộc gọi tự động.
    Rule("FB-8", Indicator.FINANCIAL_BAIT, Severity.MEDIUM,
         _compile(rf"có {_gap(1)}{_alt('bảo hiểm', 'bưu phẩm', 'bưu kiện', 'khoản tiền', 'phần quà', 'gói hàng', 'kiện hàng')} "
                  rf"{_gap(2)}chưa nhận"), (_negated, _clause_is_question)),
    Rule("FB-9", Indicator.FINANCIAL_BAIT, Severity.MEDIUM, _compile(_GAMBLING), (_negated, _clause_is_question)),
    Rule("FB-7", Indicator.FINANCIAL_BAIT, Severity.MEDIUM,
         _compile(rf"khoản {_alt('hoàn lại', 'hoàn tiền', 'hoàn trả', 'bồi thường')} {_gap(3)}mà {_gap(1)}{_alt('bạn', 'anh', 'chị', 'ông', 'bà')} được"),
         (_negated, _clause_is_question)),

    # --- UNUSUAL_PAYMENT: cách trả tiền không truy lại được ---
    # Thẻ cào, thẻ quà tặng chỉ tính khi được dùng để trả tiền; "tặng thẻ quà tặng" là khuyến mãi bình thường.
    Rule("UP-1", Indicator.UNUSUAL_PAYMENT, Severity.MEDIUM,
         _compile(rf"(?P<verb>{_alt('mua', 'thanh toán', 'trả', 'nạp', 'chuyển', 'gửi', 'đọc mã', 'cào', 'bằng')}) "
                  rf"{_gap(6)}{_ODD_CARD}"), (_negated, _speaker_is_actor)),
    Rule("UP-2", Indicator.UNUSUAL_PAYMENT, Severity.MEDIUM, _compile(_ODD_CRYPTO), (_negated, _clause_is_question)),

    # --- CALL_HANDOFF: đưa thêm người vào cuộc gọi ---
    # Cuộc gọi tự động: "bấm phím sáu để được nhân viên hỗ trợ".
    Rule("CH-2", Indicator.CALL_HANDOFF, Severity.LOW,
         _compile(rf"{_alt('bấm phím', 'nhấn phím', 'ấn phím')} {_gap(2)}để {_gap(2)}{_alt('nhân viên', 'tổng đài viên', 'gặp')}"),
         ()),
    Rule("CH-1", Indicator.CALL_HANDOFF, Severity.LOW,
         _compile(rf"(?P<verb>{_HAND_OVER}) {_gap(2)}{_alt('cho', 'sang', 'với', 'tới', 'đến')} {_gap(4)}{_COLLEAGUE}"),
         (_negated,)),
)

_MAX_EVIDENCE = 3


@dataclass(frozen=True)
class Turn:
    """Một lượt lời trong hội thoại: ai nói và nói gì."""

    speaker: str
    text: str


@dataclass(frozen=True)
class SpeakerSummary:
    """Những dấu hiệu xuất phát từ lời của một người nói."""

    speaker: str
    turns: int
    indicators: list[Indicator]


@dataclass(frozen=True)
class ConversationAnalysis:
    """Kết quả phân tích một hội thoại có phân biệt người nói."""

    indicators: list[IndicatorMatch]
    # Theo thứ tự xuất hiện trong hội thoại; rỗng nếu không biết ai nói câu nào.
    speakers: list[SpeakerSummary]


# Nhãn người nói đứng đầu văn bản hoặc ngay sau dấu kết câu: "A: ...", "Người gọi: ...", "caller: ...".
_SPEAKER_LABEL = re.compile(r"(?:^|(?<=[.!?…\"”»)]\s)|(?<=\n))\s*([^\s:.!?,;][^:.!?,;\n]{0,24}?):\s")


def parse_turns(text: str) -> list[Turn] | None:
    """Tách văn bản có nhãn người nói thành các lượt lời; trả ``None`` nếu văn bản không có nhãn.

    Một cụm chỉ được coi là nhãn người nói khi nó lặp lại ít nhất hai lần, để "Lưu ý: ..." giữa câu
    không bị coi là một người nói. Người chỉ nói một lần (ví dụ người thứ ba chen vào một câu) vẫn
    được nhận nếu nhãn của họ có cùng dạng với các nhãn đã xác nhận.
    """
    candidates = [(m.start(), m.end(), " ".join(m.group(1).split())) for m in _SPEAKER_LABEL.finditer(text)]
    counts: dict[str, int] = {}
    for _, _, label in candidates:
        counts[label.casefold()] = counts.get(label.casefold(), 0) + 1
    confirmed = {label for label, count in counts.items() if count >= 2}
    if len(confirmed) < 2:
        return None
    max_length = max(len(label) for label in confirmed)
    max_words = max(len(label.split()) for label in confirmed)
    accepted = [
        candidate for candidate in candidates
        if candidate[2].casefold() in confirmed
        or (len(candidate[2]) <= max_length and len(candidate[2].split()) <= max_words)
    ]
    turns: list[Turn] = []
    for index, (_, end, label) in enumerate(accepted):
        stop = accepted[index + 1][0] if index + 1 < len(accepted) else len(text)
        content = text[end:stop].strip()
        if content:
            turns.append(Turn(speaker=label, text=content))
    return turns if len(turns) >= 2 else None


# Những dấu hiệu thể hiện người nói đang chủ động tác động lên người khác. Hối thúc, mồi nhử và chuyển máy
# không tính, vì nhân viên thật cũng nói "tôi chuyển máy cho chuyên viên".
_PRESSURE = {
    Indicator.OTP_REQUEST, Indicator.MONEY_TRANSFER, Indicator.BANK_IMPERSONATION, Indicator.ACCOUNT_LOCK_THREAT,
    Indicator.AUTHORITY_IMPERSONATION, Indicator.LEGAL_THREAT, Indicator.HARM_THREAT, Indicator.SECRECY_DEMAND,
    Indicator.REMOTE_ACCESS_REQUEST, Indicator.UNUSUAL_PAYMENT,
}


class _Hits:
    """Gom các lần khớp luật theo từng dấu hiệu."""

    def __init__(self) -> None:
        self._found: dict[Indicator, tuple[Severity, list[str], list[str]]] = {}

    def add(self, indicator: Indicator, severity: Severity, evidence: str, rule_id: str) -> None:
        current, snippets, rule_ids = self._found.get(indicator, (severity, [], []))
        if _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[current]:
            current = severity
        if evidence not in snippets and len(snippets) < _MAX_EVIDENCE:
            snippets.append(evidence)
        if rule_id not in rule_ids:
            rule_ids.append(rule_id)
        self._found[indicator] = (current, snippets, rule_ids)

    def merge(self, other: "_Hits") -> None:
        for indicator, (severity, snippets, rule_ids) in other._found.items():
            for snippet in snippets:
                self.add(indicator, severity, snippet, rule_ids[0])
            for rule_id in rule_ids[1:]:
                self.add(indicator, severity, snippets[0], rule_id)

    def codes(self) -> set[Indicator]:
        return set(self._found)

    def severity(self, indicator: Indicator) -> Severity:
        return self._found[indicator][0]

    def rule_ids(self, indicator: Indicator) -> list[str]:
        return self._found[indicator][2] if indicator in self._found else []

    def discard(self, indicator: Indicator) -> None:
        self._found.pop(indicator, None)

    def matches(self) -> list[IndicatorMatch]:
        """Mỗi dấu hiệu một mục, theo thứ tự cố định của ``Indicator``."""
        return [
            IndicatorMatch(code=indicator, severity=self._found[indicator][0], evidence=self._found[indicator][1],
                           rule_ids=self._found[indicator][2])
            for indicator in Indicator
            if indicator in self._found
        ]


# Các luật bảo người nghe thao tác trên thiết bị: cài ứng dụng, mở đường link, cấp quyền, mở trang web.
_DEVICE_INSTRUCTIONS = {"RA-2", "RA-3", "RA-4", "RA-5", "RA-9"}


def _escalate(hits: _Hits) -> None:
    """Nâng mức khi hai dấu hiệu yếu hơn cùng xuất hiện tạo thành một kịch bản rõ ràng.

    Tự gọi tới báo "máy của anh nhiễm vi-rút" (RA-8) rồi hướng dẫn thao tác trên máy là đúng kịch bản
    giả danh hỗ trợ kỹ thuật, dù chưa nói tới chữ "từ xa".
    """
    remote = set(hits.rule_ids(Indicator.REMOTE_ACCESS_REQUEST))
    if "RA-8" in remote and remote & _DEVICE_INSTRUCTIONS:
        hits.add(Indicator.REMOTE_ACCESS_REQUEST, Severity.HIGH, "infection alert followed by device instructions",
                 "RA-10")


# Mẫu do quản trị viên thêm luôn ở mức MEDIUM: đủ để góp điểm cùng các dấu hiệu khác, nhưng một mẫu nhập ẩu
# không thể tự đưa một cuộc gọi lên mức rủi ro cao.
CUSTOM_RULE_SEVERITY = Severity.MEDIUM
CUSTOM_RULE_PREFIX = "CUSTOM-"
_MIN_CUSTOM_WORDS = 2
_WORD = re.compile(r"\w+")


def custom_rule(pattern_id: str, indicator: Indicator, phrase: str) -> Rule:
    """Tạo một luật từ một cụm từ do quản trị viên nhập (bảng ``phishing_patterns`` của backend).

    Cụm từ được chuẩn hóa như transcript (chữ thường, bỏ dấu câu) rồi khớp nguyên cụm, đúng ranh giới từ. Lần
    khớp nằm sau từ phủ định ("đừng đọc mã otp cho ai") bị bỏ qua, như với các luật có sẵn. Khác với luật có sẵn,
    luật này không hiểu ngữ cảnh nào khác (ai nói, câu hỏi hay lời kể lại), nên mức nghiêm trọng của nó bị giới
    hạn ở ``CUSTOM_RULE_SEVERITY``.

    :raises ValueError: nếu cụm từ có ít hơn hai từ (một từ đơn lẻ khớp quá nhiều câu bình thường), hoặc dấu
        hiệu là ``COORDINATED_CALLERS`` (dấu hiệu đó suy ra từ số người nói, không từ câu chữ)
    """
    if indicator == Indicator.COORDINATED_CALLERS:
        raise ValueError("COORDINATED_CALLERS cannot be used for a custom pattern")
    # Đếm từ trên cụm đúng như người quản trị gõ (chuỗi chữ, số liền nhau), trước mọi bước sửa lỗi nhận dạng. Backend
    # đếm theo đúng cách này khi nhận mẫu, nên một mẫu backend đã nhận thì không bị từ chối ở đây.
    if len(_WORD.findall(unicodedata.normalize("NFC", phrase))) < _MIN_CUSTOM_WORDS:
        raise ValueError(f"a custom pattern needs at least {_MIN_CUSTOM_WORDS} words")
    words = [word for word in normalize(phrase).split() if set(word) != {"|"}]
    return Rule(
        rule_id=f"{CUSTOM_RULE_PREFIX}{pattern_id}", indicator=indicator, severity=CUSTOM_RULE_SEVERITY,
        pattern=re.compile(r"(?<!\S)" + re.escape(" ".join(words)) + r"(?!\S)"), exclusions=(_negated,),
    )


class RuleEngine:
    """Chạy toàn bộ bộ luật trên một transcript hoặc một hội thoại có phân biệt người nói."""

    version = RULESET_VERSION

    def analyze(self, text: str, extra_rules: Sequence[Rule] = ()) -> list[IndicatorMatch]:
        """Trả về các dấu hiệu tìm thấy, mỗi dấu hiệu một mục, theo thứ tự cố định của ``Indicator``.

        Nếu văn bản có nhãn người nói ("A: ... B: ...") thì nó được phân tích như một hội thoại. Mức
        nghiêm trọng của một dấu hiệu là mức cao nhất trong các luật đã khớp. Văn bản rỗng hoặc không
        có dấu hiệu nào cho danh sách rỗng.

        ``extra_rules`` là các luật bổ sung cho riêng lần gọi này (mẫu do quản trị viên quản lý, tạo bằng
        ``custom_rule``); chúng được chạy cùng bộ luật có sẵn và ghi mã luật dạng ``CUSTOM-...``.
        """
        return self.analyze_text(text, extra_rules).indicators

    def analyze_text(self, text: str, extra_rules: Sequence[Rule] = ()) -> ConversationAnalysis:
        """Như ``analyze`` nhưng trả thêm phần tổng hợp theo từng người nói khi văn bản có nhãn người nói."""
        turns = parse_turns(text)
        if turns is not None:
            return self.analyze_conversation(turns, extra_rules)
        hits = self._scan(text, extra_rules)
        _escalate(hits)
        return ConversationAnalysis(indicators=hits.matches(), speakers=[])

    def analyze_conversation(self, turns: list[Turn], extra_rules: Sequence[Rule] = ()) -> ConversationAnalysis:
        """Phân tích hội thoại theo từng lượt lời, dùng được cho hai người hoặc nhiều người nói.

        Mỗi lượt lời được xét riêng, nên lời của người này không bị ghép với lời của người khác thành
        một yêu cầu, và mỗi dấu hiệu được gán cho đúng người đã nói ra nó. Khi từ hai người trở lên
        cùng gây áp lực (ví dụ một người xưng ngân hàng rồi chuyển máy cho người xưng công an đòi
        chuyển tiền), hội thoại có thêm dấu hiệu ``COORDINATED_CALLERS``.
        """
        by_speaker: dict[str, _Hits] = {}
        turn_counts: dict[str, int] = {}
        for turn in turns:
            by_speaker.setdefault(turn.speaker, _Hits()).merge(self._scan(turn.text, extra_rules))
            turn_counts[turn.speaker] = turn_counts.get(turn.speaker, 0) + 1

        # Người chỉ hỏi số tài khoản, trong khi người khác là bên đòi tiền, chính là người sắp trả tiền:
        # câu hỏi đó không phải là moi thông tin.
        demanding = {speaker for speaker, hits in by_speaker.items() if Indicator.MONEY_TRANSFER in hits.codes()}
        for speaker, hits in by_speaker.items():
            if hits.rule_ids(Indicator.SENSITIVE_INFORMATION) == ["SI-3"] and demanding - {speaker}:
                hits.discard(Indicator.SENSITIVE_INFORMATION)

        total = _Hits()
        for hits in by_speaker.values():
            total.merge(hits)
        _escalate(total)

        pressing = [
            speaker for speaker, hits in by_speaker.items()
            if hits.codes() & _PRESSURE
            or (Indicator.SENSITIVE_INFORMATION in hits.codes()
                and hits.severity(Indicator.SENSITIVE_INFORMATION) != Severity.LOW)
        ]
        if len(pressing) >= 2:
            total.add(Indicator.COORDINATED_CALLERS, Severity.MEDIUM,
                      "speakers: " + ", ".join(pressing), "CC-1")

        speakers = [
            SpeakerSummary(speaker=speaker, turns=turn_counts[speaker],
                           indicators=[i for i in Indicator if i in hits.codes()])
            for speaker, hits in by_speaker.items()
        ]
        return ConversationAnalysis(indicators=total.matches(), speakers=speakers)

    @staticmethod
    def _scan(text: str, extra_rules: Sequence[Rule] = ()) -> _Hits:
        """Chạy mọi luật trên một đoạn văn bản của một người nói (hoặc transcript không rõ người nói)."""
        normalized = normalize(text)
        hits = _Hits()
        for rule in (*RULES, *extra_rules):
            for match in rule.pattern.finditer(normalized):
                if any(excluded(normalized, match) for excluded in rule.exclusions):
                    continue
                hits.add(rule.indicator, rule.severity, match.group(0), rule.rule_id)
        return hits
