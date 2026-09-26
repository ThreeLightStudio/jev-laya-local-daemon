from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    model: str = "convaiinnovations/laya"
    subfolder: str | None = "typed-decisions"
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=0, le=65535)
    port_strict: bool = False
    device: str | None = None
    jev_api_key: str | None = None
    jev_model: str = "jev-latest"
    jev_api_url: str = "https://api.typesafe.ai"
    jev_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("host")
    @classmethod
    def localhost_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("DAEMON_HOST must be a loopback address (127.0.0.1, localhost, or ::1)")
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        subfolder = os.getenv("LAYA_SUBFOLDER", "typed-decisions").strip()
        device = os.getenv("LAYA_DEVICE")
        jev_api_key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
        return cls(
            model=os.getenv("LAYA_MODEL", "convaiinnovations/laya"),
            subfolder=subfolder or None,
            host=os.getenv("DAEMON_HOST", "127.0.0.1"),
            port=int(os.getenv("DAEMON_PORT", "8787")),
            port_strict=os.getenv("DAEMON_PORT_STRICT", "").strip().lower() in {"1", "true", "yes"},
            device=device.strip() if device and device.strip() else None,
            jev_api_key=jev_api_key.strip() if jev_api_key and jev_api_key.strip() else None,
            jev_model=os.getenv("JEV_MODEL", "jev-latest").strip() or "jev-latest",
            jev_api_url=(os.getenv("JEV_API_URL", "https://api.typesafe.ai").strip().rstrip("/")),
            jev_timeout_seconds=float(os.getenv("JEV_TIMEOUT_SECONDS", "30")),
        )

    @property
    def model_label(self) -> str:
        return f"{self.model}/{self.subfolder}" if self.subfolder else self.model
