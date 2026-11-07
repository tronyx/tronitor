# ⏸️ tronitor

[![Tests](https://img.shields.io/github/actions/workflow/status/tronyx/tronitor/tests.yml?branch=master&label=tests)](https://github.com/tronyx/tronitor/actions/workflows/tests.yml?query=branch%3Amaster)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](docs/installation.md#-requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE.md)

tronitor pauses and unpauses your [Healthchecks](https://healthchecks.io) and [UptimeRobot](https://uptimerobot.com) monitors from the command line. Pause them before a backup or an update, and unpause them when it is done, so that nobody gets an alert for a planned outage. Run it by hand, or from cron on a schedule. So you get your own maintenance windows, also on a free plan.

## ✨ Features

- ⏸️ It pauses and unpauses monitors by name, by ID, or all at once.
- 🔍 It finds the paused monitors, and can post them to a Discord or Slack channel, so that a forgotten pause does not go unseen.
- 🔒 For Healthchecks, it writes lock files that the [HealthChecks-Linux](https://github.com/tronyx/HealthChecks-Linux) pinging script reads, so that a paused check stays paused.
- ⏰ It is made for cron. It never waits for an answer without a terminal, it reports each failure on stderr, and its exit codes tell a script what happened.
- 🛡️ It asks before it deletes or resets monitors. Unless you pass `--yes`, it changes nothing when a name matches no monitor, and never when a name matches more than one.
- 🧰 It also lists monitors, shows their records, creates and deletes monitors, and lists alert contacts. `--json` gives the data to other programs.
- 🧩 It is one file. It needs Python 3.11 or newer and nothing else, and it works on Linux, macOS and Windows.

## 🚀 Quick start

You need Python 3.11 or newer.

1. Copy `tronitor.py` and `tronitor.example.toml` to a folder, or clone the repository:

   ```bash
   git clone -b master https://github.com/tronyx/tronitor.git
   cd tronitor
   ```

2. Make your config file. On Linux and macOS, also make it readable only by you, because it holds your keys:

   ```bash
   cp tronitor.example.toml tronitor.toml
   chmod 600 tronitor.toml
   ```

   Upgrading from `tronitor.sh`? `python3 tronitor.py --migrate tronitor.sh` writes `tronitor.toml` from its settings; see [Upgrading](docs/usage.md#-upgrading-from-the-bash-script).

3. Open `tronitor.toml` and fill in your API key: a read-write project API key for Healthchecks, or the Main API key for UptimeRobot. [Configuration](docs/configuration.md#-api-keys) tells you where to find them.

4. List your monitors, then pause and unpause all of them:

   ```bash
   python3 tronitor.py -m hc -l
   python3 tronitor.py -m hc -p all
   python3 tronitor.py -m hc -u all
   ```

For UptimeRobot, type `-m ur` instead of `-m hc`. On Windows, type `py` instead of `python3`. [Installation](docs/installation.md) has the details.

## ⚙️ Common options

| Option | What it does |
| --- | --- |
| `-m PROVIDER` | The provider: `healthchecks` (`hc`) or `uptimerobot` (`ur`). Every command needs it, except `--migrate` |
| `-l` | List every monitor and its status |
| `-f` | List the paused monitors. On a terminal, offer to unpause them |
| `-n` | List the paused monitors, and never ask |
| `-w` | List the paused monitors and post them to the Discord or Slack webhook |
| `-p TARGETS` | Pause monitors: `all`, or names and IDs separated by commas, such as `-p "Filesystem Backup,Database Backup"` |
| `-u TARGETS` | Unpause monitors, in the same way |
| `--yes` | Delete or reset without asking. Also act on the monitors that were found when some were not |
| `--json` | Print the provider's records as JSON instead of a table |

A name must match the whole monitor name, but capital letters do not matter. [Usage](docs/usage.md#-all-options) describes all the options. The `--help` option also lists them.

## ⏰ From cron

To pause every Healthchecks check during a nightly backup, add lines like these to your crontab (`crontab -e`). `/opt/tronitor` is an example (use your own path):

```text
# Pause at 01:55, before the 02:00 backup
55 1 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -p all > /dev/null
# Unpause at 04:00, when the backup is done
0 4 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -u all > /dev/null
# At 08:00, post any paused checks to the webhook
0 8 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -w > /dev/null
```

`> /dev/null` discards the normal output, but errors still reach you through cron's mail, when your system sends it. A paused Healthchecks check becomes active again at its next ping, so point HealthChecks-Linux at tronitor's lock folder. [Running from cron](docs/cron.md) tells you how.

## 📖 Documentation

| Page | Contents |
| --- | --- |
| [📦 Installation](docs/installation.md) | Requirements, how to get the script, how to run it, and how to update it |
| [🔑 Configuration](docs/configuration.md) | The config file and where tronitor looks for it, every setting, the environment variables, and the API keys |
| [🚀 Usage](docs/usage.md) | How to name monitors, all the options, what each action prints, sample output, and exit codes |
| [⏰ Running from cron](docs/cron.md) | Maintenance windows, the Healthchecks lock files and HealthChecks-Linux, crontab lines, and what happens when something fails |
| [🔌 Providers](docs/providers.md) | Healthchecks and UptimeRobot: what each one supports, API keys, statuses, rate limits, and new monitors. How to add a provider, and the providers that were removed |
| [🩺 Troubleshooting](docs/troubleshooting.md) | What each message means, and what to do |
| [🧪 How it is tested](docs/testing.md) | The tests, and the tests that GitHub runs on each change |

## 🔌 Providers

tronitor works with [Healthchecks](https://healthchecks.io), on healthchecks.io or on a server that you host yourself, and with [UptimeRobot](https://uptimerobot.com). Both use version 3 of their APIs.

The Bash version of tronitor also worked with two other providers, which the Python version dropped:

- **StatusCake:** StatusCake shut down the API that tronitor used in October 2022, and nobody filed an issue about it in the four years since.
- **Upptime:** tronitor paused Upptime by turning off its GitHub workflow, a niche feature that the rewrite did not carry over.

[Uptime Kuma](https://github.com/louislam/uptime-kuma) has no API to pause and resume monitors yet. tronitor will add it when it does. [Providers](docs/providers.md) has the details.

## 🧪 How it is tested

Each change goes through tests on Linux, macOS and Windows. On Linux, the tests use both the oldest and the newest Python version that tronitor supports. The tests run the script against a fake server that answers like Healthchecks and UptimeRobot, so they need no account. Live tests against real accounts are also available, and the docs tests check every link in these pages. For more information, see [How it is tested](docs/testing.md).

## 🤝 Contributing

You can send bug reports, ideas, and pull requests. The [contributing guide](.github/CONTRIBUTING.md) tells you how. Do not open an issue to report a security vulnerability, because issues are public. Use the procedure in the [security policy](.github/SECURITY.md) instead. The [changelog](CHANGELOG.md) lists the changes in each release.

## 🙏 Thanks

Big thanks to [nemchik](https://github.com/GhostWriters/DockSTARTer/commits?author=nemchik) for all the ideas and the help with getting things to work in the original Bash script, and to [1activegeek](https://github.com/1activegeek) for asking me to create it for him in the first place. Feel free to check out their work and buy them a beer too!

## 🤖 A note on how this was built

This version of tronitor was largely written with [Claude](https://claude.ai), Anthropic's AI coding assistant. I described what I needed, directed the design, and asked for changes across many iterations rather than writing most of the code by hand. It is tested against mocked APIs (a fake server that answers like Healthchecks and UptimeRobot) and against my own Healthchecks instance. The UptimeRobot side is tested against the mocked API only, until I run the live tests against a real account.

I'd rather say that plainly than let it pass as fully hand-written. There's a lot of AI-generated code floating around that hasn't been reviewed or tested and ends up breaking people's setups, and I don't want this to be mistaken for that. If something looks off, please [open an issue](https://github.com/tronyx/tronitor/issues).

## 📄 License

The license is MIT. See [LICENSE.md](LICENSE.md).
