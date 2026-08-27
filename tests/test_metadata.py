"""Package metadata consistency tests."""

from __future__ import annotations

import re
from pathlib import Path

import pyramulator


def _project_root():
    return Path(__file__).resolve().parent.parent


def _version_file():
    text = (_project_root() / "pyramulator" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "version not found in pyramulator/_version.py"
    return match.group(1)


class TestVersionConsistency:
    def test_version_matches_version_file(self) -> None:
        assert pyramulator.__version__ == _version_file()

    def test_expected_version(self) -> None:
        assert pyramulator.__version__ == "0.5.3"
