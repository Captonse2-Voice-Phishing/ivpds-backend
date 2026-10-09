"""Phần dùng chung của các bước huấn luyện: đọc dữ liệu đã chia, tính chỉ số đánh giá."""

import json
from pathlib import Path

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

DATA = Path("data/processed")
MODELS = Path("models")
REPORTS = Path("training/reports")
SEED = 20261009
# Tập validation tổng hợp quá dễ (baseline đạt 100%) nên không phân biệt được các model. Việc chọn model dựa
# trên ``validation_vi_context``: 100 hội thoại Việt Nam viết tay, khác nguồn với dữ liệu huấn luyện.
SELECTION_SET = "validation_vi_context"
EVALUATION_SETS = ("validation", "validation_vi_context", "test", "test_vi_context", "test_real_calls")


def load_selection() -> list[dict]:
    """Các mẫu dùng để chọn model: hội thoại Việt Nam viết tay cộng với lời nói thường ngày thật của tập validation.

    Phần lời nói thật được thêm vào sau khi phép thử cho thấy model báo nhầm rất nhiều trên tiếng Việt thật:
    một model chỉ giỏi trên dữ liệu tự viết không nên được chọn.
    """
    validation = load("validation")
    real_normal = [row for row in validation if row["source"] == "vlsp_ordinary_speech"]
    # Đoạn ngắn của các kịch bản model chưa từng thấy: để model bỏ sót câu lừa đảo ngắn không còn được chọn.
    short = [row for row in validation if row.get("short")]
    return load(SELECTION_SET) + real_normal + short


def load(split: str) -> list[dict]:
    """Đọc một tập dữ liệu. Văn bản đưa vào model là ``text_plain`` (không có nhãn người nói)."""
    path = DATA / f"{split}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metrics(labels: list[int], predictions: list[int]) -> dict:
    """Precision, recall, F1 từng lớp, macro F1 và ma trận nhầm lẫn, tính bằng ``sklearn.metrics`` (theo README).

    Chỉ số của một lớp là ``None`` khi tập không có mẫu nào thuộc lớp đó (ví dụ tập cuộc gọi thật chỉ có lừa đảo).
    """
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel().tolist()
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=[0, 1], zero_division=0,
    )

    def per_class(index: int) -> dict:
        """Chỉ số của một lớp; ``None`` nếu lớp đó không có trong tập."""
        if support[index] == 0:
            return {"precision": None, "recall": None, "f1": None}
        return {"precision": round(float(precision[index]), 4), "recall": round(float(recall[index]), 4),
                "f1": round(float(f1[index]), 4)}

    normal, phishing = per_class(0), per_class(1)
    both = [value for value in (phishing["f1"], normal["f1"]) if value is not None]
    return {
        "samples": len(labels),
        "accuracy": round((tp + tn) / len(labels), 4) if labels else None,
        "phishing": phishing,
        "normal": normal,
        # Macro F1 chỉ có nghĩa khi tập có cả hai lớp.
        "macro_f1": round(sum(both) / 2, 4) if len(both) == 2 else None,
        "confusion_matrix": {"true_normal_pred_normal": tn, "true_normal_pred_phishing": fp,
                             "true_phishing_pred_normal": fn, "true_phishing_pred_phishing": tp},
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate(rows: list[dict], probabilities: list[float], threshold: float) -> dict:
    """Chỉ số trên toàn tập và tách theo nguồn dữ liệu."""
    labels = [row["label"] for row in rows]
    predictions = [int(probability >= threshold) for probability in probabilities]
    result = {"all": metrics(labels, predictions), "by_source": {}}
    for source in sorted({row["source"] for row in rows}):
        index = [i for i, row in enumerate(rows) if row["source"] == source]
        result["by_source"][source] = metrics([labels[i] for i in index], [predictions[i] for i in index])
    return result
