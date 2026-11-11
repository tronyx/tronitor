# 🚀 Usage

[← All documentation](README.md)

## ▶️ Running it

Each command names a provider with `-m` and one action:

```bash
python3 tronitor.py -m hc -l
```

The provider is `healthchecks` (short: `hc`) or `uptimerobot` (short: `ur`). Capital letters do not matter. Only `--migrate` needs no provider (see [Upgrading from the Bash script](#-upgrading-from-the-bash-script)). These pages write `tronitor` instead of `python3 tronitor.py`, because it is shorter (see [Running it](installation.md#%EF%B8%8F-running-it) in Installation). On Windows, type `py` instead of `python3`.

## 🎯 Naming monitors

The actions that pause, unpause, delete or reset monitors take a list of monitors, which `--help` calls `TARGETS`. These are the rules:

- `all` means every monitor in the account.
- Otherwise, give names and IDs, separated by commas: `-p Plex,1002`. tronitor ignores spaces around the commas.
- Put the list in quotes when a name has a space in it: `-p "Filesystem Backup,Database Backup"`. Quotes around one item in the list also work: `-p "'Plex','Sonarr'"`.
- A name must match the whole monitor name. Capital letters do not matter. So `plex` matches `Plex`, but not `Plex Backup`.
- An ID is the check's UUID on Healthchecks: a long code that Healthchecks gives each check, for example `31365bce-8da9-4729-8ff3-aaa71d56b712`. On UptimeRobot, it is the monitor's number, for example `1002`. `-l` shows the IDs. tronitor takes an item that looks like an ID as an ID, not as a name.
- On Healthchecks, a check's slug also works, for example `-p filesystem-backup`. The slug is a short form of the name that Healthchecks gives each check, in lowercase and with hyphens instead of spaces. `-l` shows it. A slug needs no quotes. Like a name, it must match whole, and capital letters do not matter. UptimeRobot has no slugs.
- A name with a comma in it cannot be given, because the comma splits the list. Use the monitor's ID instead, or on Healthchecks its slug. If an item that tronitor did not find is the start of such a name, the message says so.
- A monitor named twice in the list gets the action once.

Before tronitor changes anything, it checks the whole list:

- **A name that two or more monitors share.** tronitor lists the monitors with that name and their IDs, and does nothing. On Healthchecks, the same happens when an item is the name of one check and the slug of another. Use the ID of the one that you want. `--yes` does not change this.
- **A name, slug or ID that matches no monitor.** tronitor prints `Not found:` and the item, and does nothing. With `--yes`, it reports the missing items and acts on the monitors that it found.

In both cases, the exit code is `3` (see [Exit codes](#-exit-codes)).

`-i` takes a single monitor, by name, slug or ID, in the same way.

## 🧰 All options

| Option | What it does |
| --- | --- |
| `-m PROVIDER`, `--monitor PROVIDER`, `--provider PROVIDER` | The monitoring service: `healthchecks` (`hc`) or `uptimerobot` (`ur`). Every action but `--migrate` needs it |
| `--config PATH` | The config file to read. Without it, tronitor looks in the places that [Configuration](configuration.md#-where-tronitor-looks-for-the-file) lists |
| `--yes` | Delete or reset without asking. Also act on the monitors that were found when some were not (see [Naming monitors](#-naming-monitors)). With `--migrate`, overwrite `tronitor.toml` |
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
| `--ignore-paused-pings TARGETS` | Make checks stay paused when they get a ping (see [Lock files](cron.md#-lock-files)). Healthchecks only |
| `--resume-on-ping TARGETS` | Make checks leave the paused state when they get a ping, which is the default. Healthchecks only |
| `--migrate PATH` | Write `tronitor.toml` from the settings of the old Bash script at `PATH`. Needs no `-m` (see [Upgrading from the Bash script](#-upgrading-from-the-bash-script)) |

<details>
<summary>The full --help output</summary>

```text
usage: tronitor [-h] [-m PROVIDER] [--config PATH] [--yes] [--json]
                [--no-color] [--verbose] [--version] (-l | -f | -n | -w | -s |
                -a | -i TARGET | -c FILE | -p TARGETS | -u TARGETS |
                -d TARGETS | -r TARGETS | --ignore-paused-pings TARGETS |
                --resume-on-ping TARGETS | --migrate PATH)

Pause and unpause Healthchecks and UptimeRobot monitors, from cron or by hand.

options:
  -h, --help            show this help message and exit
  -m, --monitor, --provider PROVIDER
                        the monitoring service: healthchecks (hc) or
                        uptimerobot (ur); every action but --migrate needs it
  --config PATH         the config file (default: tronitor.toml next to the
                        script, then in your user config folder)
  --yes                 delete or reset without asking, act on the monitors
                        that were found when some were not, and let --migrate
                        overwrite tronitor.toml
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
  --ignore-paused-pings TARGETS
                        make paused checks ignore pings and stay paused
                        (Healthchecks only)
  --resume-on-ping TARGETS
                        make paused checks leave the paused state on a ping,
                        the default (Healthchecks only)
  --migrate PATH        write tronitor.toml, next to the old tronitor.sh at
                        PATH, from the script's settings (no -m needed)

PROVIDER is healthchecks (hc) or uptimerobot (ur).

TARGETS is "all", or a comma-separated list of monitor names and IDs. Put names
in quotes, for example: -p "Filesystem Backup,Database Backup". A name must
match the whole monitor name, but capital letters do not matter. A Healthchecks
ID is the check's UUID; an UptimeRobot ID is the monitor's number. Healthchecks
also takes a check's slug, which -l shows, for example: -p filesystem-backup.

Examples:
  tronitor -m hc -l
  tronitor -m hc -p all
  tronitor -m ur -u "Plex,Tautulli"
  tronitor --migrate tronitor.sh

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

### 🚚 Upgrading from the Bash script

The old Bash version, `tronitor.sh`, kept its settings at the top of the script. `--migrate` reads them and writes them to a new `tronitor.toml`, in the same folder as the script. It needs no `-m`, and `-m` and `--json` have no effect on it. It refuses `--config`, because the new file always goes next to the script:

```bash
tronitor --migrate tronitor.sh
```

tronitor looks for `tronitor.toml` next to `tronitor.py` (see [Configuration](configuration.md#-where-tronitor-looks-for-the-file)). So put `tronitor.py` in the folder of `tronitor.sh`, or move the new file next to `tronitor.py` afterwards.

Do you update with `git pull`? Then copy `tronitor.sh` to another folder first, because the update removes it. Then run `--migrate` on the copy.

tronitor does not run the script. It reads the lines of the form `name='value'` above the line `# Declare some variables`, and the `tempDir` line below it. Each setting must be on a line of its own, in the form `name='value'`: with single quotes, and with nothing after the closing quote, not even a comment. If the line of a setting has another form, tronitor does not copy it. Instead, it prints `Skipped:` and the name, so that you can fill in the value in `tronitor.toml` yourself. It copies these settings:

| In `tronitor.sh` | In `tronitor.toml` |
| --- | --- |
| `hcApiKey` | `[healthchecks] api_key` |
| `healthchecksDomain` | `[healthchecks] url`. tronitor puts `https://` in front, unless the value starts with `http://` or `https://` |
| `urApiKey` | `[uptimerobot] api_key` |
| `webhookUrl` | `[notify] webhook_url` |
| `notifyAll` | `[notify] notify_all`. `true`, in capital or small letters, gives `true`. Any other value gives `false` |

`[notify] format` is always `"discord"`, because the Bash script sent Discord messages. The other settings get their defaults, as in `tronitor.example.toml`. Then tronitor loads the new file, to make sure that it is valid. On Linux and macOS, the new file is readable only by you.

tronitor drops the settings that it has no use for: the StatusCake key and username, the Upptime settings and the jq setting. tronitor no longer supports StatusCake and Upptime (see the [changelog](../CHANGELOG.md)).

tronitor prints what it did. It names each setting that it carried over, dropped or skipped, but it never shows a key or the webhook address. Only the Healthchecks server address appears, because it is not a secret. A setting that is empty, or that still has the value that the script came with, is not listed. For example:

```text
Read tronitor.sh
Carried over: Healthchecks API key
Carried over: webhook URL
Dropped: the jq setting (no longer used)
Note: the lock folder is now /tmp by default (your TEMP folder on Windows); the Bash script used $HOME/tronitor/. See docs/cron.md.
Note: if HealthChecks-Linux reads its lock files from another folder, set lock_dir in tronitor.toml.
Wrote tronitor.toml (readable only by you)
```

> [!IMPORTANT]
> The lock files moved. The Bash script kept them in its `tempDir` folder, `~/tronitor/` by default. tronitor keeps them in `/tmp` by default. HealthChecks-Linux must read the lock files from the folder that tronitor uses. If it reads another folder, set `lock_dir` in `tronitor.toml` to that folder. See [Lock files](cron.md#-lock-files).

If `tronitor.toml` exists already, tronitor changes nothing and stops with exit code `2`. To overwrite the file, add `--yes`. If the new file is not valid, for example because the webhook address has a space in it, tronitor removes the new file and stops with exit code `2`. An old `tronitor.toml` then stays as it was. [Troubleshooting](troubleshooting.md#-upgrading-from-the-bash-script) explains each message.

tronitor does not need `tronitor.sh` after the migration. The script still holds your keys, so delete it when you no longer need it.

## 📤 Output

### 🎨 The table and colour

`-l`, `-f`, `-n` and `-w` print a table, with one line for each monitor:

```text
The following Healthchecks monitors were found:
Filesystem Backup  UUID: 31365bce-8da9-4729-8ff3-aaa71d56b712  Slug: filesystem-backup  Status: Up
Database Backup    UUID: 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41  Slug: database-backup    Status: Paused
```

On Healthchecks, the table also shows each check's slug, or `(none)` for a check without one. UptimeRobot monitors have no slug column.

On a terminal, the status has a colour: green for up, red for down, yellow for paused, orange for grace and seems down, and magenta for new, started and pending. The `UUID:` label (`ID:` on UptimeRobot) is bold cyan, and the `Slug:` label is bold bright blue. tronitor uses no colour when the output goes to a file or a pipe, when you give `--no-color`, or when the `NO_COLOR` environment variable is set, to any value.

If a monitor's name, slug or ID holds a control character (an invisible character that gives commands to the terminal), tronitor shows a `?` instead.

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

Note: a paused Healthchecks check becomes active again when it next receives a ping. The HealthChecks-Linux script skips a check while its lock file exists (see the docs). Running --ignore-paused-pings on a check keeps it paused when it gets a ping.

$ tronitor -m hc -u all
Unpausing Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712)... done
Unpausing Database Backup (UUID 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41)... done
```

If some of the checks ignore pings while they are paused, the note names only the others. If all of them do, tronitor prints no note. See [Lock files](cron.md#-lock-files).

</details>

<details>
<summary>Make every Healthchecks check ignore pings while paused</summary>

```text
$ tronitor -m hc --ignore-paused-pings all
Filesystem Backup (UUID 31365bce-8da9-4729-8ff3-aaa71d56b712) already ignores pings while paused
Setting Database Backup (UUID 4b1d9a2e-6c3f-4e8a-9b7d-2f1e0c5a8d41) to ignore pings while paused... done
```

Run the command again after you add checks. It changes only the checks that do not have the setting yet.

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

Note: a paused Healthchecks check becomes active again when it next receives a ping. The HealthChecks-Linux script skips a check while its lock file exists (see the docs). Running --ignore-paused-pings on a check keeps it paused when it gets a ping.
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
