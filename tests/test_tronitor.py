"""Unit tests for the tronitor module."""

import re
import socket
import sys
import tempfile
from pathlib import Path

import pytest
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
