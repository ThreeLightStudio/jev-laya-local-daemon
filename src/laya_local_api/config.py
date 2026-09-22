from __future__ import annotations

import os

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    model: str = "convaiinnovations/laya"
    subfolder: str | None = "typed-decisions"
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    device: str | None = None

    @field_validator("host")
    @classmethod
    def localhost_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LAYA_HOST must be a loopback address (127.0.0.1, localhost, or ::1)")
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        subfolder = os.getenv("LAYA_SUBFOLDER", "typed-decisions").strip()
        device = os.getenv("LAYA_DEVICE")
        return cls(
            model=os.getenv("LAYA_MODEL", "convaiinnovations/laya"),
            subfolder=subfolder or None,
            host=os.getenv("LAYA_HOST", "127.0.0.1"),
            port=int(os.getenv("LAYA_PORT", "8787")),
            device=device.strip() if device and device.strip() else None,
        )

    @property
    def model_label(self) -> str:
        return f"{self.model}/{self.subfolder}" if self.subfolder else self.model

