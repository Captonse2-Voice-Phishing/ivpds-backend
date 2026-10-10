"""Ghi lại hai tín hiệu đầu vào của Risk Engine cho từng cuộc gọi trong các bộ validation và test.

Cách dùng (chạy từ thư mục ``ai`` trong image huấn luyện, có GPU thì nhanh hơn):

    docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -w /work \
        ivpds/train:dev python -m tools.risk_signals_dump phobert-base-r6

Với mỗi dòng, script chạy NLP Model và Rule Engine trên cùng một transcript liền (không có nhãn người nói, giống
transcript Whisper trả về) rồi ghi xác suất của model và danh sách dấu hiệu vào ``data/risk/signals.jsonl``.
File này dùng để chọn trọng số và đánh giá Risk Engine mà không phải chạy lại model mỗi lần đổi công thức.
"""

import json
import sys
from pathlib import Path

from app.nlp import TextClassifier
from app.rules import RuleEngine

OUT = Path("data/risk/signals.jsonl")
# Tập dùng để CHỌN trọng số (tuning) và tập chỉ dùng để BÁO CÁO kết quả (report).
SETS = {
    "tuning": ["data/processed/validation.jsonl", "data/processed/validation_vi_context.jsonl"],
    "report": ["data/processed/test.jsonl", "data/processed/test_vi_context.jsonl",
               "data/extra_tests/real_calls.jsonl", "data/extra_tests/everyday_calls.jsonl",
               "data/extra_tests/short_sentences.jsonl", "data/extra_tests/short_requests.jsonl",
               "data/extra_tests/context_pairs.jsonl", "data/extra_tests/translated_calls.jsonl"],
    # Bộ test làm sau khi đã chốt công thức Risk Engine. ``generated_test_calls`` đã chuyển sang huấn luyện từ đợt 6
    # nên không còn ở đây; thay vào đó là phần giữ lại của bộ viết tay và 38 hội thoại của kho data_scam/gendata.
    "final": ["data/extra_tests/handwritten_holdout.jsonl", "data/extra_tests/user_gendata.jsonl",
              "data/extra_tests/translated_calls_rest.jsonl"],
}


def main(model_name: str) -> int:
    """Chạy model và bộ luật trên từng dòng, ghi kết quả ra file."""
    model = TextClassifier(f"models/{model_name}", device="cuda" if _has_cuda() else "cpu")
    engine = RuleEngine()
    lines = []
    for role, paths in SETS.items():
        for path in paths:
            if not Path(path).is_file():
                print(f"{path}: missing, skipped", flush=True)
                continue
            rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in rows:
                text = row.get("text_plain") or row["text"]
                prediction = model.predict(text)
                lines.append(json.dumps({
                    "role": role, "set": Path(path).stem, "id": row["id"], "label": row["label"],
                    "group": row.get("group") or row.get("type") or "", "words": len(text.split()),
                    "probability": round(prediction.phishing_probability, 6),
                    "indicators": [[m.code.value, m.severity.value] for m in engine.analyze(text)],
                }, ensure_ascii=False))
            print(f"{path}: {len(rows)} rows", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"wrote {OUT}: {len(lines)} rows (model {model.config['version']}, ruleset {engine.version})")
    return 0


def _has_cuda() -> bool:
    """Có GPU dùng được không."""
    import torch

    return torch.cuda.is_available()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
