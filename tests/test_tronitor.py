"""Unit tests for the tronitor module."""

import re
import sys
import tempfile
from pathlib import Path

import pytest

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
