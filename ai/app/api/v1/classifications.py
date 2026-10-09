"""API của NLP Model: phân loại một transcript là bình thường hay lừa đảo."""

from fastapi import APIRouter, Request

from app.errors import ApiError
from app.schemas import ClassificationRequest, ClassificationResponse

router = APIRouter(tags=["Classifications"])


@router.post("/classifications")
def classify(request: Request, body: ClassificationRequest) -> ClassificationResponse:
    """Chạy model đã fine-tune trên transcript và trả về xác suất lừa đảo.

    Nếu chưa có artifact của model thì trả lỗi 503; service không bao giờ trả một kết quả thay thế.
    Hàm khai báo đồng bộ (``def``) để FastAPI chạy nó trong luồng riêng, vì suy luận tốn CPU.
    """
    classifier = request.app.state.nlp
    if classifier is None:
        raise ApiError(503, "NLP_MODEL_UNAVAILABLE", "The NLP model is not available.")
    prediction = classifier.predict(body.text)
    return ClassificationResponse(
        label=prediction.label,
        phishing_probability=round(prediction.phishing_probability, 6),
        chunk_count=len(prediction.chunk_probabilities),
        chunk_probabilities=[round(value, 6) for value in prediction.chunk_probabilities],
        model_version=classifier.config["version"],
    )
