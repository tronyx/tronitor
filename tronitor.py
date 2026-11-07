"""Pause and unpause Healthchecks and UptimeRobot monitors from the command line or cron.

tronitor lists the monitors in an account, finds the paused ones, pauses and unpauses them by name or ID,
and can post a summary to a Discord or Slack webhook. Credentials come from a TOML config file or
environment variables.
"""

import argparse
import difflib
import functools
import http.client
import io
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

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
        unsupported = f"unsupported URL for {log_label}" if log_label is not None else f"unsupported URL: {url}"
        if scheme not in ("http", "https"):
            raise ProviderError(unsupported)
        all_headers = {"Accept": "application/json", "User-Agent": f"tronitor/{__version__}", **(headers or {})}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        except ValueError:
            raise ProviderError(unsupported) from None
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
            if 200 <= status < 300 and status not in allow_statuses:
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
UR_STATUS = {"UP": "up", "DOWN": "down", "PAUSED": "paused", "STARTED": "pending", "LOOKS_DOWN": "seems down"}
UR_MAX_PAGES = 100
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
    supports_reset = False

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


class UptimeRobotProvider(Provider):
    """UptimeRobot API v3."""

    label = "UptimeRobot"
    id_kind = "ID"
    supports_lock_files = False
    supports_reset = True

    def __init__(self, http: Http, config: UptimeRobotConfig) -> None:
        self._http = http
        self._base = config.base_url
        self._headers = {"Authorization": f"Bearer {config.api_key}"}

    def list_monitors(self) -> list[Monitor]:
        """Return every monitor, following the pagination links."""
        monitors: list[Monitor] = []
        url = f"{self._base}/monitors?limit=200"
        for _ in range(UR_MAX_PAGES):
            body = _expect_dict(self._http.request("GET", url, headers=self._headers).json, self.label)
            for item in _expect_list(body.get("data"), self.label):
                monitors.append(self._monitor(_expect_dict(item, self.label)))
            link = body.get("nextLink")
            if not isinstance(link, str) or not link:
                return monitors
            if link.startswith(("http://", "https://")):
                if link != self._base and not link.startswith(self._base + "/"):
                    raise ProviderError(f"{self.label} returned a pagination link on another host")
                url = link
            else:
                url = f"{self._base}/monitors?limit=200&cursor={urllib.parse.quote(link, safe='')}"
        raise ProviderError(f"{self.label} returned more than {UR_MAX_PAGES} pages of monitors")

    def _monitor(self, item: dict[str, Any]) -> Monitor:
        """Turn one monitor record into a Monitor; a record without an id, name or status is unexpected."""
        if item.get("id") is None or item.get("friendlyName") is None or item.get("status") is None:
            raise ProviderError(f"unexpected response from {self.label}")
        raw_status = str(item["status"])
        status = UR_STATUS.get(raw_status.upper(), raw_status.lower())
        return Monitor(id=str(item["id"]), name=str(item["friendlyName"]), status=status, raw=item)

    def pause(self, monitor: Monitor) -> None:
        """Pause a monitor; pausing one that is already paused succeeds."""
        self._http.request("POST", f"{self._base}/monitors/{monitor.id}/pause", headers=self._headers, json_body={})

    def unpause(self, monitor: Monitor) -> None:
        """Start a monitor again."""
        self._http.request("POST", f"{self._base}/monitors/{monitor.id}/start", headers=self._headers, json_body={})

    def reset(self, monitor: Monitor) -> None:
        """Reset a monitor's statistics."""
        self._http.request("POST", f"{self._base}/monitors/{monitor.id}/reset", headers=self._headers, json_body={})

    def delete(self, monitor: Monitor) -> None:
        """Delete a monitor."""
        self._http.request("DELETE", f"{self._base}/monitors/{monitor.id}", headers=self._headers)

    def info(self, monitor: Monitor) -> dict[str, Any]:
        """Return the full record of a monitor."""
        response = self._http.request("GET", f"{self._base}/monitors/{monitor.id}", headers=self._headers)
        return _expect_dict(response.json, self.label)

    def stats(self) -> dict[str, Any]:
        """Return the account record, which holds the monitor count and limit."""
        return _expect_dict(self._http.request("GET", f"{self._base}/user/me", headers=self._headers).json, self.label)

    def alert_contacts(self) -> list[dict[str, Any]]:
        """Return the account's alert contacts."""
        response = self._http.request("GET", f"{self._base}/user/alert-contacts", headers=self._headers)
        return [_expect_dict(contact, self.label) for contact in _expect_list(response.json, self.label)]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a monitor and return it."""
        response = self._http.request("POST", f"{self._base}/monitors", headers=self._headers, json_body=payload)
        return _expect_dict(response.json, self.label)

    @staticmethod
    def is_id(text: str) -> bool:
        """Return True if text is a numeric monitor ID."""
        return text.isascii() and text.isdigit()


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


"""Output: tables, colour, JSON and the yes/no prompt."""

RESET = "\x1b[0m"
STATUS_COLORS: dict[str, str] = {
    "up": "\x1b[32m",
    "down": "\x1b[31m",
    "paused": "\x1b[33m",
    "grace": "\x1b[38;5;202m",
    "seems down": "\x1b[38;5;202m",
    "new": "\x1b[35m",
    "pending": "\x1b[35m",
}


class NeedsTerminal(Exception):
    """Raised when a confirmation is needed but there is no terminal; the message is the question."""


def is_terminal(stream: TextIO | None) -> bool:
    """Return True if stream is a terminal."""
    try:
        return stream is not None and bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def use_color(stream: TextIO, env: Mapping[str, str], no_color_flag: bool) -> bool:
    """Return True if output to stream may be coloured.

    Colour needs a terminal, no NO_COLOR variable (any value) and no --no-color flag.
    """
    return not no_color_flag and "NO_COLOR" not in env and is_terminal(stream)


def plain_text(text: str) -> str:
    """Return text with every control character replaced by "?", so provider data cannot move the cursor."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "?", text)


