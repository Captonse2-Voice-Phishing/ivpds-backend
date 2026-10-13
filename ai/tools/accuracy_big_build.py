"""Dựng bộ test lớn (khoảng mười nghìn cuộc gọi) để đo độ chính xác của cả hệ thống ở mức transcript.

Cách dùng (chạy từ thư mục ``ai``):

    python -m tools.accuracy_big_build

Ghi ``data/extra_tests/accuracy_big.jsonl``. Mỗi dòng có ``id``, ``label`` (0 bình thường, 1 lừa đảo), ``part`` (phần
nào của bộ test), ``group`` (kịch bản hoặc nhóm), ``text`` (transcript liền, không có nhãn người nói, như Whisper trả
về). Bộ gồm năm phần:

* ``new_scenarios``: hội thoại sinh từ 60 kịch bản chưa có trong huấn luyện (``tools/accuracy_big_scenarios.py``).
* ``original``: các bộ test tiếng Việt sẵn có, giữ nguyên.
* ``perturbed``: các bộ test đó sau khi biến đổi mà nhãn không đổi: viết kiểu transcript (chữ thường, không dấu
  câu), chêm từ đệm, rớt từ, lặp từ, chèn vài câu chuyện phiếm thật vào trước hoặc sau.
* ``perturbed_unseen``: bốn phép biến đổi KHÔNG có trong ``tools/dataset_augment.py`` (đợt huấn luyện 8): cụm từ
  đệm dài ("nói chung là", "kiểu như"), đổi chỗ hai từ cạnh nhau, chèn chuyện phiếm vào GIỮA cuộc gọi, và mất dấu
  thanh ở một số từ. Phần ``perturbed`` dùng các phép giống lúc huấn luyện nên sau đợt 8 không còn khách quan; phần
  này dùng để đo xem model có bền hơn thật không.
* ``mixed``: ghép một cuộc gọi bình thường với một cuộc khác. Bình thường + lừa đảo vẫn là lừa đảo.
* ``long_ordinary_speech``: lời nói thường ngày thật (VLSP 2020, phần chỉ dùng để test) ghép thành đoạn dài.

Giới hạn cần nhớ khi đọc kết quả: phần lớn bộ này là dữ liệu tổng hợp hoặc biến đổi từ dữ liệu tổng hợp; các biến thể
của cùng một kịch bản giống nhau nhiều, nên đơn vị đáng tin là "kịch bản", không phải "cuộc gọi". Bộ này đo transcript,
không đo khâu nhận dạng giọng nói.

**Chỉ dùng để test.** Không đưa file này hay các kịch bản của nó vào huấn luyện.
"""

import json
import random
import re
import sys
import unicodedata
from pathlib import Path

from tools.accuracy_big_scenarios import NORMAL, SCAM
from tools.dataset_synthesize_vi import FILLERS, PRONOUNS, _fill

OUT = Path("data/extra_tests/accuracy_big.jsonl")
SEED = 20261013
PER_SCENARIO = 85
LONG_SPEECH_SAMPLES = 1000

# Các bộ test tiếng Việt sẵn có (chưa từng dùng để huấn luyện) làm gốc cho phần ``original`` và ``perturbed``.
HELD_OUT = ["handwritten_holdout", "everyday_calls", "context_pairs", "short_requests", "short_sentences",
            "short_monologues", "real_calls", "user_gendata"]
PROCESSED_TESTS = ["test_vi_context", "test"]
ORDINARY_SPEECH = Path("data/extra_tests/vlsp_ordinary_speech.jsonl")
# Chỉ biến đổi các bộ này: bộ ``test`` (576 dòng dịch máy) và lời nói thường ngày được giữ nguyên ở phần ``original``.
PERTURB_SETS = set(HELD_OUT) | {"test_vi_context"}

_PUNCTUATION = re.compile(r"[.,!?;:…]")
_SPEAKER_LABEL = re.compile(r"(?:^|\s)(?:[A-C]|Người gọi(?: 2)?|Người nghe|Bên gọi(?: 2)?|Bên nghe|caller|callee)\s*:\s*",
                            re.IGNORECASE)
_INTERJECTIONS = ["dạ", "ờ", "à", "ừm", "ờm", "thì", "là"]


