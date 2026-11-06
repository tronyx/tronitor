"""Pause and unpause Healthchecks and UptimeRobot monitors from the command line or cron.

tronitor lists the monitors in an account, finds the paused ones, pauses and unpauses them by name or ID,
and can post a summary to a Discord or Slack webhook. Credentials come from a TOML config file or
environment variables.
"""

import argparse
import difflib
import http.client
import json
import os
import re
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__version__ = "2026-11-06"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3

UR_BASE_URL = "https://api.uptimerobot.com/v3"


"""Configuration: the TOML file and the environment variables that override it."""

HC_DEFAULT_URL = "https://healthchecks.io"
NOTIFY_FORMATS = ("discord", "slack")
KNOWN_KEYS: dict[str, dict[str, type]] = {
    "general": {"lock_dir": str},
    "healthchecks": {"url": str, "api_key": str},
    "uptimerobot": {"api_key": str, "base_url": str},
    "notify": {"webhook_url": str, "format": str, "notify_all": bool},
}


class ConfigError(Exception):
    """The configuration file or an environment variable is invalid."""


@dataclass(frozen=True)
class HealthchecksConfig:
    """Healthchecks connection settings."""

    url: str
    api_key: str


@dataclass(frozen=True)
class UptimeRobotConfig:
    """UptimeRobot connection settings."""

    api_key: str
    base_url: str = UR_BASE_URL


@dataclass(frozen=True)
class NotifyConfig:
    """Webhook notification settings."""

    webhook_url: str = ""
    format: str = "discord"
    notify_all: bool = False


@dataclass(frozen=True)
class Config:
    """The complete configuration."""

    lock_dir: Path
    healthchecks: HealthchecksConfig | None
    uptimerobot: UptimeRobotConfig | None
    notify: NotifyConfig


def default_lock_dir() -> Path:
    """Return the default lock directory: /tmp, or the temp directory on Windows."""
    if sys.platform != "win32":
        return Path("/tmp")
    temp = os.environ.get("TEMP")
    return Path(temp) if temp else Path(tempfile.gettempdir())


def config_search_paths(script_path: Path, home: Path, env: Mapping[str, str]) -> list[Path]:
    """Return the places to look for a config file, in order."""
    user_dir = home / ".config"
    if sys.platform == "win32" and env.get("APPDATA"):
        user_dir = Path(env["APPDATA"])
    return [script_path.parent / "tronitor.toml", user_dir / "tronitor" / "tronitor.toml"]


def _suggest(name: str, known: Sequence[str]) -> str:
    """Return a did-you-mean hint for name, or an empty string."""
    match = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    return f" (did you mean '{match[0]}'?)" if match else ""


