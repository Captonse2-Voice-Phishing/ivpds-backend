import pytest

from app.audio import AudioProcessor
from app.errors import ApiError

FORMATS = ["speech.wav", "speech.mp3", "speech.m4a", "speech.ogg", "speech.webm", "speech.flac", "speech.3gp",
           "speech.aac"]


@pytest.fixture
def processor():
    return AudioProcessor(timeout_seconds=60, max_seconds=600)


def test_ffmpeg_is_available():
    assert AudioProcessor.available()


def test_probe_reads_the_real_properties_of_the_file(processor, samples):
    info = processor.probe(samples["speech.wav"])

    assert info.container == "wav"
    assert info.codec == "pcm_s16le"
    assert info.sample_rate == 22050
    assert info.channels == 1
    assert 5 < info.duration_seconds < 10


@pytest.mark.parametrize("name", FORMATS)
def test_every_supported_format_is_normalised_to_16k_mono_pcm(processor, samples, tmp_path, name):
    expected_duration = processor.probe(samples["speech.wav"]).duration_seconds

    info = processor.normalize(samples[name], tmp_path / "out.wav")

    assert (info.container, info.codec, info.sample_rate, info.channels) == ("wav", "pcm_s16le", 16000, 1)
    assert info.duration_seconds == pytest.approx(expected_duration, abs=0.3)


def test_stereo_44k_audio_is_downmixed_and_resampled(processor, samples, tmp_path):
    source = processor.probe(samples["tone_stereo_44k.wav"])

    info = processor.normalize(samples["tone_stereo_44k.wav"], tmp_path / "out.wav")

    assert (source.sample_rate, source.channels) == (44100, 2)
    assert (info.sample_rate, info.channels) == (16000, 1)
    assert info.duration_seconds == pytest.approx(5.0, abs=0.1)
    # 5 seconds of 16 kHz 16-bit mono is 160 000 bytes plus the WAV header.
    assert (tmp_path / "out.wav").stat().st_size == pytest.approx(160_000, abs=200)


def test_audio_track_of_a_video_file_is_extracted_without_the_video(processor, samples, tmp_path):
    info = processor.normalize(samples["video.mp4"], tmp_path / "out.wav")

    assert (info.codec, info.channels) == ("pcm_s16le", 1)
    assert info.duration_seconds == pytest.approx(2.0, abs=0.3)


@pytest.mark.parametrize("name", ["text.wav", "empty.wav", "playlist.wav", "concat.wav"])
def test_files_that_are_not_audio_are_rejected(processor, samples, tmp_path, name):
    for operation in (lambda: processor.probe(samples[name]),
                      lambda: processor.normalize(samples[name], tmp_path / "out.wav")):
        with pytest.raises(ApiError) as error:
            operation()

        assert error.value.code == "INVALID_AUDIO"
        assert error.value.status_code == 422
        # The message goes to the caller, so it must not reveal server paths.
        assert str(samples[name].parent) not in error.value.message


def test_playlist_cannot_make_ffmpeg_read_another_file(processor, samples, tmp_path):
    target = tmp_path / "out.wav"

    with pytest.raises(ApiError):
        processor.normalize(samples["concat.wav"], target)

    # The playlist points at a perfectly valid audio file; nothing of it may come out.
    assert not target.exists() or target.stat().st_size == 0


def test_audio_longer_than_the_limit_is_rejected(samples, tmp_path):
    short_limit = AudioProcessor(timeout_seconds=60, max_seconds=2)

    with pytest.raises(ApiError) as error:
        short_limit.normalize(samples["tone_stereo_44k.wav"], tmp_path / "out.wav")

    assert error.value.code == "AUDIO_TOO_LONG"
    # Decoding stopped right after the limit instead of converting the whole file.
    assert (tmp_path / "out.wav").stat().st_size < 16000 * 2 * 4


def test_audio_exactly_at_the_limit_is_accepted(samples, tmp_path):
    exact_limit = AudioProcessor(timeout_seconds=60, max_seconds=5)

    info = exact_limit.normalize(samples["tone_stereo_44k.wav"], tmp_path / "out.wav")

    assert info.duration_seconds == pytest.approx(5.0, abs=0.01)


def test_timeout_is_reported_as_a_service_problem_not_as_bad_audio(samples):
    impatient = AudioProcessor(timeout_seconds=0.0001, max_seconds=600)

    with pytest.raises(ApiError) as error:
        impatient.probe(samples["speech.wav"])

    assert (error.value.status_code, error.value.code) == (503, "AUDIO_PROCESSING_TIMEOUT")


def test_missing_ffmpeg_is_reported_as_unavailable(processor, samples, monkeypatch):
    monkeypatch.setenv("PATH", "")

    assert not AudioProcessor.available()
    with pytest.raises(ApiError) as error:
        processor.probe(samples["speech.wav"])

    assert (error.value.status_code, error.value.code) == (503, "AUDIO_PROCESSING_UNAVAILABLE")
