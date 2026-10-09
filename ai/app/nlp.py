"""NLP Model: phân loại transcript cuộc gọi thành bình thường hoặc lừa đảo bằng một model Transformer đã fine-tune.

Đây là thành phần machine learning, tách biệt với Rule Engine. Nó chỉ trả về xác suất do model tính ra;
việc kết hợp với các dấu hiệu của Rule Engine thành điểm rủi ro thuộc về Risk Engine.

Cuộc gọi thường dài hơn giới hạn đầu vào của model, nên văn bản được cắt thành các đoạn gối nhau; mỗi đoạn
được chấm riêng rồi gộp lại theo cách đã chọn lúc huấn luyện (ghi trong ``nlp_config.json`` của artifact).
Cùng một đoạn code này được dùng khi đánh giá model và khi phục vụ API, để kết quả đo đúng là kết quả chạy thật.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = "nlp_config.json"
LABELS = ("NORMAL", "PHISHING")
_NOT_WORD = re.compile(r"[^\w]+")


def normalize_for_model(text: str) -> str:
    """Đưa văn bản về dạng transcript của Whisper: chữ thường, không dấu câu, một khoảng trắng giữa các từ.

    Dữ liệu huấn luyện là văn viết có dấu câu và chữ hoa, còn khi chạy thật model nhận transcript trơn. Chuẩn hóa
    cả hai về cùng một dạng để model không dựa vào dấu câu hay chữ hoa, là những thứ không có lúc chạy thật.
    """
    lowered = unicodedata.normalize("NFC", text).lower()
    return " ".join(_NOT_WORD.sub(" ", lowered).split())


def token_windows(token_ids: list[int], window: int, stride: int) -> list[list[int]]:
    """Cắt dãy token thành các đoạn dài tối đa ``window``, đoạn sau bắt đầu sau đoạn trước ``stride`` token."""
    if len(token_ids) <= window:
        return [token_ids]
    windows = []
    for start in range(0, len(token_ids), stride):
        windows.append(token_ids[start:start + window])
        if start + window >= len(token_ids):
            break
    return windows


def with_special_tokens(tokenizer, token_ids: list[int]) -> list[int]:
    """Thêm token mở đầu và kết thúc mà model cần quanh một đoạn (``<s> ... </s>`` hoặc ``[CLS] ... [SEP]``)."""
    first = tokenizer.cls_token_id if tokenizer.cls_token_id is not None else tokenizer.bos_token_id
    last = tokenizer.sep_token_id if tokenizer.sep_token_id is not None else tokenizer.eos_token_id
    return [first, *token_ids, last]


def aggregate(probabilities: list[float], method: str) -> float:
    """Gộp xác suất lừa đảo của các đoạn thành một xác suất cho cả cuộc gọi.

    ``mean``: trung bình các đoạn. ``max``: đoạn đáng ngờ nhất. ``top2``: trung bình hai đoạn đáng ngờ nhất,
    ít nhạy với một đoạn bị chấm cao bất thường hơn ``max``.
    """
    if method == "mean":
        return sum(probabilities) / len(probabilities)
    if method == "max":
        return max(probabilities)
    if method == "top2":
        top = sorted(probabilities, reverse=True)[:2]
        return sum(top) / len(top)
    raise ValueError(f"unknown aggregation: {method}")


@dataclass(frozen=True)
class Prediction:
    """Kết quả phân loại một transcript."""

    label: str
    # Xác suất model gán cho lớp PHISHING, từ 0 đến 1. Đây không phải điểm rủi ro.
    phishing_probability: float
    # Xác suất của từng đoạn, theo thứ tự trong transcript.
    chunk_probabilities: list[float]


class TextClassifier:
    """Nạp artifact đã fine-tune và phân loại transcript."""

    def __init__(self, artifact_dir: str | Path, device: str = "cpu") -> None:
        """Nạp trọng số, tokenizer và cấu hình từ thư mục artifact; ``device`` là "cpu" hoặc "cuda"."""
        # Nạp thư viện nặng ở đây để phần còn lại của service khởi động được khi chưa cài torch.
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        directory = Path(artifact_dir)
        self.config = json.loads((directory / CONFIG_FILE).read_text(encoding="utf-8"))
        self._tokenizer = AutoTokenizer.from_pretrained(directory)
        self._model = AutoModelForSequenceClassification.from_pretrained(directory).to(device).eval()
        self._device = device
        self._segment = None
        if self.config.get("word_segmentation"):
            from pyvi import ViTokenizer

            self._segment = ViTokenizer.tokenize

    @property
    def name(self) -> str:
        """Tên model nền và phiên bản artifact, để hiển thị ở ``/v1/info``."""
        return f"{self.config['base_model']} ({self.config['version']})"

    def encode(self, text: str) -> list[list[int]]:
        """Chuẩn hóa, tách token và cắt thành các đoạn (chưa thêm token đặc biệt)."""
        prepared = normalize_for_model(text)
        if self._segment is not None:
            prepared = self._segment(prepared)
        token_ids = self._tokenizer.encode(prepared, add_special_tokens=False)
        return token_windows(token_ids, self.config["max_length"] - 2, self.config["stride"])

    def predict(self, text: str, batch_size: int = 16) -> Prediction:
        """Phân loại một transcript. Văn bản rỗng được coi là bình thường với xác suất 0."""
        if not normalize_for_model(text):
            return Prediction(label=LABELS[0], phishing_probability=0.0, chunk_probabilities=[])
        windows = self.encode(text)
        probabilities = self.chunk_probabilities(windows, batch_size)
        score = aggregate(probabilities, self.config["aggregation"])
        label = LABELS[1] if score >= self.config["threshold"] else LABELS[0]
        return Prediction(label=label, phishing_probability=score, chunk_probabilities=probabilities)

    def chunk_probabilities(self, windows: list[list[int]], batch_size: int = 16) -> list[float]:
        """Xác suất PHISHING của từng đoạn token."""
        torch = self._torch
        results: list[float] = []
        for start in range(0, len(windows), batch_size):
            batch = [with_special_tokens(self._tokenizer, ids) for ids in windows[start:start + batch_size]]
            longest = max(len(ids) for ids in batch)
            pad = self._tokenizer.pad_token_id
            input_ids = torch.tensor([ids + [pad] * (longest - len(ids)) for ids in batch], device=self._device)
            mask = torch.tensor([[1] * len(ids) + [0] * (longest - len(ids)) for ids in batch], device=self._device)
            with torch.inference_mode():
                logits = self._model(input_ids=input_ids, attention_mask=mask).logits
            results.extend(torch.softmax(logits.float(), dim=-1)[:, 1].tolist())
        return results
