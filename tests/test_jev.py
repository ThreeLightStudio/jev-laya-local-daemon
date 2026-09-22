from __future__ import annotations

import json

import pytest

from jev_laya_local_daemon.config import Settings
from jev_laya_local_daemon.jev import JevClient, JevNotConfiguredError


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_jev_client_builds_official_systemone_request(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "model": "jev-1.13.0",
                "answers": {"x": {"type": "noul", "noul": 0.9, "stats": {}}},
                "usage": {"input_tokens": 12, "output_tokens": 2},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    settings = Settings(
        jev_api_key="secret-key",
        jev_model="jev-latest",
        jev_api_url="https://api.typesafe.ai",
        jev_timeout_seconds=7.5,
    )
    client = JevClient(settings)
    result = client.predict(
        {"message": "hello"},
        {"x": {"type": "noul", "instructions": "Is this a greeting?"}},
    )

    assert result["model"] == "jev-1.13.0"
    assert captured == {
        "url": "https://api.typesafe.ai/v1/systemone",
        "method": "POST",
        "authorization": "Bearer secret-key",
        "content_type": "application/json",
        "body": {
            "model": "jev-latest",
            "state": {"message": "hello"},
            "questions": {"x": {"type": "noul", "instructions": "Is this a greeting?"}},
        },
        "timeout": 7.5,
    }


def test_jev_client_requires_api_key() -> None:
    client = JevClient(Settings())
    with pytest.raises(JevNotConfiguredError, match="JEV_API_KEY"):
        client.predict({}, {"x": {"type": "noul", "instructions": "Proceed?"}})
