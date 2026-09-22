import pytest
from pydantic import ValidationError

from laya_local_api.config import Settings


def test_default_host_is_loopback() -> None:
    assert Settings().host == "127.0.0.1"


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")
