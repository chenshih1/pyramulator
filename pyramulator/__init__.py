"""Pyramulator: Python bindings for Ramulator DRAM simulator."""

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)
from pyramulator._core import (
    Config as _Config,
    MemorySystem as _MemorySystem,
    RequestType,
)
from pyramulator.configs import (
    supported_standards,
    supported_speeds,
    supported_orgs,
    _standard_key,
    SPEED_GRADES,
    ORGANIZATIONS,
)

__all__ = [
    "Config", "MemorySystem", "RequestType", "RequestInfo",
    "supported_standards", "supported_speeds", "supported_orgs",
    "theoretical_bandwidth",
]
__version__ = "0.1.0"


class RequestInfo(NamedTuple):
    """Completed request metadata passed to callbacks."""
    addr: int
    type: RequestType
    arrive: int
    depart: int

    @property
    def latency(self):
        """Request latency in DRAM clock cycles."""
        return self.depart - self.arrive


class Config(_Config):
    """DRAM configuration. Accepts a config file path or keyword arguments.

    Examples:
        cfg = Config("ddr4.cfg")
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
        cfg = Config.from_file("ddr4.cfg", channels=2)
    """

    _DEFAULTS = {"channels": "1", "ranks": "1"}

    def __init__(self, config_file=None, **kwargs):
        if config_file is not None:
            super().__init__(config_file)
        else:
            super().__init__()
        for key, value in kwargs.items():
            self.add(key, str(value))
        for key, value in self._DEFAULTS.items():
            if not self.contains(key):
                self.add(key, value)
        logger.debug("Config created: %s", self)

    @classmethod
    def from_file(cls, path, **overrides):
        """Load config from file, optionally overriding specific fields."""
        obj = cls(config_file=path)
        for key, value in overrides.items():
            obj.set(key, str(value))
        if overrides:
            logger.debug("Config overrides from %s: %s", path, overrides)
        return obj

    def validate(self):
        """Check that standard/speed/org are valid. Raises ValueError if not."""
        standard = self["standard"]
        if not standard:
            raise ValueError("missing required field: standard")
        if standard not in supported_standards():
            raise ValueError(
                f"unsupported standard '{standard}', "
                f"choose from: {supported_standards()}")

        key = _standard_key(standard)
        speed = self["speed"]
        if speed and speed not in SPEED_GRADES.get(key, []):
            raise ValueError(
                f"invalid speed '{speed}' for {standard}, "
                f"choose from: {SPEED_GRADES.get(key, [])}")

        org = self["org"]
        if org and org not in ORGANIZATIONS.get(key, []):
            raise ValueError(
                f"invalid org '{org}' for {standard}, "
                f"choose from: {ORGANIZATIONS.get(key, [])}")

        channels = int(self["channels"])
        ranks = int(self["ranks"])
        if channels < 1 or (channels & (channels - 1)) != 0:
            raise ValueError(f"channels must be a power of 2, got {channels}")
        if ranks < 1 or (ranks & (ranks - 1)) != 0:
            raise ValueError(f"ranks must be a power of 2, got {ranks}")

        return True

    def __repr__(self):
        std = self["standard"] or "?"
        speed = self["speed"] or "?"
        org = self["org"] or "?"
        ch = self["channels"]
        return f"Config(standard={std!r}, speed={speed!r}, org={org!r}, channels={ch})"