def _plain(text: str) -> str:
    """Bỏ nhãn người nói và gộp khoảng trắng."""
    return " ".join(_SPEAKER_LABEL.sub(" ", text).split())


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def new_scenarios(rng: random.Random) -> list[dict]:
    """Sinh hội thoại từ các kịch bản mới; mỗi kịch bản cho ``PER_SCENARIO`` biến thể khác nhau."""
    rows = []
    for label, scenarios in ((1, SCAM), (0, NORMAL)):
        for name, script in scenarios.items():
            seen: set[str] = set()
            attempts = 0
            while len(seen) < PER_SCENARIO and attempts < PER_SCENARIO * 60:
                attempts += 1
                me, you, victim = rng.choice(PRONOUNS)
                values = {key: rng.choice(options) for key, options in FILLERS.items()}
                values |= {"m": me, "y": you, "v": victim}
                # Cuộc bình thường đi theo một mạch (cách nói thứ k của mọi lượt) để hỏi đáp khớp nhau; cuộc lừa
                # đảo trộn tự do, vì cái cớ, yêu cầu và lời hối thúc thay thế được cho nhau.
                thread = rng.randrange(3)
                turns = []
                for _, options, keep in script:
                    if rng.random() >= keep:
                        continue
                    chosen = options[thread % len(options)] if label == 0 else rng.choice(options)
                    turns.append(_fill(chosen, values))
                text = " ".join(turns)
                if text in seen:
                    continue
                seen.add(text)
                kind = "lừa đảo" if label else "bình thường"
                rows.append({"label": label, "part": "new_scenarios", "group": f"{name} ({kind})", "text": text})
    return rows


def originals() -> list[dict]:
    """Các bộ test sẵn có, giữ nguyên nội dung."""
    rows = []
    for name in HELD_OUT:
        for row in _read(Path(f"data/extra_tests/{name}.jsonl")):
            rows.append({"label": row["label"], "part": "original", "group": name, "source": name,
                         "text": _plain(row.get("text_plain") or row["text"])})
    for name in PROCESSED_TESTS:
        for row in _read(Path(f"data/processed/{name}.jsonl")):
            rows.append({"label": row["label"], "part": "original", "group": name, "source": name,
                         "text": _plain(row.get("text_plain") or row["text"])})
    for row in _read(ORDINARY_SPEECH):
        rows.append({"label": 0, "part": "original", "group": "vlsp_ordinary_speech", "source": "vlsp_ordinary_speech",
                     "text": _plain(row["text"])})
    return rows


def _stt_style(text: str, rng: random.Random) -> str:
    return " ".join(_PUNCTUATION.sub(" ", text).lower().split())


def _with_interjections(text: str, rng: random.Random) -> str:
    words = []
    for word in text.split():
        if rng.random() < 0.12:
            words.append(rng.choice(_INTERJECTIONS))
        words.append(word)
    return " ".join(words)


def _dropped_words(text: str, rng: random.Random) -> str:
    words = text.split()
    kept = [word for word in words if rng.random() >= 0.07]
    return " ".join(kept if len(kept) >= 3 else words)


def _repeated_words(text: str, rng: random.Random) -> str:
    words = []
    for word in text.split():
        words.append(word)
        if rng.random() < 0.06:
            words.append(word)
    return " ".join(words)


def perturbed(base: list[dict], chatter: list[str], rng: random.Random) -> list[dict]:
    """Sáu biến thể của mỗi cuộc gọi gốc. Không biến thể nào làm đổi nhãn."""
    def small_talk() -> str:
        return " ".join(rng.sample(chatter, rng.randint(3, 5)))

    transforms = {
        "kiểu transcript (chữ thường, không dấu câu)": _stt_style,
        "chêm từ đệm": _with_interjections,
        "rớt từ (7%)": _dropped_words,
        "lặp từ (6%)": _repeated_words,
        "chuyện phiếm thật ở trước": lambda text, _: f"{small_talk()} {text}",
        "chuyện phiếm thật ở sau": lambda text, _: f"{text} {small_talk()}",
    }
    rows = []
    for row in base:
        if row["source"] not in PERTURB_SETS:
            continue
        for name, transform in transforms.items():
            rows.append({"label": row["label"], "part": "perturbed", "group": name, "source": row["source"],
                         "text": transform(row["text"], rng)})
    return rows


_FILLER_PHRASES = ["nói chung là", "kiểu như", "thật ra", "ấy mà", "nói thật", "đúng không", "thế này nhé"]
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _filler_phrases(text: str, rng: random.Random) -> str:
    """Chêm cụm từ đệm dài vào đầu một số câu (hoặc sau mỗi chừng mười từ nếu văn bản không có dấu câu)."""
    sentences = _SENTENCE_END.split(text)
    if len(sentences) < 2:
        words = text.split()
        sentences = [" ".join(words[start:start + 10]) for start in range(0, len(words), 10)]
    return " ".join(f"{rng.choice(_FILLER_PHRASES)} {sentence}" if rng.random() < 0.45 else sentence
                    for sentence in sentences)


