"""Tạo bộ test khoảng 1.000 cuộc gọi (lừa đảo và bình thường) từ một nguồn không dùng để huấn luyện.

Cách dùng (cần mạng và GPU; chạy từ thư mục ``ai`` trong image huấn luyện):

    docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work \
        ivpds/train:dev python -m tools.translated_calls_fetch

Không có bộ cuộc gọi tiếng Việt có nhãn nào đủ lớn được công bố, nên bộ test này lấy hội thoại điện thoại tiếng
Anh rồi dịch máy sang tiếng Việt:

* ``shakeleoatmeal/phone-scam-detection-synthetic`` (MIT): 1.800 hội thoại do máy sinh, mỗi chủ đề (hỗ trợ kỹ
  thuật, an sinh xã hội, hoàn tiền) có cả bản lừa đảo lẫn bản hợp pháp. Lấy ngẫu nhiên 500 lừa đảo + 500 bình thường.
* ``BothBosu/youtube-scam-conversations`` (Apache-2.0): 20 cuộc gọi lừa đảo thật chép từ YouTube.

Dịch bằng ``Helsinki-NLP/opus-mt-en-vi`` (Apache-2.0), từng câu một. Kết quả ghi vào
``data/extra_tests/translated_calls.jsonl``. Đây là dữ liệu chỉ để test: không được đưa vào huấn luyện.

Giới hạn cần nhớ khi đọc kết quả: nội dung là kịch bản kiểu Mỹ, phần lớn do máy sinh, và bản dịch máy không tự
nhiên như lời người Việt nói.
"""

import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

OUT = Path("data/extra_tests/translated_calls.jsonl")
TRANSLATOR = "Helsinki-NLP/opus-mt-en-vi"
SEED = 20261009
PER_CLASS = 500
_SPEAKER = re.compile(r"\b(?:caller|receiver|suspect|innocent|agent|customer)\s*:\s*", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def fetch_rows(dataset: str, split: str, total: int) -> list[dict]:
    """Tải toàn bộ một tập của dataset qua API của Hugging Face, mỗi lần 100 dòng."""
    rows = []
    for offset in range(0, total, 100):
        url = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
            {"dataset": dataset, "config": "default", "split": split, "offset": offset, "length": 100})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - URL cố định
                    rows.extend(item["row"] for item in json.load(response)["rows"])
                break
            except Exception:  # noqa: BLE001 - lỗi mạng tạm thời, thử lại
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"could not fetch {dataset} {split} at {offset}")
    return rows


def sentences_of(dialogue: str) -> list[str]:
    """Bỏ nhãn người nói rồi tách hội thoại thành từng câu để dịch (model dịch làm tốt nhất với câu ngắn)."""
    turns = [turn.strip() for turn in _SPEAKER.split(dialogue) if turn.strip()]
    return [sentence.strip() for turn in turns for sentence in _SENTENCE.split(turn) if sentence.strip()]


def translate(sentences: list[str], device: str) -> list[str]:
    """Dịch danh sách câu tiếng Anh sang tiếng Việt, theo lô, các câu dài gần nhau đi cùng lô."""
    tokenizer = AutoTokenizer.from_pretrained(TRANSLATOR)
    model = AutoModelForSeq2SeqLM.from_pretrained(TRANSLATOR).to(device).eval()
    order = sorted(range(len(sentences)), key=lambda index: len(sentences[index]))
    result = [""] * len(sentences)
    for start in range(0, len(order), 64):
        batch = order[start:start + 64]
        encoded = tokenizer([sentences[index] for index in batch], return_tensors="pt", padding=True, truncation=True,
                            max_length=256).to(device)
        with torch.inference_mode():
            output = model.generate(**encoded, max_new_tokens=256, num_beams=4)
        for index, text in zip(batch, tokenizer.batch_decode(output, skip_special_tokens=True)):
            result[index] = text
        if (start // 64) % 40 == 0:
            print(f"translated {start + len(batch)}/{len(order)} sentences", flush=True)
    return result


def main() -> int:
    """Tải, chọn mẫu, dịch và ghi bộ test."""
    rng = random.Random(SEED)
    synthetic = []
    for split, total in (("train", 1259), ("validation", 361), ("test", 180)):
        synthetic += fetch_rows("shakeleoatmeal/phone-scam-detection-synthetic", split, total)
    names = {"support": "hỗ trợ kỹ thuật", "ssn": "an sinh xã hội", "refund": "hoàn tiền"}
    chosen = []
    for label in (1, 0):
        pool = [row for row in synthetic if row["label"] == label]
        rng.shuffle(pool)
        for number, row in enumerate(pool[:PER_CLASS]):
            kind = names.get(row["type"], row["type"])
            chosen.append({"id": f"tr-{'scam' if label else 'legit'}-{number}", "label": label, "source": "synthetic-en",
                           "group": f"{'lừa đảo' if label else 'bình thường'} - {kind} (dịch máy)",
                           "text_en": row["dialogue"]})
    real = fetch_rows("BothBosu/youtube-scam-conversations", "train", 20)
    for number, row in enumerate(real):
        chosen.append({"id": f"tr-youtube-{number}", "label": int(row["labels"]), "source": "youtube-en",
                       "group": ("lừa đảo" if row["labels"] else "bình thường") + " - cuộc gọi thật tiếng Anh (dịch máy)",
                       "text_en": row["dialogue"]})

    pieces = [sentences_of(row["text_en"]) for row in chosen]
    flat = [sentence for sentences in pieces for sentence in sentences]
    print(f"{len(chosen)} dialogues, {len(flat)} sentences to translate", flush=True)
    translated = iter(translate(flat, "cuda" if torch.cuda.is_available() else "cpu"))
    for row, sentences in zip(chosen, pieces):
        row["text"] = " ".join(next(translated) for _ in sentences)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in chosen).encode("utf-8"))
    print(f"wrote {OUT}: {len(chosen)} calls ({sum(row['label'] for row in chosen)} scam, "
          f"{sum(1 - row['label'] for row in chosen)} normal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