def _read_toml(path: Path) -> dict[str, Any]:
    """Parse the TOML file at path."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def _check_type(value: object, label: str, expected: type, source: str) -> None:
    """Raise ConfigError if value is not of the expected type."""
    if not isinstance(value, expected):
        what = "true or false" if expected is bool else "a string"
        raise ConfigError(f"{source}: {label} must be {what}")


def _check_table(table: str, values: Mapping[str, Any], source: str) -> None:
    """Raise ConfigError for unknown keys or wrong types in one table."""
    known = KNOWN_KEYS[table]
    for key, value in values.items():
        if key not in known:
            raise ConfigError(f"{source}: unknown key '{table}.{key}'{_suggest(key, list(known))}")
        _check_type(value, f"{table}.{key}", known[key], source)


def _check_known_keys(doc: Mapping[str, Any], source: str) -> None:
    """Raise ConfigError for unknown tables or keys and for values of the wrong type."""
    for name, value in doc.items():
        if isinstance(value, dict):
            if name not in KNOWN_KEYS:
                raise ConfigError(f"{source}: unknown table '{name}'{_suggest(name, list(KNOWN_KEYS))}")
            _check_table(name, value, source)
        elif name in KNOWN_KEYS:
            raise ConfigError(f"{source}: {name} must be a table")
        else:
            raise ConfigError(f"{source}: unknown key '{name}'{_table_hint(name)}")


def _table_hint(key: str) -> str:
    """Return a hint naming the table that has a key called key, or an empty string."""
    for table, keys in KNOWN_KEYS.items():
        if key in keys:
            return f" (did you mean '{table}.{key}'?)"
    return ""


def _url(value: str, prefix: str, subject: str) -> str:
    """Strip value, require an http or https scheme, and drop trailing slashes."""
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        raise ConfigError(f"{prefix}: {subject}must start with http:// or https://")
    return value.rstrip("/")


def _setting(doc: Mapping[str, Any], table: str, key: str, default: str = "") -> str:
    """Return the stripped string at doc[table][key], or default."""
    return str(doc.get(table, {}).get(key, default)).strip()


def _env_value(env: Mapping[str, str], name: str) -> str:
    """Return the stripped environment variable name; a variable that is unset or empty gives ''."""
    return env.get(name, "").strip()


def _resolve(
    doc: Mapping[str, Any], env: Mapping[str, str], var: str, table: str, key: str, source: str
) -> tuple[str, str, str]:
    """Return (value, error prefix, error subject) for a setting; the environment wins over the file."""
    value = _env_value(env, var)
    if value:
        return value, var, ""
    return _setting(doc, table, key), source, f"{table}.{key} "


def _healthchecks(doc: Mapping[str, Any], env: Mapping[str, str], source: str) -> HealthchecksConfig | None:
    """Build the Healthchecks settings, or None when there is no API key."""
    api_key = _resolve(doc, env, "TRONITOR_HEALTHCHECKS_API_KEY", "healthchecks", "api_key", source)[0]
    value, prefix, subject = _resolve(doc, env, "TRONITOR_HEALTHCHECKS_URL", "healthchecks", "url", source)
    url = _url(value or HC_DEFAULT_URL, prefix, subject)
    return HealthchecksConfig(url, api_key) if api_key else None


def _uptimerobot(doc: Mapping[str, Any], env: Mapping[str, str], source: str) -> UptimeRobotConfig | None:
    """Build the UptimeRobot settings, or None when there is no API key."""
    api_key = _resolve(doc, env, "TRONITOR_UPTIMEROBOT_API_KEY", "uptimerobot", "api_key", source)[0]
    base_url = _url(_setting(doc, "uptimerobot", "base_url") or UR_BASE_URL, source, "uptimerobot.base_url ")
    return UptimeRobotConfig(api_key, base_url) if api_key else None


def _notify(doc: Mapping[str, Any], env: Mapping[str, str], source: str) -> NotifyConfig:
    """Build the notification settings."""
    fmt = _setting(doc, "notify", "format", "discord")
    if fmt not in NOTIFY_FORMATS:
        raise ConfigError(f'{source}: notify.format must be "discord" or "slack"')
    webhook, prefix, subject = _resolve(doc, env, "TRONITOR_WEBHOOK_URL", "notify", "webhook_url", source)
    if webhook:
        webhook = _url(webhook, prefix, subject)
    return NotifyConfig(webhook, fmt, bool(doc.get("notify", {}).get("notify_all", False)))


def _find_config_file(path: Path | None, env: Mapping[str, str], search_paths: Sequence[Path]) -> Path | None:
    """Return the config file to read, or None when there is none."""
    if path is None and _env_value(env, "TRONITOR_CONFIG"):
        path = Path(_env_value(env, "TRONITOR_CONFIG"))
    if path is not None:
        if not path.is_file():
            raise ConfigError(f"{path}: config file does not exist")
        return path
    return next((p for p in search_paths if p.is_file()), None)


def load_config(path: Path | None, env: Mapping[str, str], search_paths: Sequence[Path]) -> Config:
    """Load the configuration from the file and the environment (the environment wins)."""
    found = _find_config_file(path, env, search_paths)
    source = str(found) if found else "configuration"
    doc = _read_toml(found) if found else {}
    _check_known_keys(doc, source)
    lock_dir = _resolve(doc, env, "TRONITOR_LOCK_DIR", "general", "lock_dir", source)[0]
    return Config(
        lock_dir=Path(lock_dir) if lock_dir else default_lock_dir(),
        healthchecks=_healthchecks(doc, env, source),
        uptimerobot=_uptimerobot(doc, env, source),
        notify=_notify(doc, env, source),
    )


"""HTTP: the one place that talks to the network."""

ERROR_TEXT_LIMIT = 200


class ProviderError(Exception):
    """A provider's API could not be reached, or it answered with an error."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    """A successful response: the status and the decoded JSON body (None when the body is empty)."""

    status: int
    json: Any


def _collapse(text: str) -> str:
    """Collapse whitespace in text and cut it to the error text limit."""
    return " ".join(text.split())[:ERROR_TEXT_LIMIT]


