"""Gộp các kịch bản cuộc gọi viết tay thành dữ liệu huấn luyện và một phần giữ lại để test.

Cách dùng (chạy từ thư mục ``ai``):

    python -m tools.handwritten_calls_build

Các file ``data/synthetic/handwritten/*.txt`` chứa mỗi dòng một cuộc gọi do người viết tay từng cuộc, theo dạng
``nhãn|nhóm|nội dung`` (nhãn 1 là lừa đảo, 0 là bình thường). Script kiểm tra định dạng, bỏ dòng trùng, rồi chia:
cứ năm dòng thì dòng thứ năm được giữ lại làm test (``data/extra_tests/handwritten_holdout.jsonl``), bốn dòng còn
lại vào huấn luyện (``data/synthetic/handwritten_calls.jsonl``). Phần giữ lại không bao giờ được đưa vào huấn luyện.
"""

import json
import sys
from collections import Counter
from pathlib import Path

SOURCE = Path("data/synthetic/handwritten")
OUT = Path("data/synthetic/handwritten_calls.jsonl")
HOLDOUT = Path("data/extra_tests/handwritten_holdout.jsonl")
HOLDOUT_EVERY = 5


def main() -> int:
    """Đọc mọi file nguồn, kiểm tra từng dòng và ghi bộ test."""
    rows, seen = [], set()
    for path in sorted(SOURCE.glob("*.txt")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            label, group, text = line.split("|", 2)
            if label not in ("0", "1") or "|" in text or len(text.split()) < 15:
                raise ValueError(f"{path.name}:{number}: bad line")
            if text in seen:
                continue
            seen.add(text)
            rows.append({"id": f"hw-{path.stem}-{number:02}", "label": int(label),
                         "group": ("lừa đảo - " if label == "1" else "bình thường - ") + group.strip(), "text": text.strip()})
    train = [row for index, row in enumerate(rows) if (index + 1) % HOLDOUT_EVERY]
    holdout = [row for index, row in enumerate(rows) if not (index + 1) % HOLDOUT_EVERY]
    for path, part in ((OUT, train), (HOLDOUT, holdout)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in part).encode("utf-8"))
        counts = Counter(row["label"] for row in part)
        print(f"wrote {path}: {len(part)} calls ({counts[1]} scam, {counts[0]} normal)")
    words = sorted(len(row["text"].split()) for row in rows)
    print(f"total {len(rows)} calls, median {words[len(words) // 2]} words")
    for group, count in sorted(Counter(row["group"] for row in rows).items()):
        print(f"   {count:3}  {group}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
