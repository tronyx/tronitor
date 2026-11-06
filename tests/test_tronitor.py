"""Unit tests for the tronitor module."""

import re

import tronitor


def test_exit_codes_are_the_documented_ones() -> None:
    """The exit codes match the documented values."""
    assert (tronitor.EXIT_OK, tronitor.EXIT_ERROR, tronitor.EXIT_USAGE, tronitor.EXIT_PARTIAL) == (0, 1, 2, 3)


def test_version_is_a_date() -> None:
    """The version is a YYYY-MM-DD date."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", tronitor.__version__)
