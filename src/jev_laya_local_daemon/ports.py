from __future__ import annotations

import shutil
import socket
import subprocess

SCAN_RANGE = 100


class PortUnavailableError(RuntimeError):
    pass


def _socket_family(host: str) -> socket.AddressFamily:
    return socket.AF_INET6 if host == "::1" else socket.AF_INET


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(_socket_family(host), socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _ephemeral_port(host: str) -> int:
    with socket.socket(_socket_family(host), socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, 0))
        return probe.getsockname()[1]


def find_occupant(port: int) -> str | None:
    if shutil.which("lsof") is None:
        return None
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            return f"{fields[0]} (pid {fields[1]})"
    return None


def resolve_port(host: str, preferred: int, *, strict: bool = False) -> int:
    if preferred == 0:
        return _ephemeral_port(host)
    if _port_is_free(host, preferred):
        return preferred
    if strict:
        raise PortUnavailableError(f"port {preferred} on {host} is already in use")
    last = min(preferred + SCAN_RANGE, 65535)
    for port in range(preferred + 1, last + 1):
        if _port_is_free(host, port):
            return port
    raise PortUnavailableError(f"no free port found between {preferred + 1} and {last}")
