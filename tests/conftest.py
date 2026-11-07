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
COVERAGERC = SCRIPT.parent / ".coveragerc"


def measuring_coverage() -> bool:
    """Return True when coverage runs the test process, which marks it with COVERAGE_RUN.

    Then the tests that run the script as a separate program measure that program too, so the lines
    that only they reach count. Coverage writes one data file per process (parallel = True in
    .coveragerc), and "coverage combine" merges them.
    """
    return os.environ.get("COVERAGE_RUN") == "true"


def subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the environment for a subprocess: PATH and SYSTEMROOT, the coverage settings when measuring, and extra."""
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    if measuring_coverage():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
        if "COVERAGE_FILE" in os.environ:
            env["COVERAGE_FILE"] = os.environ["COVERAGE_FILE"]
    env.update(extra or {})
    return env


def script_command(*args: str) -> list[str]:
    """Return the command that runs tronitor.py with args, through coverage when the test process is measured."""
    if measuring_coverage():
        return [sys.executable, "-m", "coverage", "run", f"--rcfile={COVERAGERC}", str(SCRIPT), *args]
    return [sys.executable, str(SCRIPT), *args]


def coverage_startup_code() -> list[str]:
    """Return the statements a "python -c" subprocess runs first to measure itself, or none when not measuring."""
    if measuring_coverage():
        return ["import coverage", "coverage.process_startup()"]
    return []


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


BASH_HEADER = """\
#!/usr/bin/env bash
# shellcheck disable=SC2102 # usage() heredoc contains literal "[OPTION]" display text, not a glob
#
# Script to utilize the UptimeRobot, StatusCake, and HealthChecks.io APIs to
# retrieve information on and work with checks you've created.
# Tronyx
set -eo pipefail
IFS=$'\\n\\t'

# Edit these with your corresponding information to finish setting up the script
# or just run it and it will prompt you for it.
# If your provider is StatusCake, specify your username.
scUsername=''
# If your provider is Upptime, specify the following.
repoOwner=''
gitHubUsername=''
upptimeRepo='upptime'
# Specify API key(s).
urApiKey=''
scApiKey=''
hcApiKey=''
ghToken=''
# Specify the domain to use for Healthchecks as they allow you to self-host the
# application. If you're self-hosting it, replace the default domain with the
# domain you're hosting it on.
healthchecksDomain='healthchecks.io'
# Specify the Discord/Slack webhook URL to send notifications to.
webhookUrl=''
# Set notifyAll to true for notification to apply for all running state as well.
notifyAll='false'
# Set JQ to false to disable its use for displaying output. This works better
# for using the script with cronjobs, etc.
jq='true'

# Declare some variables.
# Temp dir and filenames.
# Make sure you set this to something your user has write access to.
tempDir="$HOME/tronitor/"
apiTestFullFile="${tempDir}api_test_full.txt"
badMonitorsFile="${tempDir}bad_monitors.txt"
"""
"""The first 40 lines of the last tronitor.sh, the Bash script that tronitor.py replaced, with its shipped values."""


def bash_fixture(tmp_path: Path, **values: str) -> Path:
    """Write tmp_path/tronitor.sh: the Bash script's header with values in place of the shipped ones; return its path.

    Each name must be a setting of the header, such as hcApiKey or tempDir. Its line becomes name='value', in the
    place where the real script has it: tempDir stays below the "# Declare some variables" line.
    """
    lines = BASH_HEADER.splitlines()
    for name, value in values.items():
        index = next(i for i, line in enumerate(lines) if line.startswith(f"{name}="))
        lines[index] = f"{name}='{value}'"
    path = tmp_path / "tronitor.sh"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_tronitor(*args: str, env: dict[str, str] | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]:
    """Run tronitor.py with args and return the result with text output.

    The environment holds only PATH and SYSTEMROOT, plus whatever env adds (see subprocess_env).
    """
    return subprocess.run(
        script_command(*args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=subprocess_env(env),
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
