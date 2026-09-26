import socket

import pytest

from jev_laya_local_daemon.ports import PortUnavailableError, resolve_port


@pytest.fixture
def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _occupy(port: int) -> socket.socket:
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def test_free_preferred_port_is_used(free_port: int) -> None:
    assert resolve_port("127.0.0.1", free_port) == free_port


def test_occupied_port_falls_back_to_next(free_port: int) -> None:
    with _occupy(free_port):
        assert resolve_port("127.0.0.1", free_port) == free_port + 1


def test_fallback_skips_occupied_ports(free_port: int) -> None:
    with _occupy(free_port), _occupy(free_port + 1):
        assert resolve_port("127.0.0.1", free_port) == free_port + 2


def test_strict_mode_rejects_occupied_port(free_port: int) -> None:
    with _occupy(free_port):
        with pytest.raises(PortUnavailableError):
            resolve_port("127.0.0.1", free_port, strict=True)


def test_exhausted_scan_range_raises(free_port: int, monkeypatch) -> None:
    monkeypatch.setattr("jev_laya_local_daemon.ports._port_is_free", lambda host, port: False)
    with pytest.raises(PortUnavailableError):
        resolve_port("127.0.0.1", free_port)


def test_port_zero_returns_bindable_port() -> None:
    port = resolve_port("127.0.0.1", 0)
    assert 1 <= port <= 65535
    with _occupy(port):
        pass


def test_resolved_fallback_port_is_bindable(free_port: int) -> None:
    with _occupy(free_port):
        resolved = resolve_port("127.0.0.1", free_port)
    with _occupy(resolved):
        pass
