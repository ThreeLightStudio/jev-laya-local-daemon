from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import Settings


class JevNotConfiguredError(RuntimeError):
    pass


class JevUpstreamError(RuntimeError):
    pass


class JevClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.jev_api_key)

    def predict(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        api_key = self.settings.jev_api_key
        if not api_key:
            raise JevNotConfiguredError("Jev provider is not configured; set JEV_API_KEY")

        payload = {
            "model": self.settings.jev_model,
            "state": state,
            "questions": questions,
        }
        request = urllib.request.Request(
            f"{self.settings.jev_api_url}/v1/systemone",
            data=json.dumps(payload).encode(),
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.jev_timeout_seconds,
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise JevUpstreamError("Jev authentication failed") from exc
            if exc.code == 429:
                raise JevUpstreamError("Jev rate limit exceeded") from exc
            raise JevUpstreamError(f"Jev upstream request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise JevUpstreamError("Jev upstream request failed") from exc
