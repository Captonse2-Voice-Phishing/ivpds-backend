"""Fine-tune một model Transformer có sẵn để phân loại transcript NORMAL / PHISHING.

Chạy (từ thư mục ``ai``, cần GPU):

    docker run --rm --gpus all -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work ivpds/train:dev \
        python -m training.finetune --model FacebookAI/xlm-roberta-base --name xlmr-base

Cách làm:

* Văn bản được chuẩn hóa như lúc chạy thật (``app.nlp.normalize_for_model``) rồi cắt thành các đoạn gối nhau.
  Mỗi đoạn mang nhãn của cả cuộc gọi. Cuộc gọi quá dài chỉ đóng góp tối đa ``--max-chunks`` đoạn mỗi epoch.
* Sau mỗi epoch, model được đánh giá ở mức cuộc gọi trên tập validation, với từng cách gộp các đoạn. Checkpoint
  và cách gộp cho macro F1 cao nhất trên validation được giữ lại. Tập test không được dùng trong bước này.
* Artifact gồm trọng số, tokenizer và ``nlp_config.json``; ``training_log.json`` ghi lại mọi thông tin để chạy lại.
"""

import argparse
import hashlib
import json
import platform
import random
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from app.nlp import CONFIG_FILE, LABELS, aggregate, normalize_for_model, token_windows, with_special_tokens
from training.common import DATA, MODELS, SELECTION_SET, SEED, evaluate, load, load_selection

# Thứ tự cũng là thứ tự ưu tiên khi các cách gộp bằng điểm nhau trên validation. "top2" đứng đầu vì một cuộc gọi
# dài là lừa đảo khi vài đoạn của nó là lừa đảo; lấy trung bình cả cuộc gọi sẽ bị các đoạn trò chuyện bình thường
# pha loãng. Tập validation không có cuộc gọi thật dài nên thường không phân định được hai cách này.
AGGREGATIONS = ("top2", "mean", "max")


