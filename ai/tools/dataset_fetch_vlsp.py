"""Lấy transcript lời nói tiếng Việt thường ngày từ bộ VLSP 2020 (VinAI 100h) để làm dữ liệu lớp NORMAL.

Cách dùng (cần mạng; chạy từ thư mục ``ai``):

    docker run --rm -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.dataset_fetch_vlsp

Nguồn: https://huggingface.co/datasets/doof-ferb/vlsp2020_vinai_100h (CC-BY-4.0). Chỉ lấy cột chữ, không tải âm
thanh. Chủ dự án đồng ý dùng nguồn này để huấn luyện ngày 2026-10-09, sau khi phép thử cho thấy model báo nhầm
một phần ba số câu nói thường ngày.

Bộ dữ liệu có 56.427 câu. Công cụ lấy các "trang" 100 câu ở những vị trí cố định:

* trang dành cho train và validation, ghi vào ``data/raw/vlsp2020_vinai_100h/rows.jsonl``;
* các trang bắt đầu ở 0, 5000, 10000, ... 45000 KHÔNG được lấy: đó là 1.000 câu đã dùng làm bộ test
  (``data/extra_tests/vlsp_ordinary_speech.jsonl``), phải nằm ngoài huấn luyện.
"""

import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATASET = "doof-ferb/vlsp2020_vinai_100h"
OUT = Path("data/raw/vlsp2020_vinai_100h/rows.jsonl")
PROVENANCE = Path("data/raw/PROVENANCE_vlsp.json")
PAGE = 100
TEST_PAGES = set(range(0, 50000, 5000))
# 40 trang cho train, 8 trang cho validation; xen kẽ khắp bộ dữ liệu và tránh các trang test.
TRAIN_PAGES = [start for start in range(1000, 56000, 1100) if start not in TEST_PAGES][:40]
VALIDATION_PAGES = [start for start in range(1500, 56000, 6500) if start not in TEST_PAGES and start not in TRAIN_PAGES][:8]


def fetch(offset: int) -> list[dict]:
    """Một trang 100 câu, thử lại vài lần nếu máy chủ bận."""
    url = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train", "offset": offset, "length": PAGE})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - URL cố định tới huggingface.co
                return json.load(response)["rows"]
        except Exception:  # noqa: BLE001 - lỗi mạng tạm thời, thử lại
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"could not fetch rows at offset {offset}")


def main() -> int:
    """Tải các trang đã định, ghi mỗi câu một dòng kèm vị trí và tập, rồi ghi nguồn gốc."""
    assert not (set(TRAIN_PAGES) | set(VALIDATION_PAGES)) & TEST_PAGES
    rows = []
    for split, pages in (("train", TRAIN_PAGES), ("validation", VALIDATION_PAGES)):
        for offset in pages:
            for row in fetch(offset):
                text = " ".join((row["row"].get("transcription") or "").split())
                rows.append({"index": row["row_idx"], "page": offset, "split": split, "text": text})
            print(f"{split} page {offset}: ok", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    OUT.write_bytes(content)
    PROVENANCE.write_text(json.dumps({
        "vlsp2020_vinai_100h": {
            "repo": DATASET, "page": f"https://huggingface.co/datasets/{DATASET}", "license": "cc-by-4.0",
            "description": "Transcript lời nói tiếng Việt thường ngày (chỉ lấy chữ, không lấy âm thanh).",
            "synthetic": False, "approved_by_owner_on": "2026-10-09",
            "train_pages": TRAIN_PAGES, "validation_pages": VALIDATION_PAGES, "rows_per_page": PAGE,
            "pages_reserved_for_testing": sorted(TEST_PAGES),
            "rows": len(rows), "sha256": hashlib.sha256(content).hexdigest(),
        }
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
