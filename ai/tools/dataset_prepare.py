"""Kiểm tra, làm sạch và chia các dataset đã phê duyệt thành train / validation / test cho NLP Model.

Cách dùng (chạy từ thư mục ``ai``, sau ``tools.dataset_download``):

    docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test \
        python -m tools.dataset_prepare

Đọc ``data/raw/`` (không sửa), ghi ``data/processed/{train,validation,validation_vi_context,test,test_vi_context,test_real_calls}.jsonl`` và báo cáo
kiểm tra ``data/processed/AUDIT.json``. Mọi con số trong báo cáo đều được đếm từ dữ liệu thật.

Các quyết định chính:

* Chỉ dùng dữ liệu cuộc gọi. Tin nhắn SMS không được đưa vào (quyết định của chủ dự án).
* Nhãn nhị phân: 0 = NORMAL, 1 = PHISHING, theo cột ``label`` gốc.
* Bản ghi trùng hoàn toàn (sau khi chuẩn hóa) chỉ giữ một. Các bản ghi gần trùng (Jaccard >= 0.85 trên cụm
  3 từ) được giữ nhưng xếp chung một cụm, và cả cụm luôn nằm trong cùng một tập để không rò rỉ.
* Mỗi dòng của bộ hội thoại là trọn một cuộc gọi, nên chia theo dòng cũng là chia theo cuộc gọi.
* Tập test của bộ hội thoại chỉ lấy từ những cuộc chưa từng được đọc khi chỉnh Rule Engine, để sau này
  so sánh luật với model trên dữ liệu mà cả hai đều chưa thấy.
* Hội thoại bối cảnh Việt Nam do ``tools.dataset_synthesize_vi`` sinh ra (``synthetic = true``) chỉ vào train
  và validation, chia theo kịch bản: các kịch bản dành cho validation không xuất hiện trong train.
* Transcript cuộc gọi thật lấy từ YouTube (``synthetic = false``, chưa có người nghe kiểm tra) được chia
  theo video (ghi sẵn trong file chọn đoạn): một phần vào train, phần còn lại thành tập test riêng ``test_real_calls.jsonl``.
* Lời nói tiếng Việt thường ngày (VLSP 2020, dữ liệu thật) làm mẫu NORMAL: một phần giữ từng câu, một phần ghép
  các câu liền nhau thành đoạn dài như một cuộc gọi. Chia theo trang đã định sẵn khi tải; các trang dùng làm
  bộ test không bao giờ được tải về đây.
* 150 hội thoại bối cảnh Việt Nam viết tay (``synthetic = true``) chỉ dùng để test, không vào train.
"""

import collections
import hashlib
import json
import random
import re
import statistics
import sys
import unicodedata
from pathlib import Path

from app.rules import parse_turns

RAW = Path("data/raw")
OUT = Path("data/processed")
VI_CONTEXT = Path("tests/data/conversations_vi.jsonl")
RULE_TUNING = Path("data/rule_tuning_rows.json")
GENERATED = Path("data/synthetic/vi_generated.jsonl")
YOUTUBE_CALLS = RAW / "youtube_calls" / "calls.jsonl"
ORDINARY_SPEECH = RAW / "vlsp2020_vinai_100h" / "rows.jsonl"

SEED = 20261008
NEAR_DUPLICATE_JACCARD = 0.85
TEST_SHARE = 0.15
VALIDATION_SHARE = 0.15
LABEL_NAMES = {0: "NORMAL", 1: "PHISHING"}

