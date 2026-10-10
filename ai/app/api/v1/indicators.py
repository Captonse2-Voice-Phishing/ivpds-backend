"""API của Rule Engine: tìm dấu hiệu lừa đảo trong một đoạn văn bản."""

from fastapi import APIRouter, Request

from app.rules import Turn
from app.schemas import IndicatorRequest, IndicatorResponse, IndicatorResult, SpeakerResult

router = APIRouter(tags=["Indicators"])


@router.post("/indicators")
def find_indicators(request: Request, body: IndicatorRequest) -> IndicatorResponse:
    """Chạy bộ luật trên văn bản hoặc hội thoại và trả về các dấu hiệu tìm thấy kèm bằng chứng.

    Khi biết ai nói câu nào (gửi ``turns``, hoặc ``text`` có nhãn người nói), kết quả có thêm phần
    tổng hợp theo từng người nói. Nội dung rỗng hoặc không có dấu hiệu nào cho danh sách rỗng, không phải lỗi.
    """
    engine = request.app.state.rules
    extra_rules = body.extra_rules()
    if body.turns is not None:
        analysis = engine.analyze_conversation([Turn(speaker=t.speaker.strip(), text=t.text) for t in body.turns],
                                               extra_rules)
    else:
        analysis = engine.analyze_text(body.text, extra_rules)
    return IndicatorResponse(
        indicators=[
            IndicatorResult(code=m.code.value, severity=m.severity.value, evidence=m.evidence, rule_ids=m.rule_ids)
            for m in analysis.indicators
        ],
        ruleset_version=engine.version,
        speakers=[
            SpeakerResult(speaker=s.speaker, turns=s.turns, indicators=[i.value for i in s.indicators])
            for s in analysis.speakers
        ],
        speaker_count=len(analysis.speakers),
    )