def format_monitor_table(monitors: Sequence[Monitor], id_kind: str, color: bool) -> str:
    """Return one line per monitor: the padded name, the ID and the status, coloured if color is true."""
    if not monitors:
        return ""
    names = [plain_text(monitor.name) for monitor in monitors]
    width = max(len(name) for name in names)
    lines = []
    for monitor, name in zip(monitors, names, strict=True):
        status_text = monitor.status.capitalize()
        code = STATUS_COLORS.get(monitor.status)
        if color and code:
            status_text = f"{code}{status_text}{RESET}"
        lines.append(f"{name:<{width}}  {id_kind}: {plain_text(monitor.id)}  Status: {status_text}")
    return "\n".join(lines)


def format_json(data: object) -> str:
    """Return data as indented JSON with sorted keys."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def confirm(
    question: str,
    *,
    assume_yes: bool,
    interactive: bool,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Ask a yes/no question and return the answer.

    assume_yes returns True without asking. Without a terminal, raise NeedsTerminal. The default answer is no.
    """
    if assume_yes:
        return True
    if not interactive:
        raise NeedsTerminal(question)
    try:
        answer = input_fn(f"{question} [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


"""Notifications: the Discord or Slack message about paused monitors."""

DISCORD_MAX_FIELDS = 25
DISCORD_NAME_LIMIT = 256
DISCORD_VALUE_LIMIT = 1024
DISCORD_PAUSED_COLOR = 3381759
DISCORD_RUNNING_COLOR = 10092339


def build_webhook_payload(
    label: str, paused: Sequence[Monitor], id_kind: str, fmt: str, notify_all: bool
) -> dict[str, Any] | None:
    """Return the JSON body for the webhook, or None when nothing is paused and notify_all is off.

    fmt is "discord" (one embed, one field per monitor, at most 25 fields) or "slack" (one text message).
    """
    if not paused and not notify_all:
        return None
    if fmt == "slack":
        if not paused:
            return {"text": f"All {label} monitors are currently running."}
        lines = [f"• {plain_text(m.name)} ({id_kind} {plain_text(m.id)})" for m in paused]
        return {"text": "\n".join([f"There are currently paused {label} monitors:", *lines])}
    if not paused:
        return {"embeds": [{"title": f"All {label} monitors are currently running.", "color": DISCORD_RUNNING_COLOR}]}
    fields = [
        {
            "name": plain_text(m.name)[:DISCORD_NAME_LIMIT] or "(unnamed)",
            "value": f"{id_kind}: {plain_text(m.id)}"[:DISCORD_VALUE_LIMIT],
        }
        for m in paused
    ]
    if len(fields) > DISCORD_MAX_FIELDS:
        hidden = len(fields) - (DISCORD_MAX_FIELDS - 1)
        fields = [*fields[: DISCORD_MAX_FIELDS - 1], {"name": "...", "value": f"and {hidden} more"}]
    title = f"There are currently paused {label} monitors:"
    return {"embeds": [{"title": title, "color": DISCORD_PAUSED_COLOR, "fields": fields}]}


def send_notification(http: Http, config: NotifyConfig, label: str, paused: Sequence[Monitor], id_kind: str) -> bool:
    """Post the paused monitors to the webhook; return False when there was nothing to send, else True.

    A missing webhook URL raises ConfigError. An allowed status counts as success whatever its body: Discord sends
    204 with no body and Slack sends 200 with the plain text "ok". The log label keeps the URL, which holds a
    secret token, out of --verbose output and error messages.
    """
    if not config.webhook_url:
        raise ConfigError("no webhook URL: set [notify] webhook_url or TRONITOR_WEBHOOK_URL")
    payload = build_webhook_payload(label, paused, id_kind, config.format, config.notify_all)
    if payload is None:
        return False
    http.request("POST", config.webhook_url, json_body=payload, allow_statuses=(200, 201, 204), log_label="webhook")
    return True


"""Command line: options, actions and exit codes."""

DOCS_URL = "https://github.com/tronyx/tronitor/blob/master/docs/usage.md"
EXIT_INTERRUPTED = 130
PROVIDER_NAMES = {
    "hc": "healthchecks",
    "healthchecks": "healthchecks",
    "ur": "uptimerobot",
    "uptimerobot": "uptimerobot",
}
HC_REMINDER = (
    "Note: a paused Healthchecks check becomes active again when it next receives a ping. "
    "The HealthChecks-Linux script skips a check while its lock file exists (see the docs)."
)
DESCRIPTION = "Pause and unpause Healthchecks and UptimeRobot monitors, from cron or by hand."
EPILOG = f"""\
PROVIDER is healthchecks (hc) or uptimerobot (ur).

TARGETS is "all", or a comma-separated list of monitor names and IDs. Put names
in quotes, for example: -p "Filesystem Backup,Database Backup". A name must
match the whole monitor name, but capital letters do not matter. A Healthchecks
ID is the check's UUID; an UptimeRobot ID is the monitor's number.

Examples:
  tronitor -m hc -l
  tronitor -m hc -p all
  tronitor -m ur -u "Plex,Tautulli"

Documentation: {DOCS_URL}"""


class UsageError(Exception):
    """The command line asks for something that cannot be done; the message says why."""


class SelectionProblem(Exception):
    """Some requested monitors were not found or matched several; the message lists them."""


class NothingToDo(Exception):
    """There is nothing to act on; the message says so."""


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="tronitor",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-m",
        "--monitor",
        "--provider",
        dest="provider",
        metavar="PROVIDER",
        required=True,
        help="the monitoring service: healthchecks (hc) or uptimerobot (ur)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="the config file (default: tronitor.toml next to the script, then in your user config folder)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="delete or reset without asking, and act on the monitors that were found when some were not",
    )
    parser.add_argument("--json", action="store_true", help="print the provider's records as JSON instead of a table")
    parser.add_argument("--no-color", action="store_true", help="never colour the output")
    parser.add_argument("--verbose", action="store_true", help="show each API request on stderr")
    parser.add_argument("--version", action="version", version=f"tronitor {__version__}")
    actions = parser.add_argument_group("actions (choose one)").add_mutually_exclusive_group(required=True)
    actions.add_argument("-l", "--list", action="store_true", help="list every monitor and its status")
    actions.add_argument(
        "-f", "--find", action="store_true", help="list the paused monitors; on a terminal, offer to unpause them"
    )
    actions.add_argument("-n", "--no-prompt", action="store_true", help="list the paused monitors and never ask")
    actions.add_argument(
        "-w", "--webhook", action="store_true", help="list the paused monitors and post them to the webhook"
    )
    actions.add_argument("-s", "--stats", action="store_true", help="show the account statistics (UptimeRobot only)")
    actions.add_argument(
        "-a", "--alerts", action="store_true", help="list the alert contacts (Healthchecks: integrations)"
    )
    actions.add_argument("-i", "--info", metavar="TARGET", help="show the full record of one monitor")
    actions.add_argument("-c", "--create", type=Path, metavar="FILE", help="create a monitor from a JSON file")
    actions.add_argument("-p", "--pause", metavar="TARGETS", help="pause monitors")
    actions.add_argument("-u", "--unpause", metavar="TARGETS", help="unpause monitors")
    actions.add_argument("-d", "--delete", metavar="TARGETS", help="delete monitors (asks first)")
    actions.add_argument(
        "-r", "--reset", metavar="TARGETS", help="clear the statistics of monitors (asks first; not Healthchecks)"
    )
    return parser


