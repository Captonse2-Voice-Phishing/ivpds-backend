"""Thêm vào tập huấn luyện các bản biến đổi của chính nó, để model bớt phụ thuộc vào câu chữ sạch (đợt 8).

Cách dùng (chạy từ thư mục ``ai``, sau ``tools.dataset_prepare``):

    python -m tools.dataset_augment

Vì sao cần: bộ test lớn (13/10/2026) cho thấy model đợt 6 đổi hẳn kết luận khi câu chỉ thêm vài từ đệm ("dạ", "thì",
"là") hoặc khi trước và sau lời lừa đảo có vài câu chuyện phiếm: xác suất có thể tụt từ gần 1 xuống 0. Người thật nói
đầy từ đệm, và Whisper nghe sót, nghe lặp. Dữ liệu huấn luyện thì toàn câu viết gọn gàng.

Script đọc ``data/processed/train.jsonl`` và ghi thêm vào chính file đó các bản biến đổi của một phần số cuộc gọi.
Nhãn không đổi. Mỗi bản dùng một hoặc hai phép trong các phép sau:

* chêm từ đệm vào giữa câu;
* bỏ ngẫu nhiên vài từ (nghe sót);
* lặp lại vài từ (nói lắp, nghe lặp);
* chèn vài câu nói thường ngày thật vào trước hoặc sau cuộc gọi (câu lấy từ phần HUẤN LUYỆN của VLSP, không dùng
  phần test).

Bài học từ lần chạy đầu (model ``phobert-base-r8``, không dùng): model học theo từng đoạn 256 token và mỗi đoạn mang
nhãn của cả cuộc gọi. Khi chèn tới sáu câu chuyện phiếm vào trước một cuộc lừa đảo, đoạn đầu gần như toàn chuyện phiếm
mà vẫn bị dạy là "lừa đảo"; model đó báo nhầm 618/1.000 đoạn lời nói thường ngày dài. Vì vậy:

* chuyện phiếm chèn vào được giữ ngắn (tối đa ``SMALL_TALK_WORDS`` từ), không bao giờ chiếm trọn một đoạn;
* thêm ``LONG_SPEECH_ROWS`` đoạn lời nói thường ngày thật ghép dài, nhãn bình thường, để model thấy rằng nội dung
  dài toàn chuyện thường ngày là bình thường.

Chỉ tập huấn luyện được biến đổi; validation và test giữ nguyên. Mọi dòng thêm vào có ``augmented = true`` và id kết
thúc bằng ``-aug``. Chạy lại script không nhân đôi: các dòng ``-aug`` cũ bị bỏ trước khi sinh lại.

Bộ test lớn có một phần biến đổi KHÁC các phép ở đây (``perturbed_unseen`` trong ``tools/accuracy_big_build.py``),
để đo xem model có bền hơn thật hay chỉ quen với đúng các phép đã học.
"""

import json
import random
import sys
from pathlib import Path

TRAIN = Path("data/processed/train.jsonl")
INFO = Path("data/processed/AUGMENT.json")
SEED = 20261013
# Tỉ lệ cuộc gọi được thêm một bản biến đổi; cuộc gọi thật quá ít nên mỗi cuộc được thêm vài bản.
SHARE = 0.45
REAL_CALL_COPIES = 4
# Chuyện phiếm chèn trước hoặc sau một cuộc gọi: ngắn, để không tạo ra đoạn 256 token toàn chuyện phiếm mang nhãn sai.
SMALL_TALK_WORDS = 45
# Số đoạn lời nói thường ngày ghép dài (nhãn bình thường) thêm vào tập huấn luyện.
LONG_SPEECH_ROWS = 500
CHATTER_SOURCE = "vlsp_ordinary_speech"
REAL_CALL_SOURCE = "youtube_calls"
INTERJECTIONS = ["dạ", "ạ", "ờ", "à", "ừ", "ừm", "ờm", "thì", "là", "vâng", "ấy", "kiểu"]