def _error_detail(text: str, status: int) -> str:
    """Return the most useful description of an error body: its message, error or detail field, else the text.

    An empty body gives the standard reason phrase for the status.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("message", "error", "detail"):
            value = data.get(key)
            if isinstance(value, list):
                value = "; ".join(str(item) for item in value)
            if isinstance(value, str) and _collapse(value):
                return _collapse(value)
    return _collapse(text) or http.client.responses.get(status, "error")


class Http:
    """Send HTTP requests and turn every network or API failure into a ProviderError."""

    def __init__(
        self, *, timeout: float = 30.0, verbose: bool = False, log: Callable[[str], None] | None = None
    ) -> None:
        self.timeout = timeout
        self.verbose = verbose
        self._log = log or (lambda line: print(line, file=sys.stderr))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: object | None = None,
        allow_statuses: Collection[int] = (),
        log_label: str | None = None,
    ) -> HttpResponse:
        """Send a request and return the response; a status that is not 2xx or allowed raises ProviderError.

        With verbose, the log line shows the method and log_label, or the URL without its query when there is no
        label (a label hides a URL that carries a secret).
        """
        try:
            scheme = urllib.parse.urlsplit(url).scheme.lower()
        except ValueError:
            scheme = ""
        if scheme not in ("http", "https"):
            raise ProviderError(f"unsupported URL: {url}")
        all_headers = {"Accept": "application/json", "User-Agent": f"tronitor/{__version__}", **(headers or {})}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        except ValueError:
            raise ProviderError(f"unsupported URL: {url}") from None
        if self.verbose:
            self._log(f"{method} {log_label if log_label is not None else url.split('?', 1)[0]}")
        status, text = self._send(req)
        if not 200 <= status < 300 and status not in allow_statuses:
            raise ProviderError(f"HTTP {status}: {_error_detail(text, status)}", status)
        if not text:
            return HttpResponse(status, None)
        try:
            return HttpResponse(status, json.loads(text))
        except json.JSONDecodeError:
            if 200 <= status < 300:
                raise ProviderError(f"HTTP {status}: response is not JSON", status) from None
            return HttpResponse(status, None)

    def _send(self, req: urllib.request.Request) -> tuple[int, str]:
        """Send req and return (status, body text); network failures raise ProviderError."""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return int(response.status), response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            with exc:
                try:
                    return exc.code, exc.read().decode("utf-8", errors="replace")
                except (OSError, http.client.HTTPException):
                    raise ProviderError(f"HTTP {exc.code}: could not read the response body", exc.code) from None
        except TimeoutError:
            raise ProviderError(f"cannot reach {self._host(req)}: timed out") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ProviderError(f"cannot reach {self._host(req)}: timed out") from None
            raise ProviderError(f"cannot reach {self._host(req)}: {exc.reason}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise ProviderError(f"cannot reach {self._host(req)}: {exc}") from exc

    @staticmethod
    def _host(req: urllib.request.Request) -> str:
        """Return the host (and port) of a request's URL."""
        return urllib.parse.urlsplit(req.full_url).netloc


"""Providers: one class per monitoring service, each turning its records into Monitor objects."""

PAUSED = "paused"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class Monitor:
    """One monitor: its ID, name, status and the provider's raw record.

    The status is one of "up", "down", "paused", "grace", "new", "pending" or "seems down".
    """

    id: str
    name: str
    status: str
    raw: dict[str, Any]


class Unsupported(ProviderError):
    """The provider does not offer the requested action."""


def _expect_dict(value: object, label: str) -> dict[str, Any]:
    """Return value if it is a dict, else raise ProviderError for an unexpected response from label."""
    if not isinstance(value, dict):
        raise ProviderError(f"unexpected response from {label}")
    return value


def _expect_list(value: object, label: str) -> list[Any]:
    """Return value if it is a list, else raise ProviderError for an unexpected response from label."""
    if not isinstance(value, list):
        raise ProviderError(f"unexpected response from {label}")
    return value