def resolve_provider_name(text: str) -> str:
    """Return the full provider name for a short or full name, in any case."""
    name = PROVIDER_NAMES.get(text.strip().lower())
    if name is None:
        raise ConfigError(f"unknown provider '{text}'; use healthchecks (hc) or uptimerobot (ur)")
    return name


def make_provider(name: str, config: Config, http: Http) -> Provider:
    """Return the provider called name, built from its settings."""
    if name == "healthchecks":
        if config.healthchecks is None:
            raise ConfigError(
                "no Healthchecks API key: set [healthchecks] api_key in the config or TRONITOR_HEALTHCHECKS_API_KEY"
            )
        return HealthchecksProvider(http, config.healthchecks)
    if name == "uptimerobot":
        if config.uptimerobot is None:
            raise ConfigError(
                "no UptimeRobot API key: set [uptimerobot] api_key in the config or TRONITOR_UPTIMEROBOT_API_KEY"
            )
        return UptimeRobotProvider(http, config.uptimerobot)
    raise ConfigError(f"unknown provider '{name}'")


def print_error(stream: TextIO, message: str) -> None:
    """Print message to stream, prefixing "tronitor: " to every line that is not indented."""
    for line in message.splitlines() or [""]:
        line = plain_text(line)
        print(line if line.startswith(" ") else f"tronitor: {line}", file=stream)


