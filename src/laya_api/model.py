from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol

from .config import Settings

logger = logging.getLogger(__name__)


class LayaAgent(Protocol):
    def predict(self, state: str | dict[str, Any] | list[Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]: ...


Loader = Callable[[Settings], LayaAgent]


def load_laya_agent(settings: Settings) -> LayaAgent:
    import laya

    return laya.load(
        settings.model,
        device=settings.device,
        subfolder=settings.subfolder,
    )


class ModelNotReadyError(RuntimeError):
    pass


class ModelRuntime:
    def __init__(self, settings: Settings, loader: Loader = load_laya_agent) -> None:
        self.settings = settings
        self._loader = loader
        self._agent: LayaAgent | None = None
        self._status = "not_started"
        self._error: str | None = None
        self._load_count = 0
        self._state_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    @property
    def status(self) -> str:
        with self._state_lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._state_lock:
            return self._error

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def load_count(self) -> int:
        with self._state_lock:
            return self._load_count

    def load(self) -> None:
        with self._state_lock:
            if self._status in {"loading", "ready"}:
                return
            self._status = "loading"
            self._error = None
            self._load_count += 1

        try:
            agent = self._loader(self.settings)
        except Exception as exc:
            with self._state_lock:
                self._status = "failed"
                self._error = str(exc)
            logger.exception("Failed to load Laya model %s", self.settings.model_label)
            return

        with self._state_lock:
            self._agent = agent
            self._status = "ready"
        logger.info("Laya model ready: %s", self.settings.model_label)
        logger.info("Status: ready")

    def predict(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        with self._state_lock:
            agent = self._agent
            status = self._status

        if status != "ready" or agent is None:
            raise ModelNotReadyError(f"model is not ready (status={status})")

        with self._inference_lock:
            return agent.predict(state, questions)

    def release(self) -> None:
        # Laya 0.3.5 Agent exposes no close/unload API. Dropping the reference lets
        # Python release the model normally during process shutdown.
        with self._state_lock:
            self._agent = None
            if self._status == "ready":
                self._status = "stopped"
