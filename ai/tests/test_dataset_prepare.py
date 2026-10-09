"""Tests for the dataset preparation steps: cleaning, duplicate handling and leakage-free splitting.

They run on small made-up rows, so they need neither the downloaded datasets nor the network.
"""

import collections

from tools.dataset_prepare import (
    audit_and_clean,
    clean_text,
    cross_split_leakage,
    duplicate_key,
    near_duplicate_clusters,
    overlap_with,
    split_by_cluster,
    without_speaker_labels,
)

LONG = "tôi gọi từ ngân hàng để thông báo tài khoản của anh có giao dịch lạ anh vui lòng xác nhận giúp tôi ngay bây giờ"


def row(identifier, text, label, **extra):
    base = {"id": identifier, "source": "unit", "domain": "call", "raw_text": text, "raw_label": label,
            "type": "t", "synthetic": True, "rule_tuned": False}
    return {**base, **extra}


def test_clean_text_only_normalises_unicode_and_whitespace():
    assert clean_text("﻿  Xin   chào\n\tanh  ") == "Xin chào anh"
    assert clean_text("khoá") == "khoá"


def test_duplicate_key_ignores_case_and_punctuation():
    assert duplicate_key("Anh ĐỌC mã OTP, cho em!") == duplicate_key("anh đọc mã otp cho em")
    assert duplicate_key("anh đọc mã otp") != duplicate_key("chị đọc mã otp")


def test_speaker_labels_are_removed_only_when_the_text_has_them():
    assert without_speaker_labels("A: Chào anh. B: Chào em. A: Em gọi từ ngân hàng. B: Vâng.") == (
        "Chào anh. Chào em. Em gọi từ ngân hàng. Vâng."
    )
    assert without_speaker_labels("Lưu ý: tài khoản sẽ bị khóa.") == "Lưu ý: tài khoản sẽ bị khóa."


def test_near_duplicates_share_a_cluster_and_different_texts_do_not():
    almost = LONG + " ạ"
    other = "mẹ ơi cuối tuần con về quê ăn giỗ ông nội mẹ có cần con mua gì ở trên này mang về không ạ"

    clusters = near_duplicate_clusters([LONG, other, almost])

    assert clusters[0] == clusters[2] != clusters[1]


def test_exact_duplicates_keep_one_row_and_inherit_the_rule_tuned_flag():
    rows = [row("a", LONG, 1), row("b", LONG.upper() + "!", 1, rule_tuned=True), row("c", "nội dung khác hẳn", 0)]

    cleaned, report = audit_and_clean(rows)

    assert [r["id"] for r in cleaned] == ["a", "c"]
    assert cleaned[0]["rule_tuned"] is True
    assert report["exact_duplicates_removed"] == 1


def test_duplicates_with_conflicting_labels_are_all_removed():
    cleaned, report = audit_and_clean([row("a", LONG, 1), row("b", LONG, 0), row("c", "nội dung khác hẳn", 0)])

    assert [r["id"] for r in cleaned] == ["c"]
    assert report["label_conflicting_duplicates_removed"] == 2


def test_rows_without_text_or_with_an_unknown_label_are_dropped_and_counted():
    rows = [row("a", None, 1), row("b", "   ", 0), row("c", "văn bản hợp lệ", "2"), row("d", "văn bản hợp lệ", "1")]

    cleaned, report = audit_and_clean(rows)

    assert [r["id"] for r in cleaned] == ["d"]
    assert (report["missing_text"], report["empty_text"], report["invalid_label"]) == (1, 1, 1)
    assert report["class_distribution"] == {"NORMAL": 0, "PHISHING": 1, "total": 1}


def _prepared(count=200):
    rows = [row(f"r{i:03}", f"cuộc gọi số {i} nói về chủ đề riêng thứ {i} không giống cuộc nào khác {i * 7}", i % 2,
                type=f"type{i % 4}", rule_tuned=i < 80) for i in range(count)]
    # Hai cặp gần trùng nhau.
    rows += [row("dupA", LONG, 1, type="type1"), row("dupB", LONG + " ạ", 1, type="type1")]
    cleaned, _ = audit_and_clean(rows)
    return cleaned


def test_split_keeps_near_duplicates_together_and_test_free_of_rule_tuned_rows():
    cleaned = _prepared()

    assignment = split_by_cluster(cleaned, stratify="type", test_only_from_untouched=True)

    assert assignment["dupA"] == assignment["dupB"]
    assert cross_split_leakage(cleaned, assignment) == {
        "near_duplicate_clusters_in_more_than_one_split": 0, "identical_texts_in_more_than_one_split": 0,
    }
    assert not any(r["rule_tuned"] for r in cleaned if assignment[r["id"]] == "test")
    sizes = collections.Counter(assignment.values())
    assert sizes["train"] > sizes["test"] > 0 and sizes["validation"] > 0
    assert 0.12 <= sizes["test"] / len(cleaned) <= 0.20


def test_split_is_reproducible():
    first = split_by_cluster(_prepared(), stratify="type", test_only_from_untouched=True)
    second = split_by_cluster(_prepared(), stratify="type", test_only_from_untouched=True)

    assert first == second


def test_overlap_counts_reference_rows_that_nearly_match_another_set():
    reference = [{"text": LONG}, {"text": "một câu hoàn toàn khác không liên quan gì tới câu kia cả"}]

    assert overlap_with(reference, [{"text": LONG + " ạ"}]) == 1
    assert overlap_with(reference, [{"text": "văn bản thứ ba cũng chẳng giống cái nào"}]) == 0


def test_real_calls_follow_the_split_recorded_for_their_video():
    from tools.dataset_prepare import split_real_calls

    rows = [{"id": "yt-a-0", "fixed_split": "train"}, {"id": "yt-b-0", "fixed_split": "test"}]

    assert split_real_calls(rows) == {"yt-a-0": "train", "yt-b-0": "test_real_calls"}


def test_cutting_a_call_out_of_a_transcript_keeps_only_segments_inside_the_range():
    from tools.youtube_calls_build import cut

    segments = [{"start": 0, "end": 30, "text": "lời dẫn của kênh"}, {"start": 30, "end": 60, "text": "alo em gọi từ"},
                {"start": 60, "end": 90, "text": "ngân hàng ạ"}, {"start": 90, "end": 100, "text": "nhớ đăng ký kênh"}]

    assert cut(segments, 30, 90) == "alo em gọi từ ngân hàng ạ"
    assert cut(segments, 200, 300) == ""


def test_transcript_corrections_trim_narration_fix_misheard_words_and_collapse_loops():
    from tools.youtube_calls_build import collapse_repeats, correct

    corrections = {
        "everywhere": [["trụ thưởng", "trúng thưởng"]],
        "videos": {"v1": {"start_at": "a lô", "end_after": "chuyển khoản nhé", "remove": ["nhớ đăng ký kênh "]}},
    }
    raw = "lời dẫn của kênh a lô anh đã trụ thưởng nhớ đăng ký kênh mặc mặc mặc mặc mặc mặc anh chuyển khoản nhé cảm ơn"

    assert correct(raw, "v1", corrections) == "a lô anh đã trúng thưởng mặc mặc mặc anh chuyển khoản nhé"
    # A video without its own entry still gets the global fixes.
    assert correct("anh đã trụ thưởng", "other", corrections) == "anh đã trúng thưởng"
    assert collapse_repeats("vâng vâng ạ") == "vâng vâng ạ"
