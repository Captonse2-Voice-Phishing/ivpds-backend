"""Tests for the generator of Vietnamese-context synthetic conversations."""

import collections
import re

from app.rules import RuleEngine, Severity, Turn
from tools.dataset_synthesize_vi import NORMAL, PER_FAMILY, SCAM, VALIDATION_FAMILIES, generate

ROWS = generate()


def test_generation_is_reproducible():
    assert generate() == ROWS


def test_every_scenario_family_is_generated_with_the_right_label():
    labels = collections.defaultdict(set)
    for row in ROWS:
        labels[row["family"]].add(row["label"])

    assert set(labels) == set(SCAM) | set(NORMAL)
    assert all(labels[family] == {1} for family in SCAM)
    assert all(labels[family] == {0} for family in NORMAL)
    assert not set(SCAM) & set(NORMAL)


def test_no_placeholder_is_left_unfilled_and_ids_are_unique():
    assert len({row["id"] for row in ROWS}) == len(ROWS)
    for row in ROWS:
        for speaker, text in row["turns"]:
            assert speaker and text
            assert not re.search(r"[{}]", text), text
            assert text[0] == text[0].upper()


def test_conversations_within_a_family_are_distinct_and_capped():
    by_family = collections.defaultdict(list)
    for row in ROWS:
        by_family[row["family"]].append(" ".join(text for _, text in row["turns"]))

    for family, texts in by_family.items():
        assert len(texts) == len(set(texts)), family
        assert 1 <= len(texts) <= PER_FAMILY


def test_validation_scenarios_never_appear_in_train():
    splits = collections.defaultdict(set)
    for row in ROWS:
        splits[row["family"]].add(row["split"])

    assert all(len(found) == 1 for found in splits.values())
    assert {family for family, found in splits.items() if found == {"validation"}} == VALIDATION_FAMILIES
    # Validation must hold both classes, otherwise it cannot measure anything.
    assert {row["label"] for row in ROWS if row["split"] == "validation"} == {0, 1}


def test_some_conversations_have_three_speakers():
    three = [row for row in ROWS if len({speaker for speaker, _ in row["turns"]}) >= 3]

    assert len(three) > 100
    assert {row["label"] for row in three} == {0, 1}


def test_generated_normal_calls_rarely_look_like_scams_to_the_rule_engine():
    # A sanity check on the scripts themselves: a "normal" script that trips a HIGH rule is probably mislabelled.
    # Ba nhóm dưới đây cố ý chứa từ ngữ lừa đảo trong một cuộc gọi bình thường (kể lại, cảnh báo, khách tự hỏi
    # "có cần cung cấp số thẻ không"), để model NLP không học theo từ khóa. Rule Engine bắt theo cụm từ nên gắn
    # HIGH cho chúng; đó là giới hạn đã biết của Rule Engine, không phải nhãn sai.
    quoted_scam_vocabulary = {"kể chuyện bị gọi lừa đảo", "ngân hàng thật cảnh báo lừa đảo",
                              "hoàn tiền đơn hàng (hợp pháp)"}
    engine = RuleEngine()
    flagged = [
        row["id"] for row in ROWS if row["label"] == 0 and row["family"] not in quoted_scam_vocabulary
        and any(m.severity == Severity.HIGH
                for m in engine.analyze_conversation([Turn(s, t) for s, t in row["turns"]]).indicators)
    ]

    assert flagged == []
