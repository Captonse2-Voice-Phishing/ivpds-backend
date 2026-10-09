"""Risk Engine: ghép kết quả của Rule Engine và NLP Model thành một điểm rủi ro 0-100 và một mức rủi ro.

Theo README, điểm cuối gồm ba thành phần cộng lại:

    Rule Score + Model Probability + Indicator Severity = Final Risk Score

* **Model Probability** (0 đến ``MODEL_WEIGHT`` điểm): xác suất lừa đảo do NLP Model tính, nhân với trọng số.
* **Rule Score** (0 đến ``RULE_SCORE_CAP`` điểm): Rule Engine tìm thấy bao nhiêu dấu hiệu và loại gì; mỗi dấu hiệu
  cộng điểm theo mức nghiêm trọng của nó. Tổ hợp "giả danh + đòi hỏi" (tự xưng ngân hàng hoặc cơ quan nhà nước,
  rồi đòi thông tin, mã, tiền hoặc cài ứng dụng) được cộng thêm ``PATTERN_BONUS``.
* **Indicator Severity** (0 đến 20 điểm): mức nghiêm trọng của dấu hiệu nặng nhất.

Ba con số này khác nhau và không thay thế cho nhau: xác suất của model không phải điểm rủi ro, và điểm rủi ro
không phải độ tin cậy (``confidence``).

Vì sao trọng số được chọn như vậy (số liệu đo trên tập validation, xem ``training/README.md``):

* NLP Model một mình đủ để lên mức HIGH. Một nửa số cuộc gọi lừa đảo thật trong bộ test không có dấu hiệu nào
  từ Rule Engine, nên nếu bắt buộc phải có cả hai thì các cuộc đó bị hạ mức.
* Rule Engine một mình chỉ lên tới MEDIUM. Luật khớp theo cụm từ nên cũng khớp cả lời kể lại ("có người đòi
  con đọc mã OTP"); khi model không đồng ý thì kết quả là "đáng ngờ", không phải "lừa đảo".
* Một dấu hiệu mức MEDIUM hay LOW đứng riêng, model không đồng ý, thì vẫn là LOW: các dấu hiệu này xuất hiện
  thường xuyên trong cuộc gọi bình thường.
* Tổ hợp "giả danh + đòi hỏi" đủ để lên MEDIUM dù từng dấu hiệu chỉ ở mức LOW. Trong tập validation, tổ hợp này
  có ở 232 cuộc lừa đảo và không có ở cuộc bình thường nào.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.rules import Indicator, IndicatorMatch, Severity

RISK_ENGINE_VERSION = "2026.10.1"

# Điểm tối đa của thành phần Model Probability. Lớn hơn ngưỡng HIGH để model rất chắc chắn thì tự lên HIGH.
MODEL_WEIGHT = 70.0
# Điểm cộng cho mỗi dấu hiệu theo mức nghiêm trọng, và trần của tổng (Rule Score).
INDICATOR_POINTS = {Severity.LOW: 3.0, Severity.MEDIUM: 8.0, Severity.HIGH: 15.0}
RULE_SCORE_CAP = 35.0
# Tổ hợp "giả danh + đòi hỏi": người gọi tự xưng là một tổ chức rồi đòi thứ gì đó.
PATTERN_BONUS = 25.0
_IMPERSONATION = {Indicator.BANK_IMPERSONATION, Indicator.AUTHORITY_IMPERSONATION}
_REQUEST = {Indicator.SENSITIVE_INFORMATION, Indicator.OTP_REQUEST, Indicator.MONEY_TRANSFER,
            Indicator.REMOTE_ACCESS_REQUEST, Indicator.UNUSUAL_PAYMENT}
# Điểm của thành phần Indicator Severity, theo dấu hiệu nặng nhất.
SEVERITY_POINTS = {Severity.LOW: 3.0, Severity.MEDIUM: 8.0, Severity.HIGH: 20.0}
# Ngưỡng ban đầu theo README: 0-29 LOW, 30-59 MEDIUM, 60-100 HIGH.
MEDIUM_THRESHOLD = 30
HIGH_THRESHOLD = 60

_SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


class RiskLevel(StrEnum):
    """Mức rủi ro cuối cùng của một cuộc gọi."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class RiskAssessment:
    """Kết quả của Risk Engine, kèm từng thành phần để giải thích được điểm số."""

    # Điểm rủi ro cuối cùng, số nguyên từ 0 đến 100.
    risk_score: int
    risk_level: RiskLevel
    # Mức chắc chắn của kết quả, từ 0 đến 1 (xem ``_confidence``). Không phải xác suất lừa đảo.
    confidence: float
    # Ba thành phần đã cộng lại thành điểm cuối (trước khi cắt ở 100).
    model_points: float
    rule_score: float
    severity_points: float
    # Xác suất model đưa vào, và mức nghiêm trọng cao nhất trong các dấu hiệu (None nếu không có dấu hiệu).
    model_probability: float
    highest_severity: Severity | None


