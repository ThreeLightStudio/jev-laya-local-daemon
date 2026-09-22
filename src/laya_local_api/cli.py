from __future__ import annotations

import logging

import uvicorn

from .app import create_app
from .config import Settings
from .model import ModelRuntime


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    runtime = ModelRuntime(settings)

    print("laya-local-api")
    print(f"Laya: {settings.model_label}")
    print(f"Jev: {settings.jev_model} ({'configured' if settings.jev_api_key else 'not configured'})")
    print(f"Listening: http://{settings.host}:{settings.port}")
    print("Laya status: loading")

    uvicorn.run(
        create_app(settings=settings, runtime=runtime),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
