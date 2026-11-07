"""Tests that run tronitor.py as a subprocess."""

import json
from pathlib import Path

from conftest import (
    HC_UUID_DATABASE,
    HC_UUID_FILESYSTEM,
    RunCli,
    bash_fixture,
    hc_fixture_checks,
    run_tronitor,
    serve_checks,
    serve_monitors,
)
from fake_server import FakeServer

import tronitor

run = run_tronitor


def test_version_prints_the_date_and_exits_0() -> None:
    """--version prints the version and exits 0."""
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"tronitor {tronitor.__version__}"


def test_no_arguments_prints_usage_and_exits_2() -> None:
    """No arguments prints the usage to stderr and exits 2."""
    result = run()
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_cli_list_against_fake_server(fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli) -> None:
    """-l prints the header and one row per check."""
    serve_checks(fake_server)
    result = run_cli("-m", "hc", "-l")
    assert result.returncode == 0, result.stderr
    assert "The following Healthchecks monitors were found:" in result.stdout
    assert f"Filesystem Backup  UUID: {HC_UUID_FILESYSTEM}  Status: Up" in result.stdout
    assert f"Database Backup    UUID: {HC_UUID_DATABASE}  Status: Paused" in result.stdout
    assert result.stderr == ""


def test_cli_pause_all_without_tty_needs_no_input(
    fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli, tmp_path: Path
) -> None:
    """Pausing never prompts, so it works from cron with nothing on stdin."""
    serve_checks(fake_server)
    for uuid in (HC_UUID_FILESYSTEM, HC_UUID_DATABASE):
        fake_server.add("POST", f"/api/v3/checks/{uuid}/pause", 200, {"status": "paused"})
    result = run_cli("-m", "healthchecks", "-p", "all")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "locks" / "healthchecks.lock").is_file()
    assert result.stdout.count("... done") == 2


def test_cli_delete_without_yes_refuses_and_exits_2(
    fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli
) -> None:
    """Without a terminal and without --yes, delete refuses and sends no DELETE."""
    serve_checks(fake_server)
    result = run_cli("-m", "hc", "-d", "all")
    assert result.returncode == 2
    assert "tronitor: Refusing to delete without a terminal; pass --yes to confirm." in result.stderr
    assert not [r for r in fake_server.requests if r.method == "DELETE"]


def test_cli_failure_reaches_stderr(fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli) -> None:
    """A failed pause is reported on stderr, so cron sees it even when stdout is thrown away."""
    serve_checks(fake_server)
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_FILESYSTEM}/pause", 500, {"error": "server error"})
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_DATABASE}/pause", 200, {"status": "paused"})
    result = run_cli("-m", "hc", "-p", "all")
    assert result.returncode == 3
    failed = f"tronitor: Pausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... failed: HTTP 500: server error"
    assert failed in result.stderr
    assert "failed" not in result.stdout
    assert f"Pausing Database Backup (UUID {HC_UUID_DATABASE})... done" in result.stdout


def test_cli_find_f_without_tty_behaves_like_n(fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli) -> None:
    """-f without a terminal lists the paused checks and does not prompt or unpause."""
    serve_checks(fake_server)
    result = run_cli("-m", "hc", "-f", stdin="y\n")
    assert result.returncode == 0, result.stderr
    assert "The following Healthchecks monitors are paused:" in result.stdout
    assert "Database Backup" in result.stdout
    assert "Filesystem Backup" not in result.stdout
    assert "Unpause them?" not in result.stdout
    assert not [r for r in fake_server.requests if r.method == "POST"]


def test_cli_help_mentions_providers_and_all() -> None:
    """--help explains the provider names and "all" and points at the docs."""
    result = run("--help")
    assert result.returncode == 0
    assert "healthchecks (hc)" in result.stdout
    assert "uptimerobot (ur)" in result.stdout
    assert '"all"' in result.stdout
    assert result.stdout.rstrip().endswith(
        "Documentation: https://github.com/tronyx/tronitor/blob/master/docs/usage.md"
    )


def test_cli_colour_is_off_when_piped(fake_server: FakeServer, hc_config_file: Path) -> None:
    """Piped output has no colour codes even without NO_COLOR."""
    serve_checks(fake_server)
    result = run("-m", "hc", "-l", env={"TRONITOR_CONFIG": str(hc_config_file), "NO_PROXY": "127.0.0.1"})
    assert result.returncode == 0, result.stderr
    assert "Status: Paused" in result.stdout
    assert "\x1b[" not in result.stdout


