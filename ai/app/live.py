"""Phân tích cuộc gọi đang diễn ra: nhận âm thanh theo luồng, cắt thành từng câu nói, nhận dạng và chấm rủi ro dần.

Khác với phân tích một file ghi âm sau cuộc gọi, ở đây âm thanh đến từng gói nhỏ trong lúc hai bên còn đang nói.
Chuỗi xử lý cho mỗi người nói:

    gói PCM -> UtteranceSegmenter (cắt theo khoảng lặng) -> Whisper -> lượt lời
                                                                         |
                          Rule Engine + NLP Model + Risk Engine <--------+  (chạy lại trên toàn bộ hội thoại)

Sau mỗi câu nói mới, toàn bộ hội thoại tính đến lúc đó được chấm lại, nên điểm rủi ro thay đổi dần theo cuộc gọi
và cảnh báo được phát ngay khi mức rủi ro tăng. Mọi thành phần chấm điểm là đúng những thành phần dùng cho phân
tích file: không có luật hay model riêng cho chế độ trực tiếp.

Định dạng âm thanh cố định: PCM số nguyên 16 bit có dấu, little-endian, một kênh, 16 kHz. Hai người nói đi trên hai
luồng riêng (ứng dụng VoIP có sẵn tiếng micro và tiếng nhận về tách nhau), nhờ đó biết chắc ai nói câu nào.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import numpy as np

from app.nlp import aggregate
from app.risk import RISK_ENGINE_VERSION, RiskLevel, assess
from app.rules import RuleEngine, Turn

SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2
# Âm thanh được xét theo từng khung 20 ms.
FRAME_SAMPLES = SAMPLE_RATE // 50
_FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE

LIVE_API_VERSION = "1"
_LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


class Speaker(StrEnum):
    """Hai bên của cuộc gọi, nhìn từ phía người dùng ứng dụng."""

    CALLER = "CALLER"  # người ở đầu dây bên kia (người gọi đến)
    CALLEE = "CALLEE"  # người dùng ứng dụng (người nghe máy)


# Byte đầu của mỗi gói âm thanh nhị phân cho biết gói đó là tiếng của ai.
SPEAKER_BY_PREFIX = {0: Speaker.CALLER, 1: Speaker.CALLEE}


@dataclass(frozen=True)
class Utterance:
    """Một câu nói liền mạch của một người, cắt ra từ luồng âm thanh."""

    speaker: Speaker
    # Thời điểm bắt đầu và kết thúc tính từ đầu luồng của người nói đó (giây).
    start: float
    end: float
    samples: np.ndarray  # int16

    @property
    def seconds(self) -> float:
        return len(self.samples) / SAMPLE_RATE


class UtteranceSegmenter:
    """Cắt luồng âm thanh của một người nói thành từng câu, dựa vào khoảng lặng giữa các câu.

    Một khung được coi là có tiếng nói khi độ lớn trung bình (RMS) của nó vượt ngưỡng. Một câu bắt đầu ở khung có
    tiếng nói đầu tiên và kết thúc khi đã im lặng đủ lâu, hoặc khi câu dài tới giới hạn (người nói liên tục không
    nghỉ). Câu quá ngắn (tiếng động, tiếng "ờ") bị bỏ. Lớp này chỉ cắt; việc nhận ra lời nói là của Whisper.
    """

    def __init__(self, speaker: Speaker, speech_threshold: float, end_silence_ms: int, max_utterance_seconds: float,
                 min_speech_ms: int = 200, pre_roll_ms: int = 200) -> None:
        self.speaker = speaker
        self._threshold = speech_threshold
        self._end_silence_frames = max(1, round(end_silence_ms / 1000 / _FRAME_SECONDS))
        self._max_frames = max(1, round(max_utterance_seconds / _FRAME_SECONDS))
        self._min_speech_frames = max(1, round(min_speech_ms / 1000 / _FRAME_SECONDS))
        self._pre_roll_frames = round(pre_roll_ms / 1000 / _FRAME_SECONDS)
        self._remainder = b""
        self._frames_seen = 0
        # Vài khung ngay trước khi có tiếng nói, giữ lại để không cắt mất âm đầu của câu.
        self._pre_roll: list[np.ndarray] = []
        self._current: list[np.ndarray] = []
        self._current_start_frame = 0
        self._speech_frames = 0
        self._silence_run = 0

    @property
    def seconds_received(self) -> float:
        """Tổng thời lượng âm thanh đã nhận của người nói này."""
        return self._frames_seen * _FRAME_SECONDS

    def feed(self, pcm: bytes) -> list[Utterance]:
        """Nhận thêm một gói PCM và trả về các câu vừa hoàn chỉnh (thường là rỗng hoặc một câu)."""
        data = self._remainder + pcm
        frame_bytes = FRAME_SAMPLES * BYTES_PER_SAMPLE
        usable = len(data) - len(data) % frame_bytes
        self._remainder = data[usable:]
        finished = []
        if usable:
            frames = np.frombuffer(data[:usable], dtype="<i2").reshape(-1, FRAME_SAMPLES)
            for frame in frames:
                utterance = self._accept(frame)
                if utterance is not None:
                    finished.append(utterance)
        return finished

    def flush(self) -> list[Utterance]:
        """Kết thúc luồng: trả về câu đang nói dở (nếu đủ dài)."""
        utterance = self._close(trim_silence=True)
        return [utterance] if utterance is not None else []

    def _accept(self, frame: np.ndarray) -> Utterance | None:
        """Xử lý một khung 20 ms; trả về câu vừa kết thúc ở khung này, nếu có."""
        index = self._frames_seen
        self._frames_seen += 1
        is_speech = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) >= self._threshold
        if not self._current:
            if not is_speech:
                self._pre_roll.append(frame)
                del self._pre_roll[:-self._pre_roll_frames or None]
                return None
            self._current = [*self._pre_roll, frame]
            self._current_start_frame = index - len(self._pre_roll)
            self._pre_roll = []
            self._speech_frames, self._silence_run = 1, 0
            return None
        self._current.append(frame)
        if is_speech:
            self._speech_frames += 1
            self._silence_run = 0
        else:
            self._silence_run += 1
        if self._silence_run >= self._end_silence_frames:
            return self._close(trim_silence=True)
        if len(self._current) >= self._max_frames:
            return self._close(trim_silence=False)
        return None

    def _close(self, trim_silence: bool) -> Utterance | None:
        """Đóng câu hiện tại. Bỏ bớt khoảng lặng ở cuối (giữ lại 200 ms) và bỏ hẳn câu nếu quá ít tiếng nói."""
        frames, speech = self._current, self._speech_frames
        start_frame = self._current_start_frame
        self._current, self._speech_frames, self._silence_run = [], 0, 0
        if not frames or speech < self._min_speech_frames:
            return None
        if trim_silence:
            keep = len(frames)
            while keep > 0 and float(np.sqrt(np.mean(frames[keep - 1].astype(np.float32) ** 2))) < self._threshold:
                keep -= 1
            frames = frames[:min(len(frames), keep + 10)]
        samples = np.concatenate(frames)
        start = start_frame * _FRAME_SECONDS
        return Utterance(self.speaker, round(start, 2), round(start + len(samples) / SAMPLE_RATE, 2), samples)


class SampleTranscriber(Protocol):
    """Bộ nhận dạng dùng cho chế độ trực tiếp: nhận mẫu âm thanh trong bộ nhớ, trả về văn bản."""

    def transcribe_samples(self, samples: np.ndarray) -> str:
        ...


class ChunkClassifier(Protocol):
    """Phần của NLP Model mà chế độ trực tiếp dùng (đúng các phương thức của ``TextClassifier``)."""

    config: dict

    def encode(self, text: str) -> list[list[int]]:
        ...

    def chunk_probabilities(self, windows: list[list[int]]) -> list[float]:
        ...


@dataclass
class SpokenTurn:
    """Một câu đã nhận dạng xong."""

    speaker: Speaker
    start: float
    end: float
    text: str


@dataclass
class LiveSession:
    """Trạng thái của một cuộc gọi đang được phân tích: các câu đã nghe, điểm rủi ro hiện tại, cảnh báo đã phát.

    Lớp này không biết gì về WebSocket: nó nhận từng câu nói và trả về danh sách sự kiện (dict) cần gửi cho bên
    gọi. Nhờ vậy logic được test trực tiếp, và sau này đổi cách truyền (gRPC, hàng đợi...) không phải sửa ở đây.
    """

    session_id: str
    transcriber: SampleTranscriber
    rules: RuleEngine
    classifier: ChunkClassifier
    turns: list[SpokenTurn] = field(default_factory=list)
    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 1.0
    model_probability: float = 0.0
    indicators: list[str] = field(default_factory=list)
    _sequence: int = 0
    _alerted_level: RiskLevel = RiskLevel.LOW
    _chunk_cache: dict[tuple[int, ...], float] = field(default_factory=dict)
    stt_seconds: float = 0.0

    def process(self, utterance: Utterance) -> list[dict]:
        """Nhận dạng một câu, chấm lại rủi ro của cả hội thoại, và trả về các sự kiện phát sinh.

        Câu không nhận ra lời nào (tiếng ồn) không sinh sự kiện. Thứ tự sự kiện: ``transcript``, ``risk``, rồi
        ``alert`` nếu mức rủi ro vừa tăng.
        """
        started = time.perf_counter()
        text = self.transcriber.transcribe_samples(utterance.samples.astype(np.float32) / 32768.0).strip()
        self.stt_seconds += time.perf_counter() - started
        if not text:
            return []
        turn = SpokenTurn(utterance.speaker, utterance.start, utterance.end, text)
        self.turns.append(turn)
        # Hai luồng được nhận dạng xen kẽ nên câu đến sau có thể bắt đầu trước: luôn xếp lại theo thời gian.
        self.turns.sort(key=lambda item: (item.start, item.speaker.value))
        events = [self._event("transcript", speaker=turn.speaker.value, start=turn.start, end=turn.end, text=text)]
        events.extend(self._reassess())
        return events

    def _reassess(self) -> list[dict]:
        """Chạy Rule Engine, NLP Model và Risk Engine trên toàn bộ hội thoại đã nghe được."""
        analysis = self.rules.analyze_conversation([Turn(turn.speaker.value, turn.text) for turn in self.turns])
        probability = self._model_probability(" ".join(turn.text for turn in self.turns))
        result = assess(analysis.indicators, probability)

        codes = [match.code.value for match in analysis.indicators]
        new_codes = [code for code in codes if code not in self.indicators]
        self.indicators = codes
        self.risk_score, self.risk_level = result.risk_score, result.risk_level
        self.confidence, self.model_probability = result.confidence, probability

        events = [self._event("risk", **self._risk_fields(), newIndicators=new_codes)]
        if _LEVEL_ORDER[result.risk_level] > _LEVEL_ORDER[self._alerted_level]:
            # Mỗi mức chỉ cảnh báo một lần, và chỉ khi tăng: điểm dao động quanh ngưỡng không gây cảnh báo lặp lại.
            self._alerted_level = result.risk_level
            last = self.turns[-1]
            events.append(self._event("alert", **self._risk_fields(), atSeconds=last.end,
                                      triggeredBy={"speaker": last.speaker.value, "text": last.text}))
        return events

    def _model_probability(self, text: str) -> float:
        """Xác suất lừa đảo của cả hội thoại. Hội thoại dài dần nhưng phần đầu không đổi, nên các đoạn đã chấm
        được nhớ lại và mỗi lần chỉ phải chạy model trên các đoạn mới."""
        windows = self.classifier.encode(text)
        missing = [window for window in windows if tuple(window) not in self._chunk_cache]
        if missing:
            for window, probability in zip(missing, self.classifier.chunk_probabilities(missing)):
                self._chunk_cache[tuple(window)] = probability
        probabilities = [self._chunk_cache[tuple(window)] for window in windows]
        return aggregate(probabilities, self.classifier.config["aggregation"])

    def _risk_fields(self) -> dict:
        return {
            "riskScore": self.risk_score, "riskLevel": self.risk_level.value, "confidence": self.confidence,
            "indicators": list(self.indicators), "modelProbability": round(self.model_probability, 6),
        }

    def final_event(self, duration_seconds: float, ended_by: str) -> dict:
        """Sự kiện cuối cùng của phiên: toàn bộ transcript và kết quả rủi ro chốt lại.

        Nếu không nhận ra câu nào thì không có gì để chấm: các trường rủi ro là null thay vì một mức LOW mặc định.
        """
        has_speech = bool(self.turns)
        risk = self._risk_fields() if has_speech else {
            "riskScore": None, "riskLevel": None, "confidence": None, "indicators": [], "modelProbability": None}
        return self._event(
            "final", **risk, endedBy=ended_by, durationSeconds=round(duration_seconds, 3),
            transcript=" ".join(turn.text for turn in self.turns),
            turns=[{"speaker": turn.speaker.value, "start": turn.start, "end": turn.end, "text": turn.text}
                   for turn in self.turns],
            modelVersion=self.classifier.config["version"], rulesetVersion=self.rules.version,
            riskEngineVersion=RISK_ENGINE_VERSION,
        )

    def _event(self, kind: str, **fields) -> dict:
        self._sequence += 1
        return {"type": kind, "seq": self._sequence, **fields}
