"""Unit tests for the tronitor module."""

import http.client
import io
import json
import os
import re
import socket
import stat
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import (
    HC_UUID_DATABASE,
    HC_UUID_FILESYSTEM,
    bash_fixture,
    hc_fixture_checks,
    serve_checks,
    serve_monitors,
    ur_fixture_monitors,
)
from fake_server import FakeServer

import tronitor

ROOT = Path(__file__).resolve().parent.parent


def test_exit_codes_are_the_documented_ones() -> None:
    """The exit codes match the documented values."""
    assert (tronitor.EXIT_OK, tronitor.EXIT_ERROR, tronitor.EXIT_USAGE, tronitor.EXIT_PARTIAL) == (0, 1, 2, 3)


def test_version_is_a_date() -> None:
    """The version is a YYYY-MM-DD date."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", tronitor.__version__)


def write_toml(tmp_path: Path, text: str) -> Path:
    """Write text to a TOML file in tmp_path and return its path."""
    path = tmp_path / "tronitor.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_full_config_file_is_read(tmp_path: Path) -> None:
    """Every table and key in a full config file is read."""
    path = write_toml(
        tmp_path,
        '[general]\nlock_dir = "/var/lock"\n'
        '[healthchecks]\nurl = "https://hc.example.com"\napi_key = "hc-key"\n'
        '[uptimerobot]\napi_key = "ur-key"\nbase_url = "http://localhost:8080/"\n'
        '[notify]\nwebhook_url = "https://hooks.example.com/x"\nformat = "slack"\nnotify_all = true\n',
    )
    cfg = tronitor.load_config(path, {}, [])
    assert cfg.lock_dir == Path("/var/lock")
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://hc.example.com", "hc-key")
    assert cfg.uptimerobot == tronitor.UptimeRobotConfig("ur-key", "http://localhost:8080")
    assert cfg.notify == tronitor.NotifyConfig("https://hooks.example.com/x", "slack", True)


def test_missing_file_and_empty_env_gives_no_providers(tmp_path: Path) -> None:
    """With no file and no environment there are no providers and the default lock dir."""
    cfg = tronitor.load_config(None, {}, [tmp_path / "none.toml"])
    assert cfg.healthchecks is None and cfg.uptimerobot is None and cfg.lock_dir == tronitor.default_lock_dir()


def test_env_overrides_file_and_fills_in_a_missing_file(tmp_path: Path) -> None:
    """Environment variables win over the file and work without a file."""
    path = write_toml(tmp_path, '[healthchecks]\napi_key = "file-key"\n')
    cfg = tronitor.load_config(path, {"TRONITOR_HEALTHCHECKS_API_KEY": "env-key"}, [])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://healthchecks.io", "env-key")
    env = {
        "TRONITOR_HEALTHCHECKS_URL": "https://hc.example.com/",
        "TRONITOR_HEALTHCHECKS_API_KEY": "k1",
        "TRONITOR_UPTIMEROBOT_API_KEY": "k2",
        "TRONITOR_WEBHOOK_URL": "https://hooks.example.com/y",
    }
    cfg = tronitor.load_config(None, env, [tmp_path / "none.toml"])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://hc.example.com", "k1")
    assert cfg.uptimerobot == tronitor.UptimeRobotConfig("k2")
    assert cfg.notify.webhook_url == "https://hooks.example.com/y"


def test_tronitor_config_env_names_the_file(tmp_path: Path) -> None:
    """TRONITOR_CONFIG selects the file, and a missing one is an error."""
    path = write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\n')
    cfg = tronitor.load_config(None, {"TRONITOR_CONFIG": str(path)}, [])
    assert cfg.uptimerobot is not None
    with pytest.raises(tronitor.ConfigError, match="does not exist"):
        tronitor.load_config(None, {"TRONITOR_CONFIG": str(tmp_path / "no.toml")}, [])


def test_explicit_path_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    """An explicit config path that is missing is an error."""
    with pytest.raises(tronitor.ConfigError, match="does not exist"):
        tronitor.load_config(tmp_path / "missing.toml", {}, [])


def test_first_existing_search_path_is_used(tmp_path: Path) -> None:
    """The first search path that exists is read."""
    path = write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\n')
    cfg = tronitor.load_config(None, {}, [tmp_path / "none.toml", path])
    assert cfg.uptimerobot is not None


def test_unknown_key_names_the_key_and_suggests_the_right_one(tmp_path: Path) -> None:
    """An unknown key is named, with a suggestion when one is close."""
    path = write_toml(tmp_path, '[healthchecks]\napikey = "x"\n')
    with pytest.raises(
        tronitor.ConfigError, match=r"unknown key 'healthchecks.apikey' \(did you mean 'api_key'\?\)"
    ) as e:
        tronitor.load_config(path, {}, [])
    assert str(e.value).startswith(f"{path}: ")


def test_unknown_key_without_a_close_match(tmp_path: Path) -> None:
    """An unknown key with no close match has no suggestion."""
    path = write_toml(tmp_path, '[notify]\nzzzzzz = "x"\n')
    with pytest.raises(tronitor.ConfigError, match=r"unknown key 'notify.zzzzzz'$"):
        tronitor.load_config(path, {}, [])


def test_unknown_table_is_an_error(tmp_path: Path) -> None:
    """An unknown table is named, with a suggestion."""
    path = write_toml(tmp_path, '[helthchecks]\napi_key = "x"\n')
    with pytest.raises(tronitor.ConfigError, match=r"unknown table 'helthchecks' \(did you mean 'healthchecks'\?\)"):
        tronitor.load_config(path, {}, [])


def test_wrong_type_is_an_error(tmp_path: Path) -> None:
    """A value of the wrong type is an error that names the key."""
    path = write_toml(tmp_path, '[notify]\nnotify_all = "yes"\n')
    with pytest.raises(tronitor.ConfigError, match=r"notify.notify_all must be true or false"):
        tronitor.load_config(path, {}, [])
    path = write_toml(tmp_path, "[healthchecks]\napi_key = 5\n")
    with pytest.raises(tronitor.ConfigError, match=r"healthchecks.api_key must be a string"):
        tronitor.load_config(path, {}, [])


def test_bad_notify_format_is_an_error(tmp_path: Path) -> None:
    """Only discord and slack are valid formats."""
    path = write_toml(tmp_path, '[notify]\nformat = "teams"\n')
    with pytest.raises(tronitor.ConfigError, match=r'notify.format must be "discord" or "slack"'):
        tronitor.load_config(path, {}, [])


def test_url_without_scheme_is_an_error(tmp_path: Path) -> None:
    """URLs need an http or https scheme, from the file or the environment."""
    path = write_toml(tmp_path, '[healthchecks]\nurl = "hc.example.com"\napi_key = "k"\n')
    with pytest.raises(tronitor.ConfigError, match=r"healthchecks.url must start with http:// or https://"):
        tronitor.load_config(path, {}, [])
    with pytest.raises(tronitor.ConfigError, match=r"^TRONITOR_HEALTHCHECKS_URL: must start with http:// or https://"):
        tronitor.load_config(None, {"TRONITOR_HEALTHCHECKS_URL": "hc.example.com"}, [])


def test_invalid_toml_is_a_config_error(tmp_path: Path) -> None:
    """A TOML syntax error becomes a ConfigError that names the file."""
    path = write_toml(tmp_path, "[healthchecks\n")
    with pytest.raises(tronitor.ConfigError) as e:
        tronitor.load_config(path, {}, [])
    assert str(e.value).startswith(f"{path}: ")


def test_secrets_are_not_in_error_messages(tmp_path: Path) -> None:
    """An error about a key never contains its value."""
    path = write_toml(tmp_path, '[notify]\nformat = "supersecret"\n')
    with pytest.raises(tronitor.ConfigError) as e:
        tronitor.load_config(path, {}, [])
    assert "supersecret" not in str(e.value)


def test_values_are_stripped_and_url_loses_its_trailing_slash(tmp_path: Path) -> None:
    """Strings are stripped and the Healthchecks URL loses trailing slashes."""
    path = write_toml(tmp_path, '[healthchecks]\nurl = " https://hc.example.com/ "\napi_key = " abc "\n')
    cfg = tronitor.load_config(path, {}, [])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://hc.example.com", "abc")


def test_blank_api_key_means_no_provider(tmp_path: Path) -> None:
    """An api_key that is blank after stripping disables the provider."""
    path = write_toml(tmp_path, '[healthchecks]\napi_key = "  "\n[uptimerobot]\napi_key = ""\n')
    cfg = tronitor.load_config(path, {}, [])
    assert cfg.healthchecks is None and cfg.uptimerobot is None


def test_lock_dir_from_env_and_file(tmp_path: Path) -> None:
    """TRONITOR_LOCK_DIR wins over the file, and the value is a Path."""
    path = write_toml(tmp_path, '[general]\nlock_dir = "/from/file"\n')
    assert tronitor.load_config(path, {}, []).lock_dir == Path("/from/file")
    cfg = tronitor.load_config(path, {"TRONITOR_LOCK_DIR": "/from/env"}, [])
    assert cfg.lock_dir == Path("/from/env")


def test_search_paths_on_posix_and_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The search paths differ by platform."""
    script, home = Path("/opt/tronitor/tronitor.py"), Path("/home/u")
    monkeypatch.setattr(sys, "platform", "linux")
    assert tronitor.config_search_paths(script, home, {"APPDATA": "/x"}) == [
        script.parent / "tronitor.toml",
        home / ".config" / "tronitor" / "tronitor.toml",
    ]
    monkeypatch.setattr(sys, "platform", "win32")
    appdata = Path("/x") / "tronitor" / "tronitor.toml"
    assert tronitor.config_search_paths(script, home, {"APPDATA": "/x"})[1] == appdata
    assert tronitor.config_search_paths(script, home, {})[1] == home / ".config" / "tronitor" / "tronitor.toml"


def test_default_lock_dir_is_tmp_on_posix_and_temp_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default lock directory is /tmp on POSIX and TEMP on Windows."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert tronitor.default_lock_dir() == Path("/tmp")  # nosec B108
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("TEMP", "/win/temp")
    assert tronitor.default_lock_dir() == Path("/win/temp")
    monkeypatch.delenv("TEMP")
    assert tronitor.default_lock_dir() == Path(tempfile.gettempdir())


def test_example_config_loads() -> None:
    """The example config loads and equals the defaults except for the empty keys."""
    cfg = tronitor.load_config(ROOT / "tronitor.example.toml", {}, [])
    assert cfg.healthchecks is None and cfg.uptimerobot is None and cfg.notify == tronitor.NotifyConfig()
    assert cfg.lock_dir == tronitor.default_lock_dir()


def test_unknown_top_level_key_points_at_its_table(tmp_path: Path) -> None:
    """A key outside any table gets a hint naming the table that has it."""
    path = write_toml(tmp_path, 'lock_dir = "/x"\n')
    with pytest.raises(tronitor.ConfigError, match=r"unknown key 'lock_dir' \(did you mean 'general.lock_dir'\?\)"):
        tronitor.load_config(path, {}, [])


def test_empty_env_variable_means_unset(tmp_path: Path) -> None:
    """A set but empty variable does not override the file or raise."""
    path = write_toml(tmp_path, '[healthchecks]\nurl = "https://hc.example.com"\napi_key = "file-key"\n')
    env = {"TRONITOR_HEALTHCHECKS_API_KEY": "", "TRONITOR_HEALTHCHECKS_URL": "", "TRONITOR_CONFIG": ""}
    cfg = tronitor.load_config(None, env, [path])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://hc.example.com", "file-key")


def test_table_name_with_a_plain_value_is_an_error(tmp_path: Path) -> None:
    """A known table name given a plain value is reported as needing a table."""
    path = write_toml(tmp_path, 'healthchecks = "x"\n')
    with pytest.raises(tronitor.ConfigError, match="healthchecks must be a table"):
        tronitor.load_config(path, {}, [])


def test_blank_url_uses_the_default(tmp_path: Path) -> None:
    """A blank Healthchecks url falls back to the default."""
    path = write_toml(tmp_path, '[healthchecks]\nurl = ""\napi_key = "k"\n')
    cfg = tronitor.load_config(path, {}, [])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://healthchecks.io", "k")


def test_env_url_override_wins_even_when_the_file_url_is_bad(tmp_path: Path) -> None:
    """Only the winning URL is validated."""
    path = write_toml(tmp_path, '[healthchecks]\nurl = "bad"\napi_key = "k"\n')
    cfg = tronitor.load_config(path, {"TRONITOR_HEALTHCHECKS_URL": "https://ok.example.com"}, [])
    assert cfg.healthchecks == tronitor.HealthchecksConfig("https://ok.example.com", "k")


def test_webhook_url_needs_a_scheme(tmp_path: Path) -> None:
    """A non-empty webhook URL needs an http or https scheme."""
    path = write_toml(tmp_path, '[notify]\nwebhook_url = "hooks.example.com"\n')
    with pytest.raises(tronitor.ConfigError, match=r"notify.webhook_url must start with http:// or https://"):
        tronitor.load_config(path, {}, [])


def test_wrong_typed_lock_dir_and_bad_base_url_are_errors(tmp_path: Path) -> None:
    """A non-string general.lock_dir and a base_url without a scheme are errors."""
    path = write_toml(tmp_path, "[general]\nlock_dir = 5\n")
    with pytest.raises(tronitor.ConfigError, match=r"general.lock_dir must be a string"):
        tronitor.load_config(path, {}, [])
    path = write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\nbase_url = "localhost:8080"\n')
    with pytest.raises(tronitor.ConfigError, match=r"uptimerobot.base_url must start with http:// or https://"):
        tronitor.load_config(path, {}, [])


def test_empty_appdata_falls_back_to_dot_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty APPDATA is ignored on Windows."""
    monkeypatch.setattr(sys, "platform", "win32")
    home = Path("/home/u")
    paths = tronitor.config_search_paths(Path("/opt/t.py"), home, {"APPDATA": ""})
    assert paths[1] == home / ".config" / "tronitor" / "tronitor.toml"


def fake_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Make home the folder that "~" stands for, on POSIX and on Windows."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def test_lock_dir_expands_the_home_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lock_dir that starts with ~, from the file or the environment, is in the home folder."""
    fake_home(monkeypatch, tmp_path)
    path = write_toml(tmp_path, '[general]\nlock_dir = "~/tronitor"\n')
    assert tronitor.load_config(path, {}, []).lock_dir == tmp_path / "tronitor"
    cfg = tronitor.load_config(path, {"TRONITOR_LOCK_DIR": "~/env-locks"}, [])
    assert cfg.lock_dir == tmp_path / "env-locks"


def test_relative_lock_dir_is_an_error(tmp_path: Path) -> None:
    """A relative lock_dir would depend on cron's working folder, so it is refused."""
    path = write_toml(tmp_path, '[general]\nlock_dir = "tronitor/locks"\n')
    with pytest.raises(tronitor.ConfigError, match=r"general.lock_dir must be an absolute path$") as e:
        tronitor.load_config(path, {}, [])
    assert str(e.value).startswith(f"{path}: ")
    with pytest.raises(tronitor.ConfigError, match=r"^TRONITOR_LOCK_DIR: must be an absolute path$"):
        tronitor.load_config(None, {"TRONITOR_LOCK_DIR": "locks"}, [])


def test_config_path_expands_the_home_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TRONITOR_CONFIG and --config may start with ~."""
    fake_home(monkeypatch, tmp_path)
    write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\n')
    assert tronitor.load_config(None, {"TRONITOR_CONFIG": "~/tronitor.toml"}, []).uptimerobot is not None
    assert tronitor.load_config(Path("~/tronitor.toml"), {}, []).uptimerobot is not None


@pytest.mark.parametrize(
    "url",
    ["https://hooks.example.com/api/webhooks/1/SECRET TOKEN", "https://hooks.example.com/SECRET\x7fTOKEN"],
    ids=["space", "control character"],
)
def test_url_with_a_space_or_control_character_is_an_error(tmp_path: Path, url: str) -> None:
    """An address with a space or a control character inside is refused, and the message does not show it."""
    path = write_toml(tmp_path, f"[notify]\nwebhook_url = {json.dumps(url)}\n")
    with pytest.raises(tronitor.ConfigError, match=r"notify.webhook_url contains a space or a control character$") as e:
        tronitor.load_config(path, {}, [])
    assert "SECRET" not in str(e.value)
    with pytest.raises(tronitor.ConfigError, match=r"^TRONITOR_WEBHOOK_URL: contains a space") as e:
        tronitor.load_config(None, {"TRONITOR_WEBHOOK_URL": url}, [])
    assert "SECRET" not in str(e.value)


def test_http_get_json(fake_server: FakeServer) -> None:
    """A GET returns the status and decoded JSON, and sends the key and Accept headers."""
    fake_server.add("GET", "/ping", 200, {"ok": True})
    r = tronitor.Http().request("GET", fake_server.url + "/ping", headers={"X-Api-Key": "k"})
    assert r.status == 200 and r.json == {"ok": True}
    assert fake_server.requests[0].headers["X-Api-Key"] == "k"
    assert fake_server.requests[0].headers["Accept"] == "application/json"
    assert fake_server.requests[0].headers["User-Agent"] == f"tronitor/{tronitor.__version__}"


def test_http_posts_json_body_and_content_type(fake_server: FakeServer) -> None:
    """An empty dict is still sent as a JSON body with a Content-Type header."""
    fake_server.add("POST", "/p", 200, {})
    tronitor.Http().request("POST", fake_server.url + "/p", json_body={})
    seen = fake_server.requests[0]
    assert seen.body == {}
    assert seen.headers["Content-Type"] == "application/json"


def test_http_empty_2xx_body_is_none(fake_server: FakeServer) -> None:
    """A success with no body gives json=None."""
    fake_server.add("POST", "/e", 200)
    r = tronitor.Http().request("POST", fake_server.url + "/e")
    assert r.status == 200 and r.json is None


def test_http_error_status_raises_with_message_field(fake_server: FakeServer) -> None:
    """An error status raises ProviderError carrying the message field."""
    fake_server.add("GET", "/x", 401, {"code": "000-005", "message": "The API key is missing, invalid or expired."})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert e.value.status == 401 and "invalid or expired" in str(e.value)


def test_http_error_with_message_list_joins_it(fake_server: FakeServer) -> None:
    """A message that is a list is joined with semicolons."""
    fake_server.add("GET", "/x", 400, {"message": ["a", "b"]})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert str(e.value) == "HTTP 400: a; b"


def test_http_error_falls_back_to_error_then_detail(fake_server: FakeServer) -> None:
    """The error field, then the detail field, supply the message when message is absent."""
    fake_server.add("GET", "/a", 400, {"error": "bad one"})
    fake_server.add("GET", "/b", 400, {"detail": "bad two"})
    http = tronitor.Http()
    with pytest.raises(tronitor.ProviderError, match="HTTP 400: bad one"):
        http.request("GET", fake_server.url + "/a")
    with pytest.raises(tronitor.ProviderError, match="HTTP 400: bad two"):
        http.request("GET", fake_server.url + "/b")


def test_http_html_error_page_is_reported_not_raised_raw(fake_server: FakeServer) -> None:
    """A non-JSON error body is reported as collapsed text."""
    fake_server.add("GET", "/x", 502, "<html>Bad Gateway</html>")
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert str(e.value) == "HTTP 502: <html>Bad Gateway</html>"
    assert e.value.status == 502


def test_http_allowed_status_is_returned(fake_server: FakeServer) -> None:
    """A status listed in allow_statuses is returned, not raised."""
    fake_server.add("POST", "/x", 409, {"message": "already"})
    r = tronitor.Http().request("POST", fake_server.url + "/x", allow_statuses={409})
    assert r == tronitor.HttpResponse(409, {"message": "already"})


def test_http_unreachable_host_is_a_provider_error() -> None:
    """A refused connection raises ProviderError with no status."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http(timeout=5).request("GET", f"http://127.0.0.1:{port}/")
    assert e.value.status is None and "cannot reach" in str(e.value)


