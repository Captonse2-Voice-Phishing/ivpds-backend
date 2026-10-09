"""Tải các dataset đã được phê duyệt về ``data/raw/`` và ghi lại nguồn gốc.

Cách dùng (chạy từ thư mục ``ai``):

    docker run --rm -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.dataset_download

Mỗi file được tải theo đúng một revision (commit) của kho dữ liệu, nên chạy lại ở máy khác vẫn ra cùng nội
dung. Sau khi tải, công cụ ghi ``data/raw/PROVENANCE.json`` gồm URL, revision, license, kích thước và mã
SHA-256 của từng file. Dữ liệu trong ``data/raw/`` là bản gốc: các bước sau chỉ đọc, không được sửa.

Chỉ những dataset có trong ``APPROVED`` mới được tải. Thêm dataset mới phải được chủ dự án phê duyệt trước.
"""

import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RAW_DIR = Path("data/raw")

# Dataset đã được phê duyệt ngày 2026-10-08. Bộ SMS (trannguyenthaituan/vietnamese_sms_dataset) từng được
# duyệt nhưng đã bị chủ dự án rút lại cùng ngày: dữ liệu huấn luyện chỉ gồm cuộc gọi, không gồm tin nhắn.
# ``revision`` là commit của kho dữ liệu tại thời điểm phê duyệt.
APPROVED = [
    {
        "name": "adamtc_scam_dialogues",
        "repo": "adamtc/scam_dialogues",
        "revision": None,  # điền khi tải lần đầu, sau đó được giữ cố định trong PROVENANCE.json
        "license": "apache-2.0",
        "files": ["scam-dialogues-train-text.json", "README.md"],
        "description": "Hội thoại điện thoại lừa đảo/bình thường, tổng hợp, tiếng Việt dịch máy.",
        "synthetic": True,
    },
]


def _fetch(url: str) -> bytes:
    """Tải nội dung một URL và trả về dạng bytes."""
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - URL cố định tới huggingface.co
        return response.read()


def _current_revision(repo: str) -> str:
    """Commit mới nhất của kho dữ liệu trên Hugging Face."""
    return json.loads(_fetch(f"https://huggingface.co/api/datasets/{repo}"))["sha"]


def main() -> int:
    """Tải từng file, kiểm tra với lần tải trước (nếu có) và ghi lại nguồn gốc."""
    provenance_path = RAW_DIR / "PROVENANCE.json"
    previous = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {}
    record = {}
    for dataset in APPROVED:
        earlier = previous.get(dataset["name"], {})
        # Giữ nguyên revision của lần tải đầu để mọi máy dùng đúng một phiên bản dữ liệu.
        revision = dataset["revision"] or earlier.get("revision") or _current_revision(dataset["repo"])
        folder = RAW_DIR / dataset["name"]
        folder.mkdir(parents=True, exist_ok=True)
        files = {}
        for name in dataset["files"]:
            url = f"https://huggingface.co/datasets/{dataset['repo']}/resolve/{revision}/{name}"
            content = _fetch(url)
            digest = hashlib.sha256(content).hexdigest()
            expected = earlier.get("files", {}).get(name, {}).get("sha256")
            if expected and expected != digest:
                print(f"HASH MISMATCH {dataset['name']}/{name}: expected {expected}, got {digest}")
                return 1
            (folder / name).write_bytes(content)
            files[name] = {"url": url, "bytes": len(content), "sha256": digest}
            print(f"{dataset['name']}/{name}: {len(content)} bytes sha256={digest[:16]}")
        record[dataset["name"]] = {
            "repo": dataset["repo"],
            "page": f"https://huggingface.co/datasets/{dataset['repo']}",
            "revision": revision,
            "license": dataset["license"],
            "description": dataset["description"],
            "synthetic": dataset["synthetic"],
            "approved_by_owner_on": "2026-10-08",
            "downloaded_at": earlier.get("downloaded_at") or datetime.now(UTC).isoformat(timespec="seconds"),
            "files": files,
        }
    provenance_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
