"""Live tests against real Healthchecks and UptimeRobot accounts.

These tests create, pause, unpause and delete real monitors, so they run only when credentials are set:

- Healthchecks: TRONITOR_LIVE_HEALTHCHECKS_URL and TRONITOR_LIVE_HEALTHCHECKS_API_KEY (a read-write key).
- UptimeRobot: TRONITOR_LIVE_UPTIMEROBOT_API_KEY.

Without the variables every test is skipped, and GitHub never runs them. They create only monitors named
"tronitor-test-<8 hex characters>" and, at teardown, delete only monitors whose name starts with "tronitor-test-",
even when an assertion fails. They never touch any other monitor.

The UptimeRobot free plan allows 10 requests per minute, so each UptimeRobot test makes at most 10 calls and the
fixture waits until 60 seconds have passed since the previous UptimeRobot test finished. Those tests therefore take
about two minutes. If the limit is hit anyway (HTTP 429), the test is skipped instead of failed.

Run them with, for example:

    export TRONITOR_LIVE_HEALTHCHECKS_URL=https://hc.example.com
    export TRONITOR_LIVE_HEALTHCHECKS_API_KEY=...
    python -m pytest tests/test_live.py -v

The UptimeRobot create body is built inline because the examples directory does not exist yet.
"""

import os
import secrets
import sys
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager, suppress
from typing import Any

import pytest

import tronitor

HC_URL = os.environ.get("TRONITOR_LIVE_HEALTHCHECKS_URL", "").rstrip("/")
HC_KEY = os.environ.get("TRONITOR_LIVE_HEALTHCHECKS_API_KEY", "")
UR_KEY = os.environ.get("TRONITOR_LIVE_UPTIMEROBOT_API_KEY", "")

TEST_PREFIX = "tronitor-test-"
UR_SPACING = 60.0

CREATED: list[tuple[tronitor.Provider, tronitor.Monitor]] = []
_last_ur_start: float | None = None

needs_hc = pytest.mark.skipif(
    not (HC_URL and HC_KEY),
    reason="set TRONITOR_LIVE_HEALTHCHECKS_URL and TRONITOR_LIVE_HEALTHCHECKS_API_KEY to run",
)
needs_ur = pytest.mark.skipif(not UR_KEY, reason="set TRONITOR_LIVE_UPTIMEROBOT_API_KEY to run")


def make_name() -> str:
    """Return a fresh name for a test monitor."""
    return f"{TEST_PREFIX}{secrets.token_hex(4)}"


def create_test_monitor(provider: tronitor.Provider, payload: dict[str, Any]) -> tronitor.Monitor:
    """Create a monitor, record it for teardown and return it."""
    record = provider.create(payload)
    is_ur = isinstance(provider, tronitor.UptimeRobotProvider)
    name = str(payload["friendlyName" if is_ur else "name"])
    found = record.get("id" if is_ur else "uuid")
    if found is None:
        raise AssertionError(f"create returned no id for {name}; delete it by hand")
    monitor_id = str(found)
    monitor = tronitor.Monitor(id=monitor_id, name=name, status=str(record.get("status", "")), raw=record)
    CREATED.append((provider, monitor))
    return monitor


def _delete_with_retry(provider: tronitor.Provider, monitor: tronitor.Monitor) -> bool:
    """Delete a monitor; after a 429, wait 60 seconds and try once more. Return True on success."""
    for attempt in range(2):
        try:
            provider.delete(monitor)
        except tronitor.ProviderError as error:
            if error.status == 429 and attempt == 0:
                time.sleep(UR_SPACING)
                continue
            return False
        return True
    return False


def _clean_up(provider: tronitor.Provider) -> None:
    """Delete the monitors recorded for this provider, one failure never hiding the others, never raising."""
    for pair in [pair for pair in CREATED if pair[0] is provider]:
        CREATED.remove(pair)
        if pair[1].name.startswith(TEST_PREFIX) and not _delete_with_retry(provider, pair[1]):
            monitor = pair[1]
            print(f"could not delete test monitor {monitor.name} ({monitor.id}); delete it by hand", file=sys.stderr)


def _sweep_healthchecks(provider: tronitor.Provider) -> None:
    """Delete stale tronitor-test-* checks left by earlier runs; Healthchecks has no rate limit."""
    try:
        monitors = provider.list_monitors()
    except tronitor.ProviderError:
        return
    for monitor in monitors:
        if monitor.name.startswith(TEST_PREFIX):
            with suppress(tronitor.ProviderError):
                provider.delete(monitor)


@pytest.fixture
def hc_live() -> Iterator[tronitor.HealthchecksProvider]:
    """Yield a Healthchecks provider for the live account and delete the test checks afterwards."""
    provider = tronitor.HealthchecksProvider(tronitor.Http(), tronitor.HealthchecksConfig(HC_URL, HC_KEY))
    try:
        yield provider
    finally:
        _clean_up(provider)
        _sweep_healthchecks(provider)