def parse() -> argparse.Namespace:
    """Đọc các tham số dòng lệnh: dùng model nào, cắt đoạn dài bao nhiêu, huấn luyện mấy vòng, tốc độ học..."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Tên model trên Hugging Face")
    parser.add_argument("--revision", default=None, help="Commit của model; bỏ trống để dùng bản mới nhất")
    parser.add_argument("--name", required=True, help="Tên thư mục artifact trong models/")
    parser.add_argument("--max-length", type=int, default=256, help="Số token tối đa của một đoạn đưa vào model")
    parser.add_argument("--stride", type=int, default=128, help="Đoạn sau bắt đầu sau đoạn trước bao nhiêu token")
    parser.add_argument("--max-chunks", type=int, default=6, help="Số đoạn tối đa lấy từ một cuộc gọi mỗi epoch")
    parser.add_argument("--epochs", type=int, default=3, help="Số vòng đi qua toàn bộ dữ liệu huấn luyện")
    parser.add_argument("--batch-size", type=int, default=16, help="Số đoạn xử lý cùng lúc; giảm nếu GPU thiếu bộ nhớ")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Tốc độ học")
    parser.add_argument("--seed", type=int, default=SEED, help="Hạt giống ngẫu nhiên, để chạy lại ra cùng kết quả")
    parser.add_argument("--word-segmentation", action="store_true", help="Tách từ tiếng Việt bằng pyvi (PhoBERT cần)")
    parser.add_argument("--freeze-embeddings", action="store_true",
                        help="Không cập nhật bảng từ vựng khi học; cần cho model có bảng từ vựng lớn trên GPU ít bộ nhớ")
    parser.add_argument("--limit", type=int, default=0, help="Chỉ dùng N mẫu đầu, để chạy thử nhanh")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Mã SHA-256 của một file dữ liệu, ghi vào nhật ký để biết chính xác model đã học từ phiên bản dữ liệu nào."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    """Toàn bộ quá trình fine-tune: chuẩn bị dữ liệu, huấn luyện, chọn checkpoint tốt nhất, lưu artifact.

    Các bước:
      1. Tách token và cắt mỗi cuộc gọi thành các đoạn.
      2. Nạp model có sẵn, gắn thêm lớp phân loại hai nhãn.
      3. Mỗi epoch: học trên các đoạn của tập train, rồi chấm điểm trên hai tập validation.
      4. Giữ lại checkpoint có điểm cao nhất trên tập validation khó.
      5. Lưu trọng số, tokenizer, cấu hình và nhật ký huấn luyện.
    """
    args = parse()
    # Cố định hạt giống để lần chạy sau cho kết quả giống lần này.
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # --- Bước 1: chuẩn bị dữ liệu ---
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    segment = None
    if args.word_segmentation:
        from pyvi import ViTokenizer

        segment = ViTokenizer.tokenize
    window = args.max_length - 2  # chừa chỗ cho token mở đầu và kết thúc

    def encode(row: dict) -> list[list[int]]:
        """Biến một cuộc gọi thành danh sách các đoạn token: chuẩn hóa chữ, tách từ (nếu cần), tách token, cắt đoạn."""
        text = normalize_for_model(row["text_plain"])
        if segment is not None:
            text = segment(text)
        return token_windows(tokenizer.encode(text, add_special_tokens=False), window, args.stride)

    train, validation, selection = load("train"), load("validation"), load_selection()
    if args.limit:
        train, validation = train[:args.limit], validation[:args.limit]
    train_windows = [encode(row) for row in train]
    validation_windows = [encode(row) for row in validation]
    selection_windows = [encode(row) for row in selection]

    # --- Bước 2: nạp model có sẵn và các công cụ huấn luyện ---
    # Lớp phân loại hai nhãn (NORMAL / PHISHING) được khởi tạo mới ở trên cùng của model.
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, revision=args.revision, num_labels=2, id2label=dict(enumerate(LABELS)),
        label2id={label: index for index, label in enumerate(LABELS)},
    ).to(device)
    if args.freeze_embeddings:
        # Bảng từ vựng của model đa ngôn ngữ chiếm phần lớn số trọng số. Bộ tối ưu giữ thêm hai bản sao cho mỗi
        # trọng số được học, nên đóng băng bảng này giảm mạnh bộ nhớ GPU cần dùng.
        for parameter in model.get_input_embeddings().parameters():
            parameter.requires_grad = False
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    # Bộ tối ưu: cập nhật trọng số của model sau mỗi batch.
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0.01)
    chunks_per_epoch = sum(min(len(windows), args.max_chunks) for windows in train_windows)
    steps = args.epochs * ((chunks_per_epoch + args.batch_size - 1) // args.batch_size)
    # Lịch tốc độ học: tăng dần trong 10% số bước đầu rồi giảm đều về 0, giúp huấn luyện ổn định.
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * steps), steps)
    # Tính toán bằng số 16 bit trên GPU để nhanh hơn và tốn ít bộ nhớ hơn.
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    pad = tokenizer.pad_token_id

    def batch_tensors(windows: list[list[int]]) -> tuple[torch.Tensor, torch.Tensor]:
        """Gom các đoạn thành một batch: thêm token mở đầu/kết thúc, đệm cho bằng độ dài, chuyển lên GPU.

        Trả về mã token và mặt nạ cho biết vị trí nào là token thật (1), vị trí nào là phần đệm (0).
        """
        rows = [with_special_tokens(tokenizer, ids) for ids in windows]
        longest = max(len(ids) for ids in rows)
        input_ids = torch.tensor([ids + [pad] * (longest - len(ids)) for ids in rows], device=device)
        mask = torch.tensor([[1] * len(ids) + [0] * (longest - len(ids)) for ids in rows], device=device)
        return input_ids, mask

    def document_chunk_probabilities(all_windows: list[list[list[int]]]) -> list[list[float]]:
        """Chấm điểm (không học): trả về xác suất PHISHING của từng đoạn, nhóm theo cuộc gọi.

        Dùng sau mỗi epoch để đánh giá model trên các tập validation.
        """
        flat = [(index, ids) for index, windows in enumerate(all_windows) for ids in windows]
        flat.sort(key=lambda item: len(item[1]))  # các đoạn dài gần nhau vào cùng batch để đỡ phải đệm
        scores: list[list[float]] = [[] for _ in all_windows]
        model.eval()
        for start in range(0, len(flat), args.batch_size * 2):
            part = flat[start:start + args.batch_size * 2]
            input_ids, mask = batch_tensors([ids for _, ids in part])
            with torch.inference_mode(), torch.autocast(device_type=device, enabled=device == "cuda"):
                logits = model(input_ids=input_ids, attention_mask=mask).logits
            for (index, _), probability in zip(part, torch.softmax(logits.float(), dim=-1)[:, 1].tolist()):
                scores[index].append(probability)
        return scores

    out = MODELS / args.name
    out.mkdir(parents=True, exist_ok=True)
    history, best = [], None
    started = time.perf_counter()
    # --- Bước 3: vòng lặp huấn luyện ---
    for epoch in range(1, args.epochs + 1):
        # Mỗi đoạn là một ví dụ học, mang nhãn của cả cuộc gọi. Cuộc gọi quá dài chỉ lấy ngẫu nhiên một số đoạn,
        # để vài cuộc gọi rất dài không lấn át phần còn lại.
        examples = []
        for windows, row in zip(train_windows, train):
            chosen = windows if len(windows) <= args.max_chunks else random.sample(windows, args.max_chunks)
            examples.extend((ids, row["label"]) for ids in chosen)
        random.shuffle(examples)
        model.train()
        total_loss = 0.0
        for start in range(0, len(examples), args.batch_size):
            part = examples[start:start + args.batch_size]
            input_ids, mask = batch_tensors([ids for ids, _ in part])
            labels = torch.tensor([label for _, label in part], device=device)
            # Model đoán nhãn của batch; loss đo mức sai so với nhãn đúng.
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                loss = model(input_ids=input_ids, attention_mask=mask, labels=labels).loss
            # Tính hướng cần chỉnh cho từng trọng số, giới hạn độ lớn của lần chỉnh, rồi cập nhật trọng số.
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            total_loss += loss.item() * len(part)
            # Báo tiến độ định kỳ để biết tốc độ thật (GPU thiếu bộ nhớ sẽ chạy chậm đi rất nhiều).
            done = start // args.batch_size + 1
            if done % 200 == 0:
                print(f"epoch {epoch} step {done}/{(len(examples) + args.batch_size - 1) // args.batch_size} "
                      f"elapsed {time.perf_counter() - started:.0f}s", flush=True)

        # --- Bước 4: chấm điểm sau epoch và giữ checkpoint tốt nhất ---
        # Thử cả ba cách gộp điểm các đoạn thành điểm của cuộc gọi (trung bình, hai đoạn cao nhất, đoạn cao nhất).
        chunk_scores = document_chunk_probabilities(validation_windows)
        selection_scores = document_chunk_probabilities(selection_windows)
        record = {"epoch": epoch, "train_loss": round(total_loss / len(examples), 4), "validation": {}, SELECTION_SET: {}}
        for method in AGGREGATIONS:
            easy = evaluate(validation, [aggregate(scores, method) for scores in chunk_scores], 0.5)["all"]
            hard = evaluate(selection, [aggregate(scores, method) for scores in selection_scores], 0.5)["all"]
            for name, result in (("validation", easy), (SELECTION_SET, hard)):
                record[name][method] = {"macro_f1": result["macro_f1"], "false_positives": result["false_positives"],
                                        "false_negatives": result["false_negatives"]}
            # Chọn theo tập validation khó; tập validation tổng hợp chỉ dùng để phân định khi bằng điểm.
            score = (hard["macro_f1"], easy["macro_f1"])
            if best is None or score > (best["selection_macro_f1"], best["validation_macro_f1"]):
                best = {"selection_macro_f1": hard["macro_f1"], "validation_macro_f1": easy["macro_f1"],
                        "epoch": epoch, "aggregation": method}
                model.save_pretrained(out)
        history.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    # --- Bước 5: lưu artifact ---
    duration = round(time.perf_counter() - started, 1)
    tokenizer.save_pretrained(out)
    # Cấu hình mà service cần để dùng model đúng như lúc huấn luyện (độ dài đoạn, cách gộp, ngưỡng).
    config = {
        "version": time.strftime("%Y.%m.%d") + "-" + args.name, "base_model": args.model,
        "base_model_revision": args.revision, "max_length": args.max_length, "stride": args.stride,
        "aggregation": best["aggregation"], "threshold": 0.5, "labels": list(LABELS),
        "word_segmentation": args.word_segmentation, "text_normalization": "app.nlp.normalize_for_model",
    }
    (out / CONFIG_FILE).write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = json.loads((DATA / "AUDIT.json").read_text(encoding="utf-8"))
    # Nhật ký huấn luyện: mọi thông tin cần để chạy lại và kiểm chứng (dữ liệu, tham số, phần cứng, kết quả từng epoch).
    log = {
        **config,
        "dataset_files": {name: file_hash(DATA / f"{name}.jsonl") for name in ("train", "validation")},
        "dataset_sources": {name: source.get("provenance", source.get("note")) for name, source in audit["sources"].items()},
        "random_seed": args.seed, "train_size": len(train), "validation_size": len(validation),
        "selection_set": SELECTION_SET, "selection_size": len(selection),
        "train_class_distribution": {LABELS[label]: sum(1 for row in train if row["label"] == label) for label in (0, 1)},
        "train_chunks_per_epoch": chunks_per_epoch,
        "hyperparameters": {"epochs": args.epochs, "batch_size": args.batch_size, "learning_rate": args.learning_rate,
                            "weight_decay": 0.01, "warmup_share": 0.1, "max_chunks_per_document": args.max_chunks,
                            "optimizer": "AdamW", "mixed_precision": device == "cuda",
                            "frozen_embeddings": args.freeze_embeddings,
                            "trainable_parameters": sum(parameter.numel() for parameter in trainable)},
        "tokenizer": type(tokenizer).__name__,
        "hardware": torch.cuda.get_device_name(0) if device == "cuda" else platform.processor() or "CPU",
        "torch_version": torch.__version__, "training_seconds": duration,
        "best_checkpoint": best, "history": history,
    }
    (out / "training_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # File trọng số được ghi với quyền chỉ chủ sở hữu đọc được; service chạy bằng người dùng khác nên phải mở quyền đọc.
    for path in out.iterdir():
        path.chmod(0o644)
    print(f"best: {best} | {duration}s | saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
