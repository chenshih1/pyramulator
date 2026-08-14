"""Package metadata consistency tests."""

from pathlib import Path

import pyramulator


def _project_root():
    return Path(__file__).resolve().parent.parent


def _toml_version():
    import tomllib

    with open(_project_root() / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


class TestVersionConsistency:
    def test_version_matches_pyproject(self):
        assert pyramulator.__version__ == _toml_version()

    def test_expected_version(self):
        assert pyramulator.__version__ == "0.1.0"
