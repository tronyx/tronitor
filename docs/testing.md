# 🧪 How it is tested

[← All documentation](README.md)

To run the tests yourself, see [Running everything locally](#-running-everything-locally) below, or [Making a change](../.github/CONTRIBUTING.md#%EF%B8%8F-making-a-change) in the contributing guide.

## 🧾 The tests

The tests are in the `tests` folder. Most of them talk to a fake server instead of the real providers, so they need no account and no network.

### 🎭 The fake server

[tests/fake_server.py](../tests/fake_server.py) is a small web server that runs on your own computer during the tests. Each test tells it what to answer, for example the list of checks that Healthchecks would send, or an `HTTP 429` error. The server also records each request that it gets, so a test can check what tronitor sent: the address, the headers and the body. [tests/conftest.py](../tests/conftest.py) holds the parts that many tests share, such as sample checks and monitors, and config files that point at the fake server.

### 🧠 Logic tests

The logic tests are in [tests/test_tronitor.py](../tests/test_tronitor.py). They test the functions of the script one by one:

- Loading the configuration: the search order, the environment variables, and each error, with its hint.
- Each provider's requests and how it reads the answers, also answers that are wrong or incomplete.
- Matching names and IDs: whole names, capital letters, quotes, commas, `all`, names that several monitors share, and names that match nothing.
- The lock files: when tronitor creates and removes each one, and what happens when the folder cannot be used.
- The output: the table, the colours, JSON, and control characters in names.
- The questions, `--yes`, and what happens without a terminal.
- The Discord and Slack messages, and that the webhook address never appears in the output.
- The exit code of each case.

### 💻 Command-line tests

The command-line tests are in [tests/test_cli.py](../tests/test_cli.py). They run `tronitor.py` as a separate program, as you do, and test its output on stdout and stderr and its exit code. For example, they make sure that a failure reaches stderr, that `-f` acts like `-n` without a terminal, that a delete without `--yes` refuses, that the output has no colour in a pipe, and that `--verbose` never shows a secret.

### 🌐 Live tests

The live tests are in [tests/test_live.py](../tests/test_live.py). They use real Healthchecks and UptimeRobot accounts instead of the fake server. They create a monitor, pause it, unpause it, read it and delete it, and they read the alert contacts. For UptimeRobot, they also reset the monitor and read the account statistics. So they find a change in a provider's API, which the fake server cannot show.

They run only when you set these environment variables:

| Variable | What it is |
| --- | --- |
| `TRONITOR_LIVE_HEALTHCHECKS_URL` | The address of a Healthchecks server, such as `https://healthchecks.io` |
| `TRONITOR_LIVE_HEALTHCHECKS_API_KEY` | A read-write API key of a project on that server |
| `TRONITOR_LIVE_UPTIMEROBOT_API_KEY` | The Main API key of an UptimeRobot account |

Without them, pytest skips these tests, and GitHub never runs them. The tests create only monitors with a name that starts with `tronitor-test-`, and at the end they delete only those, also when a test fails. They never touch any other monitor. Still, use test accounts, not the accounts that watch your real servers.

The UptimeRobot free plan allows 10 requests a minute. So each UptimeRobot test sends about 10 requests or fewer, and waits until a minute has passed since the previous UptimeRobot test ended. These tests take two minutes or more. On an `HTTP 429`, tronitor itself waits and retries once, before the test sees the error (see [Rate limits](providers.md#-rate-limits)). If the second try gets an `HTTP 429` too, the test is skipped, not failed.

UptimeRobot's list of monitors can be out of date for about two minutes (see [The monitor list can be out of date](providers.md#-the-monitor-list-can-be-out-of-date)). So the round trip reads the status after a pause and after a start from the monitor's own record. It uses the list only to see that a new monitor appears and a deleted one goes, and asks again every 20 seconds, for up to 2 minutes.

The maintainer ran the Healthchecks live tests against a Healthchecks server that they host themselves, and the tests passed. The UptimeRobot live tests ran against a real UptimeRobot account on 2026-11-06. That run found that the list of monitors can be out of date, and the round trip was changed to allow for it.

### 📝 Docs tests

The docs tests are in [tests/test_docs.py](../tests/test_docs.py). They test the links in the README, in these pages, in the changelog, and in the files in `.github`. Each link must go to a file that exists. If a link goes to a heading, the heading must exist. The tests make the anchor of each heading (the part of the link after `#`) in the same way as GitHub.

The tests also compare the links to this repository's files on GitHub with the files here. Examples are the links in the issue forms and in the `--help` of the script. So if you move or rename a page, or change a heading, the tests find each link that stops working.

Once the repository's wiki is turned on, a workflow copies these pages there with each release. On the way, it changes only the link targets, because wiki pages have no `.md` at the end of their names. The docs tests check that copy too.

## 🤖 What GitHub runs

GitHub runs the tests on each push and each pull request, and once a week on the default branch, so a new Python release that breaks the script shows up without a push (see [.github/workflows/tests.yml](../.github/workflows/tests.yml)). It runs them on these systems:

| System | Python |
| --- | --- |
| Linux | 3.11 (the oldest version that tronitor supports) and 3.14 |
| macOS | 3.14 |
| Windows | 3.14 |
| Linux | 3.15, the next release, while it is a pre-release. This job can fail without failing the run, as an early warning |

Another job lints the code (examines it for errors and style problems) with [ruff](https://docs.astral.sh/ruff/). It also makes sure that the type hints are correct with [mypy](https://mypy-lang.org), once for Linux and once for Windows, because the script takes different paths on each. Then it lints the workflows with [actionlint](https://github.com/rhysd/actionlint), and the Markdown files with [markdownlint](https://github.com/DavidAnson/markdownlint-cli2).

## 📈 Coverage

Coverage shows which lines of the script the tests run. GitHub measures it on each run and shows the result in the job's log. The result is for information only: a lower number never makes a run fail.

## 🏠 Running everything locally

Install the tools that the tests use, once:

```bash
pip install -r requirements-dev.txt
```

Then run the tests and the checks:

```bash
python -m pytest
```

```bash
python -m ruff check .
```

```bash
python -m mypy
```

To see the coverage, run the tests with the `coverage` tool:

```bash
python -m coverage run -m pytest
python -m coverage report
```

If you have Docker, you can also lint the workflows and the Markdown files, as GitHub does:

```bash
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12
```

```bash
docker run --rm -v "$PWD:/workdir" davidanson/markdownlint-cli2 "**/*.md"
```

To run the live tests, set the variables above, then run this command:

```bash
python -m pytest tests/test_live.py -v
```
