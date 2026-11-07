"""Shared pytest fixtures for the tronitor tests."""

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fake_server import FakeServer

import tronitor

HC_UUID_FILESYSTEM = "31365bce-8da9-4729-8ff3-aaa71d56b712"
HC_UUID_DATABASE = "4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41"
SCRIPT = Path(__file__).resolve().parent.parent / "tronitor.py"


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


def serve_checks(fake_server: FakeServer, checks: list[dict[str, Any]] | None = None) -> None:
    """Answer the Healthchecks list request with checks (default: the two fixture checks)."""
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": hc_fixture_checks() if checks is None else checks})


@pytest.fixture
def hc_provider(fake_server: FakeServer) -> tronitor.HealthchecksProvider:
    """Return a Healthchecks provider that talks to the fake server."""
    return tronitor.HealthchecksProvider(tronitor.Http(), tronitor.HealthchecksConfig(fake_server.url, "hc-test-key"))


@pytest.fixture
def hc_config_file(tmp_path: Path, fake_server: FakeServer) -> Path:
    """Write a config file for a Healthchecks account on the fake server, with locks in tmp_path/locks."""
    path = tmp_path / "tronitor.toml"
    path.write_text(
        f"[general]\nlock_dir = '{tmp_path / 'locks'}'\n\n"
        f"[healthchecks]\nurl = '{fake_server.url}'\napi_key = 'hc-test-key'\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def hc_config_file_with_webhook(hc_config_file: Path, fake_server: FakeServer) -> Path:
    """Extend the Healthchecks config with a [notify] webhook on the fake server (route /hook).

    The [notify] table comes last, so a test can append more keys, such as format = "slack".
    """
    with hc_config_file.open("a", encoding="utf-8") as handle:
        handle.write(f'\n[notify]\nwebhook_url = "{fake_server.url}/hook"\n')
    return hc_config_file


def _ur_monitor(monitor_id: int, name: str, status: str) -> dict[str, Any]:
    """Return one canned UptimeRobot monitor."""
    return {
        "id": monitor_id,
        "friendlyName": name,
        "status": status,
        "url": f"https://{name.lower()}.example.com",
        "type": "HTTP",
        "interval": 300,
        "createDateTime": "2026-01-01T00:00:00Z",
        "tags": [],
        "assignedAlertContacts": [],
    }


def ur_fixture_monitors() -> list[dict[str, Any]]:
    """Return three canned UptimeRobot monitors: up, paused and seems down."""
    return [
        _ur_monitor(1001, "Plex", "UP"),
        _ur_monitor(1002, "Sonarr", "PAUSED"),
        _ur_monitor(1003, "Radarr", "LOOKS_DOWN"),
    ]


def serve_monitors(fake_server: FakeServer, monitors: list[dict[str, Any]] | None = None) -> None:
    """Answer the UptimeRobot list request with monitors (default: the three fixture monitors), on one page."""
    data = ur_fixture_monitors() if monitors is None else monitors
    fake_server.add("GET", "/monitors", 200, {"nextLink": None, "data": data})


@pytest.fixture
def ur_provider(fake_server: FakeServer) -> tronitor.UptimeRobotProvider:
    """Return an UptimeRobot provider that talks to the fake server."""
    return tronitor.UptimeRobotProvider(tronitor.Http(), tronitor.UptimeRobotConfig("ur-test-key", fake_server.url))


@pytest.fixture
def ur_config_file(tmp_path: Path, fake_server: FakeServer) -> Path:
    """Write a config file for an UptimeRobot account on the fake server."""
    path = tmp_path / "tronitor.toml"
    path.write_text(
        f"[general]\nlock_dir = '{tmp_path / 'locks'}'\n\n"
        f'[uptimerobot]\napi_key = "ur-test-key"\nbase_url = "{fake_server.url}"\n',
        encoding="utf-8",
    )
    return path


def run_tronitor(*args: str, env: dict[str, str] | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]:
    """Run tronitor.py with args and return the result with text output.

    The environment holds only PATH and SYSTEMROOT, plus whatever env adds.
    """
    full_env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=full_env,
        input=stdin,
        check=False,
    )


RunCli = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def run_cli(hc_config_file: Path) -> RunCli:
    """Return a function that runs tronitor.py against the Healthchecks config file, with NO_COLOR set."""

    def run(*args: str, stdin: str = "", env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = {"TRONITOR_CONFIG": str(hc_config_file), "NO_COLOR": "1", "NO_PROXY": "127.0.0.1", **(env_extra or {})}
        return run_tronitor(*args, env=env, stdin=stdin)

    return run


@pytest.fixture
def run_cli_ur(ur_config_file: Path) -> RunCli:
    """Return a function that runs tronitor.py against the UptimeRobot config file, with NO_COLOR set."""

    def run(*args: str, stdin: str = "", env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = {"TRONITOR_CONFIG": str(ur_config_file), "NO_COLOR": "1", "NO_PROXY": "127.0.0.1", **(env_extra or {})}
        return run_tronitor(*args, env=env, stdin=stdin)

    return run
