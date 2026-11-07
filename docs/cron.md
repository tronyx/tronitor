# ⏰ Running from cron

[← All documentation](README.md)

## 🔧 Maintenance windows

A maintenance window is a time when you expect a server or a job to be down, for example during a backup or an update. If the monitors keep running then, the provider sends alerts for nothing, and someone may be woken up. Some providers offer maintenance windows only on paid plans.

With tronitor and cron, you can make your own. Cron is the Linux and macOS service that runs commands on a schedule. A typical schedule is:

1. Pause the monitors just before the backup starts.
2. Unpause them when the backup is done.
3. Every night, post the monitors that are still paused to Discord or Slack, so that a forgotten pause does not go unseen.

## 📝 Crontab lines

The crontab is your list of scheduled commands. To edit it, run `crontab -e`. Each line has five time fields (minute, hour, day of the month, month and day of the week), and then the command.

```text
# Pause every Healthchecks check at 01:55, before the 02:00 backup
55 1 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -p all > /dev/null
# Unpause them at 04:00, when the backup is done
0 4 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -u all > /dev/null
# At 08:00, post the paused checks to the webhook
0 8 * * * /usr/bin/python3 /opt/tronitor/tronitor.py -m hc -w > /dev/null
```

Some notes on these lines:

- Cron does not read your shell's startup files, so an alias such as `tronitor` does not work. Give the full path of Python and of `tronitor.py`. To find the path of Python, run `command -v python3`. If `tronitor.py` is executable (see [Running it](installation.md#%EF%B8%8F-running-it)), the path of the script alone also works, for example `/opt/tronitor/tronitor.py -m hc -p all`. The script then looks for `python3` on cron's PATH, which is usually `/usr/bin:/bin`. If you made a virtual environment (a private copy of Python) for the script, use the Python in it, for example `/opt/tronitor/.venv/bin/python`. tronitor needs no packages, so a virtual environment is optional.
- tronitor finds `tronitor.toml` next to `tronitor.py`, so cron needs no other settings. To use another file, add `--config /path/to/tronitor.toml`.
- `> /dev/null` discards the normal output. Errors go to stderr, a program's second output, which is meant for errors. Cron still mails stderr to you when your system sends cron mail. A failed pause or unpause of one monitor is an error too (see [Errors and stderr](usage.md#%EF%B8%8F-errors-and-stderr)). To keep a log instead, write `>> /var/log/tronitor.log 2>&1` at the end of the line.
- For UptimeRobot, write `-m ur` instead of `-m hc`.

If the backup is a script that you start from cron, you can also pause and unpause around it, in the same script:

```bash
#!/bin/sh
/usr/bin/python3 /opt/tronitor/tronitor.py -m hc -p "Filesystem Backup"
/opt/backup/run-backup.sh
/usr/bin/python3 /opt/tronitor/tronitor.py -m hc -u "Filesystem Backup"
```

The lines are separated by line breaks, not by `&&`, so the unpause also runs when the backup fails. Then the check is active again, and it reports the failed backup.

## 🔒 Lock files

This section is only for Healthchecks.

A paused Healthchecks check becomes active again when it next receives a ping. A ping is the signal that a job sends to Healthchecks to say that it ran. So if a job pings the check every few minutes, the next ping ends the pause, and the maintenance window with it.

