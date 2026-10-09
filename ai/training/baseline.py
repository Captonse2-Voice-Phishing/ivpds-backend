"""Baseline: TF-IDF + Logistic Regression (scikit-learn).

Chạy (từ thư mục ``ai``, không cần GPU):

    docker run --rm -v "D:/Capstone2/ai:/work" -w /work ivpds/train:dev python -m training.baseline

Baseline cho biết bài toán khó tới đâu trước khi dùng Transformer: nếu một model đếm từ đã đạt điểm rất cao
trên tập test thì tập test đó dễ, và điểm cao của Transformer trên cùng tập không chứng minh được nhiều.
"""

import json
import sys
import time

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from app.nlp import normalize_for_model
from training.common import EVALUATION_SETS, MODELS, REPORTS, SELECTION_SET, SEED, evaluate, load, load_selection

# Tên thư mục kết quả; truyền tên khác trên dòng lệnh để giữ lại kết quả của lần huấn luyện trước.
NAME = sys.argv[1] if len(sys.argv) > 1 else "baseline-tfidf-logreg"
C_VALUES = (0.1, 1.0, 10.0)


def build(c: float) -> Pipeline:
    """Đặc trưng từ (1-2 từ) và ký tự (2-5 ký tự, chịu lỗi chính tả tốt hơn) đưa vào hồi quy logistic."""
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("classifier", LogisticRegression(C=c, max_iter=2000, random_state=SEED))])


def texts(rows: list[dict]) -> list[str]:
    """Lấy văn bản của từng mẫu và chuẩn hóa giống hệt lúc chạy thật (chữ thường, không dấu câu)."""
    return [normalize_for_model(row["text_plain"]) for row in rows]


def main() -> int:
    """Huấn luyện baseline với vài mức điều chuẩn C, giữ mức tốt nhất trên tập chọn model, rồi chấm trên mọi tập.

    Lưu model vào ``models/baseline-tfidf-logreg/`` và các chỉ số vào ``training/reports/``.
    """
    started = time.perf_counter()
    train, validation = load("train"), load_selection()
    tried = {}
    best = None
    for c in C_VALUES:
        model = build(c).fit(texts(train), [row["label"] for row in train])
        score = evaluate(validation, model.predict_proba(texts(validation))[:, 1].tolist(), 0.5)["all"]["macro_f1"]
        tried[str(c)] = score
        if best is None or score > best[0]:
            best = (score, c, model)
    _, c, model = best

    out = MODELS / NAME
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    report = {
        "name": NAME, "kind": "baseline", "seed": SEED, "selected_C": c, "selection_set": SELECTION_SET, "selection_macro_f1_by_C": tried,
        "train_samples": len(train), "training_seconds": round(time.perf_counter() - started, 1),
        "hardware": "CPU", "threshold": 0.5, "results": {},
    }
    for split in EVALUATION_SETS:
        rows = load(split)
        report["results"][split] = evaluate(rows, model.predict_proba(texts(rows))[:, 1].tolist(), 0.5)
    (REPORTS / NAME).mkdir(parents=True, exist_ok=True)
    (REPORTS / NAME / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for split in EVALUATION_SETS:
        summary = report["results"][split]["all"]
        print(f"{split:16} n={summary['samples']:4} P={summary['phishing']['precision']} R={summary['phishing']['recall']} "
              f"F1={summary['phishing']['f1']} macroF1={summary['macro_f1']} FP={summary['false_positives']} "
              f"FN={summary['false_negatives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
