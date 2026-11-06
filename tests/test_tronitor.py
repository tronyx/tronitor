"""Unit tests for the tronitor module."""

import io
import json
import os
import re
import socket
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import HC_UUID_DATABASE, HC_UUID_FILESYSTEM, hc_fixture_checks, serve_checks
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
    assert tronitor.default_lock_dir() == Path("/tmp")
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


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x", "not a url", "http://[::1"])
def test_http_rejects_non_http_urls(url: str) -> None:
    """A URL that is not http or https raises ProviderError before any request is made."""
    with pytest.raises(tronitor.ProviderError, match="unsupported URL") as e:
        tronitor.Http().request("GET", url)
    assert e.value.status is None


def test_http_verbose_uses_the_label_and_strips_the_query(fake_server: FakeServer) -> None:
    """The verbose line shows the label when given, else the URL without its query."""
    fake_server.add("POST", "/hook/secret-token", 204)
    fake_server.add("GET", "/list", 200, {})
    lines: list[str] = []
    http = tronitor.Http(verbose=True, log=lines.append)
    http.request("POST", fake_server.url + "/hook/secret-token", json_body={}, log_label="webhook")
    http.request("GET", fake_server.url + "/list?api_key=secret")
    assert lines == ["POST webhook", f"GET {fake_server.url}/list"]


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


def test_table_colours_only_the_status() -> None:
    """Only the status text carries colour codes."""
    text = tronitor.format_monitor_table(sample_monitors(), "UUID", True)
    first, second = text.split("\n")
    assert first.startswith("web       UUID: id1  Status: ")
    assert "\x1b[33mPaused\x1b[0m" in first
    assert "\x1b[38;5;202mSeems down\x1b[0m" in second
    unknown = tronitor.Monitor("i", "n", "odd", {})
    assert tronitor.format_monitor_table([unknown], "ID", True) == "n  ID: i  Status: Odd"


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
    assert set(tronitor.STATUS_COLORS) == {"up", "down", "paused", "grace", "seems down", "new", "pending"}
    assert all(code.startswith("\x1b[") for code in tronitor.STATUS_COLORS.values())


"""Command line: the actions, run through main() against the fake server."""

FS_PAUSE = f"/api/v3/checks/{HC_UUID_FILESYSTEM}/pause"
DB_PAUSE = f"/api/v3/checks/{HC_UUID_DATABASE}/pause"
DB_RESUME = f"/api/v3/checks/{HC_UUID_DATABASE}/resume"
REMINDER = (
    "Note: a paused Healthchecks check becomes active again when it next receives a ping. "
    "The HealthChecks-Linux script skips a check while its lock file exists (see the docs)."
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
        f"Filesystem Backup  UUID: {HC_UUID_FILESYSTEM}  Status: Up",
        f"Database Backup    UUID: {HC_UUID_DATABASE}  Status: Paused",
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
        f"Database Backup  UUID: {HC_UUID_DATABASE}  Status: Paused",
    ]
    assert posts(fake_server) == []


def test_find_with_nothing_paused(hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    """No paused check gives the 'none paused' line, for -f, -n and -w alike."""
    serve_checks(fake_server, hc_fixture_checks()[:1])
    for flag in ("-f", "-n", "-w"):
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
    hc_env: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """-n and -w do not prompt even on a terminal."""
    serve_checks(fake_server)
    make_tty(monkeypatch, "y\n")
    for flag in ("-n", "-w"):
        assert tronitor.main(["-m", "hc", flag]) == 0
        assert "Unpause" not in capsys.readouterr().out
    assert posts(fake_server) == []


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


def test_pause_named_creates_per_monitor_lock(
    hc_env: Path, locks: Path, fake_server: FakeServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """--pause NAME creates only that check's lock file and pauses only it."""
    serve_checks(fake_server)
    fake_server.add("POST", FS_PAUSE, 200, {"status": "paused"})
    assert tronitor.main(["-m", "hc", "-p", "'filesystem backup'"]) == 0
    assert [p.name for p in locks.iterdir()] == [f"{HC_UUID_FILESYSTEM}.lock"]
    assert posts(fake_server) == [FS_PAUSE]


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
    config.write_text("[general]\nlock_dir = 'x'\n", encoding="utf-8")
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


def test_uptimerobot_is_not_available_yet(hc_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UptimeRobot is recognised but not built yet."""
    assert tronitor.main(["--provider", "UR", "-l"]) == 2
    assert capsys.readouterr().err == "tronitor: UptimeRobot is not available yet\n"


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