def test_http_verbose_logs_method_and_url_only(fake_server: FakeServer) -> None:
    """Verbose logging shows the method and URL, never headers or bodies."""
    fake_server.add("POST", "/ping", 200, {"ok": True})
    lines: list[str] = []
    tronitor.Http(verbose=True, log=lines.append).request(
        "POST", fake_server.url + "/ping", headers={"X-Api-Key": "secret-key"}, json_body={"token": "secret-body"}
    )
    assert lines == [f"POST {fake_server.url}/ping"]


def test_http_is_silent_unless_verbose(fake_server: FakeServer) -> None:
    """Without verbose, nothing is logged."""
    fake_server.add("GET", "/ping", 200, {})
    lines: list[str] = []
    tronitor.Http(log=lines.append).request("GET", fake_server.url + "/ping")
    assert lines == []


def test_http_non_json_success_is_an_error(fake_server: FakeServer) -> None:
    """A success whose body is not JSON raises ProviderError."""
    fake_server.add("GET", "/x", 200, "<html>")
    with pytest.raises(tronitor.ProviderError, match="response is not JSON") as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert e.value.status == 200


def test_http_error_body_read_failure_is_a_provider_error(fake_server: FakeServer) -> None:
    """An error response whose body is cut short raises ProviderError, not a raw exception.

    The route declares Content-Length 100 but sends a short body and the server closes the connection,
    so reading the body raises http.client.IncompleteRead.
    """
    fake_server.add("GET", "/x", 500, {"message": "short"}, headers={"Content-Length": "100"})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert e.value.status == 500 and "could not read the response body" in str(e.value)


def test_http_truncated_success_body_is_a_provider_error(fake_server: FakeServer) -> None:
    """A success response cut short raises ProviderError."""
    fake_server.add("GET", "/x", 200, {"ok": True}, headers={"Content-Length": "100"})
    with pytest.raises(tronitor.ProviderError, match="cannot reach"):
        tronitor.Http().request("GET", fake_server.url + "/x")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("file:///etc/passwd", "unsupported URL"),
        ("ftp://user:secret@x/SECRET", "unsupported URL: x"),
        ("not a url", "unsupported URL"),
        ("http://[::1", "unsupported URL"),
    ],
)
def test_http_rejects_non_http_urls(url: str, message: str) -> None:
    """A URL that is not http or https raises ProviderError before any request is made.

    The message names only the host, without a user name or password, or nothing when there is no host.
    """
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", url)
    assert str(e.value) == message
    assert e.value.status is None


def test_http_invalid_url_with_a_label_is_not_echoed(fake_server: FakeServer) -> None:
    """A URL that http.client refuses, such as one with a raw newline, is reported by its label only."""
    url = fake_server.url + "/api/webhooks/1/SECRET\nTOKEN"
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("POST", url, json_body={}, log_label="webhook")
    assert str(e.value) == "unsupported URL for webhook"
    assert fake_server.requests == []


def test_http_invalid_url_without_a_label_names_only_the_host(fake_server: FakeServer) -> None:
    """Without a label, the message names the host and port, not the path."""
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/a b/SECRET")
    assert str(e.value) == f"unsupported URL: {fake_server.url.removeprefix('http://')}"


def test_http_host_leaves_out_user_info() -> None:
    """The host in a message never includes a user name or password from the URL."""
    req = urllib.request.Request("http://user:secret@example.com:8080/x")
    assert tronitor.Http._host(req) == "example.com:8080"


@pytest.mark.parametrize(("method", "status"), [("GET", 301), ("POST", 302)])
def test_http_does_not_follow_redirects(fake_server: FakeServer, method: str, status: int) -> None:
    """A redirect is an error, so the headers never go to another address and a POST never becomes a GET."""
    fake_server.add(method, "/old", status, headers={"Location": fake_server.url + "/new"})
    fake_server.add("GET", "/new", 200, {})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request(method, fake_server.url + "/old", headers={"X-Api-Key": "k"})
    assert e.value.status == status and str(e.value).startswith(f"HTTP {status}: ")
    assert [r.path for r in fake_server.requests] == ["/old"]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [({"Retry-After": "2"}, 2), ({}, 60), ({"Retry-After": "300"}, 60), ({"Retry-After": "0"}, 1)],
    ids=["as asked", "missing", "capped at 60", "at least 1"],
)
def test_http_retries_once_after_a_429(fake_server: FakeServer, headers: dict[str, str], expected: int) -> None:
    """With retry_on_429, a 429 waits for Retry-After (1 to 60 seconds, 60 by default) and sends the request again."""
    fake_server.add("POST", "/x", 429, {"message": "slow down"}, headers=headers, once=True)
    fake_server.add("POST", "/x", 200, {"ok": True})
    sleeps: list[float] = []
    r = tronitor.Http(sleep=sleeps.append).request("POST", fake_server.url + "/x", json_body={}, retry_on_429=True)
    assert r == tronitor.HttpResponse(200, {"ok": True})
    assert sleeps == [expected]
    assert [req.body for req in fake_server.requests_for("POST", "/x")] == [{}, {}]


def test_http_retry_after_that_is_not_a_number_waits_60(fake_server: FakeServer) -> None:
    """A Retry-After that is not a whole number of seconds, such as a date, gives the 60-second default."""
    fake_server.add("GET", "/x", 429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, once=True)
    fake_server.add("GET", "/x", 200, {})
    sleeps: list[float] = []
    tronitor.Http(sleep=sleeps.append).request("GET", fake_server.url + "/x", retry_on_429=True)
    assert sleeps == [60]


def test_http_second_429_is_an_error(fake_server: FakeServer) -> None:
    """A second 429 for the same request raises the usual ProviderError, after one wait."""
    fake_server.add("GET", "/x", 429, {"message": "slow down"}, headers={"Retry-After": "1"})
    sleeps: list[float] = []
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http(sleep=sleeps.append).request("GET", fake_server.url + "/x", retry_on_429=True)
    assert e.value.status == 429 and str(e.value) == "HTTP 429: slow down"
    assert sleeps == [1]
    assert len(fake_server.requests) == 2


def test_http_does_not_retry_a_429_by_default(fake_server: FakeServer) -> None:
    """Without retry_on_429, a 429 is an error at once."""
    fake_server.add("GET", "/x", 429, {"message": "slow down"}, headers={"Retry-After": "1"}, once=True)
    fake_server.add("GET", "/x", 200, {})
    sleeps: list[float] = []
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http(sleep=sleeps.append).request("GET", fake_server.url + "/x")
    assert e.value.status == 429
    assert sleeps == [] and len(fake_server.requests) == 1


def test_http_verbose_logs_the_wait(fake_server: FakeServer) -> None:
    """With verbose, the wait is logged by the label, or by the host when there is none, and each request too."""
    fake_server.add("GET", "/x", 429, headers={"Retry-After": "3"}, once=True)
    fake_server.add("GET", "/x", 200, {})
    lines: list[str] = []
    http = tronitor.Http(verbose=True, log=lines.append, sleep=lambda seconds: None)
    http.request("GET", fake_server.url + "/x", retry_on_429=True)
    host = fake_server.url.removeprefix("http://")
    assert lines == [f"GET {fake_server.url}/x", f"waiting 3 s for the {host} rate limit", f"GET {fake_server.url}/x"]
    fake_server.add("POST", "/hook", 429, headers={"Retry-After": "3"}, once=True)
    fake_server.add("POST", "/hook", 204)
    lines.clear()
    http.request("POST", fake_server.url + "/hook", json_body={}, log_label="webhook", retry_on_429=True)
    assert lines == ["POST webhook", "waiting 3 s for the webhook rate limit", "POST webhook"]


def test_http_verbose_uses_the_label_and_strips_the_query(fake_server: FakeServer) -> None:
    """The verbose line shows the label when given, else the URL without its query."""
    fake_server.add("POST", "/hook/secret-token", 204)
    fake_server.add("GET", "/list", 200, {})
    lines: list[str] = []
    http = tronitor.Http(verbose=True, log=lines.append)
    http.request("POST", fake_server.url + "/hook/secret-token", json_body={}, log_label="webhook")
    http.request("GET", fake_server.url + "/list?api_key=secret")
    assert lines == ["POST webhook", f"GET {fake_server.url}/list"]


def test_http_allowed_2xx_non_json_body_returns_none(fake_server: FakeServer) -> None:
    """A listed status never raises for a non-JSON body."""
    fake_server.add("POST", "/hook", 200, "ok")
    response = tronitor.Http().request("POST", fake_server.url + "/hook", json_body={}, allow_statuses=(200,))
    assert response == tronitor.HttpResponse(200, None)


def test_http_empty_error_body_uses_the_reason_phrase(fake_server: FakeServer) -> None:
    """An error with no body is described by the standard reason phrase."""
    fake_server.add("GET", "/x", 500)
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert str(e.value) == "HTTP 500: Internal Server Error"


def test_http_json_error_detail_is_collapsed_and_cut(fake_server: FakeServer) -> None:
    """A JSON message is whitespace-collapsed and limited to ERROR_TEXT_LIMIT characters."""
    fake_server.add("GET", "/x", 400, {"message": "a\n  b " + "z" * 500})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert str(e.value) == "HTTP 400: " + ("a b " + "z" * 500)[: tronitor.ERROR_TEXT_LIMIT]


def test_http_allowed_status_with_non_json_body_gives_none(fake_server: FakeServer) -> None:
    """An allowed non-2xx status with a body that is not JSON returns json=None."""
    fake_server.add("GET", "/x", 404, "<html>nope</html>")
    r = tronitor.Http().request("GET", fake_server.url + "/x", allow_statuses={404})
    assert r == tronitor.HttpResponse(404, None)


def test_fake_server_once_responses_are_used_in_order_then_fall_back(fake_server: FakeServer) -> None:
    """Once responses are consumed in order, then the next registered response for the route applies."""
    fake_server.add("GET", "/p", 200, {"page": 1}, once=True)
    fake_server.add("GET", "/p", 200, {"page": 2}, once=True)
    fake_server.add("GET", "/p", 200, {"page": "rest"})
    http = tronitor.Http()
    pages = [http.request("GET", fake_server.url + "/p").json["page"] for _ in range(4)]
    assert pages == [1, 2, "rest", "rest"]


def test_fake_server_route_with_only_consumed_once_responses_is_404(fake_server: FakeServer) -> None:
    """After its once responses are used up, a route answers like an unknown one."""
    fake_server.add("GET", "/p", 200, {}, once=True)
    http = tronitor.Http()
    http.request("GET", fake_server.url + "/p")
    with pytest.raises(tronitor.ProviderError) as e:
        http.request("GET", fake_server.url + "/p")
    assert e.value.status == 404


def test_fake_server_unknown_route_is_404_no_route(fake_server: FakeServer) -> None:
    """An unknown route answers 404 with the no-route error."""
    r = tronitor.Http().request("GET", fake_server.url + "/nope", allow_statuses={404})
    assert r == tronitor.HttpResponse(404, {"error": "no route"})


def test_fake_server_records_query_and_filters_requests(fake_server: FakeServer) -> None:
    """The query is parsed into RecordedRequest.query, routes match on the path, requests_for filters."""
    fake_server.add("GET", "/a", 200, {})
    fake_server.add("POST", "/a", 200, {})
    http = tronitor.Http()
    http.request("GET", fake_server.url + "/a?x=1&x=2&y=3")
    http.request("POST", fake_server.url + "/a", json_body={"k": "v"})
    assert fake_server.requests[0].query == {"x": ["1", "2"], "y": ["3"]}
    assert fake_server.requests[0].path == "/a"
    assert [r.body for r in fake_server.requests_for("POST", "/a")] == [{"k": "v"}]
    assert fake_server.requests_for("GET", "/b") == []


