"""Package metadata consistency tests."""

import re
from pathlib import Path

import pyramulator


def _project_root():
    return Path(__file__).resolve().parent.parent


def _toml_version():
    text = (_project_root() / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "version not found in pyproject.toml"
    return match.group(1)


class TestVersionConsistency:
    def test_version_matches_pyproject(self):
        assert pyramulator.__version__ == _toml_version()

    def test_expected_version(self):
        assert pyramulator.__version__ == "0.1.0"
