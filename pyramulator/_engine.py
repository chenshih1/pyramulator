"""Internal Ramulator engine: the cycle-accurate DRAM timing core.

This module wraps Ramulator's public C++ API (the same calls gem5's
Gem5Wrapper makes; no Ramulator source is modified). It is the engine
behind :class:`pyramulator.dram.Dram` and is not part of the public
DES API -- use :class:`pyramulator.dram.Dram` for memory simulation.

The engine is time-stepped (one ``tick()`` per DRAM clock cycle); the
DES layer in :mod:`pyramulator.dram` embeds it behind events.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, NamedTuple, TypeAlias

from pyramulator._core import (
    Config as _Config,
)
from pyramulator._core import (
    MemorySystem as _MemorySystem,
)
from pyramulator._core import (
    RequestType,
)
from pyramulator.configs import (
    ORGANIZATIONS,
    SPEED_GRADES,
    _standard_key,
    estimate_capacity,
    supported_standards,
)
from pyramulator.configs_data import MIN_CACHELINE, SUPPORTED_MAPPINGS
from pyramulator.metrics import summarize_metrics

logger = logging.getLogger(__name__)


class RequestInfo(NamedTuple):
    """Completed request metadata passed to callbacks."""

    addr: int
    type: RequestType
    arrive_cycle: int
    depart_cycle: int
    core_id: int = 0

    @property
    def latency(self) -> int:
        """Request latency in DRAM clock cycles."""
        return self.depart_cycle - self.arrive_cycle


CompletionCallback: TypeAlias = Callable[[RequestInfo], None] | None
"""User-provided callback that receives a :class:`RequestInfo`."""


class Config(_Config):
    """DRAM configuration. Accepts a config file path or keyword arguments.

    Only Ramulator's public API is used (add/contains/set_core_num); there
    is no value-overwrite setter.

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

    def validate(self) -> None:
        """Check that standard/speed/org/mapping are valid; raises ValueError."""
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
        if channels < 1 or channels.bit_count() != 1:
            raise ValueError(f"channels must be a power of 2, got {channels}")
        if ranks < 1 or ranks.bit_count() != 1:
            raise ValueError(f"ranks must be a power of 2, got {ranks}")

    def __repr__(self) -> str:
        std = self["standard"] or "?"
        speed = self["speed"] or "?"
        org = self["org"] or "?"
        ch = self["channels"]
        return f"Config(standard={std!r}, speed={speed!r}, org={org!r}, channels={ch})"

    # -- Attribute access --------------------------------------------------
    #
    # The underlying C++ Config is dict-like; these properties expose the
    # common fields as attributes (cfg.standard instead of cfg["standard"]).

    def _get(self, key: str) -> str:
        return self[key] if self.contains(key) else ""

    @property
    def standard(self) -> str:
        """DRAM standard (e.g. ``"DDR4"``)."""
        return self._get("standard")

    @property
    def speed(self) -> str:
        """Speed grade (e.g. ``"DDR4_2400R"``)."""
        return self._get("speed")

    @property
    def org(self) -> str:
        """Organization/density (e.g. ``"DDR4_4Gb_x8"``)."""
        return self._get("org")

    @property
    def mapping(self) -> str:
        """Address mapping scheme."""
        return self._get("mapping")

    @property
    def channels(self) -> int:
        """Number of channels."""
        return int(self["channels"])

    @property
    def ranks(self) -> int:
        """Number of ranks per channel."""
        return int(self["ranks"])


