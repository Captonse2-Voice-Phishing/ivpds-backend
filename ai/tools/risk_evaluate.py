"""Chấm Risk Engine trên các tín hiệu đã ghi sẵn và so với việc chỉ dùng NLP Model hoặc chỉ dùng Rule Engine.

Cách dùng (chạy từ thư mục ``ai``, sau khi đã chạy ``tools.risk_signals_dump``):

    python -m tools.risk_evaluate

Đọc ``data/risk/signals.jsonl``, áp dụng công thức hiện tại trong ``app/risk.py`` cho từng cuộc gọi, rồi in bảng
và ghi ``training/reports/risk-engine.json``. Một cuộc lừa đảo được coi là "phát hiện" khi mức rủi ro từ MEDIUM
trở lên; một cuộc bình thường bị coi là "báo nhầm" cũng khi từ MEDIUM trở lên.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from app.risk import (HIGH_THRESHOLD, INDICATOR_POINTS, MEDIUM_THRESHOLD, MODEL_WEIGHT, PATTERN_BONUS,
                      RISK_ENGINE_VERSION, RULE_SCORE_CAP, SEVERITY_POINTS, assess)
from app.rules import RULESET_VERSION, Indicator, IndicatorMatch, Severity

SIGNALS = Path("data/risk/signals.jsonl")
REPORT = Path("training/reports/risk-engine.json")
# Năm bộ cuộc gọi tiếng Việt dùng để báo cáo con số tổng.
VIETNAMESE_CALL_SETS = ("real_calls", "everyday_calls", "short_sentences", "short_requests", "context_pairs")


def rule_only_flags(indicators: list[list[str]]) -> bool:
    """Tiêu chí tạm của riêng Rule Engine: có dấu hiệu HIGH, hoặc từ hai dấu hiệu trở lên với ít nhất một MEDIUM."""
    severities = [severity for _, severity in indicators]
    return "HIGH" in severities or (len(severities) >= 2 and "MEDIUM" in severities)


def summarise(rows: list[dict]) -> dict:
    """Đếm mức rủi ro theo nhãn, kèm số ca sót và báo nhầm của từng cách làm."""
    scam = [row for row in rows if row["label"] == 1]
    normal = [row for row in rows if row["label"] == 0]
    levels = lambda subset: dict(Counter(row["level"] for row in subset))  # noqa: E731
    return {
        "scam": {"total": len(scam), "levels": levels(scam)},
        "normal": {"total": len(normal), "levels": levels(normal)},
        "risk_engine": {"scam_missed": sum(1 for row in scam if row["level"] == "LOW"),
                        "normal_flagged": sum(1 for row in normal if row["level"] != "LOW")},
        "model_only": {"scam_missed": sum(1 for row in scam if row["probability"] < 0.5),
                       "normal_flagged": sum(1 for row in normal if row["probability"] >= 0.5)},
        "rule_only": {"scam_missed": sum(1 for row in scam if not rule_only_flags(row["indicators"])),
                      "normal_flagged": sum(1 for row in normal if rule_only_flags(row["indicators"]))},
    }


def main() -> int:
    """Tính điểm cho từng dòng, in bảng và ghi báo cáo."""
    rows = [json.loads(line) for line in SIGNALS.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        matches = [IndicatorMatch(Indicator(code), Severity(severity), [], []) for code, severity in row["indicators"]]
        result = assess(matches, row["probability"])
        row["level"], row["score"] = result.risk_level.value, result.risk_score

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["set"], []).append(row)
    groups["TOTAL vietnamese call sets"] = [row for row in rows if row["set"] in VIETNAMESE_CALL_SETS]
    groups["TOTAL tuning sets"] = [row for row in rows if row["role"] == "tuning"]
    groups["TOTAL final test (new calls)"] = [row for row in rows if row["role"] == "final"]

    report = {
        "risk_engine_version": RISK_ENGINE_VERSION, "ruleset_version": RULESET_VERSION,
        "parameters": {
            "model_weight": MODEL_WEIGHT, "rule_score_cap": RULE_SCORE_CAP, "pattern_bonus": PATTERN_BONUS,
            "indicator_points": {key.value: value for key, value in INDICATOR_POINTS.items()},
            "severity_points": {key.value: value for key, value in SEVERITY_POINTS.items()},
            "medium_threshold": MEDIUM_THRESHOLD, "high_threshold": HIGH_THRESHOLD,
        },
        "detected_means": "risk level MEDIUM or HIGH",
        "sets": {name: summarise(subset) for name, subset in groups.items()},
    }
    for name, summary in report["sets"].items():
        scam, normal = summary["scam"], summary["normal"]
        level = lambda part, key: part["levels"].get(key, 0)  # noqa: E731
        print(f"{name:28} scam {scam['total']:4}: HIGH {level(scam, 'HIGH'):4} MEDIUM {level(scam, 'MEDIUM'):3} "
              f"LOW {level(scam, 'LOW'):3} | normal {normal['total']:4}: HIGH {level(normal, 'HIGH'):3} "
              f"MEDIUM {level(normal, 'MEDIUM'):3} LOW {level(normal, 'LOW'):4} | missed/flagged: "
              f"risk {summary['risk_engine']['scam_missed']}/{summary['risk_engine']['normal_flagged']} "
              f"model {summary['model_only']['scam_missed']}/{summary['model_only']['normal_flagged']} "
              f"rules {summary['rule_only']['scam_missed']}/{summary['rule_only']['normal_flagged']}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
