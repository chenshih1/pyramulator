"""Shared pytest fixtures."""

import pytest

from pyramulator import Config, config_dir


@pytest.fixture
def ddr4_config():
    return Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")


@pytest.fixture
def ddr3_config():
    return Config(standard="DDR3", speed="DDR3_1600K", org="DDR3_2Gb_x8")


@pytest.fixture
def ddr4_config_file():
    return config_dir().joinpath("DDR4-config.cfg")
