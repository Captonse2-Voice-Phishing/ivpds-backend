"""Đánh giá một artifact đã fine-tune bằng đúng đoạn code mà API dùng để phục vụ (``app.nlp.TextClassifier``).

Chạy (từ thư mục ``ai``):

    docker run --rm --gpus all -v "D:/Capstone2/ai:/work" -w /work ivpds/train:dev \
        python -m training.evaluate --name xlmr-base

Ghi ``training/reports/<tên>/metrics.json`` (chỉ có con số, được đưa vào git) và ``errors.jsonl`` (các mẫu bị
phân loại sai kèm trích đoạn văn bản, để phân tích lỗi; không vào git vì có thể chứa nội dung từ YouTube).
"""

import argparse
import json
import sys
import time

import torch

from app.nlp import TextClassifier
from training.common import EVALUATION_SETS, MODELS, REPORTS, evaluate, load


def main() -> int:
    """Nạp artifact, chấm trên từng tập đánh giá, ghi chỉ số và danh sách các mẫu bị phân loại sai."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    classifier = TextClassifier(MODELS / args.name, device=device)
    threshold = classifier.config["threshold"]
    log = json.loads((MODELS / args.name / "training_log.json").read_text(encoding="utf-8"))
    report = {
        "name": args.name, "kind": "transformer", "version": classifier.config["version"],
        "base_model": classifier.config["base_model"], "aggregation": classifier.config["aggregation"],
        "threshold": threshold, "max_length": classifier.config["max_length"],
        "training_seconds": log["training_seconds"], "hardware": log["hardware"],
        "best_checkpoint": log["best_checkpoint"], "evaluated_on": device, "results": {},
    }
    errors = []
    for split in EVALUATION_SETS:
        rows = load(split)
        started = time.perf_counter()
        predictions = [classifier.predict(row["text_plain"]) for row in rows]
        seconds = time.perf_counter() - started
        probabilities = [prediction.phishing_probability for prediction in predictions]
        report["results"][split] = evaluate(rows, probabilities, threshold)
        report["results"][split]["seconds_per_document"] = round(seconds / len(rows), 4)
        if split == "test_real_calls":
            # Cùng các cuộc gọi đó nhưng dùng nguyên văn PhoWhisper, đúng như hệ thống nhận được khi chạy thật.
            raw = [classifier.predict(row["text_asr"]).phishing_probability for row in rows]
            report["results"]["test_real_calls_raw_asr"] = evaluate(rows, raw, threshold)
        for row, prediction in zip(rows, predictions):
            if (prediction.phishing_probability >= threshold) != bool(row["label"]):
                errors.append({
                    "split": split, "id": row["id"], "source": row["source"], "type": row["type"],
                    "expected": row["label_name"], "predicted": prediction.label,
                    "phishing_probability": round(prediction.phishing_probability, 4),
                    "chunks": len(prediction.chunk_probabilities), "words": len(row["text_plain"].split()),
                    "excerpt": row["text_plain"][:600],
                })
    out = REPORTS / args.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "errors.jsonl").write_bytes("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in errors).encode("utf-8"))
    for split, result in report["results"].items():
        summary = result["all"]
        print(f"{split:24} n={summary['samples']:4} P={summary['phishing']['precision']} R={summary['phishing']['recall']} "
              f"F1={summary['phishing']['f1']} macroF1={summary['macro_f1']} FP={summary['false_positives']} "
              f"FN={summary['false_negatives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
