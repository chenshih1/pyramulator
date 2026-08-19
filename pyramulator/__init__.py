"""Pyramulator: Python bindings for Ramulator DRAM simulator."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any, Callable, ClassVar, Literal, NamedTuple

from pyramulator._core import (
    Config as _Config,
)
from pyramulator._core import (
    MemorySystem as _MemorySystem,
)
from pyramulator._core import (
    RequestType,
)
from pyramulator._core import (
    get_stats as _get_stats,
)
from pyramulator._core import (
    reset_stats as _reset_stats,
)
from pyramulator.benchmark import (
    benchmark_all,
    benchmark_bandwidth,
    benchmark_latency,
)
from pyramulator.configs import (
    MIN_CACHELINE,
    ORGANIZATIONS,
    SPEED_GRADES,
    SUPPORTED_MAPPINGS,
    _standard_key,
    config_dir,
    estimate_capacity,
    supported_orgs,
    supported_speeds,
    supported_standards,
    theoretical_bandwidth,
)
from pyramulator.metrics import (
    avg_read_latency,
    measured_bandwidth,
    row_hit_rate,
    summarize_metrics,
)
from pyramulator.workload import addresses, read_write_mix

logger = logging.getLogger(__name__)

__all__ = [
    "Config",
    "MemorySystem",
    "RequestInfo",
    "RequestType",
    "addresses",
    "avg_read_latency",
    "benchmark_all",
    "benchmark_bandwidth",
    "benchmark_latency",
    "config_dir",
    "estimate_capacity",
    "get_stats",
    "measured_bandwidth",
    "read_write_mix",
    "reset_stats",
    "row_hit_rate",
    "summarize_metrics",
    "supported_orgs",
    "supported_speeds",
    "supported_standards",
    "theoretical_bandwidth",
]
__version__ = "0.2.0"


def get_stats() -> dict[str, object]:
    """Return all Ramulator statistics as a {name: value} dict.

    Statistics are process-global in Ramulator: values reflect the most
    recent MemorySystem instance(s) created."""
    return _get_stats()


def reset_stats() -> None:
    """Reset all Ramulator statistics to zero (e.g. per simulation phase)."""
    _reset_stats()


class RequestInfo(NamedTuple):
    """Completed request metadata passed to callbacks."""

    addr: int
    type: RequestType
    arrive: int
    depart: int
    core_id: int = 0

    @property
    def latency(self) -> int:
        """Request latency in DRAM clock cycles."""
        return self.depart - self.arrive


class Config(_Config):
    """DRAM configuration. Accepts a config file path or keyword arguments.

    Only Ramulator's public API is used (add/contains/set_core_num), matching
    how gem5 drives Ramulator; there is no value-overwrite setter.

    Examples:
        cfg = Config("ddr4.cfg")
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
        cfg = Config.from_file("ddr4.cfg", channels=2)
    """

    _DEFAULTS: ClassVar[dict[str, str]] = {"channels": "1", "ranks": "1"}

    def __init__(
        self, config_file: str | os.PathLike | None = None, **kwargs: Any
    ) -> None:
        if config_file is not None:
            super().__init__(str(config_file))
        else:
            super().__init__()
        for key, value in kwargs.items():
            self.add(key, str(value))
        for key, value in self._DEFAULTS.items():
            if not self.contains(key):
                self.add(key, value)
        logger.debug("Config created: %s", self)

    @classmethod
    def from_file(cls, path: str | os.PathLike, **overrides: Any) -> Config:
        """Load config from a Ramulator .cfg file, optionally overriding fields.

        The file is parsed in Python (simple ``key = value`` format), merged
        with the overrides, and applied to a fresh Config via ``add`` — no
        value overwriting on an existing Config is needed.
        """
        options: dict[str, str] = {}
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                options[key.strip()] = value.strip()
        options.update({k: str(v) for k, v in overrides.items()})
        if overrides:
            logger.debug("Config overrides from %s: %s", path, overrides)
        return cls(**options)

    def validate(self) -> bool:
        """Check that standard/speed/org are valid. Raises ValueError if not."""
        standard = self["standard"]
        if not standard:
            raise ValueError("missing required field: standard")
        if standard not in supported_standards():
            raise ValueError(
                f"unsupported standard '{standard}', "
                f"choose from: {supported_standards()}"
            )

        key = _standard_key(standard)
        speed = self["speed"]
        if speed and speed not in SPEED_GRADES.get(key, []):
            raise ValueError(
                f"invalid speed '{speed}' for {standard}, "
                f"choose from: {SPEED_GRADES.get(key, [])}"
            )

        org = self["org"]
        if org and org not in ORGANIZATIONS.get(key, []):
            raise ValueError(
                f"invalid org '{org}' for {standard}, "
                f"choose from: {ORGANIZATIONS.get(key, [])}"
            )

        mapping = self["mapping"]
        if mapping and mapping not in SUPPORTED_MAPPINGS:
            raise ValueError(
                f"invalid mapping '{mapping}', choose from: {SUPPORTED_MAPPINGS}"
            )

        channels = int(self["channels"])
        ranks = int(self["ranks"])
        if channels < 1 or (channels & (channels - 1)) != 0:
            raise ValueError(f"channels must be a power of 2, got {channels}")
        if ranks < 1 or (ranks & (ranks - 1)) != 0:
            raise ValueError(f"ranks must be a power of 2, got {ranks}")

        return True

    def __repr__(self) -> str:
        std = self["standard"] or "?"
        speed = self["speed"] or "?"
        org = self["org"] or "?"
        ch = self["channels"]
        return f"Config(standard={std!r}, speed={speed!r}, org={org!r}, channels={ch})"


class MemorySystem:
    """Cycle-accurate DRAM memory system simulator.

    Examples:
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")

        with MemorySystem(cfg) as mem:
            mem.send_read(0x1000, callback=lambda info: print(info.latency))
            mem.run(1000)
    """

    def __init__(
        self,
        config: Config | _Config | dict[str, Any],
        cacheline: int = 64,
        num_cores: int = 1,
    ) -> None:
        if isinstance(config, dict):
            config = Config(**config)
        standard = config["standard"]
        min_cacheline = MIN_CACHELINE.get(_standard_key(standard), 8)
        if cacheline <= 0 or (cacheline & (cacheline - 1)) != 0:
            raise ValueError(f"cacheline must be a power of two, got {cacheline}")
        if cacheline < min_cacheline or cacheline % min_cacheline != 0:
            raise ValueError(
                f"cacheline {cacheline} is not a multiple of the {standard} "
                f"minimum channel unit ({min_cacheline} bytes)"
            )
        self._config = config
        self._cacheline = cacheline
        self._impl = _MemorySystem(config, cacheline, num_cores)
        self._clk = 0
        logger.debug(
            "MemorySystem created: tck=%.3fns, cacheline=%d, cores=%d",
            self.tck,
            cacheline,
            num_cores,
        )

    @property
    def tck(self) -> float:
        """Clock period in nanoseconds."""
        return self._impl.tck

    @property
    def clk(self) -> int:
        """Current cycle count."""
        return self._clk

    @property
    def pending(self) -> int:
        """Number of in-flight requests."""
        return self._impl.pending

    @property
    def capacity(self) -> int:
        """Nominal DRAM capacity in bytes (from the org configuration)."""
        return estimate_capacity(
            self._config["standard"],
            self._config["org"],
            channels=int(self._config["channels"]),
            ranks=int(self._config["ranks"]),
        )

    def tick(self) -> None:
        """Advance simulation by one DRAM clock cycle."""
        self._impl.tick()
        self._drain_completed()
        self._clk += 1

    def _drain_completed(self):
        """Flush completion events recorded by C++ into user callbacks.

        Completions are batched in C++ (no GIL round-trip per event); the
        Python callbacks run here, with the GIL already held, once per batch.
        """
        self._dispatch(self._impl.drain_completed())

    def _dispatch(self, events):
        """Invoke user callbacks for a batch of completion events.

        Exception-safe: if a callback raises, the remaining events in the
        batch are still delivered, then the first exception is re-raised.
        """
        first_exc = None
        for addr, type_, arrive, depart, core_id, cb in events:
            try:
                cb(addr, type_, arrive, depart, core_id)
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc
        if first_exc is not None:
            raise first_exc

    def run(self, cycles: int) -> None:
        """Advance simulation by the given number of cycles.

        The tick loop runs inside C++ and completion events are dispatched in
        one batch, so long runs avoid per-cycle Python overhead.
        """
        n, events = self._impl.run(cycles)
        self._clk += n
        self._dispatch(events)

    def run_until_idle(self, max_cycles: int = 1_000_000) -> int:
        """Tick until no requests are pending or max_cycles is reached."""
        n, events = self._impl.run_until_idle(max_cycles)
        self._clk += n
        self._dispatch(events)
        return self._clk

    def flush(self, max_cycles: int = 1_000_000) -> int:
        """Write barrier: run until every accepted request — including
        writes, which Ramulator otherwise completes silently — has been
        serviced by the DRAM. Returns the cycle count."""
        return self.run_until_idle(max_cycles)

    def send(
        self,
        addr: int,
        request_type: RequestType,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> bool:
        """Send a memory request. Returns True if accepted, False if queue full.

        callback receives a RequestInfo(addr, type, arrive, depart, core_id)
        namedtuple. Read completions are delivered by Ramulator itself. Like
        gem5, a write request is considered complete upon acceptance:
        Ramulator has no write-completion callback upstream, so WRITE
        callbacks fire immediately when the request is accepted.
        """
        if request_type == RequestType.WRITE:
            accepted = self._impl.send(addr, request_type, core_id, None)
            if accepted and callback is not None:
                callback(RequestInfo(addr, request_type, self.clk, self.clk, core_id))
            return accepted

        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart, core_id_):
                user_cb(
                    RequestInfo(addr_, RequestType(type_), arrive, depart, core_id_)
                )

            return self._impl.send(addr, request_type, core_id, _wrap)
        return self._impl.send(addr, request_type, core_id, None)

    def send_read(
        self,
        addr: int,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> bool:
        """Send a READ request."""
        return self.send(addr, RequestType.READ, core_id, callback)

    def send_write(
        self,
        addr: int,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> bool:
        """Send a WRITE request."""
        return self.send(addr, RequestType.WRITE, core_id, callback)

    def send_reads(
        self,
        addrs: Iterable[int],
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> list[bool]:
        """Send multiple READ requests in one C++ call. Returns accept flags.

        Completions arrive through callback as individual RequestInfo objects
        once the simulation advances (tick/run)."""
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart, core_id_):
                user_cb(
                    RequestInfo(addr_, RequestType(type_), arrive, depart, core_id_)
                )

            return list(self._impl.send_batch(addrs, RequestType.READ, core_id, _wrap))
        return list(self._impl.send_batch(addrs, RequestType.READ, core_id, None))

    def send_writes(
        self,
        addrs: Iterable[int],
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> list[bool]:
        """Send multiple WRITE requests in one C++ call. Returns accept flags.

        Like gem5, writes complete upon acceptance, so accepted requests fire
        callback immediately."""
        accepted = list(self._impl.send_batch(addrs, RequestType.WRITE, core_id, None))
        if callback is not None:
            for addr, ok in zip(addrs, accepted):
                if ok:
                    callback(
                        RequestInfo(
                            addr, RequestType.WRITE, self.clk, self.clk, core_id
                        )
                    )
        return accepted

    def send_reads_range(
        self,
        start: int,
        count: int,
        stride: int | None = None,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> list[bool]:
        """Send count READ requests at start, start+stride, ... in one call.

        Stride defaults to the memory system's cacheline. Avoids
        materializing the address list in Python; returns accept flags.
        """
        if stride is None:
            stride = self._cacheline
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart, core_id_):
                user_cb(
                    RequestInfo(addr_, RequestType(type_), arrive, depart, core_id_)
                )

            return list(
                self._impl.send_range(
                    start, count, stride, RequestType.READ, core_id, _wrap
                )
            )
        return list(
            self._impl.send_range(start, count, stride, RequestType.READ, core_id, None)
        )

    def send_writes_range(
        self,
        start: int,
        count: int,
        stride: int | None = None,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> list[bool]:
        """Send count WRITE requests at start, start+stride, ... in one call.

        Stride defaults to the memory system's cacheline. Writes complete
        upon acceptance, so accepted requests fire callback immediately."""
        if stride is None:
            stride = self._cacheline
        accepted = list(
            self._impl.send_range(
                start, count, stride, RequestType.WRITE, core_id, None
            )
        )
        if callback is not None:
            for i, ok in enumerate(accepted):
                if ok:
                    callback(
                        RequestInfo(
                            start + i * stride,
                            RequestType.WRITE,
                            self.clk,
                            self.clk,
                            core_id,
                        )
                    )
        return accepted

    def drive(
        self,
        addrs: Iterable[int],
        queue_depth: int = 32,
        batch: int = 100,
        max_cycles: int = 1_000_000,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> int:
        """Run the full drive loop inside C++ for a list of addresses.

        Requests are issued until `queue_depth` are in flight, then the DRAM
        advances `batch` cycles at a time, until every request completes or
        max_cycles is reached (the role gem5's MemCtrl scheduler plays).
        Completions are dispatched through callback in one batch. Returns
        the number of issued requests."""
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart, core_id_):
                user_cb(
                    RequestInfo(addr_, RequestType(type_), arrive, depart, core_id_)
                )

            n, issued, events = self._impl.drive(
                addrs, queue_depth, batch, max_cycles, _wrap
            )
        else:
            n, issued, events = self._impl.drive(
                addrs, queue_depth, batch, max_cycles, None
            )
        self._clk += n
        self._dispatch(events)
        return issued

    def drive_range(
        self,
        start: int,
        count: int,
        stride: int | None = None,
        queue_depth: int = 32,
        batch: int = 100,
        max_cycles: int = 1_000_000,
        callback: Callable[[RequestInfo], None] | None = None,
    ) -> int:
        """Drive loop over a contiguous address range (start, +stride, ...).

        Stride defaults to the memory system's cacheline. Returns the number
        of issued requests."""
        if stride is None:
            stride = self._cacheline
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive, depart, core_id_):
                user_cb(
                    RequestInfo(addr_, RequestType(type_), arrive, depart, core_id_)
                )

            n, issued, events = self._impl.drive_range(
                start, count, stride, queue_depth, batch, max_cycles, _wrap
            )
        else:
            n, issued, events = self._impl.drive_range(
                start, count, stride, queue_depth, batch, max_cycles, None
            )
        self._clk += n
        self._dispatch(events)
        return issued

    def get_stats(self) -> dict[str, object]:
        """Return this memory system's statistics as a {name: value} dict.

        Includes bandwidth, read/write latency, row hits/misses, queue
        depths, etc."""
        return self._impl.get_stats()

    def reset_stats(self) -> None:
        """Reset this memory system's statistics to zero (e.g. per phase)."""
        self._impl.reset_stats()

    def metrics(self) -> dict[str, float]:
        """Derived performance summary computed from live statistics.

        Returns avg read latency (cycles and ns), row-buffer hit rate,
        sustained bandwidth, and request/cycle counts — usable mid-run
        without calling finish()."""
        return summarize_metrics(self.get_stats(), self._cacheline, self.tck)

    def send_blocking(
        self,
        addr: int,
        request_type: RequestType,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
        max_wait: int = 1_000_000,
    ) -> int:
        """Send a request, ticking until it is accepted.

        Returns the number of cycles waited. Raises RuntimeError if the
        request is not accepted within max_wait cycles."""
        waited = 0
        while not self.send(addr, request_type, core_id, callback):
            self.tick()
            waited += 1
            if waited >= max_wait:
                raise RuntimeError(
                    f"request to 0x{addr:x} not accepted within "
                    f"{max_wait} cycles (queue still full)"
                )
        return waited

    def send_read_blocking(
        self,
        addr: int,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
        max_wait: int = 1_000_000,
    ) -> int:
        """Blocking variant of send_read. Returns cycles waited."""
        return self.send_blocking(addr, RequestType.READ, core_id, callback, max_wait)

    def send_write_blocking(
        self,
        addr: int,
        core_id: int = 0,
        callback: Callable[[RequestInfo], None] | None = None,
        max_wait: int = 1_000_000,
    ) -> int:
        """Blocking variant of send_write. Returns cycles waited."""
        return self.send_blocking(addr, RequestType.WRITE, core_id, callback, max_wait)

    def set_write_queue_watermark(self, high: float = 0.8, low: float = 0.2) -> None:
        """Set write queue watermarks that control read/write scheduling."""
        self._impl.set_high_writeq_watermark(high)
        self._impl.set_low_writeq_watermark(low)

    def finish(self) -> None:
        """Finalize simulation and flush statistics."""
        logger.debug("MemorySystem finished: %d cycles simulated", self._clk)
        self._impl.finish()

    def __repr__(self) -> str:
        return (
            f"MemorySystem(tck={self.tck:.3f}ns, clk={self._clk}, "
            f"pending={self.pending})"
        )

    def __enter__(self) -> MemorySystem:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        self.finish()
        return False
