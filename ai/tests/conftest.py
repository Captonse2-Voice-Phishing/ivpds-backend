import subprocess
from pathlib import Path

import pytest

# Imported first: it sets AI_API_KEY before the app reads its settings.
from helpers import API_KEY, SPEECH_TEXT, make_settings

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.stt import WhisperTranscriber  # noqa: E402


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    # Server exceptions are turned into responses, as they are for a real HTTP client.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth():
    return {"X-API-Key": API_KEY}


def _run(*command: object) -> None:
    subprocess.run([str(part) for part in command], check=True, capture_output=True)


def _ffmpeg(*args: object) -> None:
    _run("ffmpeg", "-nostdin", "-v", "error", "-y", *args)


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    """Real audio files in every supported container, plus files that must be rejected."""
    folder = tmp_path_factory.mktemp("audio")
    files = {name: folder / name for name in [
        "speech.wav", "speech.mp3", "speech.m4a", "speech.ogg", "speech.webm", "speech.flac", "speech.3gp",
        "speech.aac", "tone_stereo_44k.wav", "silence.wav", "video.mp4",
        "text.wav", "empty.wav", "playlist.wav", "concat.wav",
    ]}

    _run("espeak-ng", "-v", "vi", "-s", "140", "-w", files["speech.wav"], SPEECH_TEXT)
    for name, codec in [
        ("speech.mp3", ["-c:a", "libmp3lame"]),
        ("speech.m4a", ["-c:a", "aac"]),
        ("speech.ogg", ["-c:a", "libvorbis"]),
        ("speech.webm", ["-c:a", "libopus"]),
        ("speech.flac", ["-c:a", "flac"]),
        ("speech.3gp", ["-c:a", "aac"]),
        ("speech.aac", ["-c:a", "aac", "-f", "adts"]),
    ]:
        _ffmpeg("-i", files["speech.wav"], *codec, files[name])

    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-ar", "44100", "-ac", "2",
            files["tone_stereo_44k.wav"])
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "5", files["silence.wav"])
    _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10", "-i", files["speech.wav"],
            "-c:v", "mpeg4", "-c:a", "aac", "-shortest", files["video.mp4"])

    files["text.wav"].write_text("this is not audio\n" * 50)
    files["empty.wav"].write_bytes(b"")
    # Playlists disguised as audio: they point FFmpeg at another file on the server.
    files["playlist.wav"].write_text(
        f"#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:1.0,\nfile://{files['speech.wav']}\n#EXT-X-ENDLIST\n")
    files["concat.wav"].write_text(f"ffconcat version 1.0\nfile {files['speech.wav']}\n")
    return files


@pytest.fixture(scope="session")
def whisper() -> WhisperTranscriber:
    """The real Whisper model, loaded once for the whole test run."""
    settings = make_settings()
    return WhisperTranscriber(
        model=settings.whisper_model,
        compute_type=settings.whisper_compute_type,
        language=settings.whisper_language,
        beam_size=settings.whisper_beam_size,
        cpu_threads=settings.whisper_cpu_threads,
    )
