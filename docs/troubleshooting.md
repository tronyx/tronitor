# 🩺 Troubleshooting

[← All documentation](README.md)

Each error that tronitor prints goes to stderr and starts with `tronitor:`, apart from the indented lines of a list and the `Interrupted.` line. When the provider's API or the network causes the error, the provider's name comes next, for example `tronitor: Healthchecks: HTTP 401: ...`. This page leaves out the `tronitor:` part.

To see each request that tronitor sends, add `--verbose` to the command. [Exit codes](usage.md#-exit-codes) explains the number that tronitor gives back. If your problem is not here, [open a bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml).

## 🐍 Python version

### `/usr/bin/python3 is Python 3.10.12 without the tomli package; install tomli (...) or use Python 3.11 or newer`

Python 3.10 can run tronitor, but it needs the `tomli` package to read the config file (see [Requirements](installation.md#-requirements)). The exit code is `2`. Install the package for the Python that runs the script. On Debian and Ubuntu:

```bash
sudo apt install python3-tomli
```

Elsewhere, or when the package is not there:

```bash
python3 -m pip install --user tomli
```

If a newer Python is easy to get, the other way out is to run the script with it, as the next message explains.

### `Python 3.10 or newer is needed, but /usr/bin/python3 is Python 3.9.2`

The Python that runs the script is too old. tronitor needs Python 3.10 or newer (see [Requirements](installation.md#-requirements)). The message names the Python that was used and its version, and the exit code is `2`. This often happens on a server whose system Python is older, for example Debian 11 (Python 3.9) or Ubuntu 20.04 (Python 3.8).

Install a newer Python, and run the script with it by name, for example `python3.11 tronitor.py -m hc -l`. Use the same Python in your crontab lines. If your system has no package for a newer Python, [uv](https://docs.astral.sh/uv/) installs one without root rights: after `uv python install 3.11`, the command `uv python find 3.11` prints the path of the Python to use. If you made a symbolic link so that you can type `tronitor`, point it at a two-line script instead, which runs the right Python:

```bash
#!/bin/sh
exec python3.11 /opt/tronitor/tronitor.py "$@"
```

An older copy of tronitor stopped on such a Python with a traceback that ended in `ModuleNotFoundError: No module named 'tomllib'`. That is the same problem.

## 🤔 My paused Healthchecks check came back by itself

A paused Healthchecks check becomes active again when it next receives a ping. A ping is the signal that a job sends to Healthchecks to say that it ran. So if a job pings the check every few minutes, the pause ends at the next ping. Healthchecks works this way on purpose, and tronitor cannot change it.

To keep a check paused, the job that pings it must stop while the check is paused. [HealthChecks-Linux](https://github.com/tronyx/HealthChecks-Linux) does this when it finds tronitor's lock files. If the check still comes back:

- Make sure that `lock_dir` in `tronitor.toml` and `tempDir` in HealthChecks-Linux point at the same folder. The defaults, `/tmp` and `/tmp/`, match. See [Setting up HealthChecks-Linux](cron.md#-setting-up-healthchecks-linux).
- Make sure that tronitor and HealthChecks-Linux run on the same computer.
- Make sure that nothing else pings the check, such as another job or another computer.

## 🧭 Command-line errors

These errors come after the short usage text, and start with `tronitor: error:`. tronitor does nothing, and the exit code is `2`. Run `python3 tronitor.py --help` to see every option.

### `choose a provider with -m: healthchecks (hc) or uptimerobot (ur)`

Each action needs `-m` and the provider, for example `-m hc` or `-m ur`. Only `--migrate` runs without it. Unlike the other errors here, this one comes without the usage text, and starts with `tronitor:` only.

### `one of the arguments -l/--list -f/--find ... is required`

Each command needs one action, such as `-l`, `-p all` or `-u all`. The message lists them all.

### `argument -p/--pause: not allowed with argument -l/--list`

A command takes only one action. Run two commands instead, for example first `-l` and then `-p all`.

## 📄 Config file errors

These errors name the file, or the environment variable, and the problem. The exit code is `2`. See [Configuration](configuration.md) for each setting.

### `unknown key 'healthchecks.api_kye' (did you mean 'api_key'?)`

The file has a key or a table that tronitor does not know, usually because of a typing error. The hint in brackets is the nearest known name. Correct the name in the file.

If the hint names a table, for example `(did you mean 'healthchecks.api_key'?)`, the key is outside its table. Move it below the line with the table's name, here `[healthchecks]`.

### `notify.notify_all must be true or false`

A value has the wrong type. `notify_all` takes `true` or `false`, without quotes. Every other setting takes a string, in quotes. `healthchecks must be a table` means that the file has `healthchecks = ...` instead of a `[healthchecks]` line.

### `healthchecks.url must start with http:// or https://`

An address in `url`, `base_url` or `webhook_url` has no `http://` or `https://` at its start. Add it. If the address comes from an environment variable, the message names the variable instead.

### `notify.webhook_url contains a space or a control character`

The address has a space, a line break or another invisible character inside it, often from a copy and paste. Copy the address again. tronitor does not show the address, because a webhook address holds a secret. The same message exists for `url` and `base_url`.

### `general.lock_dir must be an absolute path`

`lock_dir` is a relative path, such as `locks`. Under cron, a relative path points at another folder, so tronitor refuses it. Give the whole path, such as `/var/lock/tronitor`, or start it with `~` for your home folder. If the folder comes from `TRONITOR_LOCK_DIR`, the message names the variable instead.

### `notify.format must be "discord" or "slack"`

`format` takes only these two values, in quotes and in lowercase.

### `config file does not exist`

`--config` or `TRONITOR_CONFIG` names a file that is not there. Check the path.

### A message with a line and a column

The file is not valid TOML, for example because of a missing quote or bracket. The message says where tronitor found the problem. Compare the line with `tronitor.example.toml`.

### `[Errno 13] Permission denied`

The message starts with the path of the config file, for example `/opt/tronitor/tronitor.toml: [Errno 13] Permission denied: ...`. tronitor found the file, but the user that runs it cannot read it. This often happens after `chmod 600 tronitor.toml`, when cron runs tronitor as another user, for example from root's crontab or from a system crontab. Put the line in the crontab of the user who owns the file, or make that user the owner of the file with `chown`.

### `unknown provider 'x'; use healthchecks (hc) or uptimerobot (ur)`

`-m` names a provider that tronitor does not know. Use one of the four names in the message.

## 🔑 API keys and connections

### `no Healthchecks API key: set [healthchecks] api_key in the config or TRONITOR_HEALTHCHECKS_API_KEY`

tronitor found no key for the provider in `-m`. The same message exists for UptimeRobot. Maybe tronitor read another config file than you expected: it reads only the first one that it finds (see [Where tronitor looks](configuration.md#-where-tronitor-looks-for-the-file)). The exit code is `2`.

### `the Healthchecks API key is read-only; tronitor needs a read-write key`

The key is a read-only key. It can list checks, but it cannot pause them. Create a read-write key in the project's settings, and put it in `api_key`. See [API keys](configuration.md#-api-keys).

### `Healthchecks: HTTP 401: ...`

The provider did not accept the key. HTTP 401 means "not authorized". Copy the key again, and check that no space or line break came with it. For UptimeRobot, use the Main API key, not another kind of key. For Healthchecks, make sure that the key belongs to the server in `url`.

### Other HTTP codes

The provider answered with an error. The text after the code is the provider's own explanation, when it gives one.

- `HTTP 301` or `HTTP 302`: the server redirects tronitor to another address. tronitor does not follow redirects, so that your key goes only to the address that you set. Use the address that the server redirects to. Usually it is the same address with `https://` instead of `http://`.
- `HTTP 404` from Healthchecks: often, `url` has a path that it should not have. Give only the main address, such as `https://hc.example.com`, without `/api` or `/api/v3`. It can also mean that the check was deleted after tronitor listed it.
- `HTTP 5xx` (500 to 599): the provider has a problem. Try again later.

### `Healthchecks: cannot reach hc.example.com: ...`

tronitor could not connect to the server. For UptimeRobot, the message starts with `UptimeRobot:`. The exit code is `1`. The text after the colon gives the reason. Some common ones:

- `Name or service not known`, or similar: the address in `url` has a typing error, or the computer cannot look up names.
- `Connection refused`: nothing listens at that address and port. A server that you host may be down.
- `timed out`: no answer came within 30 seconds. A firewall may block the connection, or the server may be slow.
- `CERTIFICATE_VERIFY_FAILED`: the server's HTTPS certificate is not trusted. A server that you host may use a self-signed certificate. tronitor always checks certificates, so use a certificate that your computer trusts.

If you need a proxy (a server that forwards your web traffic), set the `HTTPS_PROXY` environment variable. tronitor uses it.

### `unexpected response from Healthchecks`

The provider answered, but not with the data that tronitor expected. Usually `url` points at something that is not the Healthchecks API, such as another web page. `HTTP 200: response is not JSON` has the same cause. Check `url`. If it is correct, run the command with `--verbose` and [open a bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml).

`UptimeRobot returned more than 100 pages of monitors` and `UptimeRobot returned a pagination link on another host` are similar. tronitor stops because it does not trust the answer.

### `UptimeRobot returned a status tronitor does not know: 'WEIRD'; treated as 'weird'`

This is a warning. UptimeRobot sent a status that tronitor does not know, so tronitor shows it in lowercase and without a colour. The command still works, and `-u` still starts each monitor that you select. Please [open a bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml) with the status in the message. See [Confirmed against a live account](providers.md#-confirmed-against-a-live-account).

### I paused a monitor and `-f` still shows it as running

This happens on UptimeRobot. UptimeRobot keeps a copy of the list of monitors for about two minutes, so `-l`, `-f`, `-n` and `-w` can show the old status. The pause worked: `-i` shows the current status at once. See [The monitor list can be out of date](providers.md#-the-monitor-list-can-be-out-of-date).

## 🎯 Naming monitors

### `Not found: Plex Backup`

No monitor has this name, slug or ID. tronitor does nothing, and the exit code is `3`.

- A name must match the whole monitor name. `plex` does not match `Plex Backup`. Capital letters do not matter.
- Run `-l` to see the exact names and IDs, and on Healthchecks the slugs.
- Put the list in quotes if a name has a space in it.

With `--yes`, tronitor still prints this line, but it acts on the monitors that it found. See [Naming monitors](usage.md#-naming-monitors).

### `"Plex" matches 2 monitors; use the ID instead:`

Two or more monitors have this name. On Healthchecks, this also happens when the item is the name of one check and the slug of another, and the line says `use the UUID instead`. tronitor lists the monitors with their IDs, and does nothing, also with `--yes`. Give the ID of the monitor that you want instead of the name. The exit code is `3`.

### `Names with commas cannot be selected; use the ID instead.`

A comma splits the list of monitors, so a name with a comma in it cannot be given. tronitor adds this line when an item that it did not find is the start of such a name. Give the monitor's ID instead, or on Healthchecks its slug. On Healthchecks, the line says `use the slug or the UUID instead`.

### `--info takes one monitor`

`-i` takes one name, slug or ID, not `all` and not a list.

### `--pause needs "all" or a comma-separated list of monitors`

The list after `-p`, `-u`, `-d` or `-r` is empty, for example `-p ""`.

## 🔁 Actions on each monitor

### `Pausing Plex (ID 1001)... failed: ...`

The action failed for this monitor. tronitor continues with the other monitors. The text after `failed:` gives the reason, for example `HTTP 429: ...` (see the next section). If other monitors worked, the exit code is `3`. If none worked, it is `1`.

The same line exists for `Unpausing`, `Deleting` and `Resetting`. The `Deleting` and `Resetting` lines show only the name, without the ID.

### `HTTP 429: ...`

The provider received too many requests in a short time. This usually happens on the free UptimeRobot plan, which allows 10 requests a minute.

On a `429` from UptimeRobot, tronitor waits for the time that UptimeRobot asks for (up to 60 seconds) and sends the request once more. So `-p all` works on a free account of any size, but it takes about a minute for every ten monitors. You see this message only when the second try gets a `429` too: then wait a minute, and pause by name the monitors that failed, or run `-u all` again. Healthchecks allows about 100 requests a minute, so tronitor does not retry there. [Rate limits](providers.md#-rate-limits) explains why.

### `Healthchecks does not support stats`

The provider does not offer this action. Healthchecks has no account statistics (`-s`) and no reset (`-r`). See [What each provider supports](providers.md#-what-each-provider-supports). The exit code is `2`.

### `Refusing to delete without a terminal; pass --yes to confirm.`

`-d` and `-r` ask before they act, and tronitor cannot ask without a terminal, for example in cron or in a pipe. Run the command in a terminal, or add `--yes` to act without asking. The same message exists for `reset`. The exit code is `2`.

## 📁 Creating a monitor

### `my-check.json: cannot read the file: ...`

The file in `-c` does not exist, or tronitor cannot read it. Check the path.

### `my-check.json: not valid JSON: ...`

The file is not valid JSON, for example because of a comma after the last field. The message gives the line and column. Compare the file with the files in the `examples` folder.

### `my-check.json: must hold a JSON object`

The file must hold one object, in `{` and `}`. It holds something else, such as a list.

## 🔒 Lock files

These messages are for Healthchecks only. See [Lock files](cron.md#-lock-files).

### `/tmp/locks is not a directory`

`lock_dir` names a file, not a folder. Set `lock_dir` to a folder, or remove the file. tronitor tests the folder before it pauses anything, so nothing changed. The exit code is `1`.

### `cannot create /tmp/locks: ...` or `cannot write to /tmp/locks: ...`

tronitor cannot create the lock folder, or cannot create files in it. Usually, the user that runs tronitor has no write permission there. Choose another folder, or fix the permissions. Set the same folder as `tempDir` in HealthChecks-Linux. tronitor tests the folder before it pauses anything, so nothing changed. The exit code is `1`.

If the message names a lock file, for example `cannot create /tmp/locks/31365bce-8da9-4729-8ff3-aaa71d56b712.lock`, it comes after `Pausing <name>... failed:`. tronitor did not pause that check, and continued with the others.

Under `-p all`, tronitor creates `healthchecks.lock` before it pauses anything, and no lock file for each check. If that fails, `cannot create /tmp/locks/healthchecks.lock: ...` is a top-level error, not a line for a check. tronitor pauses nothing, and the exit code is `1`.

### `refusing to use '../x' as a lock file name`

The provider sent a check ID that would name a file outside the lock folder, for example with a `/` or `..` in it. tronitor creates and removes no file for it. A real Healthchecks ID is a UUID, so tronitor refuses such an answer before this point. If you see this message, [open a bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml).

### `cannot remove /tmp/healthchecks.lock: ...`

tronitor unpaused the checks, but it cannot delete a lock file. HealthChecks-Linux skips the check while the file exists. Delete the file yourself, and check the permissions of the folder. The exit code is `3`, or `1` if no check needed an unpause.

### `healthchecks.lock is still present, so the pinging script skips every check until you run --unpause all`

This is a warning. You unpaused some checks by name after `-p all`. tronitor removed their own lock files, but `healthchecks.lock` from `-p all` still makes HealthChecks-Linux skip every check. Run `-u all` when the maintenance is done.

## 🔔 Webhook

### `no webhook URL: set [notify] webhook_url or TRONITOR_WEBHOOK_URL`

`-w` needs a webhook address. Set it in the config file, or in the environment variable. The exit code is `2`.

### `webhook: HTTP 404: ...`

Discord or Slack did not accept the message. `HTTP 404` or `HTTP 401` usually means that the webhook was deleted, or that the address is wrong. Make a new webhook, and put its address in `webhook_url`. `HTTP 400` usually means that `format` does not match the service: use `"discord"` for Discord and `"slack"` for Slack. tronitor never prints the address itself, because it holds a secret. The exit code is `1`.

### `webhook: cannot reach discord.com: ...`

tronitor could not connect to the webhook's server. The reasons are the same as for [a provider that cannot be reached](#-api-keys-and-connections): a typing error in the address, no network, a firewall, or a proxy that is needed. The message shows only the server's name, not the whole address. The exit code is `1`.

### `webhook: unsupported URL for webhook`

The webhook address is not one that tronitor can use: its form is wrong, or it has a character that an address cannot hold. Copy the address again from Discord or Slack. tronitor does not show the address, because it holds a secret. The exit code is `1`.

## 🚚 Upgrading from the Bash script

These messages come from `--migrate`. Apart from the `Skipped:` line, each one stops tronitor before it changes a file, with exit code `2`. See [Upgrading from the Bash script](usage.md#-upgrading-from-the-bash-script).

### `tronitor.sh does not look like a tronitor.sh (no urApiKey or hcApiKey line)`

The file has no `urApiKey='...'` or `hcApiKey='...'` line above the `# Declare some variables` line. So it is not the Bash version of tronitor, or its top part was changed. Check the path that you gave to `--migrate`. If you changed the script, put the two lines back, in the form `urApiKey='your key'`, with single quotes.

### `--migrate writes tronitor.toml next to the Bash script; --config does not apply`

`--migrate` always writes `tronitor.toml` in the folder of `tronitor.sh`, so it refuses `--config`. Run the command without `--config`. Then move the new file where you want it, and give its path to `--config` for the other actions.

### `tronitor.toml already exists; pass --yes to overwrite it`

The folder of `tronitor.sh` has a `tronitor.toml` already. tronitor does not change it. To replace it with the settings from the script, add `--yes`. To keep it, fill in its keys by hand instead.

### `the migrated config is not valid: tronitor.toml: ...`

A value from `tronitor.sh` cannot be used in `tronitor.toml`. The rest of the message names the setting and the problem, as in [Config file errors](#-config-file-errors). For example, `notify.webhook_url contains a space or a control character` means that `webhookUrl` in the script has a space in it. tronitor removed the new file, and an old `tronitor.toml` stays as it was. Correct the value in `tronitor.sh`, then run `--migrate` again.

### `tronitor.sh: cannot read the file: ...` or `cannot write tronitor.toml: ...`

tronitor cannot read the script, or cannot create `tronitor.toml` in the folder of the script. Check the path. Make sure that you can write to the folder, and that `tronitor.toml` is not a folder.

### `Skipped: urApiKey (not in the form name='value'; check tronitor.toml)`

This line is not an error: `--migrate` still writes the file, with exit code `0`. The line of this setting in `tronitor.sh` is not in the form `name='value'`. For example, it has a comment after the closing quote, or double quotes. So tronitor did not copy the value. Fill it in yourself, in the matching key of `tronitor.toml`. [Upgrading from the Bash script](usage.md#-upgrading-from-the-bash-script) lists which key that is.

## ⌨️ Interrupted

`Interrupted.` means that you pressed Ctrl+C. tronitor stops at once, with exit code `130`. Monitors that it already paused or unpaused stay so. Run `-l` to see where it stopped.
