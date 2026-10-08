import pytest
from pydantic import ValidationError

from app.config import Settings


def test_api_key_is_required(monkeypatch):
    monkeypatch.delenv("AI_API_KEY")

    with pytest.raises(ValidationError) as error:
        Settings()

    assert "api_key" in str(error.value)


def test_short_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "too-short")

    with pytest.raises(ValidationError):
        Settings()


def test_unknown_log_level_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        Settings()


def test_defaults_and_overrides(monkeypatch):
    assert Settings().log_level == "INFO"
    assert Settings().service_name == "ivpds-ai"

    monkeypatch.setenv("AI_LOG_LEVEL", "DEBUG")

    assert Settings().log_level == "DEBUG"


def test_settings_do_not_expose_the_api_key_under_an_unprefixed_name(monkeypatch):
    # Only AI_-prefixed variables are read, so an unrelated API_KEY in the environment is ignored.
    monkeypatch.delenv("AI_API_KEY")
    monkeypatch.setenv("API_KEY", "unprefixed-key-0123456789")

    with pytest.raises(ValidationError):
        Settings()