class Provider:
    """The interface every monitoring service implements."""

    label = ""
    id_kind = ""
    supports_lock_files = False

    def list_monitors(self) -> list[Monitor]:
        """Return every monitor in the account."""
        raise NotImplementedError

    def pause(self, monitor: Monitor) -> None:
        """Pause a monitor."""
        raise NotImplementedError

    def unpause(self, monitor: Monitor) -> None:
        """Unpause a monitor; a monitor that is already running is not an error."""
        raise NotImplementedError

    def info(self, monitor: Monitor) -> dict[str, Any]:
        """Return the provider's full record for a monitor."""
        raise NotImplementedError

    def alert_contacts(self) -> list[dict[str, Any]]:
        """Return the account's alert contacts (notification channels)."""
        raise NotImplementedError

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a monitor from a provider-specific payload and return the new record."""
        raise NotImplementedError

    def delete(self, monitor: Monitor) -> None:
        """Delete a monitor."""
        raise NotImplementedError

    def stats(self) -> dict[str, Any]:
        """Return account statistics; most providers do not offer them."""
        raise Unsupported(f"{self.label} does not support stats")

    def reset(self, monitor: Monitor) -> None:
        """Reset a monitor's statistics; most providers do not offer this."""
        raise Unsupported(f"{self.label} does not support reset")

    @staticmethod
    def is_id(text: str) -> bool:
        """Return True if text looks like this provider's monitor ID."""
        return False


