# 🔒 Security policy

## ✅ Supported versions

The project doesn't use version numbers. Only the latest release is supported: the `master` branch. Fixes aren't made to older copies, so update to the latest before reporting (`git pull`, or download `tronitor.py` again).

The `develop` branch is the next release in progress. A vulnerability there is welcome too, since fixing it early keeps it out of the next release.

## 📮 Reporting a vulnerability

**Please don't open a public issue.** Report it privately instead, through GitHub: on the [Security tab](https://github.com/tronyx/tronitor/security), choose **Report a vulnerability**, or go straight to the [form](https://github.com/tronyx/tronitor/security/advisories/new). Only you and the maintainer can see the report.

It helps to include:

- what an attacker could do, and what they'd need first (for example, an account on the same computer, or control of a Healthchecks server);
- how to reproduce it: the command, your config file with the keys removed, and the provider (Healthchecks or UptimeRobot);
- your operating system and your Python version (`python3 --version`).

If you can't use the form, [open an issue](https://github.com/tronyx/tronitor/issues) asking for a private way to get in touch, with no details of the problem.

## ⏱️ What to expect

This project is maintained by one volunteer in their spare time, so please allow for that:

- You'll get a reply within **7 days** saying whether the report is accepted.
- An accepted report is fixed privately, then released, with an advisory on the [Security tab](https://github.com/tronyx/tronitor/security) that credits you, unless you'd rather not be named. The aim is a release within **90 days** of the report, sooner for something serious, and you'll be kept up to date along the way.
- Please keep it private until the fix is released and the advisory published.

## 🎯 Scope

The script holds the API keys of your monitoring accounts, often runs from cron, and writes lock files to a folder that other users may share. These are in scope:

- **The script:**
  - **Lock files.** [HealthChecks-Linux](https://github.com/tronyx/HealthChecks-Linux) is a separate script that pings Healthchecks from cron. A lock file tells it to skip checks: `healthchecks.lock` skips every check, and `<UUID>.lock` skips one. tronitor writes these files to the folder set by `lock_dir` in `tronitor.toml`. HealthChecks-Linux reads them from the folder set by `tempDir` in its own script. Both are `/tmp` by default (tronitor uses your `TEMP` folder on Windows). Both settings must point at the same folder. If you change only one, the pinging script never sees the lock files, and a paused check becomes active again on its next ping. In scope is a trick in that folder that makes the script create, change or delete a file it shouldn't.

    **Known limitation.** Every user on the computer can write to `/tmp`. So any local user can create or delete `/tmp/healthchecks.lock`, or a check's lock file, without running tronitor, and so stop or restart the pings for your checks. This is known, so please don't report it. To prevent it on a shared computer, set `lock_dir` and `tempDir` to the same folder, one that only you can write to (keep the `/` at the end of `tempDir`).
  - **The config file.** It holds the API keys and the webhook URL (an address with a secret token in it). In scope is anything that makes the script reveal them: in its output, its error messages, its `--verbose` log, the webhook message, or a file that other users can read. Keep your `tronitor.toml` readable only by you (on Linux and macOS, `chmod 600 tronitor.toml`).
  - **What a provider sends back.** A monitor name, ID or other API response that makes the script write a file outside the lock folder, run a command, put terminal control codes in its output, or send your keys or data anywhere else. Such a response could come from a self-hosted Healthchecks server that someone else controls.
- **The repository's workflows:** anything that could expose their token, let someone else's code run with their permissions, or push to the repository or its wiki.

Out of scope:

- vulnerabilities in Healthchecks, UptimeRobot or Python themselves; please report those to their own projects;
- anything that needs an attacker who can already run commands as the user running the script;
- the script failing to pause or unpause a monitor, or reporting an error: that's a bug, for a [bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml).