@dataclass
class Context:
    """What every action needs: the provider, the settings, the streams and the user's choices."""

    provider: Provider
    config: Config
    http: Http
    out: TextIO
    err: TextIO
    color: bool
    json_output: bool
    assume_yes: bool
    interactive: bool
    lock_files: LockFiles | None
    stdin: TextIO

    def say(self, text: str) -> None:
        """Print a line of normal output."""
        print(text, file=self.out)

    def ask(self, question: str, *, assume_yes: bool) -> bool:
        """Ask a yes/no question on the terminal (see confirm)."""
        return confirm(question, assume_yes=assume_yes, interactive=self.interactive, input_fn=self._read_answer)

    def _read_answer(self, prompt: str) -> str:
        """Show prompt and read one line from stdin; the end of input raises EOFError."""
        self.out.write(prompt)
        self.out.flush()
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")


@dataclass
class Targets:
    """The monitors an action applies to, and whether the user asked for all of them."""

    listed: list[Monitor]
    chosen: list[Monitor]
    everything: bool
    incomplete: bool


@dataclass
class Outcome:
    """What happened when an action ran on each monitor."""

    done: list[Monitor] = field(default_factory=list)
    failed: list[Monitor] = field(default_factory=list)
    lock_errors: int = 0

    def exit_code(self, incomplete: bool) -> int:
        """Return 1 if only failures, 3 if some failures or an incomplete selection, else 0."""
        failures = len(self.failed) + self.lock_errors
        if failures and not self.done:
            return EXIT_ERROR
        if failures or incomplete:
            return EXIT_PARTIAL
        return EXIT_OK


def parse_targets(option: str, text: str) -> list[str]:
    """Split the value of a selection option; an empty selection is a usage error."""
    items = split_selection(text)
    if not items:
        raise UsageError(f'{option} needs "all" or a comma-separated list of monitors')
    return items


def select_targets(ctx: Context, items: list[str]) -> Targets:
    """List the monitors and pick the ones items name.

    Unmatched or ambiguous items raise SelectionProblem, unless --yes was given, nothing was ambiguous and something
    matched: then the problems are reported and the action goes ahead with the matches.
    """
    listed = ctx.provider.list_monitors()
    everything = items == ["all"]
    if everything and not listed:
        raise NothingToDo("No monitors found.")
    selection = select_monitors(listed, items, ctx.provider.is_id)
    if not selection.ok:
        problems = describe_selection_problems(selection, listed, ctx.provider.id_kind)
        if not (ctx.assume_yes and selection.matched and not selection.ambiguous):
            raise SelectionProblem(problems)
        print_error(ctx.err, problems)
    return Targets(listed, selection.matched, everything, incomplete=not selection.ok)