def test_cli_env_only_no_config_file(fake_server: FakeServer, tmp_path: Path) -> None:
    """With the URL, key and lock directory in the environment, no config file is needed."""
    serve_checks(fake_server)
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_DATABASE}/pause", 200, {"status": "paused"})
    env = {
        "TRONITOR_HEALTHCHECKS_URL": fake_server.url,
        "TRONITOR_HEALTHCHECKS_API_KEY": "hc-test-key",
        "TRONITOR_LOCK_DIR": str(tmp_path / "env-locks"),
        "HOME": str(tmp_path),
        "APPDATA": str(tmp_path),
        "NO_COLOR": "1",
        "NO_PROXY": "127.0.0.1",
    }
    result = run("-m", "hc", "-p", "Database Backup", env=env)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "env-locks" / f"{HC_UUID_DATABASE}.lock").is_file()
    assert fake_server.requests[0].headers["X-Api-Key"] == "hc-test-key"


def test_cli_secret_never_printed_with_verbose(fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli) -> None:
    """--verbose logs the requests but never the API key, even when a request fails."""
    serve_checks(fake_server)
    fake_server.add("GET", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 401, {"error": "The API key is invalid."})
    listed = run_cli("-m", "hc", "-l", "--verbose")
    failed = run_cli("-m", "hc", "-i", "Filesystem Backup", "--verbose")
    assert listed.returncode == 0
    assert failed.returncode == 1
    assert "GET " in listed.stderr
    for result in (listed, failed):
        assert "hc-test-key" not in result.stdout + result.stderr


def test_cli_json_with_a_non_latin_name_does_not_crash(fake_server: FakeServer, run_cli: RunCli) -> None:
    """A name outside the console's code page is printed as UTF-8 rather than crashing."""
    checks = hc_fixture_checks()
    checks[0]["name"] = "Sauvegarde 日本"
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": checks})
    result = run_cli("-m", "hc", "-l", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["name"] == "Sauvegarde 日本"


def test_cli_missing_provider_is_a_usage_error() -> None:
    """An action without -m is rejected with exit 2, with a message that names the providers."""
    result = run("-l")
    assert result.returncode == 2
    assert result.stderr == "tronitor: choose a provider with -m: healthchecks (hc) or uptimerobot (ur)\n"


def test_cli_migrate(tmp_path: Path) -> None:
    """--migrate, without -m, writes tronitor.toml next to the Bash script and exits 0."""
    webhook = "https://discord.com/api/webhooks/1/secret-token"
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key", webhookUrl=webhook)
    result = run("--migrate", str(script))
    assert result.returncode == 0, result.stderr
    out = tmp_path / "tronitor.toml"
    assert f"Wrote {out}" in result.stdout
    assert "hc-secret-key" not in result.stdout + result.stderr
    assert "secret-token" not in result.stdout + result.stderr
    config = tronitor.load_config(out, {}, [])
    assert config.healthchecks == tronitor.HealthchecksConfig("https://healthchecks.io", "hc-secret-key")
    assert config.notify.webhook_url == webhook


def test_cli_two_actions_are_a_usage_error() -> None:
    """Two actions at once are rejected with exit 2."""
    result = run("-m", "hc", "-l", "-f")
    assert result.returncode == 2
    assert "not allowed with" in result.stderr


def test_cli_ur_list(fake_server: FakeServer, ur_config_file: Path, run_cli_ur: RunCli) -> None:
    """-m ur -l prints one row per UptimeRobot monitor."""
    serve_monitors(fake_server)
    result = run_cli_ur("-m", "ur", "-l")
    assert result.returncode == 0, result.stderr
    assert "The following UptimeRobot monitors were found:" in result.stdout
    assert "Plex    ID: 1001  Status: Up" in result.stdout
    assert "Sonarr  ID: 1002  Status: Paused" in result.stdout
    assert "Radarr  ID: 1003  Status: Seems down" in result.stdout
    assert "ur-test-key" not in result.stdout + result.stderr


def test_cli_unpause_all_resumes_and_removes_the_locks(
    fake_server: FakeServer, hc_config_file: Path, run_cli: RunCli, tmp_path: Path
) -> None:
    """-u all resumes the paused check, removes healthchecks.lock and each check's lock, and exits 0."""
    serve_checks(fake_server)
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_DATABASE}/resume", 200, {"status": "new"})
    locks = tmp_path / "locks"
    locks.mkdir()
    names = ["healthchecks.lock", f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock", "other.lock"]
    for name in names:
        (locks / name).touch()
    result = run_cli("-m", "hc", "-u", "all")
    assert result.returncode == 0, result.stderr
    assert "Filesystem Backup is already running" in result.stdout
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in result.stdout
    assert [r.path for r in fake_server.requests if r.method == "POST"] == [f"/api/v3/checks/{HC_UUID_DATABASE}/resume"]
    assert [p.name for p in locks.iterdir()] == ["other.lock"]
    assert result.stderr == ""