class MemorySystem:
    """Cycle-accurate DRAM memory system (internal engine).

    Time-stepped wrapper around Ramulator: ``tick()`` advances one DRAM
    clock cycle. This is the engine behind the DES :class:`Dram`
    component; prefer :class:`pyramulator.dram.Dram` for simulation.

    Examples:
        mem = MemorySystem(Config(standard="DDR4", speed="DDR4_2400R",
                                  org="DDR4_4Gb_x8"))
        mem.send_read(0x1000, callback=lambda info: print(info.latency))
        mem.run_until_idle()
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
        self._num_cores = num_cores
        self._impl = _MemorySystem(config, cacheline, num_cores)
        self._clk = 0
        logger.debug(
            "MemorySystem created: tck=%.3fns, cacheline=%d, cores=%d",
            self.tck,
            cacheline,
            num_cores,
        )

    def _check_core_id(self, core_id: int) -> None:
        """Validate core_id against num_cores before it reaches C++.

        Ramulator indexes per-core statistic arrays with coreid; an
        out-of-range id silently corrupts the heap, so fail fast here."""
        if not 0 <= core_id < self._num_cores:
            raise ValueError(
                f"core_id {core_id} out of range for {self._num_cores} cores"
            )

    def _fire_write_completion(
        self,
        addr: int,
        core_id: int,
        callback: CompletionCallback,
    ) -> None:
        """Deliver the acceptance-time completion of an accepted WRITE.

        Ramulator has no write-completion callback upstream (writes never
        enter its ``pending`` list), so writes complete upon acceptance;
        the completion is recorded at the current cycle."""
        if callback is not None:
            callback(RequestInfo(addr, RequestType.WRITE, self.clk, self.clk, core_id))

    def _read_cb(self, callback: CompletionCallback):
        """Callback to attach to a READ request for the C++ layer.

        A user callback is wrapped so it receives a :class:`RequestInfo`
        (the C++ layer calls back with raw ``(addr, type, arrive_cycle,
        depart_cycle, core_id)``)."""
        if callback is not None:
            user_cb = callback

            def _wrap(addr_, type_, arrive_cycle, depart_cycle, core_id_):
                user_cb(
                    RequestInfo(
                        addr_, RequestType(type_), arrive_cycle, depart_cycle, core_id_
                    )
                )

            return _wrap
        return None

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

    def tick(self) -> int:
        """Advance simulation by one DRAM clock cycle; returns 1."""
        self._impl.tick()
        self._drain_completed()
        self._clk += 1
        return 1

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
        for addr, type_, arrive_cycle, depart_cycle, core_id, cb in events:
            try:
                cb(addr, type_, arrive_cycle, depart_cycle, core_id)
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc
        if first_exc is not None:
            raise first_exc

    def run(self, cycles: int) -> int:
        """Advance simulation by up to *cycles*; returns cycles advanced.

        The tick loop runs inside C++ and completion events are dispatched in
        one batch, so long runs avoid per-cycle Python overhead.
        """
        n, events = self._impl.run(cycles)
        self._clk += n
        self._dispatch(events)
        return n

    def run_until_idle(self, max_cycles: int = 1_000_000) -> int:
        """Tick until no requests are pending or max_cycles is reached.

        Returns the number of cycles advanced.
        """
        n, events = self._impl.run_until_idle(max_cycles)
        self._clk += n
        self._dispatch(events)
        return n

    def flush(self, max_cycles: int = 1_000_000) -> int:
        """Write barrier: run until every accepted request — including
        writes, which Ramulator otherwise completes silently — has been
        serviced by the DRAM. Returns the cycles advanced."""
        return self.run_until_idle(max_cycles)

    def send(
        self,
        addr: int,
        request_type: RequestType,
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> bool:
        """Send a memory request. Returns True if accepted, False if queue full.

        callback receives a RequestInfo(addr, type, arrive_cycle, depart_cycle,
        core_id) namedtuple. Read completions are delivered by Ramulator itself.
        Ramulator has no write-completion callback upstream (writes never
        enter its ``pending`` list), so WRITE callbacks fire immediately
        when the request is accepted; use ``flush()`` to wait until writes
        are truly serviced by the DRAM. Raises ValueError if core_id is
        out of range (Ramulator indexes per-core stats with coreid).
        """
        self._check_core_id(core_id)
        if request_type == RequestType.WRITE:
            accepted = self._impl.send(addr, request_type, core_id, None)
            if accepted:
                self._fire_write_completion(addr, core_id, callback)
            return accepted

        return self._impl.send(addr, request_type, core_id, self._read_cb(callback))

    def send_read(
        self,
        addr: int,
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> bool:
        """Send a READ request."""
        return self.send(addr, RequestType.READ, core_id, callback)

    def send_write(
        self,
        addr: int,
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> bool:
        """Send a WRITE request."""
        return self.send(addr, RequestType.WRITE, core_id, callback)

    def _send_batch(
        self,
        addrs: Iterable[int],
        request_type: RequestType,
        core_id: int,
        callback: CompletionCallback,
    ) -> list[bool]:
        """Send a burst in one C++ call; returns accept flags.

        WRITE completions fire immediately upon acceptance (no upstream
        write callback); READ completions arrive through *callback*."""
        addrs = list(addrs)
        self._check_core_id(core_id)
        if request_type == RequestType.WRITE:
            accepted = list(
                self._impl.send_batch(addrs, RequestType.WRITE, core_id, None)
            )
            for addr, ok in zip(addrs, accepted, strict=False):
                if ok:
                    self._fire_write_completion(addr, core_id, callback)
            return accepted
        return list(
            self._impl.send_batch(
                addrs, RequestType.READ, core_id, self._read_cb(callback)
            )
        )

    def send_reads(
        self,
        addrs: Iterable[int],
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> list[bool]:
        """Send multiple READ requests in one C++ call. Returns accept flags.

        Completions arrive through callback as individual RequestInfo objects
        once the simulation advances (tick/run)."""
        return self._send_batch(addrs, RequestType.READ, core_id, callback)

    def send_writes(
        self,
        addrs: Iterable[int],
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> list[bool]:
        """Send multiple WRITE requests in one C++ call. Returns accept flags.

        Writes complete upon acceptance (no upstream write callback), so
        accepted requests fire callback immediately."""
        return self._send_batch(addrs, RequestType.WRITE, core_id, callback)

    def _send_range(
        self,
        start: int,
        count: int,
        stride: int | None,
        request_type: RequestType,
        core_id: int,
        callback: CompletionCallback,
    ) -> list[bool]:
        """Send count requests at start, start+stride, ... in one call.

        WRITE completions fire immediately upon acceptance; READ
        completions arrive through *callback*."""
        if stride is None:
            stride = self._cacheline
        self._check_core_id(core_id)
        if request_type == RequestType.WRITE:
            accepted = list(
                self._impl.send_range(
                    start, count, stride, RequestType.WRITE, core_id, None
                )
            )
            for i, ok in enumerate(accepted):
                if ok:
                    self._fire_write_completion(start + i * stride, core_id, callback)
            return accepted
        return list(
            self._impl.send_range(
                start, count, stride, RequestType.READ, core_id, self._read_cb(callback)
            )
        )

    def send_reads_range(
        self,
        start: int,
        count: int,
        stride: int | None = None,
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> list[bool]:
        """Send count READ requests at start, start+stride, ... in one call.

        Stride defaults to the memory system's cacheline. Avoids
        materializing the address list in Python; returns accept flags.
        """
        return self._send_range(
            start, count, stride, RequestType.READ, core_id, callback
        )

    def send_writes_range(
        self,
        start: int,
        count: int,
        stride: int | None = None,
        core_id: int = 0,
        callback: CompletionCallback = None,
    ) -> list[bool]:
        """Send count WRITE requests at start, start+stride, ... in one call.

        Stride defaults to the memory system's cacheline. Writes complete
        upon acceptance, so accepted requests fire callback immediately."""
        return self._send_range(
            start, count, stride, RequestType.WRITE, core_id, callback
        )

    def drive(
        self,
        addrs: Iterable[int],
        queue_depth: int = 32,
        batch: int = 100,
        max_cycles: int = 1_000_000,
        callback: CompletionCallback = None,
    ) -> int:
        """Run the full drive loop inside C++ for a list of addresses.

        Requests are issued until `queue_depth` are in flight, then the DRAM
        advances `batch` cycles at a time, until every request completes or
        max_cycles is reached (the role gem5's MemCtrl scheduler plays).
        Completions are dispatched through callback in one batch. Returns
        the number of issued requests."""
        n, issued, events = self._impl.drive(
            list(addrs), queue_depth, batch, max_cycles, self._read_cb(callback)
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
        callback: CompletionCallback = None,
    ) -> int:
        """Drive loop over a contiguous address range (start, +stride, ...).

        Stride defaults to the memory system's cacheline. Returns the number
        of issued requests."""
        if stride is None:
            stride = self._cacheline
        n, issued, events = self._impl.drive_range(
            start,
            count,
            stride,
            queue_depth,
            batch,
            max_cycles,
            self._read_cb(callback),
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

    def set_write_queue_watermark(self, high: float = 0.8, low: float = 0.2) -> None:
        """Set write queue watermarks that control read/write scheduling."""
        self._impl.set_high_writeq_watermark(high)
        self._impl.set_low_writeq_watermark(low)

    def __repr__(self) -> str:
        return (
            f"MemorySystem(tck={self.tck:.3f}ns, clk={self._clk}, "
            f"pending={self.pending})"
        )