def act_on_each(
    ctx: Context, verb: str, monitors: Sequence[Monitor], step: Callable[[Monitor], object], *, show_id: bool = True
) -> Outcome:
    """Run step on each monitor and never stop early.

    Prints "<verb> <name>... done" on stdout, or "<verb> <name>... failed: <reason>" as an error on stderr.
    """
    outcome = Outcome()
    for monitor in monitors:
        what = f"{verb} {plain_text(monitor.name)}"
        if show_id:
            what += f" ({ctx.provider.id_kind} {plain_text(monitor.id)})"
        try:
            step(monitor)
        except Unsupported:
            raise
        except (ProviderError, LockError) as exc:
            print_error(ctx.err, f"{what}... failed: {exc}")
            outcome.failed.append(monitor)
        else:
            ctx.say(f"{what}... done")
            outcome.done.append(monitor)
    return outcome


def try_lock_removal(ctx: Context, remove: Callable[[], object]) -> int:
    """Call remove; return 0, or report its LockError and return 1."""
    try:
        remove()
    except LockError as exc:
        print_error(ctx.err, str(exc))
        return 1
    return 0


def remove_locks(ctx: Context, lock_files: LockFiles, ids: Sequence[str], *, everything: bool) -> int:
    """Remove the lock files of ids, and healthchecks.lock first when everything.

    Each removal is tried on its own, so one that fails does not stop the rest; failures are reported and counted.
    """
    errors = 0
    if everything:
        errors += try_lock_removal(ctx, lambda: lock_files.unlock_all([]))
    for monitor_id in ids:
        errors += try_lock_removal(ctx, functools.partial(lock_files.unlock, monitor_id))
    return errors


def unpause_monitors(ctx: Context, targets: Sequence[Monitor], *, listed: Sequence[Monitor] | None) -> Outcome:
    """Unpause the paused monitors among targets, then remove lock files.

    With listed (every monitor, for "all" and the --find prompt), healthchecks.lock goes with the lock file of each
    listed monitor; without it, only the targets' lock files go. A monitor whose unpause failed keeps its lock file.
    """
    for monitor in targets:
        if monitor.status != PAUSED:
            ctx.say(f"{plain_text(monitor.name)} is already running")
    outcome = act_on_each(ctx, "Unpausing", [m for m in targets if m.status == PAUSED], ctx.provider.unpause)
    if ctx.lock_files is not None:
        failed = {m.id for m in outcome.failed}
        ids = [m.id for m in (targets if listed is None else listed) if m.id not in failed]
        outcome.lock_errors = remove_locks(ctx, ctx.lock_files, ids, everything=listed is not None)
        if listed is None and ctx.lock_files.all_locked:
            print_error(
                ctx.err,
                f"{LockFiles.ALL_NAME} is still present, so the pinging script skips every check "
                "until you run --unpause all",
            )
    return outcome


def show_monitors(ctx: Context, monitors: Sequence[Monitor], header: str, empty: str) -> None:
    """Print monitors as JSON with --json, else as a table under header, or empty when there are none."""
    if ctx.json_output:
        ctx.say(format_json([m.raw for m in monitors]))
    elif monitors:
        ctx.say(header)
        ctx.say(format_monitor_table(monitors, ctx.provider.id_kind, ctx.color))
    else:
        ctx.say(empty)


def notify_webhook(ctx: Context, paused: Sequence[Monitor]) -> int:
    """Post the paused monitors to the webhook and say so; a webhook failure exits 1 without the provider label."""
    try:
        sent = send_notification(ctx.http, ctx.config.notify, ctx.provider.label, paused, ctx.provider.id_kind)
    except ProviderError as exc:
        print_error(ctx.err, f"webhook: {exc.message}")
        return EXIT_ERROR
    message = "Notification sent." if sent else "Nothing to notify."
    print(message, file=ctx.err if ctx.json_output else ctx.out)
    return EXIT_OK


