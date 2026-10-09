"""Thước đo chất lượng nhận dạng giọng nói: tỉ lệ lỗi từ (WER)."""

import re
import unicodedata

_NOT_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_words(text: str) -> list[str]:
    """Tách văn bản thành danh sách từ để so sánh: chuẩn hóa Unicode, chữ thường, bỏ dấu câu.

    Tiếng Việt viết cách nhau theo từng tiếng (âm tiết), nên "từ" ở đây là một tiếng.
    """
    normalized = unicodedata.normalize("NFC", text).lower()
    return _NOT_WORD.sub(" ", normalized).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Tính WER = (số từ thay thế + xóa + chèn) / số từ của văn bản chuẩn.

    0.0 nghĩa là giống hệt; giá trị có thể lớn hơn 1.0 nếu kết quả nhận dạng chèn thêm nhiều từ.

    :param reference: văn bản chuẩn do người nghe và gõ lại
    :param hypothesis: văn bản do model nhận dạng
    :raises ValueError: nếu văn bản chuẩn không có từ nào
    """
    ref = normalize_words(reference)
    hyp = normalize_words(hypothesis)
    if not ref:
        raise ValueError("The reference text has no words.")

    # Khoảng cách chỉnh sửa (Levenshtein) trên từ, chỉ giữ một hàng của bảng quy hoạch động.
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            substitution = previous[j - 1] + (ref_word != hyp_word)
            current[j] = min(substitution, previous[j] + 1, current[j - 1] + 1)
        previous = current
    return previous[len(hyp)] / len(ref)