# Data rate in MT/s (mega-transfers per second) per speed grade prefix.
# Used for theoretical bandwidth estimation.
_DATA_RATES = {
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

# Channel width in bits per standard (from DRAM spec).
_CHANNEL_WIDTHS = {
    "DDR3": 64, "DDR4": 64,
    "LPDDR3": 32, "LPDDR4": 16,
    "GDDR5": 32, "WideIO": 128,
    "WideIO2": 128, "HBM": 128,
    "SALP": 64,
}


def theoretical_bandwidth(config, cacheline=64):
    """Estimate peak theoretical bandwidth in GB/s for a config.

    Uses data rate × channel width × channels. Does not account for
    protocol overhead, refresh, or timing constraints.
    """
    if isinstance(config, dict):
        config = Config(**config)

    standard = config["standard"]
    speed = config["speed"]
    channels = int(config["channels"])

    key = _standard_key(standard)
    width_bits = _CHANNEL_WIDTHS.get(key, 64)

    # Strip trailing letter suffixes from speed grade: "DDR4_2400R" → "DDR4_2400"
    parts = speed.split("_")
    prefix = parts[0] + "_" + parts[1].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    data_rate = _DATA_RATES.get(prefix, 0)
    if data_rate == 0:
        raise ValueError(f"unknown data rate for speed '{speed}'")

    transfers_per_sec = data_rate * 1e6
    bytes_per_transfer = width_bits // 8
    peak_gbs = transfers_per_sec * bytes_per_transfer * channels / 1e9
    return peak_gbs


class MemorySystem:
    """Cycle-accurate DRAM memory system simulator.

    Examples:
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")

        with MemorySystem(cfg) as mem:
            mem.send_read(0x1000, callback=lambda info: print(info.latency))
            mem.run(1000)
    """

    def __init__(self, config, cacheline=64, num_cores=1):
        if isinstance(config, dict):
            config = Config(**config)
        self._impl = _MemorySystem(config, cacheline, num_cores)
        self._clk = 0
        logger.debug("MemorySystem created: tck=%.3fns, cacheline=%d, cores=%d",
                     self.tck, cacheline, num_cores)

    @property
    def tck(self):
        """Clock period in nanoseconds."""
        return self._impl.tck

    @property
    def clk(self):
        """Current cycle count."""
        return self._clk

    @property
    def pending(self):
        """Number of in-flight requests."""
        return self._impl.pending

    def tick(self):
        """Advance simulation by one DRAM clock cycle."""
        self._impl.tick()
        self._clk += 1

    def run(self, cycles):
        """Advance simulation by the given number of cycles."""
        for _ in range(cycles):
            self._impl.tick()
        self._clk += cycles

    def run_until_idle(self, max_cycles=1_000_000):
        """Tick until no requests are pending or max_cycles is reached."""
        for _ in range(max_cycles):
            self._impl.tick()
            self._clk += 1
            if self._impl.pending == 0:
                break
        return self._clk

    def send(self, addr, request_type, core_id=0, callback=None):
        """Send a memory request. Returns True if accepted, False if queue full.

        callback receives a RequestInfo(addr, type, arrive, depart) namedtuple.
        """
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart):
                user_cb(RequestInfo(addr_, RequestType(type_), arrive, depart))

            return self._impl.send(addr, request_type, core_id, _wrap)
        return self._impl.send(addr, request_type, core_id, None)

    def send_read(self, addr, core_id=0, callback=None):
        """Send a READ request."""
        return self.send(addr, RequestType.READ, core_id, callback)

    def send_write(self, addr, core_id=0, callback=None):
        """Send a WRITE request."""
        return self.send(addr, RequestType.WRITE, core_id, callback)

    def send_reads(self, addrs, core_id=0, callback=None):
        """Send multiple READ requests. Returns list of accept booleans."""
        return [self.send_read(a, core_id, callback) for a in addrs]

    def send_writes(self, addrs, core_id=0, callback=None):
        """Send multiple WRITE requests. Returns list of accept booleans."""
        return [self.send_write(a, core_id, callback) for a in addrs]

    def set_write_queue_watermark(self, high=0.8, low=0.2):
        """Set write queue watermarks that control read/write scheduling."""
        self._impl.set_high_writeq_watermark(high)
        self._impl.set_low_writeq_watermark(low)

    def finish(self):
        """Finalize simulation and flush statistics."""
        logger.debug("MemorySystem finished: %d cycles simulated", self._clk)
        self._impl.finish()

    def __repr__(self):
        return (f"MemorySystem(tck={self.tck:.3f}ns, clk={self._clk}, "
                f"pending={self.pending})")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.finish()
        return False