def action_list(ctx: Context, args: argparse.Namespace) -> int:
    """List every monitor."""
    label = ctx.provider.label
    show_monitors(
        ctx, ctx.provider.list_monitors(), f"The following {label} monitors were found:", "No monitors found."
    )
    return EXIT_OK


def action_find(ctx: Context, args: argparse.Namespace) -> int:
    """List the paused monitors; -f on a terminal offers to unpause them, -w posts them to the webhook."""
    label = ctx.provider.label
    monitors = ctx.provider.list_monitors()
    paused = [m for m in monitors if m.status == PAUSED]
    show_monitors(ctx, paused, f"The following {label} monitors are paused:", f"No {label} monitors are paused.")
    if args.webhook:
        return notify_webhook(ctx, paused)
    if args.find and paused and ctx.interactive and not ctx.json_output and ctx.ask("Unpause them?", assume_yes=False):
        return unpause_monitors(ctx, paused, listed=monitors).exit_code(incomplete=False)
    return EXIT_OK


def action_pause(ctx: Context, args: argparse.Namespace) -> int:
    """Pause monitors, creating their lock files first when the provider uses them."""
    items = parse_targets("--pause", args.pause)
    locks = ctx.lock_files
    if locks is not None:
        locks.prepare()
    targets = select_targets(ctx, items)
    if locks is not None and targets.everything:
        locks.lock_all()

    def pause(monitor: Monitor) -> None:
        """Create the monitor's lock file when needed, then pause it."""
        if locks is not None and not targets.everything:
            locks.lock(monitor.id)
        ctx.provider.pause(monitor)

    outcome = act_on_each(ctx, "Pausing", targets.chosen, pause)
    if outcome.done and ctx.provider.supports_lock_files:
        ctx.say("")
        ctx.say(HC_REMINDER)
    return outcome.exit_code(targets.incomplete)


def action_unpause(ctx: Context, args: argparse.Namespace) -> int:
    """Unpause monitors and remove their lock files; "all" on an empty account still removes healthchecks.lock."""
    try:
        targets = select_targets(ctx, parse_targets("--unpause", args.unpause))
    except NothingToDo:
        if ctx.lock_files is not None:
            remove_locks(ctx, ctx.lock_files, [], everything=True)
        raise
    outcome = unpause_monitors(ctx, targets.chosen, listed=targets.listed if targets.everything else None)
    return outcome.exit_code(targets.incomplete)


def action_info(ctx: Context, args: argparse.Namespace) -> int:
    """Print the full record of one monitor."""
    items = split_selection(args.info)
    if len(items) != 1 or items == ["all"]:
        raise UsageError("--info takes one monitor")
    ctx.say(format_json(ctx.provider.info(select_targets(ctx, items).chosen[0])))
    return EXIT_OK


def action_alerts(ctx: Context, args: argparse.Namespace) -> int:
    """Print the alert contacts."""
    contacts = ctx.provider.alert_contacts()
    if not ctx.json_output:
        ctx.say(f"The following {ctx.provider.label} alert contacts were found:")
    ctx.say(format_json(contacts))
    return EXIT_OK


def action_stats(ctx: Context, args: argparse.Namespace) -> int:
    """Print the account statistics."""
    ctx.say(format_json(ctx.provider.stats()))
    return EXIT_OK


