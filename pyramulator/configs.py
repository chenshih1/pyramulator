"""DRAM configuration helpers, capacity estimation, and bandwidth estimation.

Data tables (standards, speed grades, organizations) live in
:mod:`pyramulator.configs_data` so that this module can focus on logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files as _pkg_files
from pathlib import Path
from typing import Any

from .configs_data import (
    _CHANNEL_WIDTHS,
    _DATA_RATES,
    _UNIT_MULTIPLIERS,
    ORGANIZATIONS,
    SPEED_GRADES,
    SUPPORTED_STANDARDS,
)


def _standard_key(standard: str) -> str:
    """Map standard name to lookup key (SALP variants share one table)."""
    if standard.startswith("SALP"):
        return "SALP"
    return standard


def _parse_org(org: str) -> tuple[int, int | None]:
    """Parse an organization string like 'DDR4_4Gb_x8'.

    Returns (density_bits, chip_width). chip_width is None when the org
    describes a full stack/channel (e.g. 'WideIO_1Gb').
    """
    parts = org.split("_")
    density = parts[1].rstrip("bB")  # strip the bit suffix: "4Gb" -> "4G"
    if density[-1:].isdigit():
        bits = int(density)
    else:
        prefix, unit = density[:-1], density[-1:]
        bits = int(prefix) * _UNIT_MULTIPLIERS.get(unit.upper(), 1)
    chip_width = None
    if len(parts) > 2 and parts[2].startswith("x"):
        chip_width = int(parts[2][1:])
    return bits, chip_width


def estimate_capacity(
    standard: str, org: str, channels: int = 1, ranks: int = 1
) -> int:
    """Estimate nominal DRAM capacity in bytes from the org string.

    Computed as density x chips-per-rank x ranks x channels, where
    chips-per-rank follows from the channel width and the chip width given
    by the org (``xN`` suffix); orgs without a width describe the whole
    stack/channel.
    """
    density_bits, chip_width = _parse_org(org)
    channel_width = _CHANNEL_WIDTHS.get(_standard_key(standard), 64)
    chips_per_rank = channel_width // chip_width if chip_width else 1
    per_rank_bytes = density_bits // 8 * chips_per_rank
    return per_rank_bytes * ranks * channels


def theoretical_bandwidth(config: Mapping[str, object], cacheline: int = 64) -> float:
    """Estimate peak theoretical bandwidth in GB/s for a config.

    Uses data rate x channel width x channels. Does not account for
    protocol overhead, refresh, or timing constraints.
    """
    from . import Config  # late import to avoid a cycle with __init__

    cfg: Any = Config(**config) if isinstance(config, dict) else config  # type: ignore[arg-type]

    standard = str(cfg["standard"])
    speed = str(cfg["speed"])
    channels = int(str(cfg["channels"]))

    key = _standard_key(standard)
    width_bits = _CHANNEL_WIDTHS.get(key, 64)

    # Strip trailing letter suffixes from speed grade: "DDR4_2400R" -> "DDR4_2400"
    parts = speed.split("_")
    prefix = parts[0] + "_" + parts[1].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    data_rate = _DATA_RATES.get(prefix, 0)
    if data_rate == 0:
        raise ValueError(f"unknown data rate for speed '{speed}'")

    transfers_per_sec = data_rate * 1e6
    bytes_per_transfer = width_bits // 8
    peak_gbs = transfers_per_sec * bytes_per_transfer * channels / 1e9
    return peak_gbs


def config_dir() -> Path:
    """Path to the reference Ramulator config files bundled with this package.

    Uses :func:`importlib.resources.files` (stable since Python 3.10) so
    the directory is found both in editable installs and in the wheel.
    """
    path = Path(str(_pkg_files("pyramulator").joinpath("data", "configs")))
    if path.is_dir():
        return path
    raise FileNotFoundError(
        "pyramulator data/configs not found (package data missing?)"
    )


def supported_standards() -> list[str]:
    """Return list of supported DRAM standard names."""
    return list(SUPPORTED_STANDARDS)


def supported_speeds(standard: str) -> list[str]:
    """Return valid speed grades for a given standard."""
    key = _standard_key(standard)
    return list(SPEED_GRADES.get(key, []))


def supported_orgs(standard: str) -> list[str]:
    """Return valid organization/density options for a given standard."""
    key = _standard_key(standard)
    return list(ORGANIZATIONS.get(key, []))


def show(standard: str | None = None) -> None:
    """Print supported configurations. If standard is None, show all."""
    if standard is None:
        for std in SUPPORTED_STANDARDS:
            show(std)
        return

    key = _standard_key(standard)
    speeds = SPEED_GRADES.get(key, [])
    orgs = ORGANIZATIONS.get(key, [])
    print(f"{standard}")
    print(f"  speed: {', '.join(speeds)}")
    print(f"  org:   {', '.join(orgs)}")
    print()
