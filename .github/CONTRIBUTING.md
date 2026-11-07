# 🤝 Contributing

Thanks for wanting to help! Bug reports, ideas and pull requests are all welcome.

## 🐛 Reporting a bug

Found a security vulnerability? Please don't open an issue: see the [security policy](SECURITY.md).

[Open a bug report](https://github.com/tronyx/tronitor/issues/new?template=bug_report.yml). The form asks for:

- The command you ran and everything it printed (`--verbose` output is ideal), with any API key or webhook URL removed.
- Your operating system, and the output of `python3 --version` and `python3 tronitor.py --version`.
- The provider: Healthchecks or UptimeRobot. For Healthchecks, also whether it's healthchecks.io or a server you host yourself, and if you host it, its version.

## 💡 Suggesting a feature

[Open a feature request](https://github.com/tronyx/tronitor/issues/new?template=feature_request.yml) describing what you'd like to do and why. For anything bigger than a small fix, please do this before writing code, so we can agree on the approach and your time isn't wasted.

## 🛠️ Making a change

1. Fork the repository, then clone your fork:

   ```bash
   git clone https://github.com/<your_name>/tronitor.git
   cd tronitor
   ```

2. Create a branch from `develop`:

   ```bash
   git checkout -b my-new-feature develop
   ```

3. Make your change. Keep each pull request to one change.

4. Install the dev requirements, then run the tests and the checks:

   ```bash
   pip install -r requirements-dev.txt
   python -m pytest
   python -m ruff check .
   python -m mypy
   ```

   The tests run the script against a fake server (`tests/fake_server.py`), a small local web server that answers like Healthchecks or UptimeRobot, so they need no account and no network. To see which lines your tests reach, run `python -m coverage run -m pytest` and then `python -m coverage report`.

   The live tests (`tests/test_live.py`) are different: they create, pause and delete real monitors, in real Healthchecks and UptimeRobot accounts. They're skipped unless the `TRONITOR_LIVE_*` environment variables are set, and GitHub never runs them. The top of that file lists the variables and explains what the tests touch. Use test accounts, not the ones that watch your real servers.

   `ruff` is a linter and `mypy` checks the type hints; both are set up in `pyproject.toml`, and GitHub runs them on every push too.

   GitHub also lints the workflows ([actionlint](https://github.com/rhysd/actionlint)) and the Markdown files ([markdownlint](https://github.com/DavidAnson/markdownlint-cli2), set up in `.markdownlint.json`). If you change any of those and have Docker, you can run the same checks locally:

   ```bash
   docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12
   docker run --rm -v "$PWD:/workdir" davidanson/markdownlint-cli2 "**/*.md"
   ```

5. Commit, push, and open a pull request against `develop`:

   ```bash
   git add -A
   git commit -m "Add some feature"
   git push origin my-new-feature
   ```

## 📏 Code style

- **One file, standard library only.** People install this by copying a single script, so keep it that way: no new modules, and no new required packages. The one exception is `tomli` on Python 3.10, which stands in for the standard library's `tomllib`.
- **Python 3.10 and newer.** GitHub tests on 3.10, the newest release, and the next release's pre-release, which may fail without failing the run (a heads-up, not a blocker). Avoid syntax and library features newer than 3.10, such as reusing the same quote inside an f-string (3.12+); `mypy` checks the script as 3.10, so it catches a newer library feature.
- **Linux, macOS and Windows.** Use `pathlib` for paths, and don't run other programs: the script talks to the providers over HTTP with the standard library, so it works the same everywhere.
- **Docstrings, not comments.** Explain code in the docstring of the function or class it belongs to. Each section of the file starts with a docstring that says what it holds, above its module-level settings. Don't add `#` comments. The one exception is a marker for a checker, such as `# nosec B108` for CodeFactor's Bandit scan, with the reason in the docstring next to it.
- **Keep docstrings short and plain.** Say what something does and, where it isn't obvious, why.
- **Lines up to 120 characters, spaced as PEP 8 asks** (spaces around operators, and the like). `ruff` checks both.
- **Type hints on every function.** `mypy` checks them in strict mode, so they stay accurate and complete. If it objects to something, fix the code rather than silencing it: a `# type: ignore` is a comment, which the rule above rules out.
- **Add or update tests** for any change in behavior, against the fake server, so they run anywhere without an account. Tests of the functions go in `tests/test_tronitor.py`, and tests that run the script as a command go in `tests/test_cli.py`.
- **Update the docs** if you add an option or change what the script does. The details are in `docs/` (every option is in `docs/usage.md`); the README only has what a newcomer needs, such as the quick start and the most common options, so change it only if your change touches those. The wiki is a copy of `docs/`, made with each release, so don't edit it: changes there are overwritten.
- **Add a line to the changelog** under **Unreleased** in `CHANGELOG.md`, saying what changes for someone using the script.