[HealthChecks-Linux](https://github.com/tronyx/HealthChecks-Linux) is a script that tests your applications from cron and pings Healthchecks for each one. It skips a check while a lock file for the check exists. A lock file is an empty file whose presence means "do not ping". tronitor creates and removes these files:

| Command | Lock file |
| --- | --- |
| `-p all` | Creates `healthchecks.lock`. While it exists, HealthChecks-Linux skips every check |
| `-p <names>` | Creates `<UUID>.lock` for each check in the list. The UUID is the check's ID, a long code that Healthchecks gives each check, so the file is named like `31365bce-8da9-4729-8ff3-aaa71d56b712.lock` |
| `-u all` | Removes `healthchecks.lock`, and the lock file of every check except a check whose unpause failed |
| `-u <names>` | Removes the lock files of the checks in the list |
| `-f`, then `y` | Removes `healthchecks.lock`, and the lock file of every check except a check whose unpause failed, as `-u all` does |

The files are in the folder that `lock_dir` sets in `tronitor.toml` (see [Configuration](configuration.md#-general)). The default is `/tmp` on Linux and macOS, and your `TEMP` folder on Windows. `lock_dir` must be an absolute path, such as `/tmp/tronitor`, or start with `~` for your home folder. tronitor creates the folder if it does not exist. Before it pauses anything, it makes sure that it can write to the folder.

Some details:

- tronitor creates the lock file before it asks Healthchecks to pause the check. If the pause fails, the lock file stays. To remove it, run `-u` for the same checks, or `-u all` after `-p all`. tronitor removes a check's lock file also when the check is not paused.
- If an unpause fails, the check's own `<UUID>.lock` file stays, so the pinging script does not ping a check that is still paused. `-u all` removes `healthchecks.lock` even then. After `-p all` there are no `<UUID>.lock` files, so a failed unpause leaves no lock file behind.
- After `-p all`, an unpause of some checks by name removes their lock files, but `healthchecks.lock` still silences every check. tronitor warns you about this: `healthchecks.lock is still present, so the pinging script skips every check until you run --unpause all`.
- tronitor and HealthChecks-Linux must run on the same computer, because each one sees only its own computer's files.

If you ping your checks some other way, you can make your own job skip a ping while its lock file exists, in the same way.

### 🔗 Setting up HealthChecks-Linux

HealthChecks-Linux reads the lock files from the folder that `tempDir` sets in its script, `application_healthchecks_generic.sh`. These are the lines near its top:

```bash
tempDir='/tmp/'
# The below temp dir is for use with the Tronitor script, uncomment the line if you wish to use it
# https://github.com/christronyxyocum/tronitor
#tempDir='/tmp/tronitor/'
```

Keep `tempDir='/tmp/'`, and leave the `/tmp/tronitor/` line commented out, with the `#` at its start. tronitor's default `lock_dir` is `/tmp`, so the two scripts then use the same folder without any change.

The README of HealthChecks-Linux tells you to use the `/tmp/tronitor/` line. That was for the old Bash version of tronitor. If you already changed the lines, either change them back to what the example above shows, or set the same folder in `tronitor.toml`:

```toml
[general]
lock_dir = "/tmp/tronitor"
```

> [!WARNING]
> `lock_dir` and `tempDir` must point at the same folder. If you change only one of them, the pinging script never sees the lock files. Then a paused check becomes active again on its next ping. Keep the `/` at the end of `tempDir`, because the script adds the file name directly after it.

Every user on the computer can write to `/tmp`. So on a computer that other people use, they can create or delete the lock files. To prevent this, set `lock_dir` and `tempDir` to the same folder, one that only you can write to. The [security policy](../.github/SECURITY.md) has the details.

## 💥 When something fails

- **One monitor fails.** tronitor reports it on stderr and continues with the next monitor. The exit code is `3` if other monitors worked, or `1` if none did. See [Exit codes](usage.md#-exit-codes).
- **The provider cannot be reached, or the API key is wrong.** tronitor first lists the monitors, so it stops before it changes anything, with exit code `1`.
- **The lock folder cannot be used.** On Healthchecks, `-p` stops before it pauses anything, with exit code `1`.
- **UptimeRobot's rate limit.** The free plan allows 10 requests a minute. On an `HTTP 429` answer, tronitor waits for the time that UptimeRobot asks for (up to 60 seconds) and retries once. So one crontab line with `-p all` works on a free account of any size, but it takes about a minute for every ten monitors. If the retry gets a `429` too, tronitor reports that monitor, continues with the others, and the exit code is `3`. [Rate limits](providers.md#-rate-limits) has the details.

In each case, the failure goes to stderr, so cron mails it to you even with `> /dev/null`.

## 🙋 Questions in cron

In cron, tronitor has no terminal, so it cannot ask a question:

- `-d` and `-r` refuse to run, with exit code `2`, unless you add `--yes`. Add it only if you really want cron to delete or reset monitors without asking.
- `-f` does not ask whether to unpause the paused monitors. It lists them, as `-n` does.
- tronitor stops when a name in the list matches no monitor (exit code `3`). With `--yes`, it acts on the monitors that it found and reports the others. Without `--yes`, a typing error in a crontab line changes nothing, which is often safer.
