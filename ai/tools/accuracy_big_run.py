"""Chấm NLP Model, Rule Engine và Risk Engine trên bộ test lớn, rồi ghi báo cáo.

Cách dùng (chạy từ thư mục ``ai`` trong image huấn luyện, có GPU thì nhanh hơn):

    docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -w /work \
        ivpds/train:dev python -m tools.accuracy_big_run phobert-base-r6

Đọc ``data/extra_tests/accuracy_big.jsonl`` (dựng bằng ``tools.accuracy_big_build``). Với mỗi dòng, chạy đúng những gì
AI service chạy: Rule Engine và NLP Model trên transcript, rồi Risk Engine với số từ của transcript. Ghi:

* ``data/risk/accuracy_big-<model>.jsonl``: kết quả từng dòng (xác suất, dấu hiệu, điểm, mức);
* ``training/reports/accuracy-big-<model>.json``: các bảng tổng hợp.

Quy ước: cuộc lừa đảo được coi là "phát hiện" khi mức rủi ro là MEDIUM hoặc HIGH và "sót" khi LOW; cuộc bình thường
bị coi là "báo nhầm" khi MEDIUM hoặc HIGH. Precision, recall, F1 tính theo quy ước đó.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from app.nlp import TextClassifier
from app.risk import RISK_ENGINE_VERSION, assess
from app.rules import RuleEngine

DATA = Path("data/extra_tests/accuracy_big.jsonl")


def _has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def summarise(rows: list[dict]) -> dict:
    """Đếm theo nhãn và mức, kèm precision, recall, F1 của Risk Engine và của riêng NLP Model."""
    scam = [row for row in rows if row["label"] == 1]
    normal = [row for row in rows if row["label"] == 0]
    levels = Counter((row["label"], row["level"]) for row in rows)
    detected = len(scam) - levels[(1, "LOW")]
    flagged = len(normal) - levels[(0, "LOW")]

    def ratio(top: int, bottom: int) -> float | None:
        return round(top / bottom, 4) if bottom else None

    precision, recall = ratio(detected, detected + flagged), ratio(detected, len(scam))
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall else None
    model_missed = sum(1 for row in scam if row["probability"] < 0.5)
    model_flagged = sum(1 for row in normal if row["probability"] >= 0.5)
    return {
        "total": len(rows),
        "scam": {"total": len(scam), "HIGH": levels[(1, "HIGH")], "MEDIUM": levels[(1, "MEDIUM")],
                 "LOW": levels[(1, "LOW")]},
        "normal": {"total": len(normal), "HIGH": levels[(0, "HIGH")], "MEDIUM": levels[(0, "MEDIUM")],
                   "LOW": levels[(0, "LOW")]},
        "risk_engine": {"scam_missed": levels[(1, "LOW")], "normal_flagged": flagged,
                        "normal_flagged_high": levels[(0, "HIGH")], "precision": precision, "recall": recall,
                        "f1": f1, "accuracy": ratio(detected + levels[(0, "LOW")], len(rows))},
        "model_only": {"scam_missed": model_missed, "normal_flagged": model_flagged,
                       "accuracy": ratio(len(scam) - model_missed + len(normal) - model_flagged, len(rows))},
        "capped_by_short_text_guard": sum(1 for row in rows if row["capped"]),
    }


def main(model_name: str) -> int:
    """Chạy ba tầng trên từng dòng, ghi kết quả từng dòng và báo cáo tổng hợp."""
    model = TextClassifier(f"models/{model_name}", device="cuda" if _has_cuda() else "cpu")
    engine = RuleEngine()
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    for index, row in enumerate(rows):
        text = row["text"]
        analysis = engine.analyze_text(text)
        probability = model.predict(text).phishing_probability
        result = assess(analysis.indicators, probability, words=len(text.split()))
        row.update({
            "words": len(text.split()), "probability": round(probability, 6),
            "indicators": [[match.code.value, match.severity.value] for match in analysis.indicators],
            "score": result.risk_score, "level": result.risk_level.value, "capped": result.short_text_capped,
        })
        if (index + 1) % 2000 == 0:
            print(f"{index + 1}/{len(rows)}", flush=True)

    details = Path(f"data/risk/accuracy_big-{model_name}.jsonl")
    details.parent.mkdir(parents=True, exist_ok=True)
    details.write_bytes(("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8"))

    by_part, by_group = defaultdict(list), defaultdict(list)
    for row in rows:
        by_part[row["part"]].append(row)
        by_group[(row["part"], row["group"])].append(row)
    report = {
        "model": model.config["version"], "ruleset": engine.version, "risk_engine": RISK_ENGINE_VERSION,
        "detected_means": "risk level MEDIUM or HIGH",
        "overall": summarise(rows),
        "by_part": {part: summarise(subset) for part, subset in by_part.items()},
        "by_group": {f"{part} / {group}": summarise(subset) for (part, group), subset in sorted(by_group.items())},
    }
    out = Path(f"training/reports/accuracy-big-{model_name}.json")
    out.write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))

    def line(name: str, summary: dict) -> str:
        scam, normal, risk = summary["scam"], summary["normal"], summary["risk_engine"]
        return (f"{name[:44]:44} n={summary['total']:5} | scam {scam['total']:4}: H{scam['HIGH']:5} M{scam['MEDIUM']:4} "
                f"L{scam['LOW']:4} | normal {normal['total']:4}: H{normal['HIGH']:4} M{normal['MEDIUM']:4} "
                f"L{normal['LOW']:5} | P={risk['precision']} R={risk['recall']} F1={risk['f1']}")

    print(line("OVERALL", report["overall"]))
    for part, summary in report["by_part"].items():
        print(line(part, summary))
    print(f"wrote {details} and {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