_WORD = re.compile(r"\w+")
_VIETNAMESE_MARK = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)
_PII_PATTERNS = {
    "phone_number": re.compile(r"(?<!\d)(?:\+?84|0)\d{8,10}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "url": re.compile(r"https?://\S+|www\.\S+"),
    "long_digit_run": re.compile(r"(?<!\d)\d{9,}(?!\d)"),
}


# ------------------------------------------------------------------------------- xử lý văn bản


def clean_text(text: str) -> str:
    """Chuẩn hóa nhẹ để lưu: Unicode dựng sẵn, bỏ ký tự điều khiển, gộp khoảng trắng. Không đổi nội dung."""
    text = unicodedata.normalize("NFC", text).replace("\ufeff", "")
    return " ".join(text.split())


def duplicate_key(text: str) -> str:
    """Khóa so trùng: chỉ giữ chữ và số, viết thường. Hai bản ghi cùng khóa là trùng hoàn toàn."""
    return " ".join(_WORD.findall(unicodedata.normalize("NFC", text).lower()))


def shingles(text: str, size: int = 3) -> frozenset[int]:
    """Tập các cụm ``size`` từ liên tiếp (dạng băm), dùng để đo độ giống nhau giữa hai văn bản."""
    words = duplicate_key(text).split()
    if len(words) < size:
        return frozenset({hash(" ".join(words))})
    return frozenset(hash(" ".join(words[i:i + size])) for i in range(len(words) - size + 1))


def without_speaker_labels(text: str) -> str:
    """Bỏ nhãn người nói ("A:", "caller:") để văn bản giống transcript mà Whisper trả về."""
    turns = parse_turns(text)
    return " ".join(turn.text for turn in turns) if turns else text


def near_duplicate_clusters(texts: list[str], threshold: float = NEAR_DUPLICATE_JACCARD) -> list[int]:
    """Gán mỗi văn bản một số cụm; hai văn bản có Jaccard >= ``threshold`` thuộc cùng cụm.

    So từng cặp, nhưng bỏ qua các cặp có độ dài chênh nhau quá nhiều vì chắc chắn không đạt ngưỡng.
    """
    sets = [shingles(text) for text in texts]
    order = sorted(range(len(texts)), key=lambda i: len(sets[i]))
    parent = list(range(len(texts)))

    def find(node: int) -> int:
        """Tìm đại diện của nhóm chứa ``node`` (union-find, có nén đường đi)."""
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for position, i in enumerate(order):
        size_i = len(sets[i])
        for j in order[position + 1:]:
            size_j = len(sets[j])
            if size_i < threshold * size_j:
                break  # các văn bản phía sau còn dài hơn nữa
            common = len(sets[i] & sets[j])
            if common >= threshold * (size_i + size_j - common):
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(texts))]


# ----------------------------------------------------------------------------------- đọc nguồn


def load_dialogues() -> list[dict]:
    """Bộ hội thoại điện thoại (tổng hợp, dịch máy). Cột ``output`` là lời giải thích nhãn nên bị bỏ."""
    rows = json.loads((RAW / "adamtc_scam_dialogues" / "scam-dialogues-train-text.json").read_text(encoding="utf-8"))
    tuned = set(json.loads(RULE_TUNING.read_text(encoding="utf-8"))["rows"])
    return [
        {"id": f"dlg-{index}", "source": "adamtc_scam_dialogues", "domain": "call", "raw_text": row.get("dialogue"),
         "raw_label": row.get("label"), "type": row.get("type"), "synthetic": True, "rule_tuned": index in tuned}
        for index, row in enumerate(rows)
    ]


