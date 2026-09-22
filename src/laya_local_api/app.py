from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import Settings
from .model import ModelNotReadyError, ModelRuntime
from .schemas import DecideRequest

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    runtime: ModelRuntime | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_runtime = runtime or ModelRuntime(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = resolved_runtime
        loader_thread = threading.Thread(
            target=resolved_runtime.load,
            name="laya-model-loader",
            daemon=True,
        )
        loader_thread.start()
        try:
            yield
        finally:
            resolved_runtime.release()

    app = FastAPI(title="Laya Local API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> Any:
        current_runtime: ModelRuntime = app.state.runtime
        payload: dict[str, Any] = {
            "ready": current_runtime.ready,
            "model": resolved_settings.model_label,
            "status": current_runtime.status,
        }
        if current_runtime.error:
            payload["error"] = current_runtime.error
        if current_runtime.ready:
            return payload
        return JSONResponse(status_code=503, content=payload)

    @app.post("/v1/decide")
    def decide(request: DecideRequest) -> dict[str, Any]:
        current_runtime: ModelRuntime = app.state.runtime
        try:
            return current_runtime.predict(request.state, request.native_questions())
        except ModelNotReadyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Laya inference failed")
            raise HTTPException(status_code=500, detail="Laya inference failed") from exc

    return app


app = create_app()