def test_hc_list_monitors_maps_uuid_name_status(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """list_monitors maps each check to a Monitor and sends the API key."""
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": hc_fixture_checks()})
    monitors = hc_provider.list_monitors()
    assert [(m.id, m.name, m.status) for m in monitors] == [
        (HC_UUID_FILESYSTEM, "Filesystem Backup", "up"),
        (HC_UUID_DATABASE, "Database Backup", "paused"),
    ]
    assert monitors[0].raw == hc_fixture_checks()[0]
    assert fake_server.requests[0].headers["X-Api-Key"] == "hc-test-key"


def test_hc_read_only_key_is_rejected(hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer) -> None:
    """Checks without a uuid (a read-only key) raise a clear error."""
    checks = [{"name": "Filesystem Backup", "status": "up", "unique_key": "abc"}]
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": checks})
    with pytest.raises(
        tronitor.ProviderError, match="the Healthchecks API key is read-only; tronitor needs a read-write key"
    ):
        hc_provider.list_monitors()


def test_hc_list_monitors_reads_the_slug(hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer) -> None:
    """Each check's slug becomes the Monitor's slug."""
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": hc_fixture_checks()})
    assert [m.slug for m in hc_provider.list_monitors()] == ["filesystem-backup", "database-backup"]


def test_hc_check_without_a_slug_has_an_empty_slug(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """A check with no slug field, or an empty slug, gets an empty slug."""
    checks = hc_fixture_checks()
    del checks[0]["slug"]
    checks[1]["slug"] = ""
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": checks})
    assert [m.slug for m in hc_provider.list_monitors()] == ["", ""]


def test_hc_slug_that_is_not_a_string_is_an_unexpected_response(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """A slug that is a list, a number or null is not what the API sends."""
    checks = hc_fixture_checks()
    checks[0]["slug"] = ["filesystem-backup"]
    fake_server.add("GET", "/api/v3/checks/", 200, {"checks": checks})
    with pytest.raises(tronitor.ProviderError, match="unexpected response from Healthchecks"):
        hc_provider.list_monitors()


def test_hc_set_manual_resume_posts_the_setting(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """set_manual_resume posts manual_resume to the check's update path, with the API key."""
    path = f"/api/v3/checks/{HC_UUID_FILESYSTEM}"
    for value in (True, False):
        fake_server.add("POST", path, 200, {**hc_fixture_checks()[0], "manual_resume": value}, once=True)
        hc_provider.set_manual_resume(tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", {}), value)
        request = fake_server.requests[-1]
        assert (request.method, request.path, request.body) == ("POST", path, {"manual_resume": value})
        assert request.headers["X-Api-Key"] == "hc-test-key"


@pytest.mark.parametrize("answer", [{"manual_resume": False}, {}], ids=["the old value", "no field"])
def test_hc_set_manual_resume_fails_when_the_server_does_not_keep_it(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer, answer: dict[str, object]
) -> None:
    """A server that answers without the new value does not know the setting, so the change is a failure."""
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 200, {"name": "Filesystem Backup", **answer})
    monitor = tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", {})
    with pytest.raises(tronitor.ProviderError, match="this Healthchecks server does not support the setting"):
        hc_provider.set_manual_resume(monitor, True)


def test_ur_set_manual_resume_is_unsupported(ur_provider: tronitor.UptimeRobotProvider) -> None:
    """UptimeRobot has no setting for pings to a paused monitor."""
    with pytest.raises(tronitor.Unsupported):
        ur_provider.set_manual_resume(tronitor.Monitor("1001", "Plex", "up", {}), True)


def test_hc_pause_posts_to_pause_url(hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer) -> None:
    """pause posts an empty JSON body to the pause path."""
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_FILESYSTEM}/pause", 200, {"status": "paused"})
    hc_provider.pause(tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", {}))
    request = fake_server.requests[0]
    assert (request.method, request.path, request.body) == ("POST", f"/api/v3/checks/{HC_UUID_FILESYSTEM}/pause", {})
    assert request.headers["X-Api-Key"] == "hc-test-key"
    assert request.headers["Content-Type"] == "application/json"


def test_hc_unpause_posts_to_resume_and_accepts_409(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """unpause posts to the resume path; 409 (not paused) is not an error."""
    path = f"/api/v3/checks/{HC_UUID_DATABASE}/resume"
    monitor = tronitor.Monitor(HC_UUID_DATABASE, "Database Backup", "paused", {})
    fake_server.add("POST", path, 200, {"status": "new"}, once=True)
    fake_server.add("POST", path, 409, {"error": "not paused"})
    hc_provider.unpause(monitor)
    hc_provider.unpause(monitor)
    requests = fake_server.requests_for("POST", path)
    assert len(requests) == 2
    assert requests[0].body == {}
    assert requests[0].headers["X-Api-Key"] == "hc-test-key"


def test_hc_unpause_raises_on_other_errors(hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer) -> None:
    """unpause raises ProviderError for an error other than 409."""
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_DATABASE}/resume", 404, {"error": "not found"})
    with pytest.raises(tronitor.ProviderError) as e:
        hc_provider.unpause(tronitor.Monitor(HC_UUID_DATABASE, "Database Backup", "paused", {}))
    assert e.value.status == 404


def test_hc_info_alerts_create_delete_hit_the_right_paths(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """info, alert_contacts, create and delete use the documented methods and paths and return the body."""
    check = hc_fixture_checks()[0]
    channels = [{"id": "c1", "name": "Email", "kind": "email"}]
    payload = {"name": "New", "timeout": 3600}
    fake_server.add("GET", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 200, check)
    fake_server.add("GET", "/api/v3/channels/", 200, {"channels": channels})
    fake_server.add("POST", "/api/v3/checks/", 201, check)
    fake_server.add("DELETE", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 200, check)
    monitor = tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", check)
    assert hc_provider.info(monitor) == check
    assert hc_provider.alert_contacts() == channels
    assert hc_provider.create(payload) == check
    assert hc_provider.delete(monitor) is None
    seen = [(r.method, r.path) for r in fake_server.requests]
    assert seen == [
        ("GET", f"/api/v3/checks/{HC_UUID_FILESYSTEM}"),
        ("GET", "/api/v3/channels/"),
        ("POST", "/api/v3/checks/"),
        ("DELETE", f"/api/v3/checks/{HC_UUID_FILESYSTEM}"),
    ]
    assert all(r.headers["X-Api-Key"] == "hc-test-key" for r in fake_server.requests)
    assert fake_server.requests[2].body == payload


def test_hc_stats_and_reset_are_unsupported(hc_provider: tronitor.HealthchecksProvider) -> None:
    """stats and reset raise Unsupported for Healthchecks."""
    with pytest.raises(tronitor.Unsupported, match="Healthchecks does not support stats"):
        hc_provider.stats()
    monitor = tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", {})
    with pytest.raises(tronitor.Unsupported, match="Healthchecks does not support reset"):
        hc_provider.reset(monitor)


def test_hc_is_id_matches_uuids_only() -> None:
    """is_id accepts UUIDs in either case and rejects names."""
    assert tronitor.HealthchecksProvider.is_id(HC_UUID_FILESYSTEM)
    assert tronitor.HealthchecksProvider.is_id(HC_UUID_FILESYSTEM.upper())
    assert not tronitor.HealthchecksProvider.is_id("Plex")


@pytest.mark.parametrize(
    "body",
    [None, {"items": []}, {"checks": [{"uuid": HC_UUID_FILESYSTEM, "status": "up"}]}],
    ids=["no body", "no checks key", "check without name"],
)
def test_hc_unexpected_response_shape_is_a_provider_error(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer, body: object
) -> None:
    """A 200 with a body of the wrong shape raises ProviderError, not TypeError or KeyError."""
    fake_server.add("GET", "/api/v3/checks/", 200, body)
    with pytest.raises(tronitor.ProviderError, match="unexpected response from Healthchecks"):
        hc_provider.list_monitors()


@pytest.mark.parametrize(
    "change",
    [
        {"uuid": "/etc/passwd"},
        {"uuid": "../x"},
        {"uuid": 31365},
        {"uuid": HC_UUID_FILESYSTEM + "\n"},
        {"name": 5},
        {"name": ["Filesystem Backup"]},
        {"status": {"up": True}},
    ],
    ids=["absolute path", "parent folder", "number", "trailing newline", "number name", "list name", "dict status"],
)
def test_hc_check_with_a_bad_uuid_name_or_status_is_unexpected(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer, change: dict[str, object]
) -> None:
    """A uuid that is not a UUID string, or a name or status that is not a string, is refused.

    The uuid becomes a lock file name, so a hostile server must not be able to point it at another folder.
    """
    serve_checks(fake_server, [hc_fixture_checks()[0], {**hc_fixture_checks()[1], **change}])
    with pytest.raises(tronitor.ProviderError, match=r"^unexpected response from Healthchecks$"):
        hc_provider.list_monitors()


def test_hc_info_with_empty_body_is_a_provider_error(
    hc_provider: tronitor.HealthchecksProvider, fake_server: FakeServer
) -> None:
    """info raises ProviderError when the 200 response has no body."""
    fake_server.add("GET", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 200)
    monitor = tronitor.Monitor(HC_UUID_FILESYSTEM, "Filesystem Backup", "up", {})
    with pytest.raises(tronitor.ProviderError, match="unexpected response from Healthchecks"):
        hc_provider.info(monitor)


MONS = [
    tronitor.Monitor("1", "Plex", "up", {}),
    tronitor.Monitor("2", "Sonarr", "paused", {}),
    tronitor.Monitor("3", "sonarr", "up", {}),
    tronitor.Monitor("4", "Radarr, 4K", "up", {}),
]


def test_split_selection_handles_quotes_spaces_and_all() -> None:
    """Items are split on commas, trimmed and unquoted; a lone "all" in any case becomes ["all"]."""
    assert tronitor.split_selection(" 'Plex', \"Tautulli\" ,18095689") == ["Plex", "Tautulli", "18095689"]
    assert tronitor.split_selection("ALL") == ["all"]
    assert tronitor.split_selection("Plex,,  ,") == ["Plex"]
    assert tronitor.split_selection("all,Plex") == ["all", "Plex"]


def test_select_all_returns_everything_in_order() -> None:
    """The item "all" matches every monitor in the provider's order."""
    selection = tronitor.select_monitors(MONS, ["all"], str.isdigit)
    assert selection.matched == MONS
    assert selection.ok


def test_select_by_name_is_exact_and_case_insensitive() -> None:
    """Names match whole and ignoring case; a partial name is unmatched."""
    assert tronitor.select_monitors(MONS, ["plex"], str.isdigit).matched == [MONS[0]]
    selection = tronitor.select_monitors(MONS, ["ple"], str.isdigit)
    assert selection.matched == []
    assert selection.unmatched == ["ple"]
    assert not selection.ok


def test_select_by_id() -> None:
    """An item that looks like an ID matches on the ID, not the name."""
    selection = tronitor.select_monitors(MONS, ["2", "9"], str.isdigit)
    assert selection.matched == [MONS[1]]
    assert selection.unmatched == ["9"]


def test_id_match_is_case_insensitive() -> None:
    """UUIDs typed in upper case still match."""
    uuid = "abcdef12-0000-0000-0000-000000000000"
    mons = [tronitor.Monitor(uuid, "X", "up", {})]
    selection = tronitor.select_monitors(mons, [uuid.upper()], tronitor.HealthchecksProvider.is_id)
    assert selection.matched == mons


def test_duplicate_items_match_once() -> None:
    """The same monitor named by name and by ID appears once."""
    selection = tronitor.select_monitors(MONS, ["Plex", "1"], str.isdigit)
    assert selection.matched == [MONS[0]]


def test_ambiguous_name_is_reported_with_ids() -> None:
    """A name shared by several monitors is ambiguous and the message lists their IDs."""
    selection = tronitor.select_monitors(MONS, ["Sonarr"], str.isdigit)
    assert selection.matched == []
    assert selection.ambiguous == {"Sonarr": [MONS[1], MONS[2]]}
    assert not selection.ok
    text = tronitor.describe_selection_problems(selection, MONS, "ID")
    assert text == '"Sonarr" matches 2 monitors; use the ID instead:\n  Sonarr (ID 2)\n  sonarr (ID 3)'


def test_unmatched_is_reported_and_comma_names_get_the_hint() -> None:
    """Pieces of a name containing a comma are unmatched and the message explains why."""
    items = tronitor.split_selection('"Radarr, 4K"')
    selection = tronitor.select_monitors(MONS, items, str.isdigit)
    assert selection.unmatched == ["Radarr", "4K"]
    text = tronitor.describe_selection_problems(selection, MONS, "ID")
    assert text == "Not found: Radarr\nNot found: 4K\nNames with commas cannot be selected; use the ID instead."


def test_split_selection_drops_a_stray_quote() -> None:
    """A quoted name containing a comma is split in two; the leftover quote characters are removed."""
    assert tronitor.split_selection('"Radarr, 4K"') == ["Radarr", "4K"]


def test_prefix_of_another_name_gets_no_hint() -> None:
    """An unmatched item that merely starts a longer name (no comma) does not trigger the comma hint."""
    mons = [tronitor.Monitor("1", "Plex Media Server", "up", {})]
    selection = tronitor.select_monitors(mons, ["Plex"], str.isdigit)
    assert tronitor.describe_selection_problems(selection, mons, "ID") == "Not found: Plex"


def test_unmatched_without_a_name_prefix_has_no_hint() -> None:
    """The comma hint only appears when an unmatched item starts a monitor name."""
    selection = tronitor.select_monitors(MONS, ["Nope"], str.isdigit)
    assert tronitor.describe_selection_problems(selection, MONS, "ID") == "Not found: Nope"


SLUGGED = [
    tronitor.Monitor("1", "Filesystem Backup", "up", {}, slug="filesystem-backup"),
    tronitor.Monitor("2", "Radarr, 4K", "up", {}, slug="radarr-4k"),
    tronitor.Monitor("3", "No Slug", "up", {}),
]


def test_select_by_slug_is_exact_and_case_insensitive() -> None:
    """A slug matches whole and ignoring case; a part of a slug is unmatched."""
    assert tronitor.select_monitors(SLUGGED, ["FILESYSTEM-backup"], str.isdigit).matched == [SLUGGED[0]]
    selection = tronitor.select_monitors(SLUGGED, ["filesystem"], str.isdigit)
    assert selection.matched == []
    assert selection.unmatched == ["filesystem"]


def test_slug_selects_a_monitor_whose_name_has_a_comma() -> None:
    """The slug of a name with a comma has no comma, so it can be selected."""
    items = tronitor.split_selection("radarr-4k,Filesystem Backup")
    assert tronitor.select_monitors(SLUGGED, items, str.isdigit).matched == [SLUGGED[1], SLUGGED[0]]


def test_name_and_slug_of_one_monitor_match_it_once() -> None:
    """A monitor named by its name and by its slug, or whose name is its slug, is selected once."""
    selection = tronitor.select_monitors(SLUGGED, ["Filesystem Backup", "filesystem-backup"], str.isdigit)
    assert selection.matched == [SLUGGED[0]]
    plex = tronitor.Monitor("1", "plex", "up", {}, slug="plex")
    selection = tronitor.select_monitors([plex], ["plex"], str.isdigit)
    assert selection.matched == [plex]
    assert selection.ok


def test_name_of_one_monitor_and_slug_of_another_is_ambiguous() -> None:
    """An item that is one monitor's name and another monitor's slug selects neither and lists both IDs."""
    mons = [
        tronitor.Monitor("1", "backup", "up", {}, slug="backup-old"),
        tronitor.Monitor("2", "Nightly", "up", {}, slug="backup"),
    ]
    selection = tronitor.select_monitors(mons, ["backup"], str.isdigit)
    assert selection.matched == []
    assert selection.ambiguous == {"backup": mons}
    text = tronitor.describe_selection_problems(selection, mons, "UUID")
    assert text == '"backup" matches 2 monitors; use the UUID instead:\n  backup (UUID 1)\n  Nightly (UUID 2)'


def test_comma_hint_suggests_the_slug_when_monitors_have_slugs() -> None:
    """With slugs, the comma hint offers the slug as well as the ID."""
    items = tronitor.split_selection('"Radarr, 4K"')
    selection = tronitor.select_monitors(SLUGGED, items, str.isdigit)
    text = tronitor.describe_selection_problems(selection, SLUGGED, "UUID")
    assert text.splitlines()[-1] == "Names with commas cannot be selected; use the slug or the UUID instead."


def test_lock_all_and_lock_one_create_empty_files(tmp_path: Path) -> None:
    """lock_all and lock create empty files and return their paths."""
    locks = tronitor.LockFiles(tmp_path)
    all_path = locks.lock_all()
    one_path = locks.lock("abc")
    assert all_path == tmp_path / "healthchecks.lock"
    assert one_path == tmp_path / "abc.lock"
    assert all_path.read_bytes() == b""
    assert one_path.read_bytes() == b""
    assert locks.all_locked
    assert locks.is_locked("abc")
    assert not locks.is_locked("other")


def test_unlock_all_removes_only_known_files(tmp_path: Path) -> None:
    """unlock_all removes healthchecks.lock and the lock files of the given IDs, nothing else."""
    for name in ("healthchecks.lock", "a.lock", "b.lock", "other.lock"):
        (tmp_path / name).touch()
    removed = tronitor.LockFiles(tmp_path).unlock_all(["a", "b", "missing"])
    assert removed == [tmp_path / "healthchecks.lock", tmp_path / "a.lock", tmp_path / "b.lock"]
    assert [p.name for p in tmp_path.iterdir()] == ["other.lock"]


def test_unlock_missing_is_not_an_error(tmp_path: Path) -> None:
    """Unlocking files that do not exist is fine and reports nothing removed."""
    locks = tronitor.LockFiles(tmp_path)
    assert locks.unlock("nope") is False
    assert locks.unlock_all(["nope"]) == []
    locks.lock("yes")
    assert locks.unlock("yes") is True
    assert not locks.is_locked("yes")


def test_prepare_creates_nested_dir(tmp_path: Path) -> None:
    """prepare creates missing parent directories and leaves no probe file behind."""
    target = tmp_path / "a" / "b"
    tronitor.LockFiles(target).prepare()
    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_prepare_rejects_a_file_in_place_of_the_dir(tmp_path: Path) -> None:
    """prepare refuses a path that is a regular file."""
    path = tmp_path / "file"
    path.write_text("x")
    with pytest.raises(tronitor.LockError, match="is not a directory"):
        tronitor.LockFiles(path).prepare()


@pytest.mark.skipif(
    sys.platform == "win32" or (sys.platform != "win32" and os.geteuid() == 0), reason="needs a read-only directory"
)
def test_prepare_rejects_an_unwritable_dir(tmp_path: Path) -> None:
    """prepare reports a directory it cannot write to."""
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o500)
    try:
        with pytest.raises(tronitor.LockError, match="cannot write"):
            tronitor.LockFiles(target).prepare()
    finally:
        target.chmod(0o700)


def test_lock_in_a_missing_dir_is_a_lock_error(tmp_path: Path) -> None:
    """lock and lock_all report a missing directory as a LockError."""
    locks = tronitor.LockFiles(tmp_path / "missing")
    with pytest.raises(tronitor.LockError, match="cannot create"):
        locks.lock("a")
    with pytest.raises(tronitor.LockError, match="cannot create"):
        locks.lock_all()


def test_unlock_all_handles_a_duplicate_id(tmp_path: Path) -> None:
    """A repeated ID is removed once and is not an error."""
    (tmp_path / "a.lock").touch()
    assert tronitor.LockFiles(tmp_path).unlock_all(["a", "a"]) == [tmp_path / "a.lock"]


@pytest.mark.parametrize("monitor_id", ["../x", "..", "/etc/passwd", "a/b", "a\\b", "C:x", "a\x00b", ""])
def test_path_for_refuses_an_id_that_leaves_the_lock_dir(tmp_path: Path, monitor_id: str) -> None:
    """An ID that could name a file outside the lock folder is refused, and nothing is created or removed."""
    locks = tronitor.LockFiles(tmp_path / "locks")
    (tmp_path / "x.lock").touch()
    for call in (locks.path_for, locks.lock, locks.unlock, locks.is_locked):
        with pytest.raises(tronitor.LockError, match=r"^refusing to use .* as a lock file name$"):
            call(monitor_id)
    assert (tmp_path / "x.lock").is_file()


def test_prepare_does_not_use_a_predictable_probe_name(tmp_path: Path) -> None:
    """prepare tests the folder with a file of a random name, so a file with the old fixed name is left alone."""
    old_probe = tmp_path / f".tronitor-write-test-{os.getpid()}"
    old_probe.write_text("keep", encoding="utf-8")
    tronitor.LockFiles(tmp_path).prepare()
    assert [p.name for p in tmp_path.iterdir()] == [old_probe.name]
    assert old_probe.read_text(encoding="utf-8") == "keep"


class FakeTty(io.StringIO):
    """A StringIO that claims to be a terminal."""

    def isatty(self) -> bool:
        """Return True."""
        return True


class NoIsatty:
    """A file-like object whose isatty raises."""

    def isatty(self) -> bool:
        """Raise like a stream without terminal support."""
        raise ValueError("closed")


def test_use_color_rules() -> None:
    """Colour needs a terminal, no NO_COLOR and no flag."""
    assert tronitor.use_color(FakeTty(), {}, False) is True
    assert tronitor.use_color(FakeTty(), {"NO_COLOR": ""}, False) is False
    assert tronitor.use_color(FakeTty(), {}, True) is False
    assert tronitor.use_color(io.StringIO(), {}, False) is False
    assert tronitor.use_color(NoIsatty(), {}, False) is False  # type: ignore[arg-type]


def sample_monitors() -> list[tronitor.Monitor]:
    """Return two monitors with different name lengths."""
    return [
        tronitor.Monitor("id1", "web", "paused", {}),
        tronitor.Monitor("id2", "database", "seems down", {}),
    ]


def test_table_pads_names_and_capitalises_status() -> None:
    """Names are padded to the longest and the status is capitalised."""
    text = tronitor.format_monitor_table(sample_monitors(), "UUID", False)
    assert text == "web       UUID: id1  Status: Paused\ndatabase  UUID: id2  Status: Seems down"
    assert tronitor.format_monitor_table([], "UUID", True) == ""


def test_table_with_slugs_pads_the_slug_column() -> None:
    """With slugs=True, a slug column comes after the ID, padded to the longest slug; no slug shows (none)."""
    monitors = [
        tronitor.Monitor("id1", "web", "paused", {}, slug="web"),
        tronitor.Monitor("id2", "database", "up", {}),
    ]
    text = tronitor.format_monitor_table(monitors, "UUID", False, slugs=True)
    assert text == "web       UUID: id1  Slug: web     Status: Paused\ndatabase  UUID: id2  Slug: (none)  Status: Up"


def test_table_strips_control_characters_from_the_slug() -> None:
    """Control characters in a slug become "?"."""
    monitor = tronitor.Monitor("i", "n", "up", {}, slug="s\x1b[2J")
    assert tronitor.format_monitor_table([monitor], "UUID", False, slugs=True) == "n  UUID: i  Slug: s?[2J  Status: Up"


def test_table_colours_the_id_label_and_the_status() -> None:
    """The ID label is bold cyan and the status has its colour; names, IDs and the Status label stay plain."""
    text = tronitor.format_monitor_table(sample_monitors(), "UUID", True)
    first, second = text.split("\n")
    assert first == "web       \x1b[1;36mUUID:\x1b[0m id1  Status: \x1b[33mPaused\x1b[0m"
    assert second == "database  \x1b[1;36mUUID:\x1b[0m id2  Status: \x1b[38;5;202mSeems down\x1b[0m"
    unknown = tronitor.Monitor("i", "n", "odd", {})
    assert tronitor.format_monitor_table([unknown], "ID", True) == "n  \x1b[1;36mID:\x1b[0m i  Status: Odd"


def test_table_colours_the_slug_label_bold_bright_blue() -> None:
    """With slugs, the Slug label is bold bright blue and the padding stays outside the colour codes."""
    monitors = [
        tronitor.Monitor("id1", "web", "up", {}, slug="web"),
        tronitor.Monitor("id2", "database", "up", {}, slug="database-backup"),
    ]
    first, second = tronitor.format_monitor_table(monitors, "UUID", True, slugs=True).split("\n")
    assert first == (
        "web       \x1b[1;36mUUID:\x1b[0m id1  \x1b[1;94mSlug:\x1b[0m web              Status: \x1b[32mUp\x1b[0m"
    )
    assert second == (
        "database  \x1b[1;36mUUID:\x1b[0m id2  \x1b[1;94mSlug:\x1b[0m database-backup  Status: \x1b[32mUp\x1b[0m"
    )


def test_table_without_colour_has_no_colour_codes() -> None:
    """Without colour, neither the labels nor the status carry codes."""
    monitors = [tronitor.Monitor("id1", "web", "up", {}, slug="web")]
    assert "\x1b" not in tronitor.format_monitor_table(monitors, "UUID", False, slugs=True)


def test_format_json_is_sorted_indented_and_unescaped() -> None:
    """JSON output is indented, sorted and keeps accents."""
    assert tronitor.format_json({"b": 1, "a": "é"}) == '{\n  "a": "é",\n  "b": 1\n}'


def test_confirm_assume_yes_skips_the_prompt() -> None:
    """assume_yes returns True without asking."""

    def fail(prompt: str) -> str:
        raise AssertionError("must not prompt")

    assert tronitor.confirm("Go?", assume_yes=True, interactive=False, input_fn=fail) is True


def test_confirm_without_terminal_raises() -> None:
    """Without a terminal and without assume_yes, NeedsTerminal carries the question."""
    with pytest.raises(tronitor.NeedsTerminal, match=r"Go\?"):
        tronitor.confirm("Go?", assume_yes=False, interactive=False)


def test_confirm_accepts_yes_variants_and_defaults_to_no() -> None:
    """y and yes in any case are yes; everything else, including EOF, is no."""
    prompts: list[str] = []

    def answer(text: str) -> Callable[[str], str]:
        def fn(prompt: str) -> str:
            prompts.append(prompt)
            return text

        return fn

    for text, expected in [("Y", True), (" yes ", True), ("", False), ("n", False), ("maybe", False)]:
        assert tronitor.confirm("Go?", assume_yes=False, interactive=True, input_fn=answer(text)) is expected
    assert prompts[0] == "Go? [y/N]: "

    def eof(prompt: str) -> str:
        raise EOFError

    assert tronitor.confirm("Go?", assume_yes=False, interactive=True, input_fn=eof) is False


def test_table_strips_control_characters() -> None:
    """Control characters in a name or ID become "?" and never reach the terminal."""
    monitor = tronitor.Monitor("i\x07d", "Bad\x1b[31mName\n", "up", {})
    line = tronitor.format_monitor_table([monitor], "ID", False)
    assert "Bad?[31mName?" in line
    assert "ID: i?d" in line
    assert "\x1b" not in line
    assert "\n" not in line


def test_status_colors_cover_every_status() -> None:
    """STATUS_COLORS has exactly the known statuses and each value is an ANSI sequence."""
    statuses = {"up", "down", "paused", "grace", "seems down", "new", "started", "pending"}
    assert set(tronitor.STATUS_COLORS) == statuses
    assert all(code.startswith("\x1b[") for code in tronitor.STATUS_COLORS.values())
    assert tronitor.STATUS_COLORS["started"] == tronitor.STATUS_COLORS["new"]


def test_table_strips_control_characters_from_the_status() -> None:
    """A status from the provider with a control character is shown with "?" in its place."""
    line = tronitor.format_monitor_table([tronitor.Monitor("i", "n", "up\x1b[2J", {})], "ID", True)
    assert "\x1b[2J" not in line
    assert line == "n  \x1b[1;36mID:\x1b[0m i  Status: Up?[2j"


def test_format_json_escapes_del_and_c1_control_characters() -> None:
    """DEL and the C1 control characters are escaped, so the JSON stays valid and cannot control the terminal."""
    text = tronitor.format_json({"name": "a\x7fb\x9bc\x85d é"})
    assert text == '{\n  "name": "a\\u007fb\\u009bc\\u0085d é"\n}'
    assert not re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]", text)
    assert json.loads(text) == {"name": "a\x7fb\x9bc\x85d é"}


"""Command line: the actions, run through main() against the fake server."""

FS_PAUSE = f"/api/v3/checks/{HC_UUID_FILESYSTEM}/pause"
DB_PAUSE = f"/api/v3/checks/{HC_UUID_DATABASE}/pause"
DB_RESUME = f"/api/v3/checks/{HC_UUID_DATABASE}/resume"
REMINDER = (
    "Note: a paused Healthchecks check becomes active again when it next receives a ping. "
    "The HealthChecks-Linux script skips a check while its lock file exists (see the docs). "
    "Running --ignore-paused-pings on a check keeps it paused when it gets a ping."
)


@pytest.fixture
def hc_env(hc_config_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point TRONITOR_CONFIG at the Healthchecks config, set NO_COLOR and clear other TRONITOR_ variables."""
    for name in list(os.environ):
        if name.startswith("TRONITOR_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("TRONITOR_CONFIG", str(hc_config_file))
    monkeypatch.setenv("NO_COLOR", "1")
    return hc_config_file


@pytest.fixture
def locks(hc_config_file: Path) -> Path:
    """Return the lock directory named in the Healthchecks config (not created)."""
    return hc_config_file.parent / "locks"


def posts(fake_server: FakeServer) -> list[str]:
    """Return the paths of every POST request received."""
    return [r.path for r in fake_server.requests if r.method == "POST"]


def deletes(fake_server: FakeServer) -> list[str]:
    """Return the paths of every DELETE request received."""
    return [r.path for r in fake_server.requests if r.method == "DELETE"]


def make_tty(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    """Make stdin and stdout look like a terminal, with answer waiting on stdin."""
    monkeypatch.setattr(sys, "stdin", FakeTty(answer))
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)


def test_list_prints_table(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """-l prints the header and one row per check and exits 0."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-l"]) == 0
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "The following Healthchecks monitors were found:",
        f"Filesystem Backup  UUID: {HC_UUID_FILESYSTEM}  Slug: filesystem-backup  Status: Up",
        f"Database Backup    UUID: {HC_UUID_DATABASE}  Slug: database-backup    Status: Paused",
    ]
    assert err == ""


def test_list_with_no_monitors(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """An empty account says so."""
    serve_checks(fake_server, [])
    assert tronitor.main(["-m", "hc", "-l"]) == 0
    assert capsys.readouterr().out == "No monitors found.\n"


def test_list_json(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--json prints the raw records and nothing else."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-l", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == hc_fixture_checks()


def test_find_shows_paused_only_and_does_not_prompt_without_tty(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-f without a terminal lists the paused check, asks nothing and sends no POST."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-f"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "The following Healthchecks monitors are paused:",
        f"Database Backup  UUID: {HC_UUID_DATABASE}  Slug: database-backup  Status: Paused",
    ]
    assert posts(fake_server) == []


def test_find_with_nothing_paused(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """No paused check gives the "none paused" line, for -f and -n alike."""
    serve_checks(fake_server, hc_fixture_checks()[:1])
    for flag in ("-f", "-n"):
        assert tronitor.main(["-m", "hc", flag]) == 0
        assert capsys.readouterr().out == "No Healthchecks monitors are paused.\n"


def test_find_json_prints_paused_records(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-n --json prints only the paused records."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-n", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == [hc_fixture_checks()[1]]


def test_find_prompt_yes_unpauses_and_removes_locks(
    hc_env: Path,
    locks: Path,
    fake_server: FakeServer,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a terminal, answering y unpauses the paused check and removes the lock files."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    for name in ("healthchecks.lock", f"{HC_UUID_DATABASE}.lock", "other.lock"):
        (locks / name).touch()
    make_tty(monkeypatch, "y\n")
    assert tronitor.main(["-m", "hc", "-f"]) == 0
    out = capsys.readouterr().out
    assert "Unpause them? [y/N]: " in out
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out
    assert "already running" not in out
    assert posts(fake_server) == [DB_RESUME]
    assert sorted(p.name for p in locks.iterdir()) == ["other.lock"]


def test_find_prompt_no_changes_nothing(
    hc_env: Path,
    locks: Path,
    fake_server: FakeServer,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Answering anything but yes leaves the checks and lock files alone; --yes does not answer for -f."""
    serve_checks(fake_server)
    locks.mkdir()
    (locks / "healthchecks.lock").touch()
    make_tty(monkeypatch, "\n")
    assert tronitor.main(["-m", "hc", "-f", "--yes"]) == 0
    assert "Unpause them? [y/N]: " in capsys.readouterr().out
    assert posts(fake_server) == []
    assert (locks / "healthchecks.lock").exists()


def test_find_n_and_w_never_prompt_on_a_terminal(
    hc_env: Path,
    hc_config_file_with_webhook: Path,
    fake_server: FakeServer,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """-n and -w do not prompt even on a terminal; -w posts only to the webhook."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 204)
    make_tty(monkeypatch, "y\n")
    for flag in ("-n", "-w"):
        assert tronitor.main(["-m", "hc", flag]) == 0
        assert "Unpause" not in capsys.readouterr().out
    assert posts(fake_server) == ["/hook"]


def test_pause_all_creates_lock_and_posts_each(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--pause all creates healthchecks.lock, pauses every check and ends with the reminder."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    fake_server.add("POST", DB_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 0
    out = capsys.readouterr().out
    assert (locks / "healthchecks.lock").is_file()
    assert posts(fake_server) == [FS_PAUSE, DB_PAUSE]
    assert f"Pausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... done" in out
    assert f"Pausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out
    assert out.rstrip().endswith(REMINDER)


def checks_with_manual_resume(filesystem: object, database: object) -> list[dict[str, object]]:
    """Return the fixture checks with their manual_resume set; None removes the field, as on an old server."""
    checks: list[dict[str, object]] = list(hc_fixture_checks())
    for check, value in zip(checks, (filesystem, database), strict=True):
        if value is None:
            del check["manual_resume"]
        else:
            check["manual_resume"] = value
    return checks


def test_pause_reminder_names_only_the_checks_that_resume_on_a_ping(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """When some paused checks ignore pings, the reminder names the ones that do not."""
    serve_checks(fake_server, checks_with_manual_resume(True, False))
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    fake_server.add("POST", DB_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 0
    assert capsys.readouterr().out.rstrip().endswith(
        "Note: these paused Healthchecks checks become active again when they next receive a ping: "
        "Database Backup. The HealthChecks-Linux script skips a check while its lock file exists (see the docs). "
        "Running --ignore-paused-pings on a check keeps it paused when it gets a ping."
    )


def test_pause_has_no_reminder_when_every_paused_check_ignores_pings(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """Checks set to ignore pings while paused stay paused, so there is nothing to remind."""
    serve_checks(fake_server, checks_with_manual_resume(True, True))
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    fake_server.add("POST", DB_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 0
    out = capsys.readouterr().out
    assert "Note:" not in out
    assert out.endswith(f"Pausing Database Backup (UUID {HC_UUID_DATABASE})... done\n")


def test_pause_reminder_leaves_out_a_check_that_failed_to_pause(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the checks that were paused count: one that failed is not paused, so it is not named."""
    serve_checks(fake_server, checks_with_manual_resume(True, False))
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    fake_server.add("POST", DB_PAUSE, 500, {"error": "boom"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 3
    assert "Note:" not in capsys.readouterr().out


@pytest.mark.parametrize("value", [None, "true", 1], ids=["no field", "a string", "a number"])
def test_pause_reminder_counts_a_check_without_a_true_manual_resume_as_resuming(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], value: object
) -> None:
    """Only manual_resume true means "ignores pings"; a missing field (an old server) or another value does not."""
    serve_checks(fake_server, checks_with_manual_resume(True, value))
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    fake_server.add("POST", DB_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 0
    assert capsys.readouterr().out.rstrip().endswith(
        "ping: Database Backup. The HealthChecks-Linux script skips a check while its lock file exists (see the docs). "
        "Running --ignore-paused-pings on a check keeps it paused when it gets a ping."
    )


FS_UPDATE = f"/api/v3/checks/{HC_UUID_FILESYSTEM}"
DB_UPDATE = f"/api/v3/checks/{HC_UUID_DATABASE}"


def test_ignore_paused_pings_changes_only_the_checks_without_the_setting(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--ignore-paused-pings all skips a check that has the setting, sets the other one and touches no lock file."""
    checks = checks_with_manual_resume(True, False)
    serve_checks(fake_server, checks)
    fake_server.add("POST", DB_UPDATE, 200, {**checks[1], "manual_resume": True})
    assert tronitor.main(["-m", "hc", "--ignore-paused-pings", "all"]) == 0
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        f"Filesystem Backup (UUID {HC_UUID_FILESYSTEM}) already ignores pings while paused",
        f"Setting Database Backup (UUID {HC_UUID_DATABASE}) to ignore pings while paused... done",
    ]
    assert err == ""
    assert [(r.path, r.body) for r in fake_server.requests if r.method == "POST"] == [
        (DB_UPDATE, {"manual_resume": True})
    ]
    assert not locks.exists() or list(locks.iterdir()) == []


def test_resume_on_ping_sets_a_check_back(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--resume-on-ping posts manual_resume false for a check that ignores pings, selected by its slug."""
    checks = checks_with_manual_resume(True, True)
    serve_checks(fake_server, checks)
    fake_server.add("POST", FS_UPDATE, 200, {**checks[0], "manual_resume": False})
    assert tronitor.main(["-m", "hc", "--resume-on-ping", "filesystem-backup"]) == 0
    assert capsys.readouterr().out == (
        f"Setting Filesystem Backup (UUID {HC_UUID_FILESYSTEM}) to resume on a ping... done\n"
    )
    assert [(r.path, r.body) for r in fake_server.requests if r.method == "POST"] == [
        (FS_UPDATE, {"manual_resume": False})
    ]


def test_resume_on_ping_skips_checks_that_already_resume(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check without manual_resume true already resumes on a ping, so nothing is sent."""
    serve_checks(fake_server, checks_with_manual_resume(False, None))
    assert tronitor.main(["-m", "hc", "--resume-on-ping", "all"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Filesystem Backup (UUID {HC_UUID_FILESYSTEM}) already resumes on a ping",
        f"Database Backup (UUID {HC_UUID_DATABASE}) already resumes on a ping",
    ]
    assert posts(fake_server) == []


def test_ignore_paused_pings_reports_a_server_that_does_not_keep_the_setting(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """When one change fails and another works, the failure goes to stderr and the exit code is 3."""
    checks = hc_fixture_checks()
    serve_checks(fake_server, checks)
    fake_server.add("POST", FS_UPDATE, 200, {**checks[0], "manual_resume": True})
    fake_server.add("POST", DB_UPDATE, 200, checks[1])
    assert tronitor.main(["-m", "hc", "--ignore-paused-pings", "all"]) == 3
    out, err = capsys.readouterr()
    assert out == f"Setting Filesystem Backup (UUID {HC_UUID_FILESYSTEM}) to ignore pings while paused... done\n"
    assert err == (
        f"tronitor: Setting Database Backup (UUID {HC_UUID_DATABASE}) to ignore pings while paused... failed: "
        "this Healthchecks server does not support the setting\n"
    )


def test_ignore_paused_pings_with_an_unmatched_name_changes_nothing(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """The selection works as for --pause: a name that matches nothing stops everything with exit code 3."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "--ignore-paused-pings", "Filesystem Backup,Tautulli"]) == 3
    assert capsys.readouterr().err == "tronitor: Not found: Tautulli\n"
    assert posts(fake_server) == []


@pytest.mark.parametrize("option", ["--ignore-paused-pings", "--resume-on-ping"])
def test_paused_ping_options_are_unsupported_for_uptimerobot(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], option: str
) -> None:
    """On UptimeRobot, both options are a usage error before any request."""
    assert tronitor.main(["-m", "ur", option, "all"]) == 2
    assert capsys.readouterr().err == f"tronitor: UptimeRobot does not support {option}\n"
    assert fake_server.requests == []


def test_pause_named_creates_per_monitor_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--pause NAME creates only that check's lock file and pauses only it."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "'filesystem backup'"]) == 0
    assert [p.name for p in locks.iterdir()] == [f"{HC_UUID_FILESYSTEM}.lock"]
    assert posts(fake_server) == [FS_PAUSE]


def test_pause_by_slug_creates_that_checks_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--pause SLUG pauses that check and creates its lock file, named by its UUID."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "filesystem-backup"]) == 0
    assert [p.name for p in locks.iterdir()] == [f"{HC_UUID_FILESYSTEM}.lock"]
    assert posts(fake_server) == [FS_PAUSE]
    assert f"Pausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... done" in capsys.readouterr().out


def test_pause_unmatched_name_does_nothing_and_exits_3(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A name that matches nothing stops everything, even the names that did match."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-p", "Filesystem Backup,Tautulli"]) == 3
    out, err = capsys.readouterr()
    assert err == "tronitor: Not found: Tautulli\n"
    assert out == ""
    assert posts(fake_server) == []
    assert list(locks.iterdir()) == []


def test_pause_unmatched_with_yes_acts_on_the_rest_and_exits_3(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """With --yes, the matched checks are paused and the exit code still reports the miss."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "Filesystem Backup,Tautulli", "--yes"]) == 3
    out, err = capsys.readouterr()
    assert err == "tronitor: Not found: Tautulli\n"
    assert posts(fake_server) == [FS_PAUSE]
    assert f"Pausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... done" in out


def test_pause_ambiguous_name_exits_3_even_with_yes(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A name shared by two checks lists their UUIDs and touches nothing, --yes or not."""
    other = "0f0e0d0c-0b0a-4908-8706-050403020100"
    serve_checks(fake_server, [*hc_fixture_checks(), {**hc_fixture_checks()[0], "uuid": other}])
    assert tronitor.main(["-m", "hc", "-p", "Filesystem Backup,Database Backup", "--yes"]) == 3
    assert capsys.readouterr().err == (
        'tronitor: "Filesystem Backup" matches 2 monitors; use the UUID instead:\n'
        f"  Filesystem Backup (UUID {HC_UUID_FILESYSTEM})\n"
        f"  Filesystem Backup (UUID {other})\n"
    )
    assert posts(fake_server) == []


def test_pause_lock_dir_is_a_file_exits_1_before_any_request(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lock directory that cannot be used stops the pause before the API is called."""
    serve_checks(fake_server)
    locks.write_text("not a directory", encoding="utf-8")
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 1
    assert capsys.readouterr().err == f"tronitor: {locks} is not a directory\n"
    assert fake_server.requests == []


def test_pause_api_failure_continues_and_exits_3(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed pause is reported, the rest go ahead, and the exit code is 3."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 500, {"error": "server error"})
    fake_server.add("POST", DB_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 3
    out, err = capsys.readouterr()
    assert err == f"tronitor: Pausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... failed: HTTP 500: server error\n"
    assert "failed" not in out
    assert f"Pausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out
    assert posts(fake_server) == [FS_PAUSE, DB_PAUSE]


def test_pause_every_failure_exits_1(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """When every pause fails nothing was done, so the exit code is 1 and there is no reminder."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 500)
    assert tronitor.main(["-m", "hc", "-p", "Filesystem Backup"]) == 1
    out, err = capsys.readouterr()
    assert "failed: HTTP 500: Internal Server Error" in err
    assert "Note:" not in out


def test_pause_empty_selection_is_a_usage_error(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty or comma-only selection is a usage error, before any request."""
    for text in ("", " , "):
        assert tronitor.main(["-m", "hc", "-p", text]) == 2
        assert capsys.readouterr().err == 'tronitor: --pause needs "all" or a comma-separated list of monitors\n'
    for option in ("--unpause", "--delete", "--reset"):
        assert tronitor.main(["-m", "hc", option, ","]) == 2
        assert capsys.readouterr().err.startswith(f'tronitor: {option} needs "all"')
    assert fake_server.requests == []


def test_pause_name_with_control_characters_is_printed_safely(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check name with an escape sequence is printed with the control characters replaced."""
    serve_checks(fake_server, [{**hc_fixture_checks()[0], "name": "Bad\x1b[2JName"}])
    fake_server.add("POST", FS_PAUSE, 200, {})
    assert tronitor.main(["-m", "hc", "-p", "all"]) == 0
    out = capsys.readouterr().out
    assert "Pausing Bad?[2JName (UUID" in out
    assert "\x1b" not in out


def test_unpause_all_skips_running_checks_and_removes_locks(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--unpause all resumes only the paused check and removes the lock files of listed checks only."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    for name in ("healthchecks.lock", f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock", "other.lock"):
        (locks / name).touch()
    assert tronitor.main(["-m", "hc", "-u", "all"]) == 0
    out = capsys.readouterr().out
    assert posts(fake_server) == [DB_RESUME]
    assert "Filesystem Backup is already running" in out
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out
    assert sorted(p.name for p in locks.iterdir()) == ["other.lock"]


def test_unpause_all_keeps_the_lock_of_a_failed_check(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check whose unpause failed keeps its lock file; nothing was done, so the exit code is 1."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 500)
    locks.mkdir()
    for name in ("healthchecks.lock", f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock"):
        (locks / name).touch()
    assert tronitor.main(["-m", "hc", "-u", "all"]) == 1
    assert "failed: HTTP 500" in capsys.readouterr().err
    assert sorted(p.name for p in locks.iterdir()) == [f"{HC_UUID_DATABASE}.lock"]


def test_unpause_all_cleanup_continues_past_a_failed_removal(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """healthchecks.lock that cannot be removed is reported, and the per-check lock files still go (exit 3)."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    (locks / "healthchecks.lock").mkdir()
    for name in (f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock"):
        (locks / name).touch()
    assert tronitor.main(["-m", "hc", "-u", "all"]) == 3
    err = capsys.readouterr().err
    assert err.startswith(f"tronitor: cannot remove {locks / 'healthchecks.lock'}")
    assert err.count("\n") == 1
    assert [p.name for p in locks.iterdir()] == ["healthchecks.lock"]


def test_unpause_all_with_no_monitors_removes_the_all_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--unpause all on an empty account still removes a leftover healthchecks.lock and exits 0."""
    serve_checks(fake_server, [])
    locks.mkdir()
    (locks / "healthchecks.lock").touch()
    (locks / "other.lock").touch()
    assert tronitor.main(["-m", "hc", "-u", "all"]) == 0
    assert capsys.readouterr() == ("No monitors found.\n", "")
    assert [p.name for p in locks.iterdir()] == ["other.lock"]


def test_unpause_all_with_no_monitors_reports_a_stuck_all_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """On an empty account, a healthchecks.lock that cannot be removed is reported, but the exit code is still 0."""
    serve_checks(fake_server, [])
    locks.mkdir()
    (locks / "healthchecks.lock").mkdir()
    assert tronitor.main(["-m", "hc", "-u", "all"]) == 0
    out, err = capsys.readouterr()
    assert out == "No monitors found.\n"
    assert err.startswith(f"tronitor: cannot remove {locks / 'healthchecks.lock'}")


def test_named_unpause_warns_when_the_all_lock_remains(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """After a named unpause, a remaining healthchecks.lock is pointed out on stderr; the exit code stays 0."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    (locks / "healthchecks.lock").touch()
    (locks / f"{HC_UUID_DATABASE}.lock").touch()
    assert tronitor.main(["-m", "hc", "-u", "Database Backup"]) == 0
    assert capsys.readouterr().err == (
        "tronitor: healthchecks.lock is still present, so the pinging script skips every check "
        "until you run --unpause all\n"
    )
    assert [p.name for p in locks.iterdir()] == ["healthchecks.lock"]


def test_named_unpause_without_the_all_lock_does_not_warn(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without healthchecks.lock there is no warning."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    assert tronitor.main(["-m", "hc", "-u", "Database Backup"]) == 0
    assert capsys.readouterr().err == ""


def test_unpause_named_removes_its_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--unpause UUID resumes that check and removes only its lock file."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    for name in ("healthchecks.lock", f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock"):
        (locks / name).touch()
    assert tronitor.main(["-m", "hc", "-u", HC_UUID_DATABASE.upper()]) == 0
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in capsys.readouterr().out
    assert posts(fake_server) == [DB_RESUME]
    assert sorted(p.name for p in locks.iterdir()) == [f"{HC_UUID_FILESYSTEM}.lock", "healthchecks.lock"]


def test_unpause_named_running_check_says_so_and_removes_a_stale_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A named check that is already running is not resumed, but its leftover lock file goes."""
    serve_checks(fake_server)
    locks.mkdir()
    (locks / f"{HC_UUID_FILESYSTEM}.lock").touch()
    assert tronitor.main(["-m", "hc", "-u", "Filesystem Backup"]) == 0
    assert capsys.readouterr().out == "Filesystem Backup is already running\n"
    assert posts(fake_server) == []
    assert list(locks.iterdir()) == []


def test_unpause_lock_removal_failure_is_reported(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lock file that cannot be removed is reported and counts as a failure (exit 3 after a success)."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {"status": "new"})
    locks.mkdir()
    (locks / f"{HC_UUID_DATABASE}.lock").mkdir()
    assert tronitor.main(["-m", "hc", "-u", "Database Backup"]) == 3
    out, err = capsys.readouterr()
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out
    assert err.startswith(f"tronitor: cannot remove {locks / (HC_UUID_DATABASE + '.lock')}")


def test_info_prints_json(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--info prints the full record of one check."""
    serve_checks(fake_server)
    record = {**hc_fixture_checks()[0], "desc": "nightly"}
    fake_server.add("GET", f"/api/v3/checks/{HC_UUID_FILESYSTEM}", 200, record)
    assert tronitor.main(["-m", "hc", "-i", "Filesystem Backup"]) == 0
    assert json.loads(capsys.readouterr().out) == record


def test_info_with_two_targets_is_a_usage_error(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--info with two monitors, all or nothing is a usage error before any request."""
    for text in ("Filesystem Backup,Database Backup", "all", ""):
        assert tronitor.main(["-m", "hc", "-i", text]) == 2
        assert capsys.readouterr().err == "tronitor: --info takes one monitor\n"
    assert fake_server.requests == []


def test_info_unknown_name_exits_3(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--info with a name that matches nothing exits 3, --yes or not."""
    serve_checks(fake_server)
    for extra in ([], ["--yes"]):
        assert tronitor.main(["-m", "hc", "-i", "Tautulli", *extra]) == 3
        assert capsys.readouterr().err == "tronitor: Not found: Tautulli\n"


def test_alerts_prints_channels(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--alerts prints a header and the channels as JSON; --json drops the header."""
    channels = [{"id": "c1", "name": "Email", "kind": "email"}]
    fake_server.add("GET", "/api/v3/channels/", 200, {"channels": channels})
    assert tronitor.main(["-m", "hc", "-a"]) == 0
    header, _, body = capsys.readouterr().out.partition("\n")
    assert header == "The following Healthchecks alert contacts were found:"
    assert json.loads(body) == channels
    assert tronitor.main(["-m", "hc", "-a", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == channels


def test_stats_is_unsupported_for_healthchecks(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--stats on Healthchecks is a usage error with a clear message."""
    assert tronitor.main(["-m", "hc", "-s"]) == 2
    assert capsys.readouterr().err == "tronitor: Healthchecks does not support stats\n"
    assert fake_server.requests == []


def test_create_posts_the_file(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """--create posts the file's JSON as it is and prints the new record."""
    payload = {"name": "New check", "timeout": 3600, "tags": "café"}
    created = {**hc_fixture_checks()[0], "name": "New check"}
    fake_server.add("POST", "/api/v3/checks/", 201, created)
    path = tmp_path / "new.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert tronitor.main(["-m", "hc", "-c", str(path)]) == 0
    assert fake_server.requests_for("POST", "/api/v3/checks/")[0].body == payload
    assert json.loads(capsys.readouterr().out) == created


def test_create_missing_file_is_usage_error(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A missing file, invalid JSON or JSON that is not an object is a usage error, with no request."""
    missing = tmp_path / "missing.json"
    assert tronitor.main(["-m", "hc", "-c", str(missing)]) == 2
    assert capsys.readouterr().err.startswith(f"tronitor: {missing}: cannot read the file")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert tronitor.main(["-m", "hc", "-c", str(bad)]) == 2
    assert capsys.readouterr().err.startswith(f"tronitor: {bad}: not valid JSON")
    listed = tmp_path / "list.json"
    listed.write_text("[]", encoding="utf-8")
    assert tronitor.main(["-m", "hc", "-c", str(listed)]) == 2
    assert capsys.readouterr().err == f"tronitor: {listed}: must hold a JSON object\n"
    assert fake_server.requests == []


def test_delete_without_terminal_refuses(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a terminal and --yes, delete refuses with exit 2 and sends no DELETE."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-d", "Filesystem Backup"]) == 2
    assert capsys.readouterr().err == "tronitor: Refusing to delete without a terminal; pass --yes to confirm.\n"
    assert deletes(fake_server) == []


def test_delete_with_yes_deletes(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--yes deletes each selected check without asking."""
    serve_checks(fake_server)
    for uuid in (HC_UUID_FILESYSTEM, HC_UUID_DATABASE):
        fake_server.add("DELETE", f"/api/v3/checks/{uuid}", 200, {})
    assert tronitor.main(["-m", "hc", "-d", "all", "--yes"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Deleting Filesystem Backup... done",
        "Deleting Database Backup... done",
    ]
    assert deletes(fake_server) == [f"/api/v3/checks/{HC_UUID_FILESYSTEM}", f"/api/v3/checks/{HC_UUID_DATABASE}"]


def test_delete_prompt_on_a_terminal(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a terminal delete asks first; answering no deletes nothing."""
    serve_checks(fake_server)
    make_tty(monkeypatch, "n\n")
    assert tronitor.main(["-m", "hc", "-d", "all"]) == 0
    assert capsys.readouterr().out == (
        "Delete 2 monitor(s) from Healthchecks? This cannot be undone. [y/N]: Cancelled.\n"
    )
    assert deletes(fake_server) == []


def test_reset_is_unsupported_for_healthchecks(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--reset on Healthchecks is a usage error before any request or prompt."""
    for extra in ([], ["--yes"]):
        assert tronitor.main(["-m", "hc", "-r", "all", *extra]) == 2
        assert capsys.readouterr().err == "tronitor: Healthchecks does not support reset\n"
    assert fake_server.requests == []


def test_provider_label_is_not_repeated(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A provider message that already names the provider is not prefixed with the label again."""
    fake_server.add("GET", "/api/v3/checks/", 200, {"items": []})
    assert tronitor.main(["-m", "hc", "-l"]) == 1
    assert capsys.readouterr().err == "tronitor: unexpected response from Healthchecks\n"


def test_bad_api_key_is_exit_1_with_label(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """An API error exits 1 and the message names the provider."""
    fake_server.add("GET", "/api/v3/checks/", 401, {"error": "The API key is either missing or invalid."})
    assert tronitor.main(["-m", "hc", "-l"]) == 1
    assert capsys.readouterr().err == "tronitor: Healthchecks: HTTP 401: The API key is either missing or invalid.\n"


def test_missing_api_key_is_exit_2(
    hc_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A config without Healthchecks settings is a usage error that says how to fix it."""
    config = tmp_path / "empty.toml"
    config.write_text(f"[general]\nlock_dir = '{tmp_path / 'locks'}'\n", encoding="utf-8")
    monkeypatch.setenv("TRONITOR_CONFIG", str(config))
    assert tronitor.main(["-m", "hc", "-l"]) == 2
    assert capsys.readouterr().err == (
        "tronitor: no Healthchecks API key: set [healthchecks] api_key in the config or TRONITOR_HEALTHCHECKS_API_KEY\n"
    )


def test_unknown_provider_is_exit_2(hc_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An unknown provider name is a usage error naming the valid ones."""
    assert tronitor.main(["-m", "statuscake", "-l"]) == 2
    assert capsys.readouterr().err == (
        "tronitor: unknown provider 'statuscake'; use healthchecks (hc) or uptimerobot (ur)\n"
    )


def test_resolve_provider_name() -> None:
    """Short and long names, in any case, map to the long name."""
    assert tronitor.resolve_provider_name("hc") == "healthchecks"
    assert tronitor.resolve_provider_name("Healthchecks") == "healthchecks"
    assert tronitor.resolve_provider_name("ur") == "uptimerobot"
    assert tronitor.resolve_provider_name("uptimerobot") == "uptimerobot"
    with pytest.raises(tronitor.ConfigError, match="unknown provider 'x'"):
        tronitor.resolve_provider_name("x")


def test_missing_config_option_file_is_exit_2(hc_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A --config file that does not exist exits 2 with the message."""
    missing = tmp_path / "nope.toml"
    assert tronitor.main(["-m", "hc", "-l", "--config", str(missing)]) == 2
    assert capsys.readouterr().err == f"tronitor: {missing}: config file does not exist\n"


def test_parse_errors_and_version_return_codes(capsys: pytest.CaptureFixture[str]) -> None:
    """main() returns argparse's exit codes instead of raising SystemExit."""
    assert tronitor.main(["--version"]) == 0
    assert tronitor.main(["-m", "hc"]) == 2
    assert tronitor.main(["-m", "hc", "-l", "-n"]) == 2
    assert tronitor.main(["-l"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_ctrl_c_exits_130(hc_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Ctrl+C prints Interrupted. and exits 130."""

    def interrupt(self: tronitor.HealthchecksProvider) -> list[tronitor.Monitor]:
        raise KeyboardInterrupt

    monkeypatch.setattr(tronitor.HealthchecksProvider, "list_monitors", interrupt)
    assert tronitor.main(["-m", "hc", "-l"]) == 130
    assert capsys.readouterr().err == "\nInterrupted.\n"


def test_verbose_logs_to_stderr(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """--verbose logs each request to stderr."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-l", "--verbose"]) == 0
    assert capsys.readouterr().err == f"GET {fake_server.url}/api/v3/checks/\n"


def test_run_takes_its_streams_and_terminal_flag(hc_env: Path, fake_server: FakeServer) -> None:
    """run() reads the answer from its stdin and writes to its own streams."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {})
    args = tronitor.build_parser().parse_args(["-m", "hc", "-f"])
    out, err = io.StringIO(), io.StringIO()
    code = tronitor.run(args, stdin=io.StringIO("yes\n"), stdout=out, stderr=err, env=os.environ, interactive=True)
    assert code == 0
    assert "Unpause them? [y/N]: " in out.getvalue()
    assert posts(fake_server) == [DB_RESUME]
    assert err.getvalue() == ""


def test_find_json_on_a_terminal_never_prompts(hc_env: Path, fake_server: FakeServer) -> None:
    """-f --json on a terminal prints the JSON and does not ask, so nothing is unpaused."""
    serve_checks(fake_server)
    fake_server.add("POST", DB_RESUME, 200, {})
    args = tronitor.build_parser().parse_args(["-m", "hc", "-f", "--json"])
    out = io.StringIO()
    code = tronitor.run(
        args, stdin=io.StringIO("y\n"), stdout=out, stderr=io.StringIO(), env=os.environ, interactive=True
    )
    assert code == 0
    assert json.loads(out.getvalue()) == [hc_fixture_checks()[1]]
    assert posts(fake_server) == []


def test_find_prompt_unpause_failure_exits_3(hc_env: Path, locks: Path, fake_server: FakeServer) -> None:
    """Answering y when one of two resumes fails reports the failure on stderr, keeps its lock and exits 3."""
    checks = hc_fixture_checks()
    checks[0]["status"] = "paused"
    serve_checks(fake_server, checks)
    fake_server.add("POST", f"/api/v3/checks/{HC_UUID_FILESYSTEM}/resume", 500, {"error": "server error"})
    fake_server.add("POST", DB_RESUME, 200, {})
    locks.mkdir()
    for name in ("healthchecks.lock", f"{HC_UUID_FILESYSTEM}.lock", f"{HC_UUID_DATABASE}.lock"):
        (locks / name).touch()
    args = tronitor.build_parser().parse_args(["-m", "hc", "-f"])
    out, err = io.StringIO(), io.StringIO()
    code = tronitor.run(args, stdin=io.StringIO("y\n"), stdout=out, stderr=err, env=os.environ, interactive=True)
    assert code == 3
    assert err.getvalue() == (
        f"tronitor: Unpausing Filesystem Backup (UUID {HC_UUID_FILESYSTEM})... failed: HTTP 500: server error\n"
    )
    assert f"Unpausing Database Backup (UUID {HC_UUID_DATABASE})... done" in out.getvalue()
    assert [p.name for p in locks.iterdir()] == [f"{HC_UUID_FILESYSTEM}.lock"]


def test_reset_follows_supports_reset(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reset action follows the provider's supports_reset flag."""
    assert tronitor.Provider.supports_reset is False
    assert tronitor.HealthchecksProvider.supports_reset is False
    reset: list[str] = []

    def fake_reset(self: tronitor.HealthchecksProvider, monitor: tronitor.Monitor) -> None:
        reset.append(monitor.id)

    monkeypatch.setattr(tronitor.HealthchecksProvider, "supports_reset", True)
    monkeypatch.setattr(tronitor.HealthchecksProvider, "reset", fake_reset)
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-r", "Database Backup", "--yes"]) == 0
    assert capsys.readouterr().out == "Resetting Database Backup... done\n"
    assert reset == [HC_UUID_DATABASE]


def test_prompt_at_end_of_input_means_no(hc_env: Path, fake_server: FakeServer) -> None:
    """A prompt that meets the end of input is a no."""
    serve_checks(fake_server)
    args = tronitor.build_parser().parse_args(["-m", "hc", "-d", "all"])
    out = io.StringIO()
    code = tronitor.run(args, stdin=io.StringIO(""), stdout=out, stderr=io.StringIO(), env=os.environ, interactive=True)
    assert code == 0
    assert out.getvalue().endswith("Cancelled.\n")
    assert deletes(fake_server) == []


@pytest.fixture
def ur_env(ur_config_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point TRONITOR_CONFIG at the UptimeRobot config, set NO_COLOR and clear other TRONITOR_ variables."""
    for name in list(os.environ):
        if name.startswith("TRONITOR_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("TRONITOR_CONFIG", str(ur_config_file))
    monkeypatch.setenv("NO_COLOR", "1")
    return ur_config_file


def test_ur_list_maps_fields_and_statuses(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """list_monitors maps id, friendlyName and status, and sends the bearer token."""
    serve_monitors(fake_server)
    monitors = ur_provider.list_monitors()
    assert [(m.id, m.name, m.status) for m in monitors] == [
        ("1001", "Plex", "up"),
        ("1002", "Sonarr", "paused"),
        ("1003", "Radarr", "seems down"),
    ]
    assert monitors[0].raw == ur_fixture_monitors()[0]
    assert all(m.slug == "" for m in monitors)
    assert fake_server.requests[0].headers["Authorization"] == "Bearer ur-test-key"
    assert fake_server.requests[0].query == {"limit": ["200"]}


def test_ur_unknown_status_is_lowercased(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """An unmapped status is shown in lower case."""
    serve_monitors(fake_server, [{"id": 1, "friendlyName": "X", "status": "WEIRD"}])
    assert ur_provider.list_monitors()[0].status == "weird"


@pytest.mark.parametrize(
    "body",
    [
        ["nope"],
        {"nextLink": None},
        {"nextLink": None, "data": [1]},
        {"nextLink": None, "data": [{"friendlyName": "X", "status": "UP"}]},
        {"nextLink": None, "data": [{"id": 1, "status": "UP"}]},
        {"nextLink": None, "data": [{"id": 1, "friendlyName": "X"}]},
    ],
)
def test_ur_list_rejects_bad_shapes(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer, body: object
) -> None:
    """A list response of the wrong shape, or a monitor without id, name or status, is a ProviderError."""
    fake_server.add("GET", "/monitors", 200, body)
    with pytest.raises(tronitor.ProviderError, match="unexpected response from UptimeRobot"):
        ur_provider.list_monitors()


@pytest.mark.parametrize(
    "change",
    [{"friendlyName": {"a": 1}}, {"friendlyName": ["Plex"]}, {"status": ["UP"]}, {"id": {"x": 1}}],
    ids=["dict name", "list name", "list status", "dict id"],
)
def test_ur_monitor_with_a_non_scalar_field_is_unexpected(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer, change: dict[str, object]
) -> None:
    """An id, name or status that is a list or an object, not a string or a number, is a ProviderError."""
    serve_monitors(fake_server, [{**ur_fixture_monitors()[0], **change}])
    with pytest.raises(tronitor.ProviderError, match=r"^unexpected response from UptimeRobot$"):
        ur_provider.list_monitors()


@pytest.mark.parametrize("monitor_id", ["abc", "../1001", "1001/x", -1, 1.5, True, "", "١٢"])
def test_ur_monitor_with_an_id_that_is_not_a_number_is_unexpected(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer, monitor_id: object
) -> None:
    """An id that is not a plain number is refused, so it never reaches a request path."""
    serve_monitors(fake_server, [{**ur_fixture_monitors()[0], "id": monitor_id}])
    with pytest.raises(tronitor.ProviderError, match=r"^unexpected response from UptimeRobot$"):
        ur_provider.list_monitors()


def test_unknown_statuses_lists_each_unknown_status_once() -> None:
    """unknown_statuses gives (raw, shown) for each raw status that UR_STATUS lacks, once, in order."""
    monitors = [
        tronitor.Monitor("1", "a", "weird", {"status": "WEIRD"}),
        tronitor.Monitor("2", "b", "up", {"status": "UP"}),
        tronitor.Monitor("3", "c", "weird", {"status": "WEIRD"}),
        tronitor.Monitor("4", "d", "odd", {"status": "Odd"}),
        tronitor.Monitor("5", "e", "paused", {"status": "paused"}),
        tronitor.Monitor("6", "f", "up", {}),
    ]
    assert tronitor.unknown_statuses(monitors) == [("WEIRD", "weird"), ("Odd", "odd")]


def test_ur_list_follows_next_link_url(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """A nextLink that is a URL is requested as given."""
    monitors = ur_fixture_monitors()
    link = fake_server.url + "/monitors?cursor=2"
    fake_server.add("GET", "/monitors", 200, {"nextLink": link, "data": monitors[:2]}, once=True)
    fake_server.add("GET", "/monitors", 200, {"nextLink": None, "data": monitors[2:]})
    assert [m.id for m in ur_provider.list_monitors()] == ["1001", "1002", "1003"]
    gets = fake_server.requests_for("GET", "/monitors")
    assert len(gets) == 2
    assert gets[1].query == {"cursor": ["2"]}


def test_ur_list_follows_next_link_cursor_value(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer
) -> None:
    """A nextLink that is a bare cursor is sent as the cursor query parameter."""
    monitors = ur_fixture_monitors()
    fake_server.add("GET", "/monitors", 200, {"nextLink": "2", "data": monitors[:1]}, once=True)
    fake_server.add("GET", "/monitors", 200, {"nextLink": "", "data": monitors[1:]})
    assert [m.id for m in ur_provider.list_monitors()] == ["1001", "1002", "1003"]
    gets = fake_server.requests_for("GET", "/monitors")
    assert [g.query for g in gets] == [{"limit": ["200"]}, {"limit": ["200"], "cursor": ["2"]}]


def test_ur_list_stops_after_100_pages(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """A nextLink that never ends is cut off with a ProviderError."""
    fake_server.add("GET", "/monitors", 200, {"nextLink": "2", "data": []})
    with pytest.raises(tronitor.ProviderError, match="UptimeRobot returned more than 100 pages of monitors"):
        ur_provider.list_monitors()
    assert len(fake_server.requests_for("GET", "/monitors")) == 100


def test_ur_pause_start_reset_delete_paths_and_bodies(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer
) -> None:
    """pause, unpause, reset and delete use the documented paths, methods and JSON bodies."""
    monitor = tronitor.Monitor("1001", "Plex", "up", {})
    fake_server.add("POST", "/monitors/1001/pause", 201, ur_fixture_monitors()[0])
    fake_server.add("POST", "/monitors/1001/start", 201, ur_fixture_monitors()[0])
    fake_server.add("POST", "/monitors/1001/reset", 201)
    fake_server.add("DELETE", "/monitors/1001", 200)
    ur_provider.pause(monitor)
    ur_provider.unpause(monitor)
    ur_provider.reset(monitor)
    ur_provider.delete(monitor)
    assert [(r.method, r.path) for r in fake_server.requests] == [
        ("POST", "/monitors/1001/pause"),
        ("POST", "/monitors/1001/start"),
        ("POST", "/monitors/1001/reset"),
        ("DELETE", "/monitors/1001"),
    ]
    for request in fake_server.requests[:3]:
        assert request.body == {}
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Authorization"] == "Bearer ur-test-key"


def ur_provider_with_sleeps(fake_server: FakeServer) -> tuple[tronitor.UptimeRobotProvider, list[float]]:
    """Return an UptimeRobot provider on the fake server whose waits are recorded instead of slept."""
    sleeps: list[float] = []
    config = tronitor.UptimeRobotConfig("ur-test-key", fake_server.url)
    return tronitor.UptimeRobotProvider(tronitor.Http(sleep=sleeps.append), config), sleeps


def test_ur_pause_waits_and_retries_after_a_429(fake_server: FakeServer) -> None:
    """A pause that gets a 429 waits for Retry-After, is sent again, and succeeds."""
    provider, sleeps = ur_provider_with_sleeps(fake_server)
    fake_server.add(
        "POST", "/monitors/1001/pause", 429, {"message": "Too Many Requests"}, once=True, headers={"Retry-After": "7"}
    )
    fake_server.add("POST", "/monitors/1001/pause", 201, ur_fixture_monitors()[0])
    provider.pause(tronitor.Monitor("1001", "Plex", "up", {}))
    assert sleeps == [7]
    assert len(fake_server.requests_for("POST", "/monitors/1001/pause")) == 2


UR_CALLS: list[tuple[str, str, int, object, Callable[[tronitor.UptimeRobotProvider], object]]] = [
    ("GET", "/monitors", 200, {"nextLink": None, "data": []}, lambda p: p.list_monitors()),
    ("POST", "/monitors/1001/pause", 201, {}, lambda p: p.pause(UR_PLEX)),
    ("POST", "/monitors/1001/start", 201, {}, lambda p: p.unpause(UR_PLEX)),
    ("POST", "/monitors/1001/reset", 201, None, lambda p: p.reset(UR_PLEX)),
    ("DELETE", "/monitors/1001", 200, None, lambda p: p.delete(UR_PLEX)),
    ("GET", "/monitors/1001", 200, {"id": 1001}, lambda p: p.info(UR_PLEX)),
    ("GET", "/user/me", 200, {"email": "a@example.com"}, lambda p: p.stats()),
    ("GET", "/user/alert-contacts", 200, [], lambda p: p.alert_contacts()),
    ("POST", "/monitors", 201, {"id": 1}, lambda p: p.create({})),
]
UR_PLEX = tronitor.Monitor("1001", "Plex", "up", {})


@pytest.mark.parametrize(
    ("method", "path", "status", "body", "call"), UR_CALLS, ids=[c[1] + " " + c[0] for c in UR_CALLS]
)
def test_every_ur_request_retries_after_a_429(
    fake_server: FakeServer,
    method: str,
    path: str,
    status: int,
    body: object,
    call: Callable[[tronitor.UptimeRobotProvider], object],
) -> None:
    """Every UptimeRobot request, not only pause, waits and retries once after a 429."""
    provider, sleeps = ur_provider_with_sleeps(fake_server)
    fake_server.add(method, path, 429, headers={"Retry-After": "1"}, once=True)
    fake_server.add(method, path, status, body)
    call(provider)
    assert sleeps == [1]
    assert len(fake_server.requests_for(method, path)) == 2


def test_hc_does_not_retry_a_429(fake_server: FakeServer) -> None:
    """Healthchecks allows about 100 requests a minute, so a 429 from it is an error at once."""
    sleeps: list[float] = []
    config = tronitor.HealthchecksConfig(fake_server.url, "hc-test-key")
    provider = tronitor.HealthchecksProvider(tronitor.Http(sleep=sleeps.append), config)
    fake_server.add("POST", DB_PAUSE, 429, headers={"Retry-After": "1"}, once=True)
    fake_server.add("POST", DB_PAUSE, 200, {})
    with pytest.raises(tronitor.ProviderError) as e:
        provider.pause(tronitor.Monitor(HC_UUID_DATABASE, "Database Backup", "paused", {}))
    assert e.value.status == 429
    assert sleeps == [] and len(fake_server.requests_for("POST", DB_PAUSE)) == 1


def test_ur_info_stats_alerts_create(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """info, stats, alert_contacts and create hit the right paths and return the records."""
    monitor = tronitor.Monitor("1001", "Plex", "up", {})
    record = ur_fixture_monitors()[0]
    me = {"email": "a@example.com", "monitorsCount": 3, "monitorLimit": 50}
    contacts = [{"id": 7, "friendlyName": "Me", "type": "EMAIL", "value": "a@example.com", "status": "ACTIVE"}]
    payload = {"friendlyName": "New", "url": "https://new.example.com", "type": "HTTP", "interval": 300, "timeout": 30}
    fake_server.add("GET", "/monitors/1001", 200, record)
    fake_server.add("GET", "/user/me", 200, me)
    fake_server.add("GET", "/user/alert-contacts", 200, contacts)
    fake_server.add("POST", "/monitors", 201, record)
    assert ur_provider.info(monitor) == record
    assert ur_provider.stats() == me
    assert ur_provider.alert_contacts() == contacts
    assert ur_provider.create(payload) == record
    assert fake_server.requests_for("POST", "/monitors")[0].body == payload


def test_ur_unexpected_shapes_are_provider_errors(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer
) -> None:
    """Every response shape is guarded."""
    monitor = tronitor.Monitor("1001", "Plex", "up", {})
    fake_server.add("GET", "/monitors/1001", 200, [])
    fake_server.add("GET", "/user/me", 200, [])
    fake_server.add("GET", "/user/alert-contacts", 200, [1])
    fake_server.add("POST", "/monitors", 201)
    for call in (
        lambda: ur_provider.info(monitor),
        ur_provider.stats,
        ur_provider.alert_contacts,
        lambda: ur_provider.create({}),
    ):
        with pytest.raises(tronitor.ProviderError, match="unexpected response from UptimeRobot"):
            call()


def test_ur_alert_contacts_must_be_a_list(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """An alert-contacts response that is an object, not a list, is a ProviderError."""
    fake_server.add("GET", "/user/alert-contacts", 200, {"a": 1})
    with pytest.raises(tronitor.ProviderError, match="unexpected response from UptimeRobot"):
        ur_provider.alert_contacts()


def test_ur_list_rejects_a_next_link_on_another_host(
    ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer
) -> None:
    """A full-URL nextLink on another host is refused so the API key is never sent there."""
    fake_server.add("GET", "/monitors", 200, {"nextLink": "https://evil.example/monitors", "data": []})
    with pytest.raises(tronitor.ProviderError, match="UptimeRobot returned a pagination link on another host"):
        ur_provider.list_monitors()
    assert len(fake_server.requests) == 1


def test_ur_list_rejects_a_look_alike_host(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """A link that merely starts with the base URL text, such as a longer host name, is refused."""
    fake_server.add("GET", "/monitors", 200, {"nextLink": fake_server.url + ".evil.example/monitors", "data": []})
    with pytest.raises(tronitor.ProviderError, match="another host"):
        ur_provider.list_monitors()


def test_ur_list_encodes_the_cursor(ur_provider: tronitor.UptimeRobotProvider, fake_server: FakeServer) -> None:
    """A bare cursor is percent-encoded, so it arrives as one query value."""
    fake_server.add("GET", "/monitors", 200, {"nextLink": "a b&c", "data": []}, once=True)
    fake_server.add("GET", "/monitors", 200, {"nextLink": None, "data": []})
    ur_provider.list_monitors()
    assert fake_server.requests_for("GET", "/monitors")[1].query == {"limit": ["200"], "cursor": ["a b&c"]}


def test_ur_class_attributes_and_is_id() -> None:
    """The provider describes itself and recognises numeric IDs."""
    provider = tronitor.UptimeRobotProvider
    assert (provider.label, provider.id_kind) == ("UptimeRobot", "ID")
    assert provider.supports_reset is True and provider.supports_lock_files is False
    assert provider.unpause_only_paused is False
    assert tronitor.Provider.unpause_only_paused is True
    assert tronitor.HealthchecksProvider.unpause_only_paused is True
    assert provider.is_id("1001") and not provider.is_id("Plex") and not provider.is_id("")
    assert not provider.is_id("٣")


def test_ur_reset_via_cli_with_yes(ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """-r with --yes resets the named monitor."""
    serve_monitors(fake_server)
    fake_server.add("POST", "/monitors/1001/reset", 201)
    assert tronitor.main(["-m", "ur", "-r", "Plex", "--yes"]) == 0
    assert capsys.readouterr().out == "Resetting Plex... done\n"
    assert len(fake_server.requests_for("POST", "/monitors/1001/reset")) == 1


def test_ur_stats_via_cli(ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """-s prints the account record as JSON."""
    fake_server.add("GET", "/user/me", 200, {"email": "a@example.com", "monitorsCount": 3})
    assert tronitor.main(["-m", "ur", "-s"]) == 0
    assert json.loads(capsys.readouterr().out) == {"email": "a@example.com", "monitorsCount": 3}


def test_ur_pause_has_no_lock_files(ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """Pausing an UptimeRobot monitor creates no lock directory."""
    serve_monitors(fake_server)
    fake_server.add("POST", "/monitors/1001/pause", 201, ur_fixture_monitors()[0])
    assert tronitor.main(["-m", "ur", "-p", "Plex"]) == 0
    assert len(fake_server.requests_for("POST", "/monitors/1001/pause")) == 1
    assert not (ur_env.parent / "locks").exists()
    assert "lock" not in capsys.readouterr().out.lower()


def test_ur_unpause_starts_every_selected_monitor(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """UptimeRobot's list can show an old status, so -u starts each selected monitor, whatever the list says."""
    serve_monitors(fake_server)
    fake_server.add("POST", "/monitors/1001/start", 201, ur_fixture_monitors()[0])
    fake_server.add("POST", "/monitors/1002/start", 201, ur_fixture_monitors()[1])
    assert tronitor.main(["-m", "ur", "-u", "Plex,Sonarr"]) == 0
    assert capsys.readouterr().out == "Unpausing Plex (ID 1001)... done\nUnpausing Sonarr (ID 1002)... done\n"
    assert len(fake_server.requests_for("POST", "/monitors/1001/start")) == 1
    assert len(fake_server.requests_for("POST", "/monitors/1002/start")) == 1


def test_ur_unpause_all_starts_every_monitor(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-u all on UptimeRobot starts every monitor and prints no "is already running" line."""
    serve_monitors(fake_server)
    for monitor_id in (1001, 1002, 1003):
        fake_server.add("POST", f"/monitors/{monitor_id}/start", 201, {})
    assert tronitor.main(["-m", "ur", "-u", "all"]) == 0
    out = capsys.readouterr().out
    assert "already running" not in out and out.count("... done") == 3
    assert [r.path for r in fake_server.requests if r.method == "POST"] == [
        "/monitors/1001/start",
        "/monitors/1002/start",
        "/monitors/1003/start",
    ]


UNKNOWN_STATUS_WARNING = "tronitor: UptimeRobot returned a status tronitor does not know: 'WEIRD'; treated as 'weird'\n"


@pytest.mark.parametrize("action", ["-l", "-n", "-f"])
def test_ur_unknown_status_is_reported_once_on_stderr(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], action: str
) -> None:
    """-l, -n and -f name each status that tronitor does not know, once, and still exit 0."""
    monitors = [*ur_fixture_monitors(), {**ur_fixture_monitors()[0], "id": 1004, "status": "WEIRD"}]
    serve_monitors(fake_server, [*monitors, {**monitors[3], "id": 1005}])
    assert tronitor.main(["-m", "ur", action]) == 0
    assert capsys.readouterr().err == UNKNOWN_STATUS_WARNING


def test_ur_unknown_status_with_a_line_break_stays_on_one_line(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A control character in an unknown status becomes "?", so the warning is one line."""
    serve_monitors(fake_server, [{**ur_fixture_monitors()[0], "status": "BAD\nLINE\x1b[2J"}])
    assert tronitor.main(["-m", "ur", "-l"]) == 0
    err = capsys.readouterr().err
    assert (
        err
        == "tronitor: UptimeRobot returned a status tronitor does not know: 'BAD?LINE?[2J'; treated as 'bad?line?[2j'\n"
    )


def test_hc_statuses_are_never_reported_as_unknown(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """The warning is for UptimeRobot only: Healthchecks statuses such as grace are not in its table."""
    checks = hc_fixture_checks()
    checks[0]["status"] = "grace"
    serve_checks(fake_server, checks)
    assert tronitor.main(["-m", "hc", "-l"]) == 0
    assert capsys.readouterr().err == ""


def test_missing_uptimerobot_key_is_exit_2(hc_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A config without UptimeRobot settings is a usage error that says how to fix it."""
    assert tronitor.main(["--provider", "UR", "-l"]) == 2
    assert capsys.readouterr().err == (
        "tronitor: no UptimeRobot API key: set [uptimerobot] api_key in the config or TRONITOR_UPTIMEROBOT_API_KEY\n"
    )


def test_config_rejects_unknown_uptimerobot_key_but_accepts_base_url(tmp_path: Path) -> None:
    """An unknown [uptimerobot] key is an error; base_url is accepted."""
    path = write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\nbase_url = "http://x.test"\nbogus = 1\n')
    with pytest.raises(tronitor.ConfigError, match=r"unknown key 'uptimerobot.bogus'"):
        tronitor.load_config(path, {}, [])
    path = write_toml(tmp_path, '[uptimerobot]\napi_key = "k"\nbase_url = "http://x.test"\n')
    assert tronitor.load_config(path, {}, []).uptimerobot == tronitor.UptimeRobotConfig("k", "http://x.test")


PAUSED_MONITORS = [tronitor.Monitor("id-1", "Plex", "paused", {}), tronitor.Monitor("id-2", "Sonarr", "paused", {})]


def test_discord_payload_lists_paused_monitors() -> None:
    """Discord gets one embed with a field per paused monitor."""
    payload = tronitor.build_webhook_payload("UptimeRobot", PAUSED_MONITORS, "ID", "discord", False)
    assert payload == {
        "embeds": [
            {
                "title": "There are currently paused UptimeRobot monitors:",
                "color": 3381759,
                "fields": [
                    {"name": "Plex", "value": "ID: id-1"},
                    {"name": "Sonarr", "value": "ID: id-2"},
                ],
            }
        ]
    }


def test_discord_payload_notify_all_when_none_paused() -> None:
    """With nothing paused and notify_all, Discord gets the all-running embed."""
    assert tronitor.build_webhook_payload("Healthchecks", [], "UUID", "discord", True) == {
        "embeds": [{"title": "All Healthchecks monitors are currently running.", "color": 10092339}]
    }


def test_no_payload_when_none_paused_and_not_notify_all() -> None:
    """Nothing paused and no notify_all means there is nothing to send, in either format."""
    assert tronitor.build_webhook_payload("Healthchecks", [], "UUID", "discord", False) is None
    assert tronitor.build_webhook_payload("Healthchecks", [], "UUID", "slack", False) is None


def test_slack_payload_text() -> None:
    """Slack gets one text message with a bullet per paused monitor, or the all-running line."""
    assert tronitor.build_webhook_payload("UptimeRobot", PAUSED_MONITORS, "ID", "slack", False) == {
        "text": "There are currently paused UptimeRobot monitors:\n• Plex (ID id-1)\n• Sonarr (ID id-2)"
    }
    assert tronitor.build_webhook_payload("UptimeRobot", [], "ID", "slack", True) == {
        "text": "All UptimeRobot monitors are currently running."
    }


def test_payload_names_have_control_characters_replaced() -> None:
    """A control character in a monitor name is replaced in both formats."""
    monitors = [tronitor.Monitor("id-1", "Bad\x1b[2Jname", "paused", {})]
    discord = tronitor.build_webhook_payload("X", monitors, "ID", "discord", False)
    slack = tronitor.build_webhook_payload("X", monitors, "ID", "slack", False)
    assert discord is not None and discord["embeds"][0]["fields"][0]["name"] == "Bad?[2Jname"
    assert slack is not None and "Bad?[2Jname (ID id-1)" in slack["text"]


def test_discord_payload_caps_fields_at_25() -> None:
    """More than 25 paused monitors give 24 fields and a last field that counts the rest."""
    monitors = [tronitor.Monitor(f"id-{n}", f"M{n}", "paused", {}) for n in range(30)]
    payload = tronitor.build_webhook_payload("X", monitors, "ID", "discord", False)
    assert payload is not None
    fields = payload["embeds"][0]["fields"]
    assert len(fields) == 25
    assert fields[23] == {"name": "M23", "value": "ID: id-23"}
    assert fields[24] == {"name": "...", "value": "and 6 more"}
    exactly_25 = tronitor.build_webhook_payload("X", monitors[:25], "ID", "discord", False)
    assert exactly_25 is not None and len(exactly_25["embeds"][0]["fields"]) == 25
    assert exactly_25["embeds"][0]["fields"][24]["name"] == "M24"


def test_send_notification_posts_and_returns_true(fake_server: FakeServer) -> None:
    """The payload is POSTed as JSON to the webhook URL and True is returned."""
    fake_server.add("POST", "/hook", 204)
    config = tronitor.NotifyConfig(fake_server.url + "/hook", "discord", False)
    assert tronitor.send_notification(tronitor.Http(), config, "UptimeRobot", PAUSED_MONITORS, "ID") is True
    expected = tronitor.build_webhook_payload("UptimeRobot", PAUSED_MONITORS, "ID", "discord", False)
    assert [r.body for r in fake_server.requests_for("POST", "/hook")] == [expected]


def test_send_notification_accepts_slacks_plain_ok(fake_server: FakeServer) -> None:
    """Slack answers 200 with the plain text ok, which counts as success."""
    fake_server.add("POST", "/hook", 200, "ok")
    config = tronitor.NotifyConfig(fake_server.url + "/hook", "slack", False)
    assert tronitor.send_notification(tronitor.Http(), config, "UptimeRobot", PAUSED_MONITORS, "ID") is True


def test_send_notification_returns_false_when_nothing_to_send(fake_server: FakeServer) -> None:
    """No payload means no request and False."""
    config = tronitor.NotifyConfig(fake_server.url + "/hook", "discord", False)
    assert tronitor.send_notification(tronitor.Http(), config, "UptimeRobot", [], "ID") is False
    assert fake_server.requests == []


def test_send_notification_without_a_url_is_a_config_error() -> None:
    """An empty webhook URL is a ConfigError that says how to set it."""
    message = r"no webhook URL: set \[notify\] webhook_url or TRONITOR_WEBHOOK_URL"
    with pytest.raises(tronitor.ConfigError, match=message):
        tronitor.send_notification(tronitor.Http(), tronitor.NotifyConfig(), "X", PAUSED_MONITORS, "ID")


def test_webhook_via_cli_w(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-w lists the paused checks, posts them to the webhook and says so."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 204)
    assert tronitor.main(["-m", "hc", "-w"]) == 0
    out, err = capsys.readouterr()
    assert out.splitlines()[-1] == "Notification sent."
    assert err == ""
    [request] = fake_server.requests_for("POST", "/hook")
    assert request.body["embeds"][0]["fields"] == [{"name": "Database Backup", "value": f"UUID: {HC_UUID_DATABASE}"}]


def test_webhook_via_cli_slack_format(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """format = slack posts the text form and accepts Slack's plain ok."""
    with hc_config_file_with_webhook.open("a", encoding="utf-8") as handle:
        handle.write('format = "slack"\n')
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 200, "ok")
    assert tronitor.main(["-m", "hc", "-w"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Notification sent."
    [request] = fake_server.requests_for("POST", "/hook")
    assert request.body == {
        "text": f"There are currently paused Healthchecks monitors:\n• Database Backup (UUID {HC_UUID_DATABASE})"
    }


def test_webhook_nothing_paused_sends_nothing(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """With nothing paused and notify_all off, -w prints Nothing to notify. and posts nothing."""
    serve_checks(fake_server, hc_fixture_checks()[:1])
    assert tronitor.main(["-m", "hc", "-w"]) == 0
    assert capsys.readouterr().out.splitlines() == ["No Healthchecks monitors are paused.", "Nothing to notify."]
    assert fake_server.requests_for("POST", "/hook") == []


def test_webhook_notify_all_sends_all_running(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """With notify_all on and nothing paused, -w posts the all-running message."""
    with hc_config_file_with_webhook.open("a", encoding="utf-8") as handle:
        handle.write("notify_all = true\n")
    serve_checks(fake_server, hc_fixture_checks()[:1])
    fake_server.add("POST", "/hook", 204)
    assert tronitor.main(["-m", "hc", "-w"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Notification sent."
    [request] = fake_server.requests_for("POST", "/hook")
    assert request.body["embeds"][0]["title"] == "All Healthchecks monitors are currently running."


def test_webhook_missing_url_is_exit_2(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-w without a webhook URL is a usage error that says how to set one."""
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-w"]) == 2
    assert capsys.readouterr().err == "tronitor: no webhook URL: set [notify] webhook_url or TRONITOR_WEBHOOK_URL\n"


def test_webhook_failure_is_exit_1(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A webhook that answers 500 is reported as a webhook error with exit 1."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 500, "boom")
    assert tronitor.main(["-m", "hc", "-w"]) == 1
    assert capsys.readouterr().err == "tronitor: webhook: HTTP 500: boom\n"


def test_webhook_failure_message_has_no_url(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure message never contains the webhook URL or its path."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 500)
    assert tronitor.main(["-m", "hc", "-w"]) == 1
    err = capsys.readouterr().err
    assert "tronitor: webhook: HTTP 500" in err
    assert "/hook" not in err and fake_server.url not in err


def test_webhook_verbose_logs_a_label_not_the_url(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--verbose names the webhook request by a label, never by its URL."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 204)
    assert tronitor.main(["-m", "hc", "-w", "--verbose"]) == 0
    err = capsys.readouterr().err
    assert "POST webhook" in err
    assert "/hook" not in err


def test_discord_payload_handles_empty_and_long_names() -> None:
    """Empty names become (unnamed); names are cut to 256 characters and values to 1024."""
    monitors = [tronitor.Monitor("i" * 2000, "", "paused", {}), tronitor.Monitor("id-2", "n" * 300, "paused", {})]
    payload = tronitor.build_webhook_payload("X", monitors, "ID", "discord", False)
    assert payload is not None
    first, second = payload["embeds"][0]["fields"]
    assert first["name"] == "(unnamed)" and len(first["value"]) == 1024
    assert second["name"] == "n" * 256


def test_webhook_malformed_url_is_not_echoed(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed webhook URL is reported without its text."""
    text = hc_config_file_with_webhook.read_text(encoding="utf-8")
    hc_config_file_with_webhook.write_text(text.replace(f'"{fake_server.url}/hook"', '"http://[::1"'), encoding="utf-8")
    serve_checks(fake_server)
    assert tronitor.main(["-m", "hc", "-w"]) == 1
    err = capsys.readouterr().err
    assert "tronitor: webhook: unsupported URL for webhook" in err
    assert "[::1" not in err


def test_find_json_with_webhook_keeps_stdout_pure(
    hc_env: Path, hc_config_file_with_webhook: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """With --json, the notification line goes to stderr so stdout stays valid JSON."""
    serve_checks(fake_server)
    fake_server.add("POST", "/hook", 204)
    assert tronitor.main(["-m", "hc", "-w", "--json"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == [hc_fixture_checks()[1]]
    assert "Notification sent." in err


POSIX = sys.platform != "win32"
"""True on Linux and macOS, where --migrate makes tronitor.toml readable only by its owner."""
WEBHOOK = "https://discord.com/api/webhooks/1/secret-token"
"""A webhook address for the migration tests; its token must never reach the output."""


@pytest.fixture
def no_tronitor_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear the TRONITOR_ variables and point TRONITOR_CONFIG at a file that does not exist.

    An action that loads a config therefore fails, which shows that --migrate loads none.
    """
    for name in list(os.environ):
        if name.startswith("TRONITOR_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("TRONITOR_CONFIG", str(tmp_path / "missing.toml"))


def wrote_line(out: Path) -> str:
    """Return the last line of the migration report for out."""
    return f"Wrote {out} (readable only by you)" if POSIX else f"Wrote {out}"


def test_migrate_writes_the_config(no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The keys, the server, the webhook and notify_all are carried over; the report shows no key or URL."""
    script = bash_fixture(
        tmp_path,
        hcApiKey="hc-secret-key",
        healthchecksDomain="hc.example.com",
        urApiKey="ur-secret-key",
        webhookUrl=WEBHOOK,
        notifyAll="TRUE",
    )
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = tmp_path / "tronitor.toml"
    assert tronitor.load_config(out, {}, []) == tronitor.Config(
        lock_dir=tronitor.default_lock_dir(),
        healthchecks=tronitor.HealthchecksConfig("https://hc.example.com", "hc-secret-key"),
        uptimerobot=tronitor.UptimeRobotConfig("ur-secret-key"),
        notify=tronitor.NotifyConfig(WEBHOOK, "discord", True),
    )
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"Read {script}",
        "Carried over: Healthchecks API key",
        "Carried over: Healthchecks server https://hc.example.com",
        "Carried over: UptimeRobot API key",
        "Carried over: webhook URL",
        "Carried over: notify_all = true",
        (
            "Note: the lock folder is now /tmp by default (your TEMP folder on Windows); "
            "the Bash script used $HOME/tronitor/. See docs/cron.md."
        ),
        "Note: if HealthChecks-Linux reads its lock files from another folder, set lock_dir in tronitor.toml.",
        wrote_line(out),
    ]
    assert captured.err == ""
    for secret in ("hc-secret-key", "ur-secret-key", "secret-token"):
        assert secret not in captured.out + captured.err
    if POSIX:
        assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_migrate_reports_dropped_providers(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """StatusCake, Upptime and jq settings are dropped with a line each, and leave no trace in the TOML."""
    script = bash_fixture(
        tmp_path,
        scApiKey="sc-secret-key",
        scUsername="sc-user",
        ghToken="gh-secret-token",
        repoOwner="someone",
        upptimeRepo="status-page",
        jq="false",
    )
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = capsys.readouterr().out
    assert "Dropped: StatusCake API key and username (StatusCake is no longer supported)" in out
    assert "Dropped: Upptime settings (Upptime is no longer supported)" in out
    assert "Dropped: the jq setting (no longer used)" in out
    assert "Carried over: nothing; the script has no API key, webhook URL or other setting to copy" in out
    assert "sc-secret-key" not in out and "gh-secret-token" not in out
    toml = (tmp_path / "tronitor.toml").read_text(encoding="utf-8")
    for trace in ("sc-secret-key", "sc-user", "gh-secret-token", "someone", "status-page", "jq"):
        assert trace not in toml
    assert "statuscake" not in toml.lower() and "upptime" not in toml.lower()


def test_migrate_does_not_report_the_shipped_values(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A setting left at the value the Bash script shipped with is neither carried over nor dropped."""
    script = bash_fixture(tmp_path, urApiKey="ur-secret-key")
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = capsys.readouterr().out
    assert "Carried over: UptimeRobot API key" in out
    assert "Dropped" not in out
    assert "Healthchecks server" not in out and "notify_all" not in out


def test_migrate_notes_the_lock_folder(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tempDir of the Bash script, below the header, gives the note about the lock folder."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key", tempDir="/tmp/tronitor/")  # nosec B108
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = capsys.readouterr().out
    assert (
        "Note: the lock folder is now /tmp by default (your TEMP folder on Windows); "
        "the Bash script used /tmp/tronitor/. See docs/cron.md."
    ) in out
    assert tronitor.load_config(tmp_path / "tronitor.toml", {}, []).lock_dir == tronitor.default_lock_dir()


def test_migrate_without_temp_dir_gives_no_note(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file without a tempDir line, and so without the marker line, is read whole and gives no note."""
    script = tmp_path / "tronitor.sh"
    script.write_text("urApiKey='ur-secret-key'\n", encoding="utf-8")
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = capsys.readouterr().out
    assert "Carried over: UptimeRobot API key" in out
    assert "Note:" not in out


def test_migrate_refuses_to_overwrite(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing tronitor.toml stays as it is without --yes, with exit 2."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")
    out = tmp_path / "tronitor.toml"
    out.write_text("# my settings\n", encoding="utf-8")
    assert tronitor.main(["--migrate", str(script)]) == 2
    captured = capsys.readouterr()
    assert captured.err == f"tronitor: {out} already exists; pass --yes to overwrite it\n"
    assert captured.out == ""
    assert out.read_text(encoding="utf-8") == "# my settings\n"


def test_migrate_overwrites_with_yes(no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """With --yes, an existing tronitor.toml is replaced."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")
    out = tmp_path / "tronitor.toml"
    out.write_text("# my settings\n", encoding="utf-8")
    assert tronitor.main(["--migrate", str(script), "--yes"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == wrote_line(out)
    config = tronitor.load_config(out, {}, [])
    assert config.healthchecks == tronitor.HealthchecksConfig("https://healthchecks.io", "hc-secret-key")
    if POSIX:
        assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_migrate_rejects_a_file_that_is_not_tronitor_sh(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file without a urApiKey or hcApiKey line in its header is refused with exit 2, and nothing is written."""
    other = tmp_path / "backup.sh"
    other.write_text("#!/usr/bin/env bash\n# Declare some variables.\nhcApiKey='after-the-header'\n", encoding="utf-8")
    assert tronitor.main(["--migrate", str(other)]) == 2
    captured = capsys.readouterr()
    assert captured.err == f"tronitor: {other} does not look like a tronitor.sh (no urApiKey or hcApiKey line)\n"
    assert captured.out == ""
    assert not (tmp_path / "tronitor.toml").exists()


def test_migrate_missing_file_is_a_usage_error(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that cannot be read is reported with exit 2."""
    missing = tmp_path / "tronitor.sh"
    assert tronitor.main(["--migrate", str(missing)]) == 2
    assert capsys.readouterr().err.startswith(f"tronitor: {missing}: cannot read the file: ")
    assert not (tmp_path / "tronitor.toml").exists()


def test_migrate_invalid_value_leaves_no_file(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A webhook URL with a space fails the check of the written file: exit 2, no file, the old one kept."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key", webhookUrl="https://discord.com/api/webhooks/1/a b")
    out = tmp_path / "tronitor.toml"
    assert tronitor.main(["--migrate", str(script)]) == 2
    captured = capsys.readouterr()
    assert captured.err == (
        f"tronitor: the migrated config is not valid: {out}: "
        "notify.webhook_url contains a space or a control character\n"
    )
    assert "a b" not in captured.err and captured.out == ""
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tronitor.sh"]
    out.write_text("# my settings\n", encoding="utf-8")
    assert tronitor.main(["--migrate", str(script), "--yes"]) == 2
    assert out.read_text(encoding="utf-8") == "# my settings\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tronitor.sh", "tronitor.toml"]


def test_migrate_cannot_write_is_reported(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When tronitor.toml cannot be written (here a folder has its name), the error says so and no file is left."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")
    out = tmp_path / "tronitor.toml"
    out.mkdir()
    assert tronitor.main(["--migrate", str(script), "--yes"]) == 2
    assert capsys.readouterr().err.startswith(f"tronitor: cannot write {out}: ")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tronitor.sh", "tronitor.toml"]
    assert out.is_dir()


def test_migrate_needs_no_provider(no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--migrate runs without -m, and without loading a config: TRONITOR_CONFIG names a file that does not exist."""
    script = bash_fixture(tmp_path, urApiKey="ur-secret-key")
    assert tronitor.main(["--migrate", str(script)]) == 0
    assert capsys.readouterr().err == ""
    assert (tmp_path / "tronitor.toml").is_file()


@pytest.mark.parametrize(
    "action",
    [
        ["-l"],
        ["-f"],
        ["-n"],
        ["-w"],
        ["-s"],
        ["-a"],
        ["-i", "x"],
        ["-c", "x.json"],
        ["-p", "all"],
        ["-u", "all"],
        ["-d", "x"],
        ["-r", "x"],
    ],
)
def test_other_actions_still_need_a_provider(
    no_tronitor_env: None, action: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Every action but --migrate needs -m: without it, exit 2 with the message that names the providers."""
    assert tronitor.main(action) == 2
    captured = capsys.readouterr()
    assert captured.err == "tronitor: choose a provider with -m: healthchecks (hc) or uptimerobot (ur)\n"
    assert captured.out == ""


def test_migrate_settings_maps_the_values() -> None:
    """The domain gets https:// unless it has a scheme; notifyAll is true in any case, else false; empty is absent."""
    header = "hcApiKey='k'\nhealthchecksDomain='http://hc.local:8000/'\nnotifyAll='True'\nwebhookUrl=''\n"
    migration = tronitor.migrate_settings(header)
    assert (migration.hc_url, migration.hc_api_key, migration.notify_all) == ("http://hc.local:8000/", "k", True)
    assert migration.webhook_url == "" and "webhook URL" not in migration.carried
    assert tronitor.migrate_settings("urApiKey='k'\nhealthchecksDomain=''\nnotifyAll='yes'\n").hc_url == (
        "https://healthchecks.io"
    )
    assert tronitor.migrate_settings("urApiKey='k'\nnotifyAll='yes'\n").notify_all is False
    assert tronitor.migrate_settings("urApiKey='k'\nhealthchecksDomain='hc.example.com'\n").hc_url == (
        "https://hc.example.com"
    )


def test_migrate_settings_hides_a_password_in_the_server() -> None:
    """The carried-over server line shows no user name or password from the address."""
    migration = tronitor.migrate_settings("hcApiKey='k'\nhealthchecksDomain='https://me:pw@hc.example.com/'\n")
    assert "Healthchecks server https://hc.example.com" in migration.carried
    assert not any("pw" in line for line in migration.carried)


def test_migrate_settings_refuses_other_files() -> None:
    """Text without a urApiKey or hcApiKey line in the header raises ValueError."""
    with pytest.raises(ValueError):
        tronitor.migrate_settings("webhookUrl='https://x'\n")


def test_render_config_matches_the_example() -> None:
    """With nothing migrated, the TOML is the example file but for its first comment line."""
    rendered = tronitor.render_config(tronitor.migrate_settings("urApiKey=''\n")).splitlines()
    example = (ROOT / "tronitor.example.toml").read_text(encoding="utf-8").splitlines()
    assert rendered[1:] == example[1:]
    assert rendered[0].startswith("# ") and "--migrate" in rendered[0]


def test_render_config_writes_valid_toml_strings(tmp_path: Path) -> None:
    """Quotes, backslashes and characters outside ASCII survive the round trip through the TOML file."""
    header = "hcApiKey='a\"b\\\\c'\nurApiKey='café 日本'\n"
    path = tmp_path / "tronitor.toml"
    path.write_text(tronitor.render_config(tronitor.migrate_settings(header)), encoding="utf-8")
    config = tronitor.load_config(path, {}, [])
    assert config.healthchecks is not None and config.healthchecks.api_key == 'a"b\\\\c'
    assert config.uptimerobot is not None and config.uptimerobot.api_key == "café 日本"


def test_migrate_reports_a_line_it_cannot_read(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A known setting whose line is not name='value' (a comment after it, double quotes) is reported as skipped."""
    script = bash_fixture(tmp_path)
    text = script.read_text(encoding="utf-8")
    text = text.replace("urApiKey=''", "urApiKey='ur-key' # my key").replace("hcApiKey=''", 'hcApiKey="hc-key"')
    script.write_text(text, encoding="utf-8")
    assert tronitor.main(["--migrate", str(script)]) == 0
    out = capsys.readouterr().out
    assert "Skipped: hcApiKey (not in the form name='value'; check tronitor.toml)" in out
    assert "Skipped: urApiKey (not in the form name='value'; check tronitor.toml)" in out
    assert out.index("Skipped: hcApiKey") < out.index("Skipped: urApiKey")
    assert "ur-key" not in out and "hc-key" not in out
    toml = (tmp_path / "tronitor.toml").read_text(encoding="utf-8")
    assert "ur-key" not in toml and "hc-key" not in toml
    config = tronitor.load_config(tmp_path / "tronitor.toml", {}, [])
    assert config.uptimerobot is None and config.healthchecks is None


def test_migrate_settings_last_line_decides() -> None:
    """As in Bash, the last line of a name counts: a later line that cannot be read hides an earlier value."""
    migration = tronitor.migrate_settings("urApiKey='first'\nurApiKey='second' # note\n")
    assert migration.ur_api_key == "" and migration.skipped == ("urApiKey",)
    migration = tronitor.migrate_settings("urApiKey='first' # note\nurApiKey='second'\n")
    assert migration.ur_api_key == "second" and migration.skipped == ()


def test_migrate_refuses_config(no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--config with --migrate is a usage error, with exit 2, and nothing is written."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")
    assert tronitor.main(["--migrate", str(script), "--config", str(tmp_path / "other.toml")]) == 2
    captured = capsys.readouterr()
    assert captured.err == "tronitor: --migrate writes tronitor.toml next to the Bash script; --config does not apply\n"
    assert captured.out == ""
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tronitor.sh"]


def test_migrate_treats_a_symlink_as_existing(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tronitor.toml that is a symbolic link, even one to a missing file, is not replaced without --yes."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")
    out = tmp_path / "tronitor.toml"
    try:
        out.symlink_to(tmp_path / "elsewhere.toml")
    except OSError:
        pytest.skip("this system does not let the tests create symbolic links")
    assert tronitor.main(["--migrate", str(script)]) == 2
    assert capsys.readouterr().err == f"tronitor: {out} already exists; pass --yes to overwrite it\n"
    assert out.is_symlink() and not (tmp_path / "elsewhere.toml").exists()


def test_render_config_escapes_del(tmp_path: Path) -> None:
    r"""A DEL character in a value is written as \u007f, so the file still loads and keeps the value."""
    text = tronitor.render_config(tronitor.migrate_settings("hcApiKey='a\x7fb'\n"))
    assert "\x7f" not in text and '"a\\u007fb"' in text
    path = tmp_path / "tronitor.toml"
    path.write_text(text, encoding="utf-8")
    config = tronitor.load_config(path, {}, [])
    assert config.healthchecks is not None and config.healthchecks.api_key == "a\x7fb"


"""Error paths that nothing exercised before the coverage follow-up."""


def test_unknown_top_level_key_without_a_table_gets_no_hint(tmp_path: Path) -> None:
    """An unknown key that no table has is reported without a did-you-mean hint."""
    path = tmp_path / "tronitor.toml"
    path.write_text("bogus = 1", encoding="utf-8")
    with pytest.raises(tronitor.ConfigError) as e:
        tronitor.load_config(path, {}, [])
    assert str(e.value) == f"{path}: unknown key 'bogus'"


def test_lock_dir_with_a_tilde_but_no_home_folder_is_not_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the home folder is unknown, a lock_dir that starts with ~ stays as it is and is refused as relative."""

    def no_home(self: Path) -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "expanduser", no_home)
    path = tmp_path / "tronitor.toml"
    path.write_text("""[general]
lock_dir = "~/locks"
""", encoding="utf-8")
    with pytest.raises(tronitor.ConfigError, match="must be an absolute path"):
        tronitor.load_config(path, {}, [])


def test_http_error_with_a_json_object_without_a_message_shows_the_body(fake_server: FakeServer) -> None:
    """A JSON error body without a message, error or detail field is shown as it is."""
    fake_server.add("GET", "/x", 400, {"code": 7})
    with pytest.raises(tronitor.ProviderError) as e:
        tronitor.Http().request("GET", fake_server.url + "/x")
    assert str(e.value) == 'HTTP 400: {"code": 7}'


def test_http_rejects_an_invalid_ipv6_url() -> None:
    """A URL that urllib cannot even build a request for is an unsupported URL, not a traceback."""
    with pytest.raises(tronitor.ProviderError, match="unsupported URL"):
        tronitor.Http().request("GET", "http://[::1/")


def test_http_times_out_waiting_for_the_response(fake_server: FakeServer) -> None:
    """A server that accepts the connection but answers too slowly is reported as timed out."""
    fake_server.add("GET", "/slow", 200, {}, delay=0.5)
    with pytest.raises(tronitor.ProviderError, match="timed out"):
        tronitor.Http(timeout=0.1).request("GET", fake_server.url + "/slow")


def test_http_times_out_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connection that times out before the request is sent is reported as timed out too."""

    def slow_connect(self: http.client.HTTPConnection) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", slow_connect)
    with pytest.raises(tronitor.ProviderError, match="timed out"):
        tronitor.Http(timeout=0.1).request("GET", "http://127.0.0.1:9/x")


def test_prepare_reports_a_lock_dir_that_cannot_be_created(tmp_path: Path) -> None:
    """A lock folder under a path that is a file cannot be created, and prepare says so."""
    (tmp_path / "file").write_text("x", encoding="utf-8")
    with pytest.raises(tronitor.LockError, match="cannot create"):
        tronitor.LockFiles(tmp_path / "file" / "locks").prepare()


def test_unpause_all_on_an_empty_uptimerobot_account(
    ur_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """-u all with no monitors, on a provider without lock files, has nothing to do and nothing to remove."""
    serve_monitors(fake_server, [])
    assert tronitor.main(["-m", "ur", "-u", "all"]) == 0
    assert "No monitors" in capsys.readouterr().out


def test_create_with_a_file_that_is_not_utf8_is_reported(
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A payload file that is not UTF-8 is reported as unreadable, with exit code 2."""
    path = tmp_path / "bad.json"
    path.write_bytes(bytes([255, 254, 0, 65]))
    assert tronitor.main(["-m", "hc", "-c", str(path)]) == 2
    assert capsys.readouterr().err.startswith(f"tronitor: {path}: cannot read the file: ")


def test_main_works_when_stdout_is_not_a_file(
    hc_env: Path, fake_server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When another program embeds main() with its own stream as stdout, the UTF-8 setup skips that stream."""
    serve_checks(fake_server)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert tronitor.main(["-m", "hc", "-l"]) == 0
    assert "Filesystem Backup" in out.getvalue()


def test_migrate_when_no_temporary_file_can_be_made(
    no_tronitor_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the temporary file itself cannot be created, the error says so and nothing is left behind."""
    script = bash_fixture(tmp_path, hcApiKey="hc-secret-key")

    def no_temp(**kwargs: object) -> tuple[int, str]:
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(tronitor.tempfile, "mkstemp", no_temp)
    assert tronitor.main(["--migrate", str(script)]) == 2
    assert capsys.readouterr().err.strip() == f"tronitor: cannot write {tmp_path / 'tronitor.toml'}: Permission denied"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tronitor.sh"]
