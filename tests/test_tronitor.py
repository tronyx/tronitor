"""Unit tests for the tronitor module."""

import os
import re
import socket
import sys
import tempfile
from pathlib import Path

import pytest
from conftest import HC_UUID_DATABASE, HC_UUID_FILESYSTEM, hc_fixture_checks
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
