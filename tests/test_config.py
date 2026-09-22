import pytest
from pydantic import ValidationError

from jev_laya_local_daemon.config import Settings


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


def test_daemon_env_configuration(monkeypatch) -> None:
    monkeypatch.setenv("DAEMON_HOST", "localhost")
    monkeypatch.setenv("DAEMON_PORT", "8790")
    settings = Settings.from_env()
    assert settings.host == "localhost"
    assert settings.port == 8790


def test_repo_root_dotenv_is_loaded(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("DAEMON_PORT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "JEV_API_KEY=dotenv-key\n"
        "DAEMON_PORT=8899\n"
    )

    settings = Settings.from_env()

    assert settings.jev_api_key == "dotenv-key"
    assert settings.port == 8899
