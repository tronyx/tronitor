# 🔑 Configuration

[← All documentation](README.md)

tronitor reads its settings from a config file in the [TOML](https://toml.io) format, a simple text format of `key = value` lines in named sections. Environment variables can override most settings, so you can also run tronitor without a file.

## 📂 Where tronitor looks for the file

tronitor uses the first of these that it finds, and reads only that one file:

1. The file that `--config PATH` names.
2. The file that the `TRONITOR_CONFIG` environment variable names.
3. `tronitor.toml` in the same folder as `tronitor.py`.
4. `tronitor.toml` in your user config folder: `~/.config/tronitor/tronitor.toml` on Linux and macOS, `%APPDATA%\tronitor\tronitor.toml` on Windows.

If `--config` or `TRONITOR_CONFIG` names a file that does not exist, tronitor stops with an error. If it finds no file at all, it uses only the environment variables.

## 📝 The settings

The file has four sections, which TOML calls tables. Each table starts with its name in square brackets. These are the tables of the example file, `tronitor.example.toml`, with its explanations left out:

```toml
[general]
# lock_dir = "/tmp"

[healthchecks]
url = "https://healthchecks.io"
api_key = ""

[uptimerobot]
api_key = ""
# base_url = "https://api.uptimerobot.com/v3"

[notify]
webhook_url = ""
format = "discord"
notify_all = false
```

A line that starts with `#` is a comment, so tronitor ignores it. You need only the tables and keys of the providers that you use. A key that you leave out gets its default value.

### 📁 General

The `[general]` table has one key:

| Key | What it does | Default |
| --- | --- | --- |
| `lock_dir` | The folder for the Healthchecks lock files. tronitor creates the folder if it does not exist. It must be the same folder that the HealthChecks-Linux pinging script reads (see [Lock files](cron.md#-lock-files)) | `/tmp` on Linux and macOS, your `TEMP` folder on Windows |

### 💓 Healthchecks

The `[healthchecks]` table:

| Key | What it does | Default |
| --- | --- | --- |
| `url` | The address of your Healthchecks server. Change it only for a server that you host yourself, for example `https://hc.example.com`. Give the main address of the site, without `/api`: tronitor adds the API path itself | `https://healthchecks.io` |
| `api_key` | A read-write project API key (see [API keys](#-api-keys)). Leave it empty if you do not use Healthchecks | Empty |

### 🤖 UptimeRobot

The `[uptimerobot]` table:

| Key | What it does | Default |
| --- | --- | --- |
| `api_key` | Your Main API key (see [API keys](#-api-keys)). Leave it empty if you do not use UptimeRobot | Empty |
| `base_url` | The address of the UptimeRobot API. It is only for tests against a mock server (a stand-in that acts like UptimeRobot). Leave it out otherwise | `https://api.uptimerobot.com/v3` |

### 🔔 Notify

The `[notify]` table holds the settings for `-w`, which posts the paused monitors to a Discord or Slack webhook. A webhook is an address that a chat service gives you: a message that is sent to the address appears in a channel.

| Key | What it does | Default |
| --- | --- | --- |
| `webhook_url` | The webhook address. Leave it empty if you do not use `-w` | Empty |
| `format` | The message style: `"discord"` sends a Discord embed (a message box with one line for each monitor), `"slack"` sends a Slack text message | `"discord"` |
| `notify_all` | `true` also sends a message when no monitors are paused, to say that all of them run. `false` sends nothing then | `false` |

## 🌱 Environment variables

An environment variable overrides the same setting in the file. A variable that is set but empty counts as not set, so the file's value applies.

| Variable | Setting |
| --- | --- |
| `TRONITOR_CONFIG` | The config file to read (see [Where tronitor looks](#-where-tronitor-looks-for-the-file)) |
| `TRONITOR_HEALTHCHECKS_URL` | `[healthchecks] url` |
| `TRONITOR_HEALTHCHECKS_API_KEY` | `[healthchecks] api_key` |
| `TRONITOR_UPTIMEROBOT_API_KEY` | `[uptimerobot] api_key` |
| `TRONITOR_WEBHOOK_URL` | `[notify] webhook_url` |
| `TRONITOR_LOCK_DIR` | `[general] lock_dir` |

`base_url`, `format` and `notify_all` have no variable. Set them in the file.

For example, this command lists your Healthchecks monitors without a key in the config file:

```bash
TRONITOR_HEALTHCHECKS_API_KEY=your-key python3 tronitor.py -m hc -l
```

A key typed on the command line stays in your shell history. A file that only you can read is safer.

## 🔑 API keys

### 💓 Healthchecks

tronitor needs a read-write project API key. In Healthchecks, each project has its own keys. Open the project's **Settings** page. In its **API Access** section, the button creates two keys. tronitor needs the one labelled **API key**, not the one labelled **API key (read-only)**. tronitor sees only the checks of that project. For several projects, use a config file for each one, and pick the file with `--config`.

Healthchecks also offers read-only keys. A read-only key cannot pause checks, and the list that it returns has no check IDs. tronitor finds this and stops with the message `the Healthchecks API key is read-only; tronitor needs a read-write key`.

### 🤖 UptimeRobot

tronitor needs your Main API key, the key for your whole account. tronitor uses version 3 of the UptimeRobot API, and sends the key with each request.

## ❌ Mistakes in the file

tronitor checks the whole file before it does anything. If something is wrong, it stops with exit code `2` and a message that names the file and the problem:

- **An unknown key or table**, for example a typing error. The message names the key and suggests the nearest known name: `unknown key 'healthchecks.api_kye' (did you mean 'api_key'?)`. A key outside its table gets the table in the suggestion: `unknown key 'api_key' (did you mean 'healthchecks.api_key'?)`.
- **A value of the wrong type**, for example `notify_all = "yes"`. The message says `must be true or false` or `must be a string`.
- **An address without `http://` or `https://`**, in `url`, `base_url` or `webhook_url`.
- **A `format` other than `"discord"` or `"slack"`**.
- **A TOML syntax error**, such as a missing quote. The message gives the line and column.

[Troubleshooting](troubleshooting.md#-config-file-errors) has more about each message.

## 🔒 Keeping the keys safe

The config file holds your API keys and the webhook address. The webhook address also contains a secret: anyone who has it can post to your channel.

- Make the file readable only by you. On Linux and macOS, run `chmod 600 tronitor.toml`.
- In a cloned repository, git ignores `tronitor.toml`, so you cannot commit it by mistake.
- tronitor never prints the webhook address, not even with `--verbose` or in an error message.

The [security policy](../.github/SECURITY.md) has the details, and tells you how to report a problem privately.
