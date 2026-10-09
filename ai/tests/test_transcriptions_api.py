from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audio import AudioProcessor
from app.evaluation import word_error_rate
from app.main import create_app
from app.stt import Segment, Transcript
from helpers import SPEECH_TEXT, expected_model_name, make_settings

URL = "/v1/transcriptions"


class RecordingTranscriber:
    """Stands in for the model in tests of the HTTP layer and the FFmpeg stage.

    It records what the speech-to-text stage was given. The real model is exercised by the tests
    marked ``model`` further down and in test_stt.py.
    """

    name = "recording-stub"

    def __init__(self):
        self.received: list[tuple[Path, object]] = []

    def transcribe(self, wav_path: Path) -> Transcript:
        info = AudioProcessor(timeout_seconds=60, max_seconds=600).probe(wav_path)
        self.received.append((wav_path, info))
        return Transcript(text="xin chào", language="vi", segments=[Segment(0.0, 1.0, "xin chào")])


class FailingTranscriber:
    name = "failing-stub"

    def transcribe(self, wav_path: Path) -> Transcript:
        raise RuntimeError("secret model internals")


def client_for(transcriber=None, **settings) -> TestClient:
    return TestClient(create_app(make_settings(**settings), transcriber), raise_server_exceptions=False)


def upload(client, auth, content: bytes, filename="call.wav"):
    return client.post(URL, headers=auth, files={"audio": (filename, content, "application/octet-stream")})


# ------------------------------------------------------------------- access and availability


def test_transcription_requires_an_api_key(samples):
    client = client_for(RecordingTranscriber())

    response = client.post(URL, files={"audio": ("call.wav", samples["speech.wav"].read_bytes())})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_transcription_reports_when_the_model_is_not_loaded(auth, samples):
    client = client_for(transcriber=None)

    response = upload(client, auth, samples["speech.wav"].read_bytes())

    assert response.status_code == 503
    assert response.json()["code"] == "STT_UNAVAILABLE"
    info = client.get("/v1/info", headers=auth).json()
    assert info["components"]["speechToText"] == "UNAVAILABLE"
    assert info.get("sttModel") is None


def test_service_still_starts_when_the_model_cannot_be_loaded(auth, samples):
    app = create_app(make_settings(whisper_model="/no/such/model/directory"))

    # Entering the context runs the real startup, including the failed model load.
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").json() == {"status": "UP"}
        assert client.get("/v1/info", headers=auth).json()["components"]["speechToText"] == "UNAVAILABLE"
        assert upload(client, auth, samples["speech.wav"].read_bytes()).json()["code"] == "STT_UNAVAILABLE"


# ---------------------------------------------------------------------------- FFmpeg stage


def test_speech_to_text_receives_normalised_audio_and_temp_files_are_removed(auth, samples):
    transcriber = RecordingTranscriber()
    client = client_for(transcriber)

    response = upload(client, auth, samples["speech.m4a"].read_bytes(), filename="../../etc/passwd.m4a")

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "xin chào"
    assert body["language"] == "vi"
    assert body["sttModel"] == "recording-stub"
    assert body["segments"] == [{"start": 0.0, "end": 1.0, "text": "xin chào"}]
    # What the caller sent ...
    assert body["audio"]["container"].startswith("mov")
    assert (body["audio"]["codec"], body["audio"]["sampleRate"], body["audio"]["channels"]) == ("aac", 22050, 1)
    assert 5 < body["audio"]["durationSeconds"] < 10
    assert body["processing"]["audioMs"] >= 0 and body["processing"]["speechToTextMs"] >= 0
    # ... and what Whisper was given.
    path, info = transcriber.received[0]
    assert (info.codec, info.sample_rate, info.channels) == ("pcm_s16le", 16000, 1)
    # The caller's file name is never used on disk, and nothing is left behind.
    assert "passwd" not in str(path)
    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize(("name", "code"), [
    ("text.wav", "INVALID_AUDIO"),
    ("playlist.wav", "INVALID_AUDIO"),
    ("concat.wav", "INVALID_AUDIO"),
    ("empty.wav", "EMPTY_AUDIO"),
])
def test_invalid_uploads_are_rejected_before_speech_to_text(auth, samples, name, code):
    transcriber = RecordingTranscriber()
    client = client_for(transcriber)

    response = upload(client, auth, samples[name].read_bytes())

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert transcriber.received == []