def level_of(score: int) -> RiskLevel:
    """Đổi điểm rủi ro thành mức rủi ro theo hai ngưỡng."""
    if score >= HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if score >= MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _confidence(model_probability: float, rule_points: float) -> float:
    """Mức chắc chắn của kết quả: cao khi model dứt khoát và Rule Engine không nói ngược lại.

    Gồm hai nửa, mỗi nửa tối đa 0.5:

    * Model dứt khoát đến đâu: ``|2p - 1|`` (p = 0.5 là không biết, p = 0 hoặc 1 là dứt khoát).
    * Rule Engine ủng hộ model đến đâu. Luật có ba trạng thái: "đáng ngờ" (riêng điểm của luật đã đủ mức MEDIUM),
      "sạch" (không có dấu hiệu nào), và "yếu" (có dấu hiệu nhưng chưa đủ MEDIUM).

      ================  =========  ======  ======
      Model / Luật      đáng ngờ   yếu     sạch
      ================  =========  ======  ======
      lừa đảo (p>=0.5)  1.0        0.75    0.5
      bình thường       0.0        0.75    1.0
      ================  =========  ======  ======

      Model báo lừa đảo mà luật không thấy gì thì vẫn được 0.5: luật bỏ sót nhiều cuộc gọi lừa đảo thật nên sự im
      lặng của luật không phải bằng chứng ngược lại. Model báo bình thường mà luật thấy đáng ngờ thì được 0.
    """
    decisiveness = abs(2.0 * model_probability - 1.0)
    says_scam = model_probability >= 0.5
    if rule_points >= MEDIUM_THRESHOLD:
        support = 1.0 if says_scam else 0.0
    elif rule_points == 0:
        support = 0.5 if says_scam else 1.0
    else:
        support = 0.75
    return round(0.5 * decisiveness + 0.5 * support, 2)


def assess(indicators: list[IndicatorMatch], model_probability: float) -> RiskAssessment:
    """Tính điểm và mức rủi ro từ các dấu hiệu của Rule Engine và xác suất của NLP Model.

    :param indicators: các dấu hiệu Rule Engine tìm thấy (có thể rỗng)
    :param model_probability: xác suất lừa đảo do NLP Model tính, từ 0 đến 1
    :raises ValueError: nếu xác suất nằm ngoài khoảng 0 đến 1
    """
    if not 0.0 <= model_probability <= 1.0:
        raise ValueError("model_probability must be between 0 and 1")

    model_points = MODEL_WEIGHT * model_probability
    codes = {match.code for match in indicators}
    pattern = PATTERN_BONUS if codes & _IMPERSONATION and codes & _REQUEST else 0.0
    rule_score = min(RULE_SCORE_CAP, sum(INDICATOR_POINTS[match.severity] for match in indicators) + pattern)
    highest = max((match.severity for match in indicators), key=_SEVERITY_ORDER.__getitem__, default=None)
    severity_points = SEVERITY_POINTS[highest] if highest is not None else 0.0

    score = int(round(min(100.0, model_points + rule_score + severity_points)))
    return RiskAssessment(
        risk_score=score,
        risk_level=level_of(score),
        confidence=_confidence(model_probability, rule_score + severity_points),
        model_points=round(model_points, 2),
        rule_score=round(rule_score, 2),
        severity_points=round(severity_points, 2),
        model_probability=model_probability,
        highest_severity=highest,
    )
