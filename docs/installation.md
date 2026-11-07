# 📦 Installation

[← All documentation](README.md)

## 📋 Requirements

tronitor needs [Python](https://www.python.org) 3.11 or newer, and nothing else. It uses only the standard library (the modules that come with Python), so you do not install any packages. It does not need curl or jq, which the old Bash version needed.

It works on Linux, macOS and Windows. GitHub tests it on Linux with Python 3.11 and the newest Python release, and on macOS and Windows with the newest release. See [How it is tested](testing.md#-what-github-runs).

To check your Python version, run this command:

```bash
python3 --version
```

On Windows, type `py` instead of `python3`.

## 📥 Getting the script

tronitor is one file, `tronitor.py`. You also need the example config file, `tronitor.example.toml`, as a starting point for your own settings. Copy the two files to any folder. For example, download them from the [repository](https://github.com/tronyx/tronitor) on GitHub.

You can also clone the whole repository with git. `-b master` gets the `master` branch, which has the latest release. The `develop` branch holds changes that are not released yet:

```bash
git clone -b master https://github.com/tronyx/tronitor.git
```

The repository also has an `examples` folder. It holds sample files for new monitors (see [Creating a monitor](usage.md#-creating-a-monitor)). You need these only if you create monitors with tronitor.

## 🔑 Setting it up

1. Make a copy of `tronitor.example.toml` with the name `tronitor.toml`, in the same folder as `tronitor.py`:

   ```bash
   cp tronitor.example.toml tronitor.toml
   ```

2. Open `tronitor.toml` in a text editor and fill in the API key of your provider. For Healthchecks, this is a read-write project API key. For UptimeRobot, it is the Main API key. [Configuration](configuration.md#-api-keys) tells you where to find each key.

3. Make the file readable only by you, because it holds your keys. On Linux and macOS, run this command:

   ```bash
   chmod 600 tronitor.toml
   ```

4. List your monitors, to make sure that the key works:

   ```bash
   python3 tronitor.py -m hc -l
   ```

   For UptimeRobot, type `-m ur` instead of `-m hc`.

You can also keep the config file in your user config folder, or give the settings as environment variables. [Configuration](configuration.md) tells you how.

## ▶️ Running it

Run the script with Python:

```bash
python3 tronitor.py -m hc -l
```

The examples in `--help` and in these pages write `tronitor` instead of `python3 tronitor.py`, because it is shorter. To type `tronitor` yourself on Linux or macOS, add an alias (a short name for a longer command) to your shell's startup file, for example `~/.bashrc`:

```bash
alias tronitor='python3 /path/to/tronitor.py'
```

In cron, an alias does not work. Use the full path of Python and of the script there. See [Running from cron](cron.md#-crontab-lines).

## 🔄 Updating it

Only the newest version is supported. To update, download `tronitor.py` again, or run `git pull` in the cloned folder, on the `master` branch. Your `tronitor.toml` stays as it is: git ignores it, so a `git pull` never changes it or adds it to the repository.

To see which version you have, run this command. The version is the date of the release:

```bash
python3 tronitor.py --version
```

> [!NOTE]
> Coming from the Bash script, `tronitor.sh`? The settings moved from the top of the script to `tronitor.toml`, and the lock files moved from `~/tronitor/` to `/tmp`. Names now match whole monitor names only. The [changelog](../CHANGELOG.md) lists every change.