class HealthchecksProvider(Provider):
    """Healthchecks API v3."""

    label = "Healthchecks"
    id_kind = "UUID"
    supports_lock_files = True

    def __init__(self, http: Http, config: HealthchecksConfig) -> None:
        self._http = http
        self._api = f"{config.url}/api/v3"
        self._headers = {"X-Api-Key": config.api_key}

    def list_monitors(self) -> list[Monitor]:
        """Return every check; a read-only API key (checks without a uuid) raises ProviderError."""
        body = _expect_dict(self._http.request("GET", f"{self._api}/checks/", headers=self._headers).json, self.label)
        checks = [_expect_dict(check, self.label) for check in _expect_list(body.get("checks"), self.label)]
        if any(c.get("name") is None or c.get("status") is None for c in checks):
            raise ProviderError(f"unexpected response from {self.label}")
        if any("uuid" not in check for check in checks):
            raise ProviderError("the Healthchecks API key is read-only; tronitor needs a read-write key")
        return [Monitor(id=c["uuid"], name=c["name"], status=c["status"], raw=c) for c in checks]

    def pause(self, monitor: Monitor) -> None:
        """Pause a check."""
        self._http.request("POST", f"{self._api}/checks/{monitor.id}/pause", headers=self._headers, json_body={})

    def unpause(self, monitor: Monitor) -> None:
        """Resume a check; 409 means it was not paused, which is fine."""
        self._http.request(
            "POST",
            f"{self._api}/checks/{monitor.id}/resume",
            headers=self._headers,
            json_body={},
            allow_statuses=(409,),
        )

    def info(self, monitor: Monitor) -> dict[str, Any]:
        """Return the full record of a check."""
        response = self._http.request("GET", f"{self._api}/checks/{monitor.id}", headers=self._headers)
        return _expect_dict(response.json, self.label)

    def alert_contacts(self) -> list[dict[str, Any]]:
        """Return the account's integrations (channels)."""
        body = _expect_dict(self._http.request("GET", f"{self._api}/channels/", headers=self._headers).json, self.label)
        return [_expect_dict(channel, self.label) for channel in _expect_list(body.get("channels"), self.label)]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a check and return it."""
        response = self._http.request("POST", f"{self._api}/checks/", headers=self._headers, json_body=payload)
        return _expect_dict(response.json, self.label)

    def delete(self, monitor: Monitor) -> None:
        """Delete a check."""
        self._http.request("DELETE", f"{self._api}/checks/{monitor.id}", headers=self._headers)

    @staticmethod
    def is_id(text: str) -> bool:
        """Return True if text is a UUID."""
        return bool(UUID_RE.match(text))


"""Selection: which monitors an action applies to."""


def split_selection(text: str) -> list[str]:
    """Split a comma-separated selection into items, or return ["all"] for the single item all."""
    items = []
    for part in text.split(","):
        item = part.strip()
        if len(item) >= 2 and item[0] == item[-1] and item[0] in "'\"":
            item = item[1:-1].strip()
        else:
            item = item.removeprefix('"').removeprefix("'").removesuffix('"').removesuffix("'").strip()
        if item:
            items.append(item)
    if len(items) == 1 and items[0].casefold() == "all":
        return ["all"]
    return items


@dataclass
class Selection:
    """The outcome of matching the user's items against the provider's monitors."""

    matched: list[Monitor]
    unmatched: list[str]
    ambiguous: dict[str, list[Monitor]]

    @property
    def ok(self) -> bool:
        """Return True if every item matched exactly one monitor."""
        return not self.unmatched and not self.ambiguous


def select_monitors(monitors: Sequence[Monitor], items: Sequence[str], is_id: Callable[[str], bool]) -> Selection:
    """Match items against monitors by ID or by exact, case-insensitive name."""
    if list(items) == ["all"]:
        return Selection(matched=list(monitors), unmatched=[], ambiguous={})
    selection = Selection(matched=[], unmatched=[], ambiguous={})
    for item in items:
        wanted = item.casefold()
        if is_id(item):
            found = [m for m in monitors if m.id.casefold() == wanted]
        else:
            found = [m for m in monitors if m.name.casefold() == wanted]
        if not found:
            selection.unmatched.append(item)
        elif len(found) > 1:
            selection.ambiguous[item] = found
        elif found[0] not in selection.matched:
            selection.matched.append(found[0])
    return selection


def describe_selection_problems(selection: Selection, monitors: Sequence[Monitor], id_kind: str) -> str:
    """Describe the items that were not found or matched several monitors."""
    lines = [f"Not found: {item}" for item in selection.unmatched]
    for item, found in selection.ambiguous.items():
        lines.append(f'"{item}" matches {len(found)} monitors; use the {id_kind} instead:')
        lines.extend(f"  {m.name} ({id_kind} {m.id})" for m in found)
    names = [m.name.casefold() for m in monitors]
    if any(name.startswith(item.casefold() + ",") for item in selection.unmatched for name in names):
        lines.append(f"Names with commas cannot be selected; use the {id_kind} instead.")
    return "\n".join(lines)


"""Lock files: how a paused Healthchecks check keeps the pinging script quiet."""


class LockError(Exception):
    """The lock directory cannot be used."""


class LockFiles:
    """Create and remove the lock files that the HealthChecks-Linux pinging script looks for."""

    ALL_NAME = "healthchecks.lock"

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir

    def path_for(self, monitor_id: str) -> Path:
        """Return the path of the lock file for one monitor."""
        return self.lock_dir / f"{monitor_id}.lock"

    def prepare(self) -> None:
        """Create the lock directory if needed and check that files can be written to it."""
        if self.lock_dir.exists() and not self.lock_dir.is_dir():
            raise LockError(f"{self.lock_dir} is not a directory")
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LockError(f"cannot create {self.lock_dir}: {exc.strerror or exc}") from exc
        probe = self.lock_dir / f".tronitor-write-test-{os.getpid()}"
        try:
            probe.touch()
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise LockError(f"cannot write to {self.lock_dir}: {exc.strerror or exc}") from exc

    def lock_all(self) -> Path:
        """Create the lock file that makes the pinging script skip every check."""
        return self._create(self.lock_dir / self.ALL_NAME)

    def lock(self, monitor_id: str) -> Path:
        """Create the lock file that makes the pinging script skip one check."""
        return self._create(self.path_for(monitor_id))

    def unlock_all(self, monitor_ids: Iterable[str]) -> list[Path]:
        """Remove healthchecks.lock and the lock file of each given ID; return the paths removed."""
        removed = []
        if self._remove(self.lock_dir / self.ALL_NAME):
            removed.append(self.lock_dir / self.ALL_NAME)
        for monitor_id in monitor_ids:
            if self.unlock(monitor_id):
                removed.append(self.path_for(monitor_id))
        return removed

    def unlock(self, monitor_id: str) -> bool:
        """Remove the lock file of one monitor; return True if there was one."""
        return self._remove(self.path_for(monitor_id))

    def is_locked(self, monitor_id: str) -> bool:
        """Return True if the monitor has a lock file."""
        return self.path_for(monitor_id).exists()

    @property
    def all_locked(self) -> bool:
        """Return True if healthchecks.lock exists."""
        return (self.lock_dir / self.ALL_NAME).exists()

    @staticmethod
    def _create(path: Path) -> Path:
        """Create the empty file at path and return it; failure raises LockError."""
        try:
            path.touch()
        except OSError as exc:
            raise LockError(f"cannot create {path}: {exc.strerror or exc}") from exc
        return path

    @staticmethod
    def _remove(path: Path) -> bool:
        """Delete path; return True if this call removed it, False if there was none."""
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise LockError(f"cannot remove {path}: {exc.strerror or exc}") from exc
        return True


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="tronitor")
    parser.add_argument("--version", action="version", version=f"tronitor {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run tronitor with argv (default: sys.argv[1:]) and return the exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    parser.parse_args(args)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
