"""Pause and unpause Healthchecks and UptimeRobot monitors from the command line or cron.

tronitor lists the monitors in an account, finds the paused ones, pauses and unpauses them by name or ID,
and can post a summary to a Discord or Slack webhook. Credentials come from a TOML config file or
environment variables.
"""

import argparse
import sys
from collections.abc import Sequence

__version__ = "2026-11-06"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="tronitor")
    parser.add_argument("--version", action="version", version=f"tronitor {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run tronitor with argv (default: sys.argv[1:]) and return the exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    parser.parse_args(args)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
