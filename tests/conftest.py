"""Shared pytest fixtures for the tronitor tests."""

from collections.abc import Iterator
from typing import Any

import pytest
from fake_server import FakeServer

import tronitor

HC_UUID_FILESYSTEM = "31365bce-8da9-4729-8ff3-aaa71d56b712"
HC_UUID_DATABASE = "4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41"


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    """Yield a started fake HTTP server (never reached through a proxy) and shut it down afterwards."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    with FakeServer() as server:
        yield server


def _hc_check(uuid: str, name: str, slug: str, status: str) -> dict[str, Any]:
    """Return one canned Healthchecks check."""
    return {
        "name": name,
        "slug": slug,
        "tags": "backup",
        "grace": 3600,
        "timeout": 86400,
        "ping_url": f"https://hc-ping.com/{uuid}",
        "update_url": f"https://healthchecks.io/api/v3/checks/{uuid}",
        "pause_url": f"https://healthchecks.io/api/v3/checks/{uuid}/pause",
        "resume_url": f"https://healthchecks.io/api/v3/checks/{uuid}/resume",
        "channels": "",
        "n_pings": 12,
        "last_ping": "2026-11-05T02:00:00+00:00",
        "status": status,
        "uuid": uuid,
    }


def hc_fixture_checks() -> list[dict[str, Any]]:
    """Return two canned Healthchecks checks: one up and one paused."""
    return [
        _hc_check(HC_UUID_FILESYSTEM, "Filesystem Backup", "filesystem-backup", "up"),
        _hc_check(HC_UUID_DATABASE, "Database Backup", "database-backup", "paused"),
    ]


@pytest.fixture
def hc_provider(fake_server: FakeServer) -> tronitor.HealthchecksProvider:
    """Return a Healthchecks provider that talks to the fake server."""
    return tronitor.HealthchecksProvider(tronitor.Http(), tronitor.HealthchecksConfig(fake_server.url, "hc-test-key"))
