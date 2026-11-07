# 🔌 Providers

[← All documentation](README.md)

A provider is the monitoring service that tronitor talks to. tronitor works with two: [Healthchecks](https://healthchecks.io) and [UptimeRobot](https://uptimerobot.com). Choose one with `-m` in each command.

## 📊 What each provider supports

| Action | Healthchecks (`hc`) | UptimeRobot (`ur`) |
| --- | :---: | :---: |
| `-l` list monitors | ✅ | ✅ |
| `-f`, `-n`, `-w` find paused monitors | ✅ | ✅ |
| `-p`, `-u` pause and unpause | ✅ | ✅ |
| `-i` one monitor's record | ✅ | ✅ |
| `-a` alert contacts | ✅ (integrations) | ✅ |
| `-c` create a monitor | ✅ | ✅ |
| `-d` delete monitors | ✅ | ✅ |
| `-s` account statistics | ❌ | ✅ |
| `-r` reset statistics | ❌ | ✅ |
| Lock files for HealthChecks-Linux | ✅ | ❌ |

An action that a provider does not offer stops with a message, for example `Healthchecks does not support stats`, and exit code `2`.

## 💓 Healthchecks

Healthchecks watches jobs that report to it. Each check expects a ping (a signal from the job that it ran) at a regular interval. If no ping comes in time, Healthchecks sends an alert.

- **API:** version 3. tronitor sends its requests to `<url>/api/v3/`, where `url` is the address in your [configuration](configuration.md#-healthchecks): `https://healthchecks.io`, or your own server.
- **API key:** a read-write project API key. tronitor refuses a read-only key with a clear message. See [API keys](configuration.md#-api-keys).
- **IDs:** each check's UUID, a long code such as `31365bce-8da9-4729-8ff3-aaa71d56b712`.
- **Alert contacts:** Healthchecks calls them integrations. `-a` lists them, with their IDs.

> [!IMPORTANT]
> A paused Healthchecks check becomes active again when it next receives a ping. So a job that pings every few minutes ends the pause soon. The lock files exist for this reason: HealthChecks-Linux does not ping a check while its lock file exists. See [Lock files](cron.md#-lock-files).

## 🤖 UptimeRobot

UptimeRobot tests your websites and servers from outside, at a regular interval. It needs nothing on your side, so a paused monitor stays paused until you unpause it.

- **API:** version 3, at `https://api.uptimerobot.com/v3`. tronitor sends the key as a Bearer token: a header with each request that says `Authorization: Bearer <key>`.
- **API key:** the Main API key of your account. See [API keys](configuration.md#-api-keys).
- **IDs:** each monitor's number, such as `1002`.
- **Many monitors:** tronitor reads the list in pages of 200 monitors, and reads up to 100 pages.

## 🟢 Statuses

`-l`, `-f`, `-n` and `-w` show a status for each monitor:

| Status | Provider | Meaning |
| --- | --- | --- |
| up | Both | The monitor works |
| down | Both | The monitor failed, so the provider sends alerts |
| paused | Both | The monitor is paused, so the provider sends no alerts |
| grace | Healthchecks | The check is late: its period has passed, but its grace time (the extra time that Healthchecks waits) has not. It is not down yet |
| new | Healthchecks | The check has never received a ping. A check that you unpause is also new until its next ping |
| pending | UptimeRobot | The monitor is new, and UptimeRobot has not checked it yet |
| seems down | UptimeRobot | UptimeRobot found a failure, and is making sure before it says that the monitor is down |

Any other status is shown without a colour.

`-u` unpauses only the monitors whose status is `paused`. For each other monitor, it prints `<name> is already running`.

## 🚦 Rate limits

A rate limit is the number of requests that a provider accepts in a period of time. When you send more, the provider answers with `HTTP 429` (too many requests) and does nothing.

- **Healthchecks** accepts about 100 requests a minute. tronitor rarely gets near this.
- **UptimeRobot** accepts 10 requests a minute on the free plan. Paid plans accept more.

Each action sends one request to list the monitors, and then one request for each monitor that it changes. So on the free UptimeRobot plan, `-p all` with 10 or more monitors reaches the limit. tronitor reports each request that failed on stderr, and the exit code is `3`. Then wait a minute:

- After `-u all`, run the same command again. It sends requests only for the monitors that are still paused, so each run gets further.
- After `-p all`, run `-p` again with only the monitors that failed. Their names are in the error lines. `-p all` would send a request for every monitor again, and reach the limit at the same place.

## 🆕 New monitors

`-c FILE` sends the JSON object in `FILE` to the provider, as it is. The provider checks the fields and creates the monitor. The `examples` folder has a file to start from for each case:

| File | Monitor |
| --- | --- |
| `examples/healthchecks-check.json` | A Healthchecks check |
| `examples/uptimerobot-http-monitor.json` | An UptimeRobot HTTP monitor, which loads a web page |
| `examples/uptimerobot-keyword-monitor.json` | An UptimeRobot keyword monitor, which looks for a word on a web page |
| `examples/uptimerobot-ping-monitor.json` | An UptimeRobot ping monitor, which pings a server |
| `examples/uptimerobot-port-monitor.json` | An UptimeRobot port monitor, which connects to a port of a server |

Copy a file, change its values, and give the copy to `-c`:

```bash
tronitor -m hc -c my-check.json
```

### 💓 A Healthchecks check

tronitor sends the file to `POST /api/v3/checks/`. This is the example file:

```json
{
  "name": "Backups",
  "tags": "prod backup",
  "timeout": 3600,
  "grace": 60
}
```

These are the common fields:

| Field | What it is |
| --- | --- |
| `name` | The name of the check |
| `tags` | Tags, separated by spaces |
| `timeout` | The period, in seconds: the time that Healthchecks expects between two pings |
| `grace` | The grace time, in seconds: how long Healthchecks waits after a late ping before the check is down |
| `schedule` | A cron expression, such as `"0 2 * * *"`, to use instead of `timeout` |
| `tz` | The time zone of `schedule`, such as `"Europe/Berlin"` |
| `channels` | The integrations that get the alerts: their IDs from `-a`, separated by commas, or `"*"` for all of them |

The [Healthchecks API documentation](https://healthchecks.io/docs/api/) lists every field.

### 🤖 An UptimeRobot monitor

tronitor sends the file to `POST /v3/monitors`. This is the example file for an HTTP monitor:

```json
{
  "friendlyName": "Example",
  "url": "https://example.com",
  "type": "HTTP",
  "interval": 300,
  "timeout": 30
}
```

Each type of monitor needs these fields:

| Field | What it is |
| --- | --- |
| `friendlyName` | The name of the monitor |
| `url` | The address to test. For a ping or port monitor, the name or IP address of the server, such as `example.com` |
| `type` | `HTTP`, `KEYWORD`, `PING` or `PORT` |
| `interval` | The time between two tests, in seconds |
| `timeout` | How long UptimeRobot waits for an answer, in seconds |

A keyword monitor also needs these fields:

| Field | What it is |
| --- | --- |
| `keywordType` | `ALERT_EXISTS` sends an alert when the word is on the page. `ALERT_NOT_EXISTS` sends an alert when it is not |
| `keywordCaseType` | `CaseSensitive` or `CaseInsensitive`: whether capital letters matter |
| `keywordValue` | The word or phrase to look for |

A port monitor also needs `port`, the number of the port, such as `443`.

To choose the alert contacts of the new monitor, add the `assignedAlertContacts` field. It uses the IDs that `-a` shows; see [UptimeRobot's API documentation](https://uptimerobot.com/api/v3/) for the format. That page also lists every other field.

## 🧩 Adding a provider

Each provider is a class in `tronitor.py`. To add one:

1. Write a subclass of `Provider`. Set its `label` (the name in messages) and `id_kind` (what its IDs are called, such as `UUID`). Set `supports_lock_files` and `supports_reset` if they apply.
2. Write its methods: `list_monitors`, `pause`, `unpause`, `info`, `alert_contacts`, `create` and `delete`, and `stats` and `reset` if the provider has them. Also write `is_id`, which tells an ID from a name. `list_monitors` turns each of the provider's records into a `Monitor`, with one of the statuses above.
3. Send every request through the `Http` class, which turns each network or API failure into a `ProviderError`.
4. Add the provider to `make_provider` and to `PROVIDER_NAMES`, with a short name.
5. Add its table and keys to `KNOWN_KEYS`, its settings to the configuration code, and an environment variable for its key.
6. Add tests against the fake server, and update these pages.

Please [open a feature request](https://github.com/tronyx/tronitor/issues/new?template=feature_request.yml) before you start, so that we can agree on the approach. The [contributing guide](../.github/CONTRIBUTING.md) has the rest.

## 👋 Removed providers

The Bash version of tronitor also worked with two other providers. The Python version does not:

- **StatusCake.** StatusCake shut down the API that tronitor used in October 2022. In the four years after that, nobody filed an issue about it.
- **Upptime.** Upptime runs its monitors in a GitHub workflow, a scheduled job in your Upptime repository on GitHub. tronitor "paused" Upptime by turning that workflow off, which stopped all its monitors at once. It needed a GitHub token, and it had no monitors to pause one by one. This niche feature did not fit the rest of the script, so the rewrite did not carry it over.

If you need one of them, [open a feature request](https://github.com/tronyx/tronitor/issues/new?template=feature_request.yml).

## ⏳ Uptime Kuma

[Uptime Kuma](https://github.com/louislam/uptime-kuma) is a monitoring tool that you host yourself. tronitor does not work with it yet. As of version 2.5.9, Uptime Kuma has no REST API (a set of web addresses that a program can call) to pause and resume monitors. Its web interface uses Socket.IO instead, a two-way connection that needs a login with a username and password.

A read-only REST API is on its master branch, in no release yet. Write endpoints are proposed in [pull request 3854](https://github.com/louislam/uptime-kuma/pull/3854) ([issue 7151](https://github.com/louislam/uptime-kuma/issues/7151) was closed in its favour). tronitor will add Uptime Kuma when a release has an API that can pause and resume monitors.
