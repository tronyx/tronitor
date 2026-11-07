# 🚀 Usage

[← All documentation](README.md)

## ▶️ Running it

Each command names a provider with `-m` and one action:

```bash
python3 tronitor.py -m hc -l
```

The provider is `healthchecks` (short: `hc`) or `uptimerobot` (short: `ur`). Capital letters do not matter. These pages write `tronitor` instead of `python3 tronitor.py`, because it is shorter (see [Running it](installation.md#%EF%B8%8F-running-it) in Installation). On Windows, type `py` instead of `python3`.

## 🎯 Naming monitors

The actions that pause, unpause, delete or reset monitors take a list of monitors, which `--help` calls `TARGETS`. These are the rules:

- `all` means every monitor in the account.
- Otherwise, give names and IDs, separated by commas: `-p Plex,1002`. tronitor ignores spaces around the commas.
- Put the list in quotes when a name has a space in it: `-p "Filesystem Backup,Database Backup"`. Quotes around one item in the list also work: `-p "'Plex','Sonarr'"`.
- A name must match the whole monitor name. Capital letters do not matter. So `plex` matches `Plex`, but not `Plex Backup`.
- An ID is the check's UUID on Healthchecks: a long code that Healthchecks gives each check, for example `31365bce-8da9-4729-8ff3-aaa71d56b712`. On UptimeRobot, it is the monitor's number, for example `1002`. `-l` shows the IDs. tronitor takes an item that looks like an ID as an ID, not as a name.
- A name with a comma in it cannot be given, because the comma splits the list. Use the monitor's ID instead. If an item that tronitor did not find is the start of such a name, the message says so.
- A monitor named twice in the list gets the action once.

Before tronitor changes anything, it checks the whole list:

- **A name that two or more monitors share.** tronitor lists the monitors with that name and their IDs, and does nothing. Use the ID of the one that you want. `--yes` does not change this.
- **A name or ID that matches no monitor.** tronitor prints `Not found:` and the item, and does nothing. With `--yes`, it reports the missing items and acts on the monitors that it found.

In both cases, the exit code is `3` (see [Exit codes](#-exit-codes)).

`-i` takes a single monitor, by name or by ID, in the same way.

## 🧰 All options

| Option | What it does |
| --- | --- |
| `-m PROVIDER`, `--monitor PROVIDER`, `--provider PROVIDER` | The monitoring service: `healthchecks` (`hc`) or `uptimerobot` (`ur`). Each command needs it |
| `--config PATH` | The config file to read. Without it, tronitor looks in the places that [Configuration](configuration.md#-where-tronitor-looks-for-the-file) lists |
| `--yes` | Delete or reset without asking. Also act on the monitors that were found when some were not (see [Naming monitors](#-naming-monitors)) |
| `--json` | Print the provider's records as JSON instead of a table (see [JSON](#-json)) |
| `--no-color` | Never colour the output |
| `--verbose` | Show each API request on stderr, the output for errors (see [Errors and stderr](#%EF%B8%8F-errors-and-stderr)) |
| `--version` | Show the version, which is the date of the release |
| `-h`, `--help` | Show the help and stop |

Choose one of these actions:

| Action | What it does |
| --- | --- |
| `-l`, `--list` | List every monitor and its status |
| `-f`, `--find` | List the paused monitors. On a terminal, offer to unpause them |
| `-n`, `--no-prompt` | List the paused monitors, and never ask |
| `-w`, `--webhook` | List the paused monitors and post them to the webhook (see [Configuration](configuration.md#-notify)) |
| `-s`, `--stats` | Show the account statistics. UptimeRobot only |
| `-a`, `--alerts` | List the alert contacts. On Healthchecks, these are the integrations |
| `-i TARGET`, `--info TARGET` | Show the full record of one monitor |
| `-c FILE`, `--create FILE` | Create a monitor from a JSON file (see [Creating a monitor](#-creating-a-monitor)) |
| `-p TARGETS`, `--pause TARGETS` | Pause monitors |
| `-u TARGETS`, `--unpause TARGETS` | Unpause monitors |
| `-d TARGETS`, `--delete TARGETS` | Delete monitors. Asks first |
| `-r TARGETS`, `--reset TARGETS` | Clear the statistics of monitors. Asks first. UptimeRobot only |

<details>
<summary>The full --help output</summary>

```text
usage: tronitor [-h] -m PROVIDER [--config PATH] [--yes] [--json] [--no-color]
                [--verbose] [--version] (-l | -f | -n | -w | -s | -a |
                -i TARGET | -c FILE | -p TARGETS | -u TARGETS | -d TARGETS |
                -r TARGETS)

Pause and unpause Healthchecks and UptimeRobot monitors, from cron or by hand.

options:
  -h, --help            show this help message and exit
  -m, --monitor, --provider PROVIDER
                        the monitoring service: healthchecks (hc) or
                        uptimerobot (ur)
  --config PATH         the config file (default: tronitor.toml next to the
                        script, then in your user config folder)
  --yes                 delete or reset without asking, and act on the
                        monitors that were found when some were not
  --json                print the provider's records as JSON instead of a
                        table
  --no-color            never colour the output
  --verbose             show each API request on stderr
  --version             show program's version number and exit

actions (choose one):
  -l, --list            list every monitor and its status
  -f, --find            list the paused monitors; on a terminal, offer to
                        unpause them
  -n, --no-prompt       list the paused monitors and never ask
  -w, --webhook         list the paused monitors and post them to the webhook
  -s, --stats           show the account statistics (UptimeRobot only)
  -a, --alerts          list the alert contacts (Healthchecks: integrations)
  -i, --info TARGET     show the full record of one monitor
  -c, --create FILE     create a monitor from a JSON file
  -p, --pause TARGETS   pause monitors
  -u, --unpause TARGETS
                        unpause monitors
  -d, --delete TARGETS  delete monitors (asks first)
  -r, --reset TARGETS   clear the statistics of monitors (asks first; not
                        Healthchecks)

PROVIDER is healthchecks (hc) or uptimerobot (ur).

TARGETS is "all", or a comma-separated list of monitor names and IDs. Put names
in quotes, for example: -p "Filesystem Backup,Database Backup". A name must
match the whole monitor name, but capital letters do not matter. A Healthchecks
ID is the check's UUID; an UptimeRobot ID is the monitor's number.

Examples:
  tronitor -m hc -l
  tronitor -m hc -p all
  tronitor -m ur -u "Plex,Tautulli"

Documentation: https://github.com/tronyx/tronitor/blob/master/docs/usage.md
```

</details>

## 📋 What each action does

### 📃 Listing monitors

`-l` prints one line for each monitor: its name, its ID and its status. If the account has no monitors, it prints `No monitors found.` [Providers](providers.md#-statuses) explains each status.

### 🔍 Finding paused monitors

`-f`, `-n` and `-w` list only the paused monitors. If none are paused, they print `No Healthchecks monitors are paused.` (or `UptimeRobot`).

- `-f` then asks `Unpause them? [y/N]`. Type `y` to unpause all of them. On Healthchecks, this also removes all the lock files, as `-u all` does. Any other answer, or just Enter, leaves them paused. tronitor asks only on a terminal: when both its input and its output are a terminal window. In cron, in a pipe, or with `--json`, `-f` does not ask, so it acts like `-n`.
- `-n` never asks.
- `-w` posts the list to the webhook in your config (see [Configuration](configuration.md#-notify)). Then it prints `Notification sent.` If nothing is paused and `notify_all` is `false`, it sends nothing and prints `Nothing to notify.`.

### 💤 Pausing and unpausing

`-p` pauses each monitor in the list and prints a line for each one:

```text
Pausing Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712)... done
```

On Healthchecks, `-u` unpauses the checks in the list that are paused. For each check that is not paused, it prints `<name> is already running` and does not send a request. So `-u all` unpauses only what is paused.

On UptimeRobot, `-u` starts every monitor in the list, whatever its status, because UptimeRobot's list can show an old status for about two minutes (see [The monitor list can be out of date](providers.md#-the-monitor-list-can-be-out-of-date)).

If an action fails for one monitor, tronitor reports it and continues with the next one. See [Exit codes](#-exit-codes).

On Healthchecks, `-p` and `-u` also create and remove lock files, which keep the HealthChecks-Linux pinging script quiet while a check is paused. After a pause, tronitor prints a reminder about them. [Lock files](cron.md#-lock-files) explains how they work.

### 🔎 Showing one monitor

`-i` prints the provider's full record of one monitor, as JSON. JSON (JavaScript Object Notation) is a text format for data, which other programs can read.

### 🔔 Alert contacts and statistics

`-a` prints the alert contacts as JSON. Alert contacts are the places where the provider sends its alerts, such as an email address or a chat channel. On Healthchecks they are called integrations, or channels in the API. You need their IDs to give a new monitor its alert contacts (see [New monitors](providers.md#-new-monitors)).

`-s` prints the UptimeRobot account record as JSON. It holds the number of monitors and the limit of your plan, among other things. Healthchecks has no such statistics, so with `-m hc`, tronitor stops with exit code `2`.

### 🆕 Creating a monitor

`-c FILE` reads a JSON file and sends it to the provider as the description of a new monitor. tronitor does not change or check the fields in the file: the provider does. Then tronitor prints the new monitor's record as JSON.

```bash
tronitor -m ur -c examples/uptimerobot-http-monitor.json
```

The `examples` folder has a file for a Healthchecks check and for each type of UptimeRobot monitor. Copy one and change its values. [New monitors](providers.md#-new-monitors) lists the fields of each provider.

### ❌ Deleting and resetting

`-d` deletes monitors, with all their history. `-r` clears the statistics of UptimeRobot monitors (their uptime and response times), and keeps the monitors. Healthchecks has no reset, so with `-m hc`, `-r` stops with exit code `2`.

Both ask first, for example `Delete 2 monitor(s) from Healthchecks? This cannot be undone. [y/N]`. Type `y` to go ahead. Any other answer prints `Cancelled.` and changes nothing.

Without a terminal, for example in cron, tronitor cannot ask. Then it refuses with `Refusing to delete without a terminal; pass --yes to confirm.` and exit code `2`. With `--yes`, it deletes or resets without asking.

> [!WARNING]
> `-d all --yes` deletes every monitor in the account, and asks nothing. The provider cannot undo it.

## 📤 Output

### 🎨 The table and colour

`-l`, `-f`, `-n` and `-w` print a table, with one line for each monitor:

```text
The following Healthchecks monitors were found:
Filesystem Backup  UUID: 31365bce-8da9-4729-8ff3-aaa71d56b712  Status: Up
Database Backup    UUID: 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41  Status: Paused
```

On a terminal, the status has a colour: green for up, red for down, yellow for paused, orange for grace and seems down, and magenta for new, started and pending. tronitor uses no colour when the output goes to a file or a pipe, when you give `--no-color`, or when the `NO_COLOR` environment variable is set, to any value.

If a monitor's name or ID holds a control character (an invisible character that gives commands to the terminal), tronitor shows a `?` instead.

### 🧾 JSON

With `--json`, `-l`, `-f`, `-n` and `-w` print a JSON list of the provider's records instead of the table. Each record is exactly what the provider sent, with its keys sorted. Use it to give the data to another program, such as [jq](https://jqlang.org).

```bash
tronitor -m hc -l --json
```

With `--json`, the output holds only the JSON:

- `-a` leaves out its header line.
- `-w` prints `Notification sent.` or `Nothing to notify.` on stderr instead.
- `-f` never asks.

`-i`, `-s` and `-c` always print JSON. `--json` does not change the output of `-p`, `-u`, `-d` and `-r`.

### ⚠️ Errors and stderr

A program has two outputs: stdout for normal output, and stderr for errors. tronitor prints each error on stderr, and starts it with `tronitor:`. If an action fails for one monitor, that line goes to stderr too:

```text
tronitor: Pausing Plex (ID 1001)... failed: HTTP 429: Too Many Requests
```

So a cron job that discards stdout (with `> /dev/null`) still gets each failure. [Troubleshooting](troubleshooting.md) explains each message.

`--verbose` also prints each request that tronitor sends, on stderr:

```text
GET https://healthchecks.io/api/v3/checks/
```

The line leaves out the part of the address after `?`. For the webhook, it shows `POST webhook` instead of the address, because the address holds a secret.

Each request waits up to 30 seconds for an answer. After that, tronitor reports `cannot reach <host>: timed out`.

## 👀 Sample output

<details>
<summary>Pause every Healthchecks check, then unpause them</summary>

```text
$ tronitor -m hc -p all
Pausing Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712)... done
Pausing Database Backup (UUID 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41)... done

Note: a paused Healthchecks check becomes active again when it next receives a ping. The HealthChecks-Linux script skips a check while its lock file exists (see the docs).

$ tronitor -m hc -u all
Unpausing Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712)... done
Unpausing Database Backup (UUID 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41)... done
```

</details>

<details>
<summary>Unpause every UptimeRobot monitor</summary>

```text
$ tronitor -m ur -u all
Unpausing Plex (ID 1001)... done
Unpausing Sonarr (ID 1002)... done
Unpausing Radarr (ID 1003)... done
```

On UptimeRobot, `-u all` starts each monitor, also the ones that run already, so it prints a line for each one.

</details>

<details>
<summary>A name that matches no monitor, without and with --yes</summary>

```text
$ tronitor -m hc -p "Filesystem Backup,Nope"
tronitor: Not found: Nope

$ tronitor -m hc -p "Filesystem Backup,Nope" --yes
tronitor: Not found: Nope
Pausing Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712)... done

Note: a paused Healthchecks check becomes active again when it next receives a ping. The HealthChecks-Linux script skips a check while its lock file exists (see the docs).
```

Both commands end with exit code `3`.

</details>

<details>
<summary>A name that two monitors share</summary>

```text
$ tronitor -m ur -p plex
tronitor: "plex" matches 2 monitors; use the ID instead:
  Plex (ID 1001)
  Plex (ID 1004)
```

tronitor pauses nothing, and the exit code is `3`.

</details>

## 🔢 Exit codes

The exit code is a number that a program gives back when it ends. A script or cron job can test it, for example with `$?` in a shell.

| Code | Meaning |
| --- | --- |
| `0` | Success. Also when there was nothing to do: no monitors, nothing paused, or you answered no to a question |
| `1` | An API, network or lock folder error. Also when the webhook failed, or when the action failed for every monitor |
| `2` | Wrong arguments, a problem in the configuration or the JSON file, an action that the provider does not offer, or a question was needed and there was no terminal |
| `3` | Some monitors were not found or matched several monitors, or the action failed for some monitors and worked for others |
| `130` | You pressed Ctrl+C. tronitor prints `Interrupted.` |
