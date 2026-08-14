"""Supported DRAM standards, speed grades, and organizations."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files as _pkg_files
from pathlib import Path

SUPPORTED_STANDARDS: list[str] = [
    "DDR3", "DDR4", "LPDDR3", "LPDDR4",
    "GDDR5", "WideIO", "WideIO2", "HBM",
    "SALP-1", "SALP-2", "SALP-MASA",
]

SPEED_GRADES: dict[str, list[str]] = {
    "DDR3": [
        "DDR3_800D", "DDR3_800E",
        "DDR3_1066E", "DDR3_1066F", "DDR3_1066G",
        "DDR3_1333G", "DDR3_1333H",
        "DDR3_1600H", "DDR3_1600J", "DDR3_1600K",
        "DDR3_1866K", "DDR3_1866L",
        "DDR3_2133L", "DDR3_2133M",
    ],
    "DDR4": [
        "DDR4_1600K", "DDR4_1600L",
        "DDR4_1866M", "DDR4_1866N",
        "DDR4_2133P", "DDR4_2133R",
        "DDR4_2400R", "DDR4_2400U",
        "DDR4_3200", "DDR4_3200AA",
    ],
    "LPDDR3": ["LPDDR3_1333", "LPDDR3_1600", "LPDDR3_1866", "LPDDR3_2133"],
    "LPDDR4": ["LPDDR4_1600", "LPDDR4_2400", "LPDDR4_3200"],
    "GDDR5": [
        "GDDR5_4000", "GDDR5_4500", "GDDR5_5000",
        "GDDR5_5500", "GDDR5_6000", "GDDR5_6500", "GDDR5_7000",
    ],
    "WideIO": ["WideIO_200", "WideIO_266"],
    "WideIO2": ["WideIO2_800", "WideIO2_1066"],
    "HBM": ["HBM_1Gbps"],
    "SALP": [
        "SALP_800D", "SALP_800E",
        "SALP_1066E", "SALP_1066F", "SALP_1066G",
        "SALP_1333G", "SALP_1333H",
        "SALP_1600H", "SALP_1600J", "SALP_1600K",
        "SALP_1866K", "SALP_1866L",
        "SALP_2133L", "SALP_2133M",
    ],
}

ORGANIZATIONS: dict[str, list[str]] = {
    "DDR3": [
        "DDR3_512Mb_x4", "DDR3_512Mb_x8", "DDR3_512Mb_x16",
        "DDR3_1Gb_x4", "DDR3_1Gb_x8", "DDR3_1Gb_x16",
        "DDR3_2Gb_x4", "DDR3_2Gb_x8", "DDR3_2Gb_x16",
        "DDR3_4Gb_x4", "DDR3_4Gb_x8", "DDR3_4Gb_x16",
        "DDR3_8Gb_x4", "DDR3_8Gb_x8", "DDR3_8Gb_x16",
    ],
    "DDR4": [
        "DDR4_2Gb_x4", "DDR4_2Gb_x8", "DDR4_2Gb_x16",
        "DDR4_4Gb_x4", "DDR4_4Gb_x8", "DDR4_4Gb_x16",
        "DDR4_8Gb_x4", "DDR4_8Gb_x8", "DDR4_8Gb_x16",
    ],
    "LPDDR3": [
        "LPDDR3_4Gb_x16", "LPDDR3_4Gb_x32",
        "LPDDR3_6Gb_x16", "LPDDR3_6Gb_x32",
        "LPDDR3_8Gb_x16", "LPDDR3_8Gb_x32",
        "LPDDR3_12Gb_x16", "LPDDR3_12Gb_x32",
        "LPDDR3_16Gb_x16", "LPDDR3_16Gb_x32",
    ],
    "LPDDR4": ["LPDDR4_4Gb_x16", "LPDDR4_6Gb_x16", "LPDDR4_8Gb_x16"],
    "GDDR5": [
        "GDDR5_512Mb_x16", "GDDR5_512Mb_x32",
        "GDDR5_1Gb_x16", "GDDR5_1Gb_x32",
        "GDDR5_2Gb_x16", "GDDR5_2Gb_x32",
        "GDDR5_4Gb_x16", "GDDR5_4Gb_x32",
        "GDDR5_8Gb_x16", "GDDR5_8Gb_x32",
    ],
    "WideIO": ["WideIO_1Gb", "WideIO_2Gb", "WideIO_4Gb", "WideIO_8Gb"],
    "WideIO2": ["WideIO2_8Gb"],
    "HBM": ["HBM_1Gb", "HBM_2Gb", "HBM_4Gb"],
    "SALP": [
        "SALP_512Mb_x4", "SALP_512Mb_x8", "SALP_512Mb_x16",
        "SALP_1Gb_x4", "SALP_1Gb_x8", "SALP_1Gb_x16",
        "SALP_2Gb_x4", "SALP_2Gb_x8", "SALP_2Gb_x16",
        "SALP_4Gb_x4", "SALP_4Gb_x8", "SALP_4Gb_x16",
        "SALP_8Gb_x4", "SALP_8Gb_x8", "SALP_8Gb_x16",
    ],
}


# Address mapping schemes (channel/bank/row interleaving). Ramulator only
# honors the "mapping" config for DDR3; other standards always use their
# default mapping.
SUPPORTED_MAPPINGS: list[str] = [
    "defaultmapping",
    "row_interleaving",
    "cacheline_interleaving",
    "row_interleaving_randomized",
    "cacheline_interleaving_randomized",
]


def _standard_key(standard: str) -> str:
    """Map standard name to lookup key (SALP variants share one table)."""
    if standard.startswith("SALP"):
        return "SALP"
    return standard


# Per-standard channel width in bits, used for capacity estimation.
_CHANNEL_WIDTHS: dict[str, int] = {
    "DDR3": 64, "DDR4": 64,
    "LPDDR3": 32, "LPDDR4": 16,
    "GDDR5": 32, "WideIO": 128,
    "WideIO2": 128, "HBM": 128,
    "SALP": 64,
}

# Minimum cacheline (bytes) per standard: prefetch size x channel width / 8.
# Ramulator asserts that the cacheline is a multiple of this unit.
MIN_CACHELINE: dict[str, int] = {
    "DDR3": 64, "DDR4": 64,
    "LPDDR3": 32, "LPDDR4": 32,
    "GDDR5": 32, "WideIO": 64,
    "WideIO2": 64, "HBM": 64,
    "SALP": 64,
}

# Data rate in MT/s (mega-transfers per second) per speed grade prefix.
# Used for theoretical bandwidth estimation.
_DATA_RATES: dict[str, int] = {
    "DDR3_800": 800, "DDR3_1066": 1066, "DDR3_1333": 1333,
    "DDR3_1600": 1600, "DDR3_1866": 1866, "DDR3_2133": 2133,
    "DDR4_1600": 1600, "DDR4_1866": 1866, "DDR4_2133": 2133,
    "DDR4_2400": 2400, "DDR4_3200": 3200,
    "LPDDR3_1333": 1333, "LPDDR3_1600": 1600,
    "LPDDR3_1866": 1866, "LPDDR3_2133": 2133,
    "LPDDR4_1600": 1600, "LPDDR4_2400": 2400, "LPDDR4_3200": 3200,
    "GDDR5_4000": 4000, "GDDR5_4500": 4500, "GDDR5_5000": 5000,
    "GDDR5_5500": 5500, "GDDR5_6000": 6000,
    "GDDR5_6500": 6500, "GDDR5_7000": 7000,
    "WideIO_200": 200, "WideIO_266": 266,
    "WideIO2_800": 800, "WideIO2_1066": 1066,
    "HBM_1Gbps": 1000,
    "SALP_800": 800, "SALP_1066": 1066, "SALP_1333": 1333,
    "SALP_1600": 1600, "SALP_1866": 1866, "SALP_2133": 2133,
}

_UNIT_MULTIPLIERS: dict[str, int] = {
    "": 1, "K": 2 ** 10, "M": 2 ** 20, "G": 2 ** 30, "T": 2 ** 40,
}


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


def estimate_capacity(standard: str, org: str,
                      channels: int = 1, ranks: int = 1) -> int:
    """Estimate nominal DRAM capacity in bytes from the org string.

    Computed as density x chips-per-rank x ranks x channels, where
    chips-per-rank follows from the channel width and the chip width given
    by the org (``xN`` suffix); orgs without a width describe the whole
    stack/channel.
    """
    density_bits, chip_width = _parse_org(org)
    channel_width = _CHANNEL_WIDTHS.get(_standard_key(standard), 64)
    if chip_width:
        chips_per_rank = channel_width // chip_width
    else:
        chips_per_rank = 1
    per_rank_bytes = density_bits // 8 * chips_per_rank
    return per_rank_bytes * ranks * channels


def theoretical_bandwidth(config: Mapping[str, object],
                          cacheline: int = 64) -> float:
    """Estimate peak theoretical bandwidth in GB/s for a config.

    Uses data rate x channel width x channels. Does not account for
    protocol overhead, refresh, or timing constraints.
    """
    from . import Config  # late import to avoid a cycle with __init__

    if isinstance(config, dict):
        config = Config(**config)  # type: ignore[arg-type]

    standard = str(config["standard"])
    speed = str(config["speed"])
    channels = int(str(config["channels"]))

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
    """Path to the reference Ramulator config files bundled with this package."""
    return Path(str(_pkg_files("pyramulator").joinpath("data").joinpath("configs")))


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
