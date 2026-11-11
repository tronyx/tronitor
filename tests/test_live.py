"""Live tests against real Healthchecks and UptimeRobot accounts.

These tests create, pause, unpause and delete real monitors, so they run only when credentials are set:

- Healthchecks: TRONITOR_LIVE_HEALTHCHECKS_URL and TRONITOR_LIVE_HEALTHCHECKS_API_KEY (a read-write key).
- UptimeRobot: TRONITOR_LIVE_UPTIMEROBOT_API_KEY.

Without the variables every test is skipped, and GitHub never runs them. They create only monitors named
"tronitor-test-<8 hex characters>" and, at teardown, delete only monitors whose name starts with "tronitor-test-",
even when an assertion fails. They never touch any other monitor.

The UptimeRobot free plan allows 10 requests per minute, so each UptimeRobot test makes at most 10 calls when the
monitor list is up to date, and the fixture waits until 60 seconds have passed since the previous UptimeRobot test
finished. The round trip asks for the list again every 20 seconds, for up to 2 minutes, while a new or deleted
monitor has not reached UptimeRobot's cached list yet. Those tests therefore take two minutes or more, and the
round trip up to about six. On a 429, tronitor itself waits and
retries once; if the second try is a 429 too, the test is skipped instead of failed.

Run them with, for example:

    export TRONITOR_LIVE_HEALTHCHECKS_URL=https://hc.example.com
    export TRONITOR_LIVE_HEALTHCHECKS_API_KEY=...
    python -m pytest tests/test_live.py -v

The UptimeRobot round trip creates its monitor from examples/uptimerobot-http-monitor.json, with the test name in
place of its friendlyName, so a live run also tests the example file.
"""

import json
import os
import secrets
import sys
import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import pytest

import tronitor

HC_URL = os.environ.get("TRONITOR_LIVE_HEALTHCHECKS_URL", "").rstrip("/")
HC_KEY = os.environ.get("TRONITOR_LIVE_HEALTHCHECKS_API_KEY", "")
UR_KEY = os.environ.get("TRONITOR_LIVE_UPTIMEROBOT_API_KEY", "")

TEST_PREFIX = "tronitor-test-"
UR_HTTP_EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "uptimerobot-http-monitor.json"
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
    """Delete stale tronitor-test-* checks left by earlier runs; Healthchecks allows about 100 requests a minute."""
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


def send_ping(monitor: tronitor.Monitor) -> None:
    """Ping a check at the ping_url from its record, as a job would.

    Bandit warns that urlopen also opens file: and custom schemes. The URL is the check's own ping_url, from the
    Healthchecks server that the live tests use. The nosec marker tells Bandit (via CodeFactor) that this is safe.
    """
    with urllib.request.urlopen(str(monitor.raw["ping_url"]), timeout=30) as response:  # nosec B310
        assert response.status == 200, f"the ping answered {response.status}"


@needs_hc
def test_hc_paused_pings_round_trip(hc_live: tronitor.HealthchecksProvider) -> None:
    """With manual_resume set, a ping leaves a paused check paused; set back, the next ping resumes it."""
    uuid = create_test_monitor(hc_live, {"name": make_name(), "tags": "tronitor-test", "timeout": 3600}).id

    monitor = find(hc_live, uuid)
    assert monitor is not None
    assert monitor.raw.get("manual_resume") is False, "a new check does not resume on a ping by default"

    hc_live.set_manual_resume(monitor, True)
    hc_live.pause(monitor)
    send_ping(monitor)
    ignored = find(hc_live, uuid)
    assert ignored is not None
    assert ignored.raw.get("manual_resume") is True, "the list does not show the new setting"
    assert ignored.status == tronitor.PAUSED, "a ping resumed a check that ignores pings while paused"

    hc_live.set_manual_resume(ignored, False)
    send_ping(ignored)
    resumed = find(hc_live, uuid)
    assert resumed is not None
    assert resumed.raw.get("manual_resume") is False
    assert resumed.status == "up", "a ping did not resume a check that resumes on a ping"

    delete_test_monitor(hc_live, resumed)


@needs_hc
def test_hc_alert_contacts_is_a_list(hc_live: tronitor.HealthchecksProvider) -> None:
    """The integrations come back as a list of dicts."""
    contacts = hc_live.alert_contacts()
    assert isinstance(contacts, list), "the integrations are not a list"
    assert all(isinstance(contact, dict) for contact in contacts), "an integration is not a dict"


UR_LIST_WAIT = 20.0
UR_LIST_TIMEOUT = 120.0


def find_listed(provider: tronitor.Provider, monitor_id: str, *, present: bool) -> tronitor.Monitor | None:
    """Return the monitor with this ID from the list, asking every 20 seconds for up to 120 seconds, until it is
    there (present) or gone (not present).

    UptimeRobot serves the list from a cache for each account. In the live run it showed the old status for about
    two minutes (stale at 107 seconds, current at 122), so a monitor that was just created or deleted can take that
    long to appear in the list or leave it. Up to 7 list requests in 2 minutes stay under the free plan's limit,
    and tronitor's own retry covers a 429 on the way.
    """
    deadline = time.monotonic() + UR_LIST_TIMEOUT
    while True:
        monitor = find(provider, monitor_id)
        if (monitor is not None) == present or time.monotonic() + UR_LIST_WAIT > deadline:
            return monitor
        time.sleep(UR_LIST_WAIT)


@needs_ur
def test_ur_round_trip(ur_live: tronitor.UptimeRobotProvider) -> None:
    """Create an HTTP monitor, pause it, start it, reset it, read it and delete it.

    The status after pause and start is read with info (GET /monitors/{id}), not from the list: UptimeRobot serves
    the list from a cache that showed the old status for about two minutes after a pause in a live run (still stale
    at 107 seconds, current at 122), while the monitor's own record changes at once. The list is used only to see
    that the monitor appears after create and goes after delete. The test makes 9 requests when the list is up to
    date at once.
    """
    name = make_name()
    body: dict[str, Any] = json.loads(UR_HTTP_EXAMPLE.read_text(encoding="utf-8"))
    body["friendlyName"] = name
    with skip_on_rate_limit():
        monitor_id = create_test_monitor(ur_live, body).id

        monitor = find_listed(ur_live, monitor_id, present=True)
        assert monitor is not None, "the new monitor is not in the list after 2 minutes"
        assert monitor.name == name
        assert monitor.status in tronitor.UR_STATUS.values()

        ur_live.pause(monitor)
        assert str(ur_live.info(monitor)["status"]).upper() == "PAUSED", "the monitor is not paused"

        ur_live.unpause(monitor)
        record = ur_live.info(monitor)
        assert str(record["id"]) == monitor_id, "info returned another monitor"
        assert str(record["status"]).upper() != "PAUSED", "the monitor is still paused"

        ur_live.reset(monitor)

        delete_test_monitor(ur_live, monitor)
        assert find_listed(ur_live, monitor_id, present=False) is None, "the deleted monitor is still in the list"


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
