"""Tests that run the real Whisper model on CPU."""

import pytest

from app.audio import AudioProcessor
from app.evaluation import word_error_rate
from app.stt import model_label
from helpers import SPEECH_TEXT, expected_model_name

pytestmark = pytest.mark.model


@pytest.fixture
def normalise(samples, tmp_path):
    processor = AudioProcessor(timeout_seconds=60, max_seconds=600)

    def run(name):
        target = tmp_path / f"{name}.normalized.wav"
        info = processor.normalize(samples[name], target)
        return target, info

    return run


def test_model_identifies_itself(whisper):
    assert whisper.name == expected_model_name()


@pytest.mark.parametrize(("model", "label"), [
    ("small", "small"),
    ("large-v3-turbo", "large-v3-turbo"),
    ("/models/local/phowhisper-medium-int8", "phowhisper-medium-int8"),
    ("/models/local/phowhisper-medium-int8/", "phowhisper-medium-int8"),
])
def test_model_label_hides_server_paths(model, label):
    assert model_label(model) == label


def test_vietnamese_speech_is_transcribed_into_vietnamese_text(whisper, normalise, capsys):
    wav, info = normalise("speech.wav")

    transcript = whisper.transcribe(wav)

    with capsys.disabled():
        # Shown in the test output as evidence of what the model actually produced.
        print(f"\n  synthetic speech said : {SPEECH_TEXT}")
        print(f"  whisper transcribed   : {transcript.text}")
        print(f"  WER on synthetic voice: {word_error_rate(SPEECH_TEXT, transcript.text):.2f} (not a quality claim)")
    assert transcript.language == "vi"
    assert len(transcript.text.split()) >= 5
    # Vietnamese text, not a transliteration: it contains Vietnamese diacritics.
    assert any(ch in transcript.text.lower() for ch in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    assert transcript.text == " ".join(s.text for s in transcript.segments)
    for segment in transcript.segments:
        assert 0 <= segment.start < segment.end <= info.duration_seconds + 0.5
    starts = [s.start for s in transcript.segments]
    assert starts == sorted(starts)


@pytest.mark.parametrize("name", ["silence.wav", "tone_stereo_44k.wav"])
def test_audio_without_speech_gives_an_empty_transcript_not_invented_words(whisper, normalise, name):
    # Without the voice-activity filter, Whisper answers silence with a made-up sentence
    # ("Hãy subscribe cho kênh ..."). A scam detector must never analyse words nobody said.
    wav, _ = normalise(name)

    transcript = whisper.transcribe(wav)

    assert transcript.text == ""
    assert transcript.segments == []


def test_transcription_is_repeatable(whisper, normalise):
    wav, _ = normalise("speech.wav")

    assert whisper.transcribe(wav).text == whisper.transcribe(wav).text
