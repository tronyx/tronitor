"""Shared pytest fixtures for the tronitor tests."""

from collections.abc import Iterator

import pytest
from fake_server import FakeServer


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    """Yield a started fake HTTP server (never reached through a proxy) and shut it down afterwards."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    with FakeServer() as server:
        yield server
