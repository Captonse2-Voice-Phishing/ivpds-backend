"""API của Risk Engine: đánh giá rủi ro lừa đảo của một transcript hoặc một hội thoại."""

from fastapi import APIRouter, Request

from app.errors import ApiError
from app.risk import RISK_ENGINE_VERSION, assess
from app.rules import Turn
from app.schemas import IndicatorResult, RiskAssessmentRequest, RiskAssessmentResponse, RiskComponents

router = APIRouter(tags=["Risk assessments"])


@router.post("/risk-assessments")
def assess_risk(request: Request, body: RiskAssessmentRequest) -> RiskAssessmentResponse:
    """Chạy Rule Engine và NLP Model trên cùng một nội dung rồi ghép thành điểm và mức rủi ro.

    Nếu NLP Model chưa nạp được thì trả lỗi 503. Service không tính điểm chỉ từ Rule Engine rồi coi đó là kết
    quả đầy đủ, vì như vậy mức rủi ro sẽ sai lệch mà bên gọi không biết.
    Hàm khai báo đồng bộ (``def``) để FastAPI chạy nó trong luồng riêng, vì suy luận tốn CPU.
    """
    classifier = request.app.state.nlp
    if classifier is None:
        raise ApiError(503, "NLP_MODEL_UNAVAILABLE", "The NLP model is not available.")
    engine = request.app.state.rules
    if body.turns is not None:
        analysis = engine.analyze_conversation([Turn(speaker=t.speaker.strip(), text=t.text) for t in body.turns])
        # Model được huấn luyện trên transcript liền, không có nhãn người nói.
        text = " ".join(turn.text for turn in body.turns)
    else:
        analysis = engine.analyze_text(body.text)
        text = body.text
    prediction = classifier.predict(text)
    result = assess(analysis.indicators, prediction.phishing_probability)
    return RiskAssessmentResponse(
        risk_score=result.risk_score,
        risk_level=result.risk_level.value,
        confidence=result.confidence,
        indicators=[match.code.value for match in analysis.indicators],
        indicator_details=[
            IndicatorResult(code=m.code.value, severity=m.severity.value, evidence=m.evidence, rule_ids=m.rule_ids)
            for m in analysis.indicators
        ],
        components=RiskComponents(
            model_probability=round(result.model_probability, 6),
            model_points=result.model_points,
            rule_score=result.rule_score,
            highest_severity=result.highest_severity.value if result.highest_severity else None,
            severity_points=result.severity_points,
        ),
        model_version=classifier.config["version"],
        ruleset_version=engine.version,
        risk_engine_version=RISK_ENGINE_VERSION,
    )