def load_vi_context() -> list[dict]:
    """150 hội thoại bối cảnh Việt Nam do dự án tự viết: chỉ để test."""
    rows = [json.loads(line) for line in VI_CONTEXT.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [
        {"id": row["id"], "source": "ivpds_authored", "domain": "call",
         "raw_text": " ".join(f"{speaker}: {text}" for speaker, text in row["turns"]), "raw_label": row["label"],
         "type": row["group"], "synthetic": True, "rule_tuned": row.get("split") == "dev",
         "speakers": len({speaker for speaker, _ in row["turns"]}),
         "plain": " ".join(text for _, text in row["turns"])}
        for row in rows
    ]


_LISTENER_LABELS = {"B", "Người nghe", "Bên nghe"}
# Các kịch bản bình thường có nhắc lại lời kẻ lừa đảo ("có người đòi con đọc mã OTP"). Chỉ cả cuộc gọi mới cho thấy
# đó là lời kể hay lời dặn; một câu cắt rời thì giống hệt lời lừa đảo, nên không cắt đoạn ngắn từ các kịch bản này.
_CONTEXT_ONLY_FAMILIES = {"kể chuyện bị gọi lừa đảo", "dặn người nhà cảnh giác", "ngân hàng thật cảnh báo lừa đảo"}


def load_generated() -> list[dict]:
    """Hội thoại bối cảnh Việt Nam do dự án sinh ra theo kịch bản; tập của mỗi dòng đã được định sẵn theo kịch bản.

    Ngoài hội thoại đầy đủ, mỗi hội thoại còn cho ra các đoạn ngắn (một hoặc hai lượt lời). Lý do: mọi mẫu lừa đảo
    trong dữ liệu đều dài, còn mẫu bình thường có nhiều câu ngắn, nên model từng học lối tắt "ngắn là bình thường"
    và bỏ sót những câu như "anh đọc mã OTP cho em". Đoạn ngắn của hội thoại lừa đảo chỉ lấy lời kẻ gọi và bỏ câu
    mở đầu, vì câu mở đầu thường chỉ là lời chào hay nêu vấn đề mà nhân viên thật cũng nói. Với cặp kịch bản cùng
    chủ đề, bản hợp pháp cũng bỏ hai lượt mở đầu dùng chung: cắt rời ra thì không biết chúng thuộc bản nào.
    """
    rows = [json.loads(line) for line in GENERATED.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(SEED)
    documents = []
    for row in rows:
        base = {"source": "ivpds_generated_vi", "domain": "call", "raw_label": row["label"], "type": row["family"],
                "synthetic": True, "rule_tuned": False, "fixed_split": row["split"]}
        turns = row["turns"]
        documents.append({
            **base, "id": row["id"], "short": False,
            "raw_text": " ".join(f"{speaker}: {text}" for speaker, text in turns),
            "speakers": len({speaker for speaker, _ in turns}), "plain": " ".join(text for _, text in turns),
        })
        if row["label"] == 1:
            pool = [text for speaker, text in turns if speaker not in _LISTENER_LABELS][1:]
            wanted = 2
        elif row["family"] in _CONTEXT_ONLY_FAMILIES:
            pool, wanted = [], 0
        elif row["family"].endswith("(hợp pháp)"):
            pool, wanted = [text for _, text in turns][2:], 1
        else:
            pool = [text for _, text in turns]
            wanted = 1
        for number in range(wanted):
            if not pool:
                break
            start = rng.randrange(len(pool))
            snippet = " ".join(pool[start:start + rng.randint(1, 2)])
            documents.append({**base, "id": f"{row['id']}-s{number}", "short": True, "raw_text": snippet,
                              "speakers": 1, "plain": snippet})
    return documents


def load_ordinary_speech() -> list[dict]:
    """Lời nói thường ngày từ VLSP 2020 làm mẫu NORMAL thật. Trả về danh sách rỗng nếu chưa tải.

    Model từng coi mọi văn bản lạ là lừa đảo vì lớp NORMAL trong dữ liệu chỉ có vài chủ đề. Nguồn này cho nó thấy
    tiếng Việt nói bình thường về đủ thứ chuyện. Mỗi trang 100 câu: 30 câu đầu giữ riêng từng câu, phần còn lại
    ghép 3-12 câu liền nhau thành một đoạn dài (các câu là thật, việc ghép là nhân tạo; đánh dấu ``composed``).
    """
    if not ORDINARY_SPEECH.exists():
        return []
    rows = [json.loads(line) for line in ORDINARY_SPEECH.read_text(encoding="utf-8").splitlines() if line.strip()]
    pages: dict[int, list[dict]] = collections.defaultdict(list)
    for row in rows:
        if len(row["text"].split()) >= 6:
            pages[row["page"]].append(row)
    rng = random.Random(SEED)
    documents = []
    for page in sorted(pages):
        items = sorted(pages[page], key=lambda row: row["index"])
        pieces = [[row] for row in items[:30]]
        rest = items[30:]
        while rest:
            size = rng.randint(3, 12)
            pieces.append(rest[:size])
            rest = rest[size:]
        for number, piece in enumerate(pieces):
            text = " ".join(row["text"] for row in piece)
            documents.append({
                "id": f"vlsp-{page}-{number}", "source": "vlsp_ordinary_speech", "domain": "speech",
                "raw_text": text, "raw_label": 0, "plain": text, "synthetic": False, "rule_tuned": False,
                "type": "lời nói thường ngày (ghép nhiều câu)" if len(piece) > 1 else "lời nói thường ngày",
                "composed": len(piece) > 1, "fixed_split": items[0]["split"], "page": page,
            })
    return documents


def load_youtube_calls() -> list[dict]:
    """Transcript cuộc gọi thật do ``tools.youtube_calls_build`` cắt ra. Trả về danh sách rỗng nếu chưa thu thập."""
    if not YOUTUBE_CALLS.exists():
        return []
    rows = [json.loads(line) for line in YOUTUBE_CALLS.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [
        {"id": row["id"], "source": "youtube_calls", "domain": "call", "raw_text": row["text"],
         "raw_label": row["label"], "type": row["type"], "synthetic": False, "rule_tuned": False,
         "plain": row["text"], "fixed_split": row["split"], "text_asr": row["text_asr"], "video_id": row["video_id"], "url": row["url"], "staged": row["staged"],
         "human_verified": row["human_verified"]}
        for row in rows
    ]


def split_real_calls(rows: list[dict]) -> dict[str, str]:
    """Tập của mỗi cuộc gọi thật được ghi sẵn theo video trong file chọn đoạn, để tập test không bao giờ thay đổi."""
    return {row["id"]: "test_real_calls" if row["fixed_split"] == "test" else "train" for row in rows}


# ------------------------------------------------------------------------------------ kiểm tra


def _percentiles(values: list[int]) -> dict:
    """Thống kê độ dài: nhỏ nhất, phân vị 5%, trung vị, phân vị 95%, lớn nhất và trung bình."""
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {"min": ordered[0], "p05": pick(0.05), "median": pick(0.5), "p95": pick(0.95), "max": ordered[-1],
            "mean": round(statistics.fmean(ordered), 1)}


def audit_and_clean(rows: list[dict]) -> tuple[list[dict], dict]:
    """Kiểm tra một nguồn dữ liệu, bỏ bản ghi lỗi và trùng, gắn cụm gần trùng. Trả về (dữ liệu sạch, báo cáo)."""
    report: dict = {"rows_in_raw_file": len(rows)}
    labels = collections.Counter(str(row["raw_label"]) for row in rows)
    report["raw_label_values"] = dict(labels)

    kept, missing_text, empty_text, bad_label = [], 0, 0, 0
    for row in rows:
        if row["raw_text"] is None:
            missing_text += 1
            continue
        text = clean_text(str(row["raw_text"]))
        if not text:
            empty_text += 1
            continue
        if str(row["raw_label"]).strip() not in {"0", "1"}:
            bad_label += 1
            continue
        kept.append({**row, "text": text, "label": int(str(row["raw_label"]).strip())})
    report.update(missing_text=missing_text, empty_text=empty_text, invalid_label=bad_label)

    # Trùng hoàn toàn: giữ bản đầu tiên. Nếu các bản trùng mang nhãn khác nhau thì bỏ hết vì không biết nhãn nào đúng.
    by_key: dict[str, list[dict]] = collections.defaultdict(list)
    for row in kept:
        by_key[duplicate_key(row["text"])].append(row)
    unique, exact_removed, conflicting_removed = [], 0, 0
    for group in by_key.values():
        if len({row["label"] for row in group}) > 1:
            conflicting_removed += len(group)
            continue
        first = dict(group[0])
        # Một bản ghi được coi là "đã dùng để chỉnh luật" nếu bất kỳ bản trùng nào của nó đã được dùng.
        first["rule_tuned"] = any(row["rule_tuned"] for row in group)
        unique.append(first)
        exact_removed += len(group) - 1
    report.update(exact_duplicates_removed=exact_removed, label_conflicting_duplicates_removed=conflicting_removed)

    clusters = near_duplicate_clusters([row["text"] for row in unique])
    sizes = collections.Counter(clusters)
    labels_in_cluster: dict[int, set[int]] = collections.defaultdict(set)
    for row, cluster in zip(unique, clusters):
        row["cluster"] = f"{row['source']}-{cluster}"
        labels_in_cluster[cluster].add(row["label"])
    report["near_duplicates"] = {
        "threshold_jaccard": NEAR_DUPLICATE_JACCARD,
        "clusters_with_more_than_one_row": sum(1 for size in sizes.values() if size > 1),
        "rows_in_such_clusters": sum(size for size in sizes.values() if size > 1),
        "largest_cluster": max(sizes.values()),
        "clusters_mixing_both_labels": sum(1 for found in labels_in_cluster.values() if len(found) > 1),
    }

    words = [len(row["text"].split()) for row in unique]
    report["length_in_words"] = _percentiles(words)
    report["shorter_than_3_words"] = sum(1 for count in words if count < 3)
    report["longer_than_1500_words"] = sum(1 for count in words if count > 1500)
    report["without_vietnamese_diacritics"] = sum(1 for row in unique if not _VIETNAMESE_MARK.search(row["text"]))
    report["rows_containing"] = {
        name: sum(1 for row in unique if pattern.search(row["text"])) for name, pattern in _PII_PATTERNS.items()
    }
    report["rows_after_cleaning"] = len(unique)
    report["class_distribution"] = _distribution(unique)
    report["by_type"] = {
        kind: _distribution([row for row in unique if row["type"] == kind])
        for kind in sorted({row["type"] for row in unique})
    }
    return unique, report


def _distribution(rows: list[dict]) -> dict:
    """Đếm số dòng của từng nhãn (NORMAL, PHISHING) và tổng số dòng."""
    counts = collections.Counter(row["label"] for row in rows)
    return {"NORMAL": counts[0], "PHISHING": counts[1], "total": len(rows)}


# ------------------------------------------------------------------------------------- chia tập


def split_by_cluster(rows: list[dict], *, stratify: str, test_only_from_untouched: bool) -> dict[str, str]:
    """Chia train / validation / test theo cụm gần trùng. Trả về ``{id: tên tập}``.

    ``stratify`` là tên trường dùng để giữ tỉ lệ (loại kịch bản). Với ``test_only_from_untouched`` tập test
    chỉ lấy các cụm không có bản ghi nào từng được đọc khi chỉnh Rule Engine.
    """
    clusters: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        clusters[row["cluster"]].append(row)
    by_stratum: dict[str, list[list[dict]]] = collections.defaultdict(list)
    for members in clusters.values():
        strata = collections.Counter(str(row[stratify]) for row in members)
        by_stratum[strata.most_common(1)[0][0]].append(members)

    rng = random.Random(SEED)
    assignment: dict[str, str] = {}
    for stratum in sorted(by_stratum):
        groups = sorted(by_stratum[stratum], key=lambda members: members[0]["id"])
        rng.shuffle(groups)
        total = sum(len(members) for members in groups)
        chosen: dict[str, list[list[dict]]] = {"test": [], "validation": [], "train": []}
        eligible = [m for m in groups if not test_only_from_untouched or not any(r["rule_tuned"] for r in m)]
        count = 0
        for members in eligible:
            if count >= TEST_SHARE * total:
                break
            chosen["test"].append(members)
            count += len(members)
        taken = {id(members) for members in chosen["test"]}
        remaining = [m for m in groups if id(m) not in taken]
        count = 0
        for members in remaining:
            target = "validation" if count < VALIDATION_SHARE * total else "train"
            chosen[target].append(members)
            if target == "validation":
                count += len(members)
        for name, selected in chosen.items():
            for members in selected:
                for row in members:
                    assignment[row["id"]] = name
    return assignment


def cross_split_leakage(rows: list[dict], assignment: dict[str, str]) -> dict:
    """Đếm số cụm gần trùng và số văn bản trùng nằm ở hơn một tập. Kết quả đúng phải bằng 0."""
    splits_of_cluster: dict[str, set[str]] = collections.defaultdict(set)
    splits_of_text: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        splits_of_cluster[row["cluster"]].add(assignment[row["id"]])
        splits_of_text[duplicate_key(row["text"])].add(assignment[row["id"]])
    return {
        "near_duplicate_clusters_in_more_than_one_split": sum(1 for s in splits_of_cluster.values() if len(s) > 1),
        "identical_texts_in_more_than_one_split": sum(1 for s in splits_of_text.values() if len(s) > 1),
    }


def overlap_with(reference: list[dict], others: list[dict], threshold: float = NEAR_DUPLICATE_JACCARD) -> int:
    """Số bản ghi trong ``reference`` có độ giống (Jaccard) từ ``threshold`` trở lên với một bản ghi trong ``others``."""
    other_sets = [shingles(row["text"]) for row in others]
    found = 0
    for row in reference:
        mine = shingles(row["text"])
        for theirs in other_sets:
            common = len(mine & theirs)
            if common and common >= threshold * (len(mine) + len(theirs) - common):
                found += 1
                break
    return found


# ---------------------------------------------------------------------------------------- chạy


def _record(row: dict) -> dict:
    """Chuyển một dòng nội bộ thành bản ghi sẽ ghi ra file: chỉ giữ các trường dùng cho huấn luyện và truy vết."""
    plain = row.get("plain") or without_speaker_labels(row["text"])
    record = {
        "id": row["id"], "source": row["source"], "domain": row["domain"], "type": row["type"],
        "label": row["label"], "label_name": LABEL_NAMES[row["label"]], "synthetic": row["synthetic"],
        "rule_tuned": row["rule_tuned"], "cluster": row["cluster"],
        # ``text`` giữ nhãn người nói như bản gốc; ``text_plain`` bỏ nhãn, giống transcript của Whisper.
        "text": row["text"], "text_plain": clean_text(plain),
    }
    for extra in ("speakers", "video_id", "url", "staged", "human_verified", "text_asr", "composed", "short"):
        if extra in row:
            record[extra] = row[extra]
    return record


def _write(name: str, rows: list[dict]) -> dict:
    """Ghi một tập ra file JSONL và trả về tên file, số dòng, mã SHA-256 để ghi vào AUDIT.json."""
    path = OUT / name
    content = "".join(json.dumps(_record(row), ensure_ascii=False) + "\n" for row in rows)
    path.write_bytes(content.encode("utf-8"))
    return {"file": name, "rows": len(rows), "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def main() -> int:
    """Đọc các nguồn, làm sạch, bỏ trùng, kiểm tra rò rỉ, chia tập, rồi ghi các file JSONL và AUDIT.json."""
    OUT.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((RAW / "PROVENANCE.json").read_text(encoding="utf-8"))
    audit: dict = {"seed": SEED, "label_schema": LABEL_NAMES, "sources": {}}

    dialogues, audit["sources"]["adamtc_scam_dialogues"] = audit_and_clean(load_dialogues())
    vi_context, audit["sources"]["ivpds_authored"] = audit_and_clean(load_vi_context())
    audit["sources"]["adamtc_scam_dialogues"]["provenance"] = {
        k: provenance["adamtc_scam_dialogues"][k] for k in ("page", "revision", "license")
    }
    audit["sources"]["adamtc_scam_dialogues"]["label_mapping"] = "0 -> NORMAL, 1 -> PHISHING (theo cột label gốc)"
    audit["sources"]["adamtc_scam_dialogues"]["rows_read_while_tuning_rules"] = sum(r["rule_tuned"] for r in dialogues)

    generated, audit["sources"]["ivpds_generated_vi"] = audit_and_clean(load_generated())
    audit["sources"]["ivpds_generated_vi"]["note"] = (
        "Sinh theo kịch bản bằng tools.dataset_synthesize_vi; các hội thoại cùng kịch bản giống nhau về ý."
    )
    audit["sources"]["ivpds_generated_vi"]["scenario_families"] = {
        "PHISHING": len({row["type"] for row in generated if row["label"] == 1}),
        "NORMAL": len({row["type"] for row in generated if row["label"] == 0}),
    }

    assignment = split_by_cluster(dialogues, stratify="type", test_only_from_untouched=True)
    for row in generated:
        # Chia theo kịch bản: cả kịch bản là một cụm, và tập của nó đã được định sẵn khi sinh.
        row["cluster"] = f"ivpds_generated_vi-{row['type']}"
        assignment[row["id"]] = row["fixed_split"]
    real_calls, audit["sources"]["youtube_calls"] = audit_and_clean(load_youtube_calls()) if YOUTUBE_CALLS.exists()         else ([], {"rows_in_raw_file": 0, "note": "Chưa thu thập (chạy tools.youtube_calls_collect và _build)."})
    if real_calls:
        audit["sources"]["youtube_calls"] |= {
            "note": "Transcript PhoWhisper của ghi âm công khai trên YouTube; mốc cắt chọn bằng cách đọc transcript.",
            "videos": len({row["video_id"] for row in real_calls}),
            "human_verified_rows": sum(1 for row in real_calls if row["human_verified"]),
            "rows_marked_as_staged": sum(1 for row in real_calls if row["staged"]),
        }
        for row in real_calls:
            row["cluster"] = f"youtube_calls-{row['video_id']}"  # cả video nằm trong một tập
        assignment |= split_real_calls(real_calls)
    ordinary, audit["sources"]["vlsp_ordinary_speech"] = audit_and_clean(load_ordinary_speech())         if ORDINARY_SPEECH.exists() else ([], {"rows_in_raw_file": 0, "note": "Chưa tải (chạy tools.dataset_fetch_vlsp)."})
    if ordinary:
        audit["sources"]["vlsp_ordinary_speech"] |= {
            "note": "Transcript lời nói thường ngày, dữ liệu thật; nhãn NORMAL. Đoạn dài là các câu thật ghép lại.",
            "composed_documents": sum(1 for row in ordinary if row["composed"]),
            "pages": len({row["page"] for row in ordinary}),
        }
        for row in ordinary:
            row["cluster"] = f"vlsp_ordinary_speech-{row['page']}"  # cả trang nằm trong một tập
            assignment[row["id"]] = row["fixed_split"]
    training_rows = dialogues + generated + real_calls + ordinary

    audit["leakage"] = {
        "adamtc_scam_dialogues": cross_split_leakage(dialogues, assignment),
        "ivpds_generated_vi": cross_split_leakage(generated, assignment),
        "youtube_calls": cross_split_leakage(real_calls, assignment) if real_calls else None,
        "vlsp_ordinary_speech": cross_split_leakage(ordinary, assignment) if ordinary else None,
        "generated_scenario_families_in_both_train_and_validation": len(
            {row["type"] for row in generated if row["fixed_split"] == "train"}
            & {row["type"] for row in generated if row["fixed_split"] == "validation"}
        ),
        "test_rows_read_while_tuning_rules": sum(
            1 for row in dialogues if assignment[row["id"]] == "test" and row["rule_tuned"]
        ),
        "vi_context_rows_near_duplicate_of_any_training_row": overlap_with(vi_context, training_rows),
        # Bộ test viết tay và bộ sinh có cùng tác giả, nên đo thêm ở ngưỡng lỏng để biết mức giống nhau về câu chữ.
        "vi_context_rows_with_jaccard_0_30_or_more_to_a_generated_row": overlap_with(vi_context, generated, 0.30),
    }

    audit["splits"], audit["files"] = {}, []
    for split in ("train", "validation", "test", "test_real_calls"):
        selected = [row for row in training_rows if assignment[row["id"]] == split]
        audit["files"].append(_write(f"{split}.jsonl", selected))
        audit["splits"][split] = {
            "all": _distribution(selected),
            **{source: _distribution([row for row in selected if row["source"] == source])
               for source in ("adamtc_scam_dialogues", "ivpds_generated_vi", "youtube_calls",
                              "vlsp_ordinary_speech")},
        }
    # Hội thoại Việt Nam viết tay: 100 cuộc đã dùng khi chỉnh Rule Engine làm tập validation khó (dùng để chọn
    # model, vì tập validation tổng hợp quá dễ), 50 cuộc chưa từng dùng vào việc gì làm tập test.
    for name, part in (("validation_vi_context", [row for row in vi_context if row["rule_tuned"]]),
                       ("test_vi_context", [row for row in vi_context if not row["rule_tuned"]])):
        audit["files"].append(_write(f"{name}.jsonl", part))
        audit["splits"][name] = {
            "all": _distribution(part),
            "three_or_more_speakers": _distribution([row for row in part if row["speakers"] >= 3]),
        }

    used = training_rows
    audit["synthetic_share_of_train_validation_test"] = {
        "real_samples": sum(1 for row in used if not row["synthetic"]),
        "synthetic_samples": sum(1 for row in used if row["synthetic"]),
        "total": len(used),
        "synthetic_percentage": round(100 * sum(1 for row in used if row["synthetic"]) / len(used), 1),
    }
    (OUT / "AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
