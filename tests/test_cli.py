"""Tests that run tronitor.py as a subprocess."""

import os
import subprocess
import sys
from pathlib import Path

import tronitor

SCRIPT = Path(__file__).resolve().parent.parent / "tronitor.py"


def run(
    *args: str, env: dict[str, str] | None = None, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run tronitor.py with args and return the result with text output.

    The environment holds only PATH and SYSTEMROOT, plus whatever env adds.
    """
    full_env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=full_env,
        input=stdin,
        check=False,
    )


def test_version_prints_the_date_and_exits_0() -> None:
    """--version prints the version and exits 0."""
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"tronitor {tronitor.__version__}"


def test_no_arguments_prints_usage_and_exits_2() -> None:
    """No arguments prints the usage to stderr and exits 2."""
    result = run()
    assert result.returncode == 2
    assert "usage:" in result.stderr
