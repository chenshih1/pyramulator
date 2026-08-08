"""Supported DRAM standards, speed grades, and organizations."""

SUPPORTED_STANDARDS = [
    "DDR3", "DDR4", "LPDDR3", "LPDDR4",
    "GDDR5", "WideIO", "WideIO2", "HBM",
    "SALP-1", "SALP-2", "SALP-MASA",
]

SPEED_GRADES = {
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

ORGANIZATIONS = {
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


def _standard_key(standard):
    """Map standard name to lookup key (SALP variants share one table)."""
    if standard.startswith("SALP"):
        return "SALP"
    return standard


def supported_standards():
    """Return list of supported DRAM standard names."""
    return list(SUPPORTED_STANDARDS)


def supported_speeds(standard):
    """Return valid speed grades for a given standard."""
    key = _standard_key(standard)
    return list(SPEED_GRADES.get(key, []))


def supported_orgs(standard):
    """Return valid organization/density options for a given standard."""
    key = _standard_key(standard)
    return list(ORGANIZATIONS.get(key, []))


def show(standard=None):
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