@pytest.fixture
def ur_live() -> Iterator[tronitor.UptimeRobotProvider]:
    """Yield an UptimeRobot provider, 60 seconds after the previous UptimeRobot test finished; clean up afterwards."""
    global _last_ur_start
    if _last_ur_start is not None:
        time.sleep(max(0.0, _last_ur_start + UR_SPACING - time.monotonic()))
    provider = tronitor.UptimeRobotProvider(tronitor.Http(), tronitor.UptimeRobotConfig(UR_KEY))
    try:
        yield provider
    finally:
        _clean_up(provider)
        _last_ur_start = time.monotonic()


@contextmanager
def skip_on_rate_limit() -> Generator[None, None, None]:
    """Skip the test, instead of failing it, when UptimeRobot answers 429."""
    try:
        yield
    except tronitor.ProviderError as error:
        if error.status == 429:
            pytest.skip("the UptimeRobot rate limit (10 requests per minute) was hit; wait a minute and run again")
        raise


def find(provider: tronitor.Provider, monitor_id: str) -> tronitor.Monitor | None:
    """Return the monitor with this ID from a fresh listing, or None."""
    for monitor in provider.list_monitors():
        if monitor.id == monitor_id:
            return monitor
    return None


def delete_test_monitor(provider: tronitor.Provider, monitor: tronitor.Monitor) -> None:
    """Delete a monitor, refusing to touch one that is not a test monitor."""
    assert monitor.name.startswith(TEST_PREFIX), "refusing to delete a monitor that is not a test monitor"
    provider.delete(monitor)
    CREATED[:] = [pair for pair in CREATED if not (pair[0] is provider and pair[1].id == monitor.id)]


@needs_hc
def test_hc_round_trip(hc_live: tronitor.HealthchecksProvider) -> None:
    """Create a check, pause it, resume it twice, read it, delete it, checking a fresh listing each time."""
    name = make_name()
    uuid = create_test_monitor(hc_live, {"name": name, "tags": "tronitor-test", "timeout": 3600, "grace": 60}).id

    monitor = find(hc_live, uuid)
    assert monitor is not None
    assert monitor.name == name
    assert monitor.status == "new"

    hc_live.pause(monitor)
    paused = find(hc_live, uuid)
    assert paused is not None
    assert paused.status == tronitor.PAUSED

    hc_live.unpause(paused)
    resumed = find(hc_live, uuid)
    assert resumed is not None
    assert resumed.status == "new"

    hc_live.unpause(resumed)

    assert hc_live.info(resumed)["uuid"] == uuid, "info returned another check"

    delete_test_monitor(hc_live, resumed)
    assert find(hc_live, uuid) is None


@needs_hc
def test_hc_alert_contacts_is_a_list(hc_live: tronitor.HealthchecksProvider) -> None:
    """The integrations come back as a list of dicts."""
    contacts = hc_live.alert_contacts()
    assert isinstance(contacts, list), "the integrations are not a list"
    assert all(isinstance(contact, dict) for contact in contacts), "an integration is not a dict"


@needs_ur
def test_ur_round_trip(ur_live: tronitor.UptimeRobotProvider) -> None:
    """Create an HTTP monitor, pause it, start it, reset it, read it and delete it."""
    name = make_name()
    body: dict[str, Any] = {
        "friendlyName": name,
        "url": "https://example.com",
        "type": "HTTP",
        "interval": 300,
        "timeout": 30,
    }
    with skip_on_rate_limit():
        monitor_id = create_test_monitor(ur_live, body).id

        monitor = find(ur_live, monitor_id)
        assert monitor is not None
        assert monitor.name == name
        assert monitor.status in tronitor.UR_STATUS.values()

        ur_live.pause(monitor)
        paused = find(ur_live, monitor_id)
        assert paused is not None
        assert paused.status == tronitor.PAUSED

        ur_live.unpause(paused)
        running = find(ur_live, monitor_id)
        assert running is not None
        assert running.status != tronitor.PAUSED

        ur_live.reset(running)

        assert str(ur_live.info(running)["id"]) == monitor_id, "info returned another monitor"

        delete_test_monitor(ur_live, running)
        assert find(ur_live, monitor_id) is None


@needs_ur
def test_ur_status_values_are_known(ur_live: tronitor.UptimeRobotProvider) -> None:
    """Every status in the account maps to a known value; the message lists the raw values seen."""
    with skip_on_rate_limit():
        monitors = ur_live.list_monitors()
    seen = sorted({str(monitor.raw["status"]) for monitor in monitors})
    unknown = [monitor.status for monitor in monitors if monitor.status not in tronitor.UR_STATUS.values()]
    assert not unknown, f"unknown UptimeRobot status values; raw values seen: {seen}"


@needs_ur
def test_ur_stats_and_alert_contacts(ur_live: tronitor.UptimeRobotProvider) -> None:
    """The account record has the email and monitor limit, and the alert contacts are a list."""
    with skip_on_rate_limit():
        stats = ur_live.stats()
        contacts = ur_live.alert_contacts()
    assert isinstance(stats, dict), "the account record is not a dict"
    assert "email" in stats, "no email in the account record"
    assert "monitorLimit" in stats, "no monitorLimit in the account record"
    assert isinstance(contacts, list), "the alert contacts are not a list"
