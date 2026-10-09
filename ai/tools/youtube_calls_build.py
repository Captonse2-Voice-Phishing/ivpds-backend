"""Cắt các đoạn cuộc gọi đã chọn ra khỏi transcript YouTube và ghi thành một nguồn dữ liệu có nhãn.

Cách dùng (chạy từ thư mục ``ai``, sau ``tools.youtube_calls_collect``):

    docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test \
        python -m tools.youtube_calls_build

Đọc ``data/youtube_calls_selection.json`` (được đưa vào git): với mỗi video, danh sách đoạn ``[bắt đầu, kết
thúc]`` tính bằng giây chứa đúng một cuộc gọi, kèm nhãn và loại kịch bản. File này chỉ chứa mã video và mốc
thời gian, không chứa nội dung, nên chia sẻ được. Nội dung được lấy từ ``data/raw/youtube_calls/transcripts/``
(không vào git) và ghi ra ``data/raw/youtube_calls/calls.jsonl``.

Sau khi cắt, văn bản được sửa theo ``data/youtube_calls_corrections.json``: bỏ lời dẫn của người đăng video ở
đầu/cuối, thay các cụm PhoWhisper nghe nhầm ("trụ thưởng" -> "trúng thưởng"), rút gọn chuỗi từ lặp. Bản gốc
của PhoWhisper được giữ trong ``text_asr``.

Các mốc thời gian và chỗ sửa do người làm dự án chọn bằng cách đọc transcript, CHƯA có ai nghe lại âm thanh
để kiểm tra; mỗi dòng vì thế mang ``human_verified = false``.
"""

import json
import sys
from pathlib import Path

SELECTION = Path("data/youtube_calls_selection.json")
TRANSCRIPTS = Path("data/raw/youtube_calls/transcripts")
OUT = Path("data/raw/youtube_calls/calls.jsonl")
CORRECTIONS = Path("data/youtube_calls_corrections.json")


def cut(segments: list[dict], start: float, end: float) -> str:
    """Nối các đoạn transcript có điểm giữa nằm trong khoảng ``[start, end]``."""
    return " ".join(
        segment["text"].strip() for segment in segments if start <= (segment["start"] + segment["end"]) / 2 <= end
    ).strip()


def collapse_repeats(text: str, limit: int = 3) -> str:
    """Rút gọn chuỗi một từ bị lặp quá ``limit`` lần liên tiếp ("mặc mặc mặc ..."), lỗi hay gặp của Whisper."""
    kept: list[str] = []
    run = 0
    for word in text.split():
        run = run + 1 if kept and word == kept[-1] else 1
        if run <= limit:
            kept.append(word)
    return " ".join(kept)


def correct(text: str, video_id: str, corrections: dict) -> str:
    """Áp các chỗ sửa đã ghi trong file sửa lỗi: cắt lời dẫn đầu/cuối, thay cụm nghe nhầm, rút gọn chuỗi lặp."""
    rules = corrections["videos"].get(video_id, {})
    if "start_at" in rules and rules["start_at"] in text:
        text = text[text.index(rules["start_at"]):]
    if "end_after" in rules and rules["end_after"] in text:
        text = text[:text.index(rules["end_after"]) + len(rules["end_after"])]
    for fragment in rules.get("remove", []):
        text = text.replace(fragment, " ")
    for wrong, right in corrections["everywhere"]:
        text = text.replace(wrong, right)
    return collapse_repeats(" ".join(text.split()))


def main() -> int:
    """Cắt transcript theo các đoạn đã chọn, áp dụng bản sửa chính tả, rồi ghi ra ``calls.jsonl``."""
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    corrections = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    rows, missing = [], []
    for video in selection["videos"]:
        path = TRANSCRIPTS / f"{video['id']}.json"
        if not path.exists():
            missing.append(video["id"])
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        for index, call in enumerate(video["calls"]):
            asr_text = cut(record["segments"], call["start"], call["end"])
            if not asr_text:
                continue
            text = correct(asr_text, video["id"], corrections)
            rows.append({
                "id": f"yt-{video['id']}-{index}", "video_id": video["id"], "url": record["url"],
                "channel": record.get("channel"), "start": call["start"], "end": call["end"],
                "label": call["label"], "type": call["type"], "staged": call.get("staged", False),
                "human_verified": False, "split": video["split"],
                # ``text`` đã sửa lỗi nghe nhầm theo ngữ cảnh; ``text_asr`` là nguyên văn PhoWhisper trả về.
                "text": text, "text_asr": asr_text,
            })
    OUT.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))
    scams = sum(row["label"] for row in rows)
    print(f"wrote {OUT}: {len(rows)} calls from {len({row['video_id'] for row in rows})} videos "
          f"({scams} scam, {len(rows) - scams} normal); missing transcripts: {missing or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
