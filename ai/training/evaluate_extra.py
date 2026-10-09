"""Chấm các model đã huấn luyện và Rule Engine trên một bộ mẫu test bổ sung (chưa từng dùng để huấn luyện).

Chạy (từ thư mục ``ai``):

    docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -w /work ivpds/train:dev \
        python -m training.evaluate_extra data/extra_tests/<tên>.jsonl

Mỗi dòng của file là ``{"id", "label" (1 lừa đảo / 0 bình thường), "text", "group"}``. Kết quả được in ra và ghi
vào ``training/reports/extra/<tên>.json`` (chỉ có con số). Các mẫu model đang triển khai đoán sai được ghi vào
``training/reports/extra/<tên>.errors.jsonl`` (không vào git).
"""

import json
import sys
from pathlib import Path

import joblib
import torch

from app.nlp import TextClassifier, normalize_for_model
from app.rules import RuleEngine, Severity
from training.common import MODELS, REPORTS, metrics

# Hậu tố của đợt huấn luyện cần chấm, ví dụ "-r2"; bỏ trống là đợt đầu. Truyền làm tham số thứ hai.
ROUND = sys.argv[2] if len(sys.argv) > 2 else ""
TRANSFORMERS = tuple(name + ROUND for name in ("phobert-base", "e5-small", "xlmr-base")) if ROUND else (
    "e5-small", "phobert-base-v2", "xlmr-base")
# Đợt nào không huấn luyện đủ cả ba model thì chỉ chấm những model có artifact.
TRANSFORMERS = tuple(name for name in TRANSFORMERS if (MODELS / name).is_dir())
BASELINE = "baseline-tfidf-logreg" + ROUND
DEPLOYED = TRANSFORMERS[0]


def rule_engine_flags(text: str, engine: RuleEngine) -> bool:
    """Cách đọc tạm thời kết quả Rule Engine: một dấu hiệu HIGH, hoặc từ hai dấu hiệu với một cái từ MEDIUM."""
    matches = engine.analyze(text)
    high = any(match.severity == Severity.HIGH for match in matches)
    strong = any(match.severity != Severity.LOW for match in matches)
    return high or (strong and len(matches) >= 2)


def main(path: str) -> int:
    """Chấm từng model trên file mẫu, in bảng theo nhóm và ghi báo cáo."""
    source = Path(path)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = [row["label"] for row in rows]
    texts = [row["text"] for row in rows]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    predictions: dict[str, list[int]] = {}
    probabilities: dict[str, list[float]] = {}

    engine = RuleEngine()
    predictions["rule-engine"] = [int(rule_engine_flags(text, engine)) for text in texts]

    baseline = joblib.load(MODELS / BASELINE / "model.joblib")
    scores = baseline.predict_proba([normalize_for_model(text) for text in texts])[:, 1].tolist()
    predictions[BASELINE] = [int(score >= 0.5) for score in scores]

    for name in TRANSFORMERS:
        classifier = TextClassifier(MODELS / name, device=device)
        scores = [classifier.predict(text).phishing_probability for text in texts]
        probabilities[name] = scores
        predictions[name] = [int(score >= classifier.config["threshold"]) for score in scores]
        del classifier
        if device == "cuda":
            torch.cuda.empty_cache()

    groups = sorted({row.get("group", "") for row in rows})
    report = {"file": source.name, "samples": len(rows), "phishing": sum(labels), "normal": len(labels) - sum(labels),
              "deployed_model": DEPLOYED, "results": {}}
    for name, predicted in predictions.items():
        report["results"][name] = {
            "all": metrics(labels, predicted),
            "by_group": {
                group: {"samples": len(index), "flagged_as_phishing": sum(predicted[i] for i in index),
                        "label": "PHISHING" if labels[index[0]] else "NORMAL"}
                for group in groups
                for index in [[i for i, row in enumerate(rows) if row.get("group", "") == group]]
            },
        }
    out = REPORTS / "extra"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{source.stem}{ROUND}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = [
        {"id": row["id"], "group": row.get("group"), "expected": "PHISHING" if row["label"] else "NORMAL",
         "phishing_probability": round(probabilities[DEPLOYED][i], 4), "words": len(row["text"].split()),
         "excerpt": row["text"][:500]}
        for i, row in enumerate(rows) if predictions[DEPLOYED][i] != row["label"]
    ]
    (out / f"{source.stem}{ROUND}.errors.jsonl").write_bytes(
        "".join(json.dumps(error, ensure_ascii=False) + "\n" for error in errors).encode("utf-8"))

    print(f"{source.name}: {len(rows)} samples ({sum(labels)} phishing, {len(labels) - sum(labels)} normal)")
    for name, result in report["results"].items():
        summary = result["all"]
        print(f"  {name:22} P={summary['phishing']['precision']} R={summary['phishing']['recall']} "
              f"F1={summary['phishing']['f1']} acc={summary['accuracy']} FP={summary['false_positives']} "
              f"FN={summary['false_negatives']}")
    print("  by group (flagged as phishing / samples):")
    for group in groups:
        cells = [f"{name.split('-')[0]}={result['by_group'][group]['flagged_as_phishing']}"
                 for name, result in report["results"].items()]
        first = report["results"]["rule-engine"]["by_group"][group]
        print(f"    {group[:34]:34} {first['label']:8} n={first['samples']:4}  " + "  ".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
