"""Tests for live call analysis: cutting the audio stream into utterances, the session logic, and the WebSocket API.

Most tests use stand-ins for Whisper and the NLP model, with scripted answers, to check the protocol and the
logic around them; they say nothing about recognition or detection quality. The tests at the bottom stream
synthesised speech through the real Whisper model and the real fine-tuned artifact, and are skipped when those
are not available.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from helpers import API_KEY, make_settings

from app.live import FRAME_SAMPLES, SAMPLE_RATE, LiveSession, Speaker, Utterance, UtteranceSegmenter
from app.main import create_app
from app.nlp import CONFIG_FILE
from app.risk import RiskLevel
from app.rules import RuleEngine
from app.stt import Transcript

URL = "/v1/live-sessions"
HEADERS = {"X-API-Key": API_KEY}
CALLER, CALLEE = b"\x00", b"\x01"


# ----------------------------------------------------------------------------------- audio


def tone(seconds: float, amplitude: int = 8000) -> bytes:
    """A 300 Hz tone as PCM16; loud enough to count as speech for the segmenter."""
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 300 * t) * amplitude).astype("<i2").tobytes()


def silence(seconds: float) -> bytes:
    return bytes(int(seconds * SAMPLE_RATE) * 2)


def segmenter(**overrides) -> UtteranceSegmenter:
    options = {"speech_threshold": 300, "end_silence_ms": 700, "max_utterance_seconds": 15} | overrides
    return UtteranceSegmenter(Speaker.CALLER, **options)


# ------------------------------------------------------------------------------- segmenter


def test_silence_alone_never_makes_an_utterance():
    cutter = segmenter()

    assert cutter.feed(silence(5)) == []
    assert cutter.flush() == []
    assert cutter.seconds_received == pytest.approx(5.0)


def test_speech_followed_by_a_pause_becomes_one_utterance_with_its_position_in_the_stream():
    cutter = segmenter()

    found = cutter.feed(silence(2) + tone(1.5) + silence(1))

    assert len(found) == 1
    utterance = found[0]
    assert utterance.speaker == Speaker.CALLER
    # Starts 200 ms before the speech (pre-roll) and ends shortly after it (200 ms of trailing silence kept).
    assert utterance.start == pytest.approx(1.8, abs=0.03)
    assert utterance.end == pytest.approx(3.7, abs=0.05)
    assert utterance.samples.dtype == np.int16
    assert utterance.seconds == pytest.approx(utterance.end - utterance.start, abs=0.01)


def test_two_sentences_separated_by_a_pause_are_two_utterances():
    cutter = segmenter()

    found = cutter.feed(tone(1) + silence(1) + tone(2) + silence(1))

    assert [round(u.seconds, 1) for u in found] == pytest.approx([1.2, 2.4], abs=0.11)
    assert found[0].end <= found[1].start


def test_a_short_pause_inside_a_sentence_does_not_split_it():
    cutter = segmenter()

    found = cutter.feed(tone(1) + silence(0.3) + tone(1) + silence(1))

    assert len(found) == 1
    assert found[0].seconds == pytest.approx(2.5, abs=0.11)


def test_a_click_too_short_to_be_speech_is_dropped():
    cutter = segmenter()

    assert cutter.feed(silence(1) + tone(0.06) + silence(2)) == []


def test_someone_who_never_pauses_is_cut_at_the_maximum_length():
    cutter = segmenter(max_utterance_seconds=5)

    found = cutter.feed(tone(12)) + cutter.flush()

    assert [round(u.seconds) for u in found] == [5, 5, 2]
    assert sum(len(u.samples) for u in found) == pytest.approx(12 * SAMPLE_RATE, abs=FRAME_SAMPLES * 3)


def test_the_way_the_stream_is_split_into_packets_does_not_change_the_result():
    audio = silence(0.5) + tone(1.3) + silence(0.9) + tone(0.8) + silence(1)
    whole = segmenter().feed(audio)

    cutter = segmenter()
    pieces = []
    # Odd sizes, so packets end in the middle of a frame and even in the middle of a sample.
    for start in range(0, len(audio), 1001):
        pieces.extend(cutter.feed(audio[start:start + 1001]))

    assert [(u.start, u.end) for u in pieces] == [(u.start, u.end) for u in whole]
    assert all(np.array_equal(a.samples, b.samples) for a, b in zip(pieces, whole))


def test_flush_returns_the_sentence_being_spoken_when_the_call_ends():
    cutter = segmenter()
    assert cutter.feed(silence(1) + tone(1)) == []

    found = cutter.flush()

    assert len(found) == 1
    assert found[0].seconds == pytest.approx(1.2, abs=0.05)
    assert cutter.flush() == []


def test_quiet_background_noise_below_the_threshold_is_not_speech():
    cutter = segmenter()

    assert cutter.feed(tone(3, amplitude=100)) == []
    assert cutter.flush() == []


def test_runaway_dots_from_the_recogniser_are_collapsed_and_dots_alone_are_not_speech():
    from app.stt import _tidy

    assert _tidy(" a lô mình là bên bộ công an ạ" + "." * 60 + " ") == "a lô mình là bên bộ công an ạ."
    assert _tidy("vâng. tôi nghe.") == "vâng. tôi nghe."
    assert _tidy("... . . .") == ""
    assert _tidy("   ") == ""


# ------------------------------------------------------------------------------- stand-ins


class ScriptedTranscriber:
    """Not Whisper: answers each utterance with the next line of a script."""

    name = "scripted"

    def __init__(self, lines: list[str], delay: float = 0.0) -> None:
        self.lines = list(lines)
        self.delay = delay
        self.heard: list[int] = []

    def transcribe_samples(self, samples: np.ndarray) -> Transcript:
        time.sleep(self.delay)
        self.heard.append(len(samples))
        text = self.lines.pop(0) if self.lines else ""
        return Transcript(text=text, language="vi", segments=[])

    def transcribe(self, wav_path: Path) -> Transcript:  # pragma: no cover - unused here
        raise NotImplementedError


class TextOnly:
    """Adapter with the shape ``LiveSession`` expects from the transcription service."""

    def __init__(self, transcriber: ScriptedTranscriber) -> None:
        self.transcriber = transcriber

    def transcribe_samples(self, samples: np.ndarray) -> str:
        return self.transcriber.transcribe_samples(samples).text


class KeywordClassifier:
    """Not a model: a chunk is "phishing" when it contains the word otp. Records what it was asked to score."""

    config = {"version": "stand-in", "aggregation": "top2"}
    name = "stand-in"

    def __init__(self) -> None:
        self.scored: list[str] = []

    def encode(self, text: str) -> list[list[int]]:
        return [[ord(char) for char in text[start:start + 40]] for start in range(0, max(len(text), 1), 40)]

    def chunk_probabilities(self, windows: list[list[int]]) -> list[float]:
        chunks = ["".join(map(chr, window)) for window in windows]
        self.scored.extend(chunks)
        return [0.99 if "otp" in chunk.lower() else 0.01 for chunk in chunks]


def utterance(speaker: Speaker, start: float, seconds: float = 1.0) -> Utterance:
    return Utterance(speaker, start, start + seconds, np.zeros(int(seconds * SAMPLE_RATE), dtype=np.int16))


def session_with(lines: list[str]) -> tuple[LiveSession, KeywordClassifier]:
    classifier = KeywordClassifier()
    return LiveSession("s1", TextOnly(ScriptedTranscriber(lines)), RuleEngine(), classifier), classifier


# --------------------------------------------------------------------------------- session


def test_each_recognised_utterance_gives_a_transcript_event_and_an_updated_risk():
    session, _ = session_with(["A lô, cho hỏi ai đầu dây đấy ạ?"])

    events = session.process(utterance(Speaker.CALLEE, 0.0))

    assert [event["type"] for event in events] == ["transcript", "risk"]
    assert events[0] | {"seq": 0} == {"type": "transcript", "seq": 0, "speaker": "CALLEE", "start": 0.0, "end": 1.0,
                                      "text": "A lô, cho hỏi ai đầu dây đấy ạ?"}
    assert events[1]["riskLevel"] == "LOW" and events[1]["indicators"] == [] and events[1]["newIndicators"] == []
    assert [event["seq"] for event in events] == [1, 2]


def test_an_alert_is_sent_when_the_risk_level_rises_and_only_once_per_level():
    session, _ = session_with([
        "Chào anh, em gọi để hỏi thăm sức khỏe.",
        "Tôi gọi từ ngân hàng, tài khoản của anh đang có vấn đề, anh đọc mã OTP tôi vừa gửi.",
        "Anh đọc mã OTP ngay đi, nếu không tài khoản sẽ bị khóa.",
    ])

    first = session.process(utterance(Speaker.CALLER, 0))
    second = session.process(utterance(Speaker.CALLER, 2))
    third = session.process(utterance(Speaker.CALLER, 4))

    assert [event["type"] for event in first] == ["transcript", "risk"]
    assert [event["type"] for event in second] == ["transcript", "risk", "alert"]
    alert = second[2]
    assert alert["riskLevel"] == "HIGH" and alert["riskScore"] >= 60
    assert "OTP_REQUEST" in alert["indicators"]
    assert alert["triggeredBy"] == {"speaker": "CALLER", "text": session.turns[1].text}
    assert alert["atSeconds"] == 3.0
    assert "OTP_REQUEST" in second[1]["newIndicators"]
    # Still HIGH after the next sentence: the risk is reported again, the alert is not repeated.
    assert [event["type"] for event in third] == ["transcript", "risk"]
    assert third[1]["riskLevel"] == "HIGH"
    assert "OTP_REQUEST" not in third[1]["newIndicators"]


def test_noise_that_yields_no_words_produces_no_events_and_no_turn():
    session, classifier = session_with(["", "   "])

    assert session.process(utterance(Speaker.CALLER, 0)) == []
    assert session.process(utterance(Speaker.CALLER, 2)) == []
    assert session.turns == [] and classifier.scored == []


def test_turns_are_kept_in_the_order_they_were_spoken_not_the_order_they_were_recognised():
    session, _ = session_with(["Dạ vâng, tôi nghe.", "Tôi gọi từ ngân hàng."])

    session.process(utterance(Speaker.CALLEE, 5.0))
    session.process(utterance(Speaker.CALLER, 1.0))

    assert [(turn.speaker, turn.start) for turn in session.turns] == [(Speaker.CALLER, 1.0), (Speaker.CALLEE, 5.0)]
    assert session.final_event(8.0, "CLIENT")["transcript"] == "Tôi gọi từ ngân hàng. Dạ vâng, tôi nghe."


def test_the_model_only_scores_the_parts_of_the_conversation_it_has_not_scored_yet():
    lines = [f"Câu nói số {number} trong một cuộc trò chuyện bình thường hằng ngày." for number in range(6)]
    session, classifier = session_with(lines)

    for number in range(6):
        session.process(utterance(Speaker.CALLER, number * 2))

    whole = " ".join(lines)
    # Scoring everything from scratch after each sentence would cost far more chunks than the text has.
    assert len(classifier.scored) < 2 * len(classifier.encode(whole)) + 6
    assert len(set(classifier.scored)) == len(classifier.scored)


def test_the_final_event_carries_the_whole_transcript_and_the_last_risk():
    session, _ = session_with(["Tôi gọi từ ngân hàng.", "Anh đọc mã OTP tôi vừa gửi."])
    session.process(utterance(Speaker.CALLER, 0))
    session.process(utterance(Speaker.CALLER, 2))

    final = session.final_event(4.2, "CLIENT")

    assert final["type"] == "final" and final["endedBy"] == "CLIENT" and final["durationSeconds"] == 4.2
    assert final["transcript"] == "Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi."
    assert [turn["speaker"] for turn in final["turns"]] == ["CALLER", "CALLER"]
    assert final["riskLevel"] == "HIGH" and final["riskScore"] == session.risk_score
    assert final["modelVersion"] == "stand-in" and final["rulesetVersion"] and final["riskEngineVersion"]
    assert session.risk_level == RiskLevel.HIGH


def test_a_call_in_which_nothing_was_recognised_ends_without_a_risk_level():
    session, _ = session_with([])

    final = session.final_event(3.0, "CLIENT")

    assert final["transcript"] == "" and final["turns"] == []
    assert final["riskScore"] is None and final["riskLevel"] is None and final["confidence"] is None


# ------------------------------------------------------------------------------- WebSocket


def app_with(lines: list[str] | None = None, delay: float = 0.0, classifier=True, **settings):
    transcriber = ScriptedTranscriber(lines, delay) if lines is not None else None
    return create_app(make_settings(**settings), transcriber, KeywordClassifier() if classifier else None)


def read_until(websocket, kind: str) -> list[dict]:
    """Reads events up to and including the first one of the given type."""
    events = []
    while True:
        events.append(websocket.receive_json())
        if events[-1]["type"] == kind:
            return events


def test_the_server_can_speak_websocket():
    # The test client talks to the app directly, so it works even when the real server (uvicorn) cannot upgrade
    # a connection. Without one of these libraries uvicorn answers 404 to every WebSocket request.
    import importlib.util

    assert importlib.util.find_spec("websockets") or importlib.util.find_spec("wsproto")


def test_a_connection_without_the_api_key_is_refused():
    client = TestClient(app_with([]))

    for headers in ({}, {"X-API-Key": "wrong-key-0123456789"}):
        with pytest.raises(WebSocketDisconnect) as refused, client.websocket_connect(URL, headers=headers):
            pass
        assert refused.value.code == 4401


def test_a_session_is_refused_with_a_reason_when_a_model_is_not_loaded():
    for app, code in ((app_with(None), "STT_UNAVAILABLE"), (app_with([], classifier=False), "NLP_MODEL_UNAVAILABLE")):
        with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
            assert websocket.receive_json() == {"type": "error", "code": code, "message": websocket_message(code)}
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_json()
            assert closed.value.code == 4503


def websocket_message(code: str) -> str:
    return {"STT_UNAVAILABLE": "The speech-to-text model is not available.",
            "NLP_MODEL_UNAVAILABLE": "The NLP model is not available."}[code]


def test_a_call_is_transcribed_scored_and_alerted_while_it_is_still_going_on():
    app = app_with(["A lô, tôi nghe.", "Tôi gọi từ ngân hàng, anh đọc mã OTP tôi vừa gửi."])

    with TestClient(app).websocket_connect(URL, headers=HEADERS | {"X-Request-Id": "call-42"}) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready" and ready["sessionId"] == "call-42" and ready["apiVersion"] == "1"
        assert ready["audioFormat"] == {"encoding": "pcm_s16le", "sampleRate": 16000, "channels": 1,
                                        "speakerPrefix": {"0": "CALLER", "1": "CALLEE"}}
        assert ready["modelVersion"] == "stand-in" and ready["sttModel"] == "scripted"

        # The callee answers; the result arrives while the call is still open.
        websocket.send_bytes(CALLEE + tone(1) + silence(1))
        first = read_until(websocket, "risk")
        assert [event["type"] for event in first] == ["transcript", "risk"]
        assert first[0]["speaker"] == "CALLEE" and first[1]["riskLevel"] == "LOW"

        # The caller asks for the OTP: the alert comes before the call ends.
        websocket.send_bytes(CALLER + silence(2) + tone(1.5) + silence(1))
        second = read_until(websocket, "alert")
        assert [event["type"] for event in second] == ["transcript", "risk", "alert"]
        assert second[0]["speaker"] == "CALLER" and second[2]["riskLevel"] == "HIGH"

        websocket.send_text(json.dumps({"type": "end"}))
        final = websocket.receive_json()
        assert final["type"] == "final" and final["endedBy"] == "CLIENT"
        assert final["transcript"] == "A lô, tôi nghe. Tôi gọi từ ngân hàng, anh đọc mã OTP tôi vừa gửi."
        assert [turn["speaker"] for turn in final["turns"]] == ["CALLEE", "CALLER"]
        assert final["riskLevel"] == "HIGH" and final["durationSeconds"] == pytest.approx(4.5, abs=0.05)
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 1000
    assert app.state.live_sessions == 0


def test_ending_the_call_recognises_the_sentence_that_was_still_being_spoken():
    app = app_with(["Chuyển tiền ngay nếu không tài khoản sẽ bị khóa."])

    with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_bytes(CALLER + tone(1))
        websocket.send_text('{"type": "end"}')
        events = read_until(websocket, "final")

    assert [event["type"] for event in events][0] == "transcript"
    assert events[-1]["transcript"] == "Chuyển tiền ngay nếu không tài khoản sẽ bị khóa."
    assert {"URGENCY", "ACCOUNT_LOCK_THREAT", "MONEY_TRANSFER"} <= set(events[-1]["indicators"])


@pytest.mark.parametrize(("message", "code"), [
    (b"\x07" + tone(0.1), "INVALID_AUDIO_FRAME"),
    (b"", "INVALID_AUDIO_FRAME"),
    (CALLER + b"\x01\x02\x03", "INVALID_AUDIO_FRAME"),
    (CALLER + bytes(1024 * 1024 + 2), "AUDIO_FRAME_TOO_LARGE"),
    ("hello", "INVALID_MESSAGE"),
    ('{"type": "pause"}', "INVALID_MESSAGE"),
])
def test_messages_that_break_the_protocol_stop_the_session_with_a_reason(message, code):
    app = app_with([])

    with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
        websocket.receive_json()
        if isinstance(message, bytes):
            websocket.send_bytes(message)
        else:
            websocket.send_text(message)
        error = websocket.receive_json()
        assert error["type"] == "error" and error["code"] == code
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4400
    assert app.state.live_sessions == 0


def test_only_the_configured_number_of_calls_is_analysed_at_once():
    app = app_with([], live_max_sessions=1)
    client = TestClient(app)

    with client.websocket_connect(URL, headers=HEADERS) as first:
        assert first.receive_json()["type"] == "ready"
        with client.websocket_connect(URL, headers=HEADERS) as second:
            assert second.receive_json()["code"] == "LIVE_SESSION_LIMIT"
        first.send_text('{"type": "end"}')
        assert first.receive_json()["type"] == "final"
    # The slot is free again.
    with client.websocket_connect(URL, headers=HEADERS) as third:
        assert third.receive_json()["type"] == "ready"


def test_a_call_that_goes_quiet_is_closed_with_its_result():
    app = app_with(["Tôi gọi từ ngân hàng."], live_idle_timeout_seconds=0.4)

    with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_bytes(CALLER + tone(1) + silence(1))
        events = read_until(websocket, "final")

    assert events[-1]["endedBy"] == "IDLE_TIMEOUT"
    assert events[-1]["transcript"] == "Tôi gọi từ ngân hàng."


def test_a_call_longer_than_the_limit_is_closed_with_its_result():
    app = app_with(["Một câu nói."], live_max_session_seconds=2)

    with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_bytes(CALLER + tone(1) + silence(2))
        events = read_until(websocket, "final")

    assert events[-1]["endedBy"] == "MAX_DURATION"


def test_a_session_that_cannot_keep_up_with_the_call_says_so_instead_of_alerting_late():
    # Recognition takes 0.5 s per sentence while only 1 s of audio may wait.
    app = app_with(["một", "hai", "ba", "bốn", "năm"], delay=0.5, live_max_pending_seconds=1.0)

    with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
        websocket.receive_json()
        websocket.send_bytes(CALLER + (tone(1) + silence(1)) * 5)
        events = read_until(websocket, "error")

    assert events[-1]["code"] == "LIVE_SESSION_OVERLOADED"


# --------------------------------------------------- real Whisper and real NLP artifact

ARTIFACT = Path(os.environ.get("AI_NLP_MODEL_DIR", "/opt/models/nlp"))
needs_artifact = pytest.mark.skipif(not (ARTIFACT / CONFIG_FILE).is_file(), reason="no fine-tuned artifact mounted")


def synthesise(tmp_path: Path, name: str, text: str) -> bytes:
    """Speaks a sentence with a speech synthesiser and returns it as PCM16 16 kHz mono."""
    wav, raw = tmp_path / f"{name}.wav", tmp_path / f"{name}.raw"
    subprocess.run(["espeak-ng", "-v", "vi", "-s", "135", "-w", str(wav), text], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav), "-f", "s16le", "-ar", "16000",
                    "-ac", "1", str(raw)], check=True, capture_output=True)
    return raw.read_bytes()


def stream(websocket, prefix: bytes, pcm: bytes, packet_seconds: float = 0.2) -> None:
    size = int(packet_seconds * SAMPLE_RATE) * 2
    for start in range(0, len(pcm), size):
        websocket.send_bytes(prefix + pcm[start:start + size])


@pytest.mark.model
@needs_artifact
def test_real_models_follow_a_synthesised_call_turn_by_turn(tmp_path, whisper, capsys):
    # Synthetic speech is recognised poorly and differently from run to run ("OTP" often comes out as
    # something else), so this test does not claim a risk level for the scam script. It checks what must
    # hold whatever was recognised. Detection on a real recorded call is verified end to end, outside pytest.
    from app.nlp import TextClassifier

    app = create_app(make_settings(), whisper, TextClassifier(ARTIFACT))
    scam = [
        (CALLEE, "A lô, tôi nghe."),
        (CALLER, "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề."),
        (CALLER, "Anh đọc mã OTP tôi vừa gửi, nếu không tài khoản sẽ bị khóa."),
    ]
    ordinary = [
        (CALLER, "Mẹ ơi con nghe."),
        (CALLEE, "Con ơi, học phí kỳ này trường thông báo bao nhiêu rồi con."),
        (CALLER, "Dạ mười hai triệu mẹ ạ, hạn nộp cuối tháng."),
    ]
    results = {}
    for name, script in (("scam", scam), ("ordinary", ordinary)):
        with TestClient(app).websocket_connect(URL, headers=HEADERS) as websocket:
            assert websocket.receive_json()["type"] == "ready"
            for index, (prefix, text) in enumerate(script):
                speech = synthesise(tmp_path, f"{name}{index}", text) + silence(1.2)
                # As in a real call, both streams run all the time: the other side is silent meanwhile.
                stream(websocket, prefix, speech)
                stream(websocket, CALLEE if prefix == CALLER else CALLER, bytes(len(speech)))
            websocket.send_text('{"type": "end"}')
            results[name] = read_until(websocket, "final")

    with capsys.disabled():
        for name, events in results.items():
            final = events[-1]
            print(f"\n[live {name}] {final['riskLevel']} {final['riskScore']} {final['indicators']} | "
                  f"alerts={[e['riskLevel'] for e in events if e['type'] == 'alert']} | {final['transcript']}")

    scam_final, ordinary_final = results["scam"][-1], results["ordinary"][-1]
    assert len(scam_final["turns"]) >= 2 and scam_final["transcript"]
    # Each side's sentences come back under the right speaker and in the order they were spoken.
    assert [turn["speaker"] for turn in scam_final["turns"]][0] == "CALLEE"
    assert [turn["speaker"] for turn in ordinary_final["turns"]][0] == "CALLER"
    for events in results.values():
        final = events[-1]
        risks = [event for event in events if event["type"] == "risk"]
        alerts = [event["riskLevel"] for event in events if event["type"] == "alert"]
        # The final result is the last update, and an alert was sent exactly when the level rose above LOW.
        assert (final["riskScore"], final["riskLevel"]) == (risks[-1]["riskScore"], risks[-1]["riskLevel"])
        highest = max((risk["riskLevel"] for risk in risks), key=["LOW", "MEDIUM", "HIGH"].index)
        assert (alerts[-1] if alerts else "LOW") == highest
        assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
    assert ordinary_final["riskLevel"] == "LOW"
    assert not [event for event in results["ordinary"] if event["type"] == "alert"]
