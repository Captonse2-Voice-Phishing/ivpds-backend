import unicodedata

import pytest

from app.evaluation import normalize_words, word_error_rate


def test_identical_text_has_zero_error():
    assert word_error_rate("Anh đọc mã OTP tôi vừa gửi", "Anh đọc mã OTP tôi vừa gửi") == 0.0


def test_case_and_punctuation_do_not_count_as_errors():
    assert word_error_rate("Tôi gọi từ ngân hàng.", "tôi gọi, từ ngân hàng!") == 0.0


def test_unicode_composition_does_not_count_as_an_error():
    composed = "ngân hàng"
    # The same letters written as base letters followed by combining marks.
    decomposed = unicodedata.normalize("NFD", composed)

    assert composed != decomposed
    assert word_error_rate(composed, decomposed) == 0.0


def test_tone_marks_are_significant():
    # "ma", "má" and "mã" are different Vietnamese words.
    assert word_error_rate("đọc mã", "đọc ma") == 0.5


@pytest.mark.parametrize(("reference", "hypothesis", "expected"), [
    ("một hai ba bốn", "một hai ba", 0.25),            # one deletion
    ("một hai ba bốn", "một hai ba bốn năm", 0.25),    # one insertion
    ("một hai ba bốn", "một hai sáu bốn", 0.25),       # one substitution
    ("một hai ba bốn", "", 1.0),                       # nothing recognised
    ("một hai", "ba bốn năm sáu", 2.0),                # more errors than reference words
])
def test_error_rate_counts_substitutions_deletions_and_insertions(reference, hypothesis, expected):
    assert word_error_rate(reference, hypothesis) == expected


def test_empty_reference_is_an_error_not_a_score():
    with pytest.raises(ValueError):
        word_error_rate("  ...  ", "anything")


def test_normalize_words_splits_on_whitespace_and_punctuation():
    assert normalize_words("  Chuyển tiền NGAY,\nnếu không... ") == ["chuyển", "tiền", "ngay", "nếu", "không"]