def read_payload(path: Path) -> dict[str, Any]:
    """Return the JSON object in the file at path; a missing file or bad JSON raises ConfigError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read the file: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path}: cannot read the file: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"{path}: must hold a JSON object")
    return payload


def action_create(ctx: Context, args: argparse.Namespace) -> int:
    """Create a monitor from a JSON file and print the new record."""
    ctx.say(format_json(ctx.provider.create(read_payload(args.create))))
    return EXIT_OK


def confirm_and_act(
    ctx: Context, items: list[str], *, question: str, refusal: str, verb: str, step: Callable[[Monitor], object]
) -> int:
    """Select the monitors, ask question (with {count} and {label} filled in), then run step on each."""
    targets = select_targets(ctx, items)
    try:
        agreed = ctx.ask(
            question.format(count=len(targets.chosen), label=ctx.provider.label), assume_yes=ctx.assume_yes
        )
    except NeedsTerminal:
        raise UsageError(f"Refusing to {refusal} without a terminal; pass --yes to confirm.") from None
    if not agreed:
        ctx.say("Cancelled.")
        return EXIT_OK
    return act_on_each(ctx, verb, targets.chosen, step, show_id=False).exit_code(targets.incomplete)


def action_delete(ctx: Context, args: argparse.Namespace) -> int:
    """Delete monitors after asking."""
    return confirm_and_act(
        ctx,
        parse_targets("--delete", args.delete),
        question="Delete {count} monitor(s) from {label}? This cannot be undone.",
        refusal="delete",
        verb="Deleting",
        step=ctx.provider.delete,
    )


def action_reset(ctx: Context, args: argparse.Namespace) -> int:
    """Clear the statistics of monitors after asking; a provider without reset is a usage error."""
    items = parse_targets("--reset", args.reset)
    if not ctx.provider.supports_reset:
        raise Unsupported(f"{ctx.provider.label} does not support reset")
    return confirm_and_act(
        ctx,
        items,
        question="Reset statistics for {count} monitor(s) in {label}? This cannot be undone.",
        refusal="reset",
        verb="Resetting",
        step=ctx.provider.reset,
    )


ACTIONS: dict[str, Callable[[Context, argparse.Namespace], int]] = {
    "list": action_list,
    "find": action_find,
    "no_prompt": action_find,
    "webhook": action_find,
    "stats": action_stats,
    "alerts": action_alerts,
    "info": action_info,
    "create": action_create,
    "pause": action_pause,
    "unpause": action_unpause,
    "delete": action_delete,
    "reset": action_reset,
}


def chosen_action(args: argparse.Namespace) -> Callable[[Context, argparse.Namespace], int]:
    """Return the function for the action option that was given."""
    for name, action in ACTIONS.items():
        if getattr(args, name, None) not in (None, False):
            return action
    raise UsageError("choose an action, for example --list")


def search_paths(env: Mapping[str, str]) -> list[Path]:
    """Return the config file search paths for this script and user."""
    script = Path(__file__).resolve()
    try:
        home = Path.home()
    except RuntimeError:
        return [script.parent / "tronitor.toml"]
    return config_search_paths(script, home, env)


def make_context(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    env: Mapping[str, str],
    interactive: bool,
) -> Context:
    """Load the configuration and build the provider and the context for the action."""
    config = load_config(args.config, env, search_paths(env))
    name = resolve_provider_name(args.provider)
    http = Http(verbose=args.verbose, log=lambda line: print(line, file=stderr))
    provider = make_provider(name, config, http)
    return Context(
        provider=provider,
        config=config,
        http=http,
        out=stdout,
        err=stderr,
        color=use_color(stdout, env, args.no_color),
        json_output=args.json,
        assume_yes=args.yes,
        interactive=interactive,
        lock_files=LockFiles(config.lock_dir) if provider.supports_lock_files else None,
        stdin=stdin,
    )


def run(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    env: Mapping[str, str],
    interactive: bool,
) -> int:
    """Run the action args ask for and turn every error into its message and exit code."""
    ctx: Context | None = None
    try:
        ctx = make_context(args, stdin=stdin, stdout=stdout, stderr=stderr, env=env, interactive=interactive)
        return chosen_action(args)(ctx, args)
    except NothingToDo as exc:
        print(exc, file=stdout)
        return EXIT_OK
    except SelectionProblem as exc:
        print_error(stderr, str(exc))
        return EXIT_PARTIAL
    except (ConfigError, UsageError, Unsupported) as exc:
        print_error(stderr, str(exc))
        return EXIT_USAGE
    except NeedsTerminal as exc:
        print_error(stderr, f'cannot ask "{exc}" without a terminal; pass --yes to confirm')
        return EXIT_USAGE
    except ProviderError as exc:
        label = ctx.provider.label if ctx else ""
        print_error(stderr, exc.message if label in exc.message else f"{label}: {exc.message}")
        return EXIT_ERROR
    except LockError as exc:
        print_error(stderr, str(exc))
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nInterrupted.", file=stderr)
        return EXIT_INTERRUPTED


def main(argv: Sequence[str] | None = None) -> int:
    """Run tronitor with argv (default: sys.argv[1:]) and return the exit code."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    try:
        namespace = parser.parse_args(args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    interactive = is_terminal(sys.stdin) and is_terminal(sys.stdout)
    return run(
        namespace, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, env=os.environ, interactive=interactive
    )


if __name__ == "__main__":
    sys.exit(main())
