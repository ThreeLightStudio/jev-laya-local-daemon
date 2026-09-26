from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from .app import create_app
from .config import Settings
from .model import ModelRuntime
from .ports import PortUnavailableError, find_occupant, resolve_port


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jev-laya-local-daemon")
    parser.add_argument("--host", help="loopback bind address (overrides DAEMON_HOST)")
    parser.add_argument("--port", type=int, help="preferred port (overrides DAEMON_PORT)")
    return parser.parse_args()


def _resolve_settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    values = settings.model_dump()
    if args.host:
        values["host"] = args.host
    if args.port is not None:
        values["port"] = args.port
    return Settings(**values)


def _fail_unavailable(settings: Settings) -> None:
    occupant = find_occupant(settings.port)
    print(f"error: port {settings.port} on {settings.host} is already in use" + (f" by {occupant}" if occupant else ""), file=sys.stderr)
    print(f"  lsof -nP -iTCP:{settings.port} -sTCP:LISTEN   # who owns it", file=sys.stderr)
    print(f"  DAEMON_PORT=8790 jev-laya-local-daemon   # or pick another port", file=sys.stderr)
    print("  auto-fallback is disabled (DAEMON_PORT_STRICT=1)", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = _resolve_settings(args)

    try:
        port = resolve_port(settings.host, settings.port, strict=settings.port_strict)
    except PortUnavailableError:
        _fail_unavailable(settings)

    print("jev-laya-local-daemon")
    print(f"Laya: {settings.model_label}")
    print(f"Jev: {settings.jev_model} ({'configured' if settings.jev_api_key else 'not configured'})")
    if settings.port == 0:
        print(f"Port: auto-selected by the OS")
    elif port != settings.port:
        occupant = find_occupant(settings.port)
        print(f"Port {settings.port} is in use" + (f" by {occupant}" if occupant else "") + f"; falling back to {port}")
        print(f"Callers: DECISION_API_URL=http://{settings.host}:{port}")
    print(f"Listening: http://{settings.host}:{port}")
    print("Laya status: loading")

    runtime = ModelRuntime(settings)
    uvicorn.run(
        create_app(settings=settings, runtime=runtime),
        host=settings.host,
        port=port,
        log_level="info",
    )