def _swapped_neighbours(text: str, rng: random.Random) -> str:
    """Đổi chỗ khoảng 5% cặp từ đứng cạnh nhau."""
    words = text.split()
    index = 0
    while index < len(words) - 1:
        if rng.random() < 0.05:
            words[index], words[index + 1] = words[index + 1], words[index]
            index += 2
        else:
            index += 1
    return " ".join(words)


def _lost_tone_marks(text: str, rng: random.Random) -> str:
    """Bỏ dấu ở khoảng 8% số từ, như khi nhận dạng giọng nói nghe nhầm thanh điệu."""
    def bare(word: str) -> str:
        stripped = "".join(ch for ch in unicodedata.normalize("NFD", word) if unicodedata.category(ch) != "Mn")
        return stripped.replace("đ", "d").replace("Đ", "D")

    return " ".join(bare(word) if rng.random() < 0.08 else word for word in text.split())


def perturbed_unseen(base: list[dict], chatter: list[str], rng: random.Random) -> list[dict]:
    """Bốn biến thể của mỗi cuộc gọi gốc, bằng các phép không dùng để huấn luyện. Nhãn không đổi."""
    def chatter_in_the_middle(text: str, _: random.Random) -> str:
        words = text.split()
        cut = len(words) // 2
        return " ".join(words[:cut] + rng.sample(chatter, rng.randint(2, 4)) + words[cut:])

    transforms = {
        "cụm từ đệm dài": _filler_phrases,
        "đổi chỗ hai từ cạnh nhau (5%)": _swapped_neighbours,
        "chuyện phiếm thật ở giữa": chatter_in_the_middle,
        "mất dấu thanh (8% số từ)": _lost_tone_marks,
    }
    rows = []
    for row in base:
        if row["source"] not in PERTURB_SETS:
            continue
        for name, transform in transforms.items():
            rows.append({"label": row["label"], "part": "perturbed_unseen", "group": name, "source": row["source"],
                         "text": transform(row["text"], rng)})
    return rows


def mixed(base: list[dict], rng: random.Random) -> list[dict]:
    """Ghép một cuộc gọi bình thường đời thường với một cuộc khác: thêm lừa đảo thì thành lừa đảo."""
    normal = [row for row in base if row["source"] in ("everyday_calls", "handwritten_holdout") and row["label"] == 0]
    scams = [row for row in base if row["source"] in PERTURB_SETS and row["label"] == 1]
    rows = []
    for scam in scams:
        first = rng.choice(normal)
        order = [first["text"], scam["text"]] if rng.random() < 0.5 else [scam["text"], first["text"]]
        rows.append({"label": 1, "part": "mixed", "group": "bình thường ghép với lừa đảo", "source": scam["source"],
                     "text": " ".join(order)})
    for _ in range(len(scams)):
        first, second = rng.sample(normal, 2)
        rows.append({"label": 0, "part": "mixed", "group": "hai cuộc bình thường ghép lại", "source": first["source"],
                     "text": f"{first['text']} {second['text']}"})
    return rows


def long_ordinary_speech(chatter: list[str], rng: random.Random) -> list[dict]:
    """Ghép 8 đến 30 câu nói thường ngày thật thành một đoạn dài, để thử báo nhầm trên nội dung dài."""
    rows = []
    for _ in range(LONG_SPEECH_SAMPLES):
        text = " ".join(rng.sample(chatter, rng.randint(8, 30)))
        rows.append({"label": 0, "part": "long_ordinary_speech", "group": "lời nói thường ngày thật ghép dài",
                     "text": text})
    return rows


def main() -> int:
    """Dựng năm phần, đánh số và ghi ra file."""
    rng = random.Random(SEED)
    base = originals()
    chatter = [row["text"] for row in base if row["source"] == "vlsp_ordinary_speech" and len(row["text"].split()) >= 6]
    rows = new_scenarios(rng) + base + perturbed(base, chatter, rng) + mixed(base, rng) \
        + long_ordinary_speech(chatter, rng)
    # Sinh sau cùng với bộ số ngẫu nhiên riêng, để năm phần trên giữ nguyên nội dung như trước khi có phần này.
    rows += perturbed_unseen(base, chatter, random.Random(SEED + 1))
    for index, row in enumerate(rows):
        row["id"] = f"big-{index:05d}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8"))
    parts: dict[str, list[int]] = {}
    for row in rows:
        parts.setdefault(row["part"], [0, 0])[row["label"]] += 1
    print(f"wrote {OUT}: {len(rows)} rows")
    for part, (normal, scam) in parts.items():
        print(f"  {part:22} {normal + scam:6} ({scam} scam, {normal} normal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
