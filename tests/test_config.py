import pytest
from pydantic import ValidationError

from laya_local_api.config import Settings


def test_default_host_is_loopback() -> None:
    assert Settings().host == "127.0.0.1"


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")


def test_jev_defaults() -> None:
    settings = Settings()
    assert settings.jev_api_key is None
    assert settings.jev_model == "jev-latest"
    assert settings.jev_api_url == "https://api.typesafe.ai"


def test_jev_env_configuration(monkeypatch) -> None:
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.setenv("JEV_MODEL", "jev-1.13.0")
    monkeypatch.setenv("JEV_API_URL", "https://example.test/")
    monkeypatch.setenv("JEV_TIMEOUT_SECONDS", "12.5")
    settings = Settings.from_env()
    assert settings.jev_api_key == "test-key"
    assert settings.jev_model == "jev-1.13.0"
    assert settings.jev_api_url == "https://example.test"
    assert settings.jev_timeout_seconds == 12.5