def with_interjections(text: str, rng: random.Random) -> str:
    rate = rng.uniform(0.06, 0.16)
    words = []
    for word in text.split():
        if rng.random() < rate:
            words.append(rng.choice(INTERJECTIONS))
        words.append(word)
    return " ".join(words)


def dropped_words(text: str, rng: random.Random) -> str:
    rate = rng.uniform(0.04, 0.10)
    words = text.split()
    kept = [word for word in words if rng.random() >= rate]
    return " ".join(kept if len(kept) >= 3 else words)


def repeated_words(text: str, rng: random.Random) -> str:
    rate = rng.uniform(0.03, 0.08)
    words = []
    for word in text.split():
        words.append(word)
        if rng.random() < rate:
            words.append(word)
    return " ".join(words)


def main() -> int:
    """Sinh các bản biến đổi và ghi lại tập huấn luyện."""
    rng = random.Random(SEED)
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [row for row in rows if not row.get("augmented")]
    chatter = [row["text_plain"] for row in rows
               if row["source"] == CHATTER_SOURCE and len(row["text_plain"].split()) >= 6]
    if not chatter:
        print("no ordinary-speech rows in the training set; cannot add small talk", file=sys.stderr)
        return 1

    def small_talk() -> str:
        words = " ".join(rng.sample(chatter, rng.randint(1, 3))).split()
        return " ".join(words[:SMALL_TALK_WORDS])

    transforms = {
        "interjections": with_interjections,
        "dropped_words": dropped_words,
        "repeated_words": repeated_words,
        "small_talk_before": lambda text, _: f"{small_talk()} {text}",
        "small_talk_after": lambda text, _: f"{text} {small_talk()}",
    }
    names = list(transforms)
    added, used = [], {name: 0 for name in names}
    for row in rows:
        if row["source"] == CHATTER_SOURCE:
            continue
        copies = REAL_CALL_COPIES if row["source"] == REAL_CALL_SOURCE else int(rng.random() < SHARE)
        for copy in range(copies):
            chosen = rng.sample(names, 2 if rng.random() < 0.35 else 1)
            text = row["text_plain"]
            for name in chosen:
                text = transforms[name](text, rng)
                used[name] += 1
            suffix = "-aug" if copies == 1 else f"-{copy}-aug"
            added.append({**row, "id": row["id"] + suffix, "text": text, "text_plain": text, "synthetic": True,
                          "augmented": True, "augmentation": "+".join(chosen)})

    template = next(row for row in rows if row["source"] == CHATTER_SOURCE)
    for index in range(LONG_SPEECH_ROWS):
        text = " ".join(rng.sample(chatter, rng.randint(5, 30)))
        added.append({**template, "id": f"long-speech-{index:04d}-aug", "type": "lời nói thường ngày ghép dài",
                      "cluster": f"long-speech-{index:04d}", "text": text, "text_plain": text, "label": 0,
                      "label_name": "NORMAL", "synthetic": False, "augmented": True,
                      "augmentation": "long_ordinary_speech"})

    out = rows + added
    TRAIN.write_bytes(("\n".join(json.dumps(row, ensure_ascii=False) for row in out) + "\n").encode("utf-8"))
    labels = {label: sum(1 for row in added if row["label"] == label) for label in (0, 1)}
    info = {"seed": SEED, "share": SHARE, "real_call_copies": REAL_CALL_COPIES, "original_rows": len(rows),
            "augmented_rows": len(added), "augmented_by_label": {"NORMAL": labels[0], "PHISHING": labels[1]},
            "transform_uses": used, "long_ordinary_speech_rows": LONG_SPEECH_ROWS,
            "small_talk_max_words": SMALL_TALK_WORDS, "train_rows_after": len(out)}
    INFO.write_bytes(json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"wrote {TRAIN}: {len(rows)} original + {len(added)} augmented = {len(out)} rows; {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