def test_audio_longer_than_the_limit_is_rejected(auth, samples):
    transcriber = RecordingTranscriber()
    client = client_for(transcriber, max_audio_seconds=2)

    response = upload(client, auth, samples["speech.wav"].read_bytes())

    assert (response.status_code, response.json()["code"]) == (422, "AUDIO_TOO_LONG")
    assert transcriber.received == []


def test_missing_audio_part_is_a_validation_error(auth):
    client = client_for(RecordingTranscriber())

    response = client.post(URL, headers=auth, data={"note": "no file here"})

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")
    assert response.json()["fieldErrors"][0]["field"] == "audio"


# ------------------------------------------------------------------------------ size limits


def test_file_larger_than_the_audio_limit_is_rejected(auth, samples):
    transcriber = RecordingTranscriber()
    client = client_for(transcriber, max_audio_bytes=1000)

    response = upload(client, auth, samples["speech.wav"].read_bytes())

    assert (response.status_code, response.json()["code"]) == (413, "AUDIO_TOO_LARGE")
    assert transcriber.received == []


def test_oversized_request_is_refused_even_without_an_api_key():
    # The body is read before the API key is checked, so the size limit must not depend on the key.
    client = client_for(RecordingTranscriber(), max_audio_bytes=1000)
    too_big = b"x" * (1000 + 2 * 1024 * 1024)

    response = client.post(URL, files={"audio": ("call.wav", too_big)})

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert response.json()["requestId"] == response.headers["X-Request-Id"]


def test_oversized_request_without_content_length_is_refused(auth):
    client = client_for(RecordingTranscriber(), max_audio_bytes=1000)

    def chunks():
        # A generator body is sent with chunked transfer encoding, i.e. no Content-Length header.
        yield b"--b\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"a.wav\"\r\n\r\n"
        for _ in range(3 * 1024):
            yield b"x" * 1024
        yield b"\r\n--b--\r\n"

    response = client.post(URL, headers={**auth, "Content-Type": "multipart/form-data; boundary=b"},
                           content=chunks())

    assert response.status_code in (400, 413)
    assert response.json()["code"] in ("BAD_REQUEST", "PAYLOAD_TOO_LARGE")


# -------------------------------------------------------------------------- failure handling


def test_model_failure_is_an_error_never_a_made_up_transcript(auth, samples):
    client = client_for(FailingTranscriber())

    response = upload(client, auth, samples["speech.wav"].read_bytes())

    assert (response.status_code, response.json()["code"]) == (500, "STT_FAILED")
    assert "transcript" not in response.json()
    assert "secret model internals" not in response.text


# ------------------------------------------------------------ the real pipeline, end to end


@pytest.mark.model
def test_real_pipeline_transcribes_uploaded_vietnamese_speech(auth, samples, whisper, capsys):
    client = client_for(whisper)

    response = upload(client, auth, samples["speech.mp3"].read_bytes(), filename="call.mp3")

    assert response.status_code == 200
    body = response.json()
    with capsys.disabled():
        print(f"\n  response: {body}")
        print(f"  WER on synthetic voice: {word_error_rate(SPEECH_TEXT, body['transcript']):.2f} (not a quality claim)")
    assert len(body["transcript"].split()) >= 5
    assert body["language"] == "vi"
    assert body["sttModel"] == expected_model_name()
    assert (body["audio"]["container"], body["audio"]["codec"]) == ("mp3", "mp3")
    assert body["segments"] and body["transcript"] == " ".join(s["text"] for s in body["segments"])
    assert body["processing"]["speechToTextMs"] > 0


@pytest.mark.model
def test_real_pipeline_returns_an_empty_transcript_for_silence(auth, samples, whisper):
    client = client_for(whisper)

    response = upload(client, auth, samples["silence.wav"].read_bytes())

    assert response.status_code == 200
    assert response.json()["transcript"] == ""
    assert response.json()["segments"] == []


@pytest.mark.model
def test_info_reports_ready_components_once_the_model_is_loaded(auth, whisper):
    client = client_for(whisper)

    body = client.get("/v1/info", headers=auth).json()

    assert body["components"] == {
        "audioProcessing": "READY",
        "speechToText": "READY",
        "ruleEngine": "READY",
        # No fine-tuned artifact is given to this client.
        "nlpModel": "UNAVAILABLE",
        "riskEngine": "NOT_IMPLEMENTED",
    }
    assert body["sttModel"] == expected_model_name()
