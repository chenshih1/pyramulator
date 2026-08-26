"""Shared pytest fixtures and configuration constants."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyramulator import Config, config_dir

# -----------------------------------------------------------------------------
# Reference configuration constants used across the test suite so that
# changing the default test device only requires a single edit.
# -----------------------------------------------------------------------------

DDR4_2400R_CFG: dict[str, str] = {
    "standard": "DDR4",
    "speed": "DDR4_2400R",
    "org": "DDR4_4Gb_x8",
}

DDR3_1600K_CFG: dict[str, str] = {
    "standard": "DDR3",
    "speed": "DDR3_1600K",
    "org": "DDR3_2Gb_x8",
}


@pytest.fixture
def ddr4_config() -> Config:
    return Config(**DDR4_2400R_CFG)


@pytest.fixture
def ddr3_config() -> Config:
    return Config(**DDR3_1600K_CFG)


@pytest.fixture
def ddr4_config_file() -> Path:
    return config_dir().joinpath("DDR4-config.cfg")
