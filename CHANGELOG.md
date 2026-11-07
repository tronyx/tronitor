# 📜 Changelog

The notable changes to tronitor, newest first.

The project doesn't use version numbers. Each entry is one merge into `master`, which always has the latest release, and links to its pull request for the full details. `--version` prints the date of the release instead. Changes waiting on `develop` are listed under **Unreleased**.

## Unreleased

tronitor is rewritten in Python. The commands are mostly the same, but some changes break existing setups. Read the lines marked **Breaking** before you update.

### Changed

- tronitor is now a Python script, `tronitor.py`. It needs Python 3.11 or newer and nothing else. The Bash script, `tronitor.sh`, is gone, and with it the need for curl and jq. tronitor now works on Linux, macOS and Windows. See [Installation](docs/installation.md).
- **Breaking:** the settings are in a config file, `tronitor.toml`, or in environment variables. Before, you edited variables at the top of the script, or the script asked for each missing key and wrote it into itself. Now tronitor never asks for a key, and never changes itself. Copy `tronitor.example.toml` to `tronitor.toml`, and fill in your keys. tronitor reports an unknown key in the file, with the nearest known name. See [Configuration](docs/configuration.md).
- **Breaking:** the Healthchecks lock files are in `/tmp` by default, not in `~/tronitor/`. On Windows, they are in your `TEMP` folder. `/tmp` matches the default `tempDir='/tmp/'` of HealthChecks-Linux. If you changed `tempDir` to `/tmp/tronitor/` for the Bash version, change it back, or set `lock_dir` in `tronitor.toml` to the same folder. tronitor no longer uses the `~/tronitor/` folder of the Bash version, so you can delete it. `lock_dir` must be an absolute path, and a `~` at its start stands for your home folder. tronitor refuses a relative path, because under cron it would point at another folder. See [Lock files](docs/cron.md#-lock-files).
- **Breaking:** a name must match the whole monitor name. Before, part of a name could match a longer name. Capital letters still do not matter. A name that two monitors share, or a name that matches no monitor, stops the command before anything changes. tronitor lists the IDs of monitors that share a name. With `--yes`, it acts on the monitors that it found. See [Naming monitors](docs/usage.md#-naming-monitors).
- **Breaking:** tronitor uses version 3 of the UptimeRobot API, instead of version 2. It needs the Main API key of your account, which it sends as a Bearer token. Files for new monitors use the fields of version 3, such as `friendlyName` and `"type": "HTTP"`. If UptimeRobot sends a status that tronitor does not know, `-l`, `-f`, `-n` and `-w` say so on stderr. See [Confirmed against a live account](docs/providers.md#-confirmed-against-a-live-account).
- **Breaking:** tronitor uses version 3 of the Healthchecks API, instead of version 1. It needs a read-write project API key. It refuses a read-only key with a clear message.
- **Breaking:** `-c` takes the path of a JSON file, such as `-c examples/uptimerobot-http-monitor.json`. Before, it took a type of monitor, such as `-c http`, and read a file in the `Templates` folder.
- You set a self-hosted Healthchecks server with `url` in `tronitor.toml`. Before, you edited a line of the script.
- The webhook settings are in the `[notify]` table: `webhook_url`, `format` and `notify_all`. `format` chooses a Discord embed or a Slack text message. tronitor never prints the webhook address, not even with `--verbose`. It refuses an address with a space or a control character inside it.
- `-l`, `-f`, `-n` and `-w` print a table of names, IDs and statuses, instead of the providers' JSON answers. The status has a colour on a terminal only. The setting for jq is gone.
- `-p` and `-u` print one line for each monitor, instead of each API answer. On Healthchecks, `-u all` unpauses only the paused checks, and says `<name> is already running` for the others.
- On UptimeRobot, `-u` starts every monitor that you select, without checking its status in the list. UptimeRobot's list can show an old status for about two minutes after a pause, and starting a monitor that runs already does no harm. See [The monitor list can be out of date](docs/providers.md#-the-monitor-list-can-be-out-of-date).
- `-d` and `-r` ask `[y/N]` before they act. Without a terminal, for example in cron, they refuse unless you give `--yes`. `-f` asks only on a terminal, and acts like `-n` without one.
- Errors go to stderr and start with `tronitor:`, apart from the indented lines of a list and the `Interrupted.` line. A failed action on one monitor goes to stderr too, so a cron job that discards the normal output still gets it. tronitor continues with the other monitors.
- tronitor does not follow HTTP redirects, so your keys go only to the addresses that you set. A server that redirects gives `HTTP 301` or `HTTP 302`. See [Troubleshooting](docs/troubleshooting.md#other-http-codes).
- The exit codes have fixed meanings: `0` success, `1` an API, network or lock folder error, `2` wrong arguments or configuration, `3` some monitors not found or some actions failed, and `130` Ctrl+C. See [Exit codes](docs/usage.md#-exit-codes).

### Added

- `--config PATH`, and the `TRONITOR_CONFIG` environment variable, choose the config file. Without them, tronitor looks next to the script, then in your user config folder.
- `--yes` deletes or resets without asking, and acts on the monitors that were found when some were not.
- `--json` prints the providers' records as JSON instead of the table.
- `--no-color`, and the `NO_COLOR` environment variable, turn off the colours.
- `--verbose` shows each API request on stderr.
- `--provider` is another name for `-m` and `--monitor`.
- `--version` shows the date of the release.
- `tronitor.py` starts with a `#!/usr/bin/env python3` line and is executable, so on Linux and macOS `./tronitor.py` works without `python3` in front, and a symbolic link on your PATH lets you type `tronitor`. See [Running it](docs/installation.md#%EF%B8%8F-running-it).
- On a Python older than 3.11, tronitor stops with `Python 3.11 or newer is needed, but /usr/bin/python3 is Python 3.10.12` and exit code `2`, instead of a traceback about `tomllib`. See [Python version](docs/troubleshooting.md#-python-version).
- `--migrate PATH` writes `tronitor.toml` from the settings at the top of an old `tronitor.sh`, and says what it carried over and what it dropped. It needs no `-m`. See [Upgrading from the Bash script](docs/usage.md#-upgrading-from-the-bash-script).
- Environment variables for the keys, the addresses and the lock folder: `TRONITOR_HEALTHCHECKS_URL`, `TRONITOR_HEALTHCHECKS_API_KEY`, `TRONITOR_UPTIMEROBOT_API_KEY`, `TRONITOR_WEBHOOK_URL` and `TRONITOR_LOCK_DIR`.
- On an `HTTP 429` (too many requests) from UptimeRobot, tronitor waits for the time that UptimeRobot asks for, up to 60 seconds, and retries once. So `-p all` works on a free account of any size, but it takes about a minute for every ten monitors. See [Rate limits](docs/providers.md#-rate-limits).
- The Discord message lists at most 25 monitors. With more, its last line says `and N more`.
- An unpause of Healthchecks checks by name warns you when `healthchecks.lock` is still there from `-p all`, because it still silences every check.
- The `examples` folder has a file to start from for a Healthchecks check and for each type of UptimeRobot monitor. It replaces the `Templates` folder.
- The [documentation](docs/README.md) in the `docs` folder: installation, configuration, every option, cron, the providers, troubleshooting and the tests.
- Tests against a fake server, which run on Linux, macOS and Windows on each push and each week, and live tests against real accounts. GitHub also runs ruff, mypy, actionlint and markdownlint. See [How it is tested](docs/testing.md).

### Removed

- **StatusCake.** StatusCake shut down the API that tronitor used in October 2022, and nobody filed an issue about it in the four years since.
- **Upptime.** tronitor paused Upptime by turning off its GitHub workflow. This niche feature did not fit the rest of the script, so the rewrite did not carry it over.
- The `Templates` folder, which the `examples` folder replaces, and the `Images` folder of screenshots of the Bash script.
- The Travis CI build, which GitHub Actions replaces.

> [!NOTE]
> Uptime Kuma is not supported yet. It has no REST API to pause and resume monitors. tronitor will add it when it does. See [Uptime Kuma](docs/providers.md#-uptime-kuma).
