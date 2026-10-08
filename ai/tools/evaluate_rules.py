"""Đo Rule Engine trên một tập hội thoại đã gán nhãn và in bảng kết quả.

Cách dùng (chạy trong container của AI service):

    docker compose run --rm ai python -m tools.evaluate_rules tests/data/conversations_vi.jsonl
    docker compose run --rm ai python -m tools.evaluate_rules tests/data/conversations_vi.jsonl --split holdout
    docker compose run --rm ai python -m tools.evaluate_rules tests/data/conversations_vi.jsonl --flat

Mỗi dòng của file là một JSON: ``{"id", "label" (1 lừa đảo / 0 bình thường), "group",
"turns": [[người nói, lời nói], ...]}`` hoặc ``"text"`` thay cho ``"turns"``. ``--split`` chỉ lấy các dòng có
trường ``split`` tương ứng; ``--flat`` bỏ nhãn người nói, giống transcript mà Whisper trả về.

Rule Engine chỉ báo dấu hiệu, chưa có điểm rủi ro (đó là việc của Risk Engine). Vì vậy công cụ in ba cách
đọc kết quả, từ chặt tới lỏng, để thấy sự đánh đổi giữa bỏ sót và báo nhầm:

    suspicious  có một dấu hiệu HIGH, hoặc từ hai dấu hiệu khác nhau trong đó ít nhất một cái từ MEDIUM
    strong      có ít nhất một dấu hiệu từ MEDIUM trở lên
    any         có bất kỳ dấu hiệu nào
"""

import collections
import json
import sys
from pathlib import Path

from app.rules import IndicatorMatch, RuleEngine, Severity, Turn, parse_turns


def is_suspicious(matches: list[IndicatorMatch]) -> bool:
    """Cách đọc tạm thời khi chưa có Risk Engine: một dấu hiệu HIGH, hoặc hai dấu hiệu với một cái từ MEDIUM."""
    high = any(m.severity == Severity.HIGH for m in matches)
    strong = any(m.severity != Severity.LOW for m in matches)
    return high or (strong and len(matches) >= 2)


def _option(arguments: list[str], name: str) -> str | None:
    """Giá trị đứng sau một tùy chọn dòng lệnh, hoặc ``None`` nếu không có."""
    return arguments[arguments.index(name) + 1] if name in arguments else None


def main(arguments: list[str]) -> int:
    """Đọc file, chạy bộ luật trên từng hội thoại, in bảng theo nhóm và dòng tổng kết."""
    rows = [json.loads(line) for line in Path(arguments[0]).read_text(encoding="utf-8").splitlines() if line.strip()]
    split = _option(arguments, "--split")
    if split:
        rows = [row for row in rows if row.get("split") == split]
    flat = "--flat" in arguments
    engine = RuleEngine()

    stats: dict[tuple[int, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        # Đưa mọi dòng về danh sách lượt lời; văn bản không có nhãn người nói là một lượt duy nhất.
        if row.get("turns"):
            turns = [Turn(speaker, text) for speaker, text in row["turns"]]
        else:
            turns = parse_turns(row["text"]) or [Turn("?", row["text"])]
        speakers = len({turn.speaker for turn in turns})
        if flat:
            matches = engine.analyze_text(" ".join(turn.text for turn in turns)).indicators
        elif speakers >= 2:
            matches = engine.analyze_conversation(turns).indicators
        else:
            matches = engine.analyze_text(turns[0].text).indicators
        party = "3+ người nói" if speakers >= 3 else "2 người nói"
        stats[(row["label"], party)].update(
            n=1, any=bool(matches), strong=any(m.severity != Severity.LOW for m in matches),
            suspicious=is_suspicious(matches),
        )

    print(f"{'nhãn':10} {'nhóm':14} {'n':>5} {'suspicious':>10} {'strong':>7} {'any':>5}")
    totals: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for (label, party), counts in sorted(stats.items(), key=lambda item: (-item[0][0], item[0][1])):
        name = "lừa đảo" if label else "thường"
        print(f"{name:10} {party:14} {counts['n']:>5} {counts['suspicious']:>10} {counts['strong']:>7} {counts['any']:>5}")
        totals[label].update(counts)
    for label, title in ((1, "Phát hiện lừa đảo  "), (0, "Báo nhầm cuộc thường")):
        counts = totals[label]
        if counts["n"]:
            print(f"{title}: {counts['suspicious']}/{counts['n']} = {counts['suspicious'] / counts['n']:.1%}"
                  f"   [strong: {counts['strong']}/{counts['n']}; any: {counts['any']}/{counts['n']}]")
    print(f"ruleset {engine.version}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
